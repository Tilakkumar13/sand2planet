"""Measure how well the search recovers known places from distorted "sculptures".

Each query is a real indexed place, randomly rotated, rescaled (+-15 %), bent by a
non-linear height curve (like monocular depth), tilted, blurred and made noisy.
A hit = a returned match centred within half a window of the true spot.

  python selftest.py --index data/world_z6 --crude
  python selftest.py --index data/world_z6 --crude --heldout     # only places the learned model never saw
  python selftest.py --index data/world_z6 --matcher handcrafted # force the hand-crafted descriptor
  python selftest.py --index data/world_z6 --bias 200            # where do random shapes land?
"""
import argparse
import json
import math
import time

import cv2
import numpy as np

from s2e.device import add_device_arg, apply_device_arg
from s2e.index import Index
from s2e.terrain import render, rotate, zscore
from s2e.split import is_heldout

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--index", required=True)
p.add_argument("-n", type=int, default=60)
p.add_argument("--seed", type=int, default=1)
p.add_argument("--crude", action="store_true", help="heavier smoothing, like a rough hand-made sculpture")
p.add_argument("--heldout", action="store_true", help="query only held-out regions (fair test for the learned matcher)")
p.add_argument("--matcher", choices=["auto", "learned", "handcrafted"], default="auto")
p.add_argument("--bias", type=int, default=0, help="also run N random shapes and report the latitude of their best matches")
p.add_argument("--examples", default="selftest_examples.png")
p.add_argument("--json", help="write the numbers to this file")
add_device_arg(p)
a = p.parse_args()
apply_device_arg(a)

idx = Index(a.index, matcher=a.matcher)
rng = np.random.default_rng(a.seed)
H, W = idx.mosaic.shape


def make_query(x, y, w):
    scale = rng.uniform(0.85, 1.15)
    ang = rng.uniform(0, 360)
    span = int(w * scale)
    pad = int(span * 0.8)
    cx, cy = x + w // 2, y + w // 2
    reg = np.asarray(idx.mosaic[cy - pad:cy + pad, cx - pad:cx + pad], np.float32)
    M = cv2.getRotationMatrix2D((float(pad), float(pad)), ang, 1.0)
    rot = cv2.warpAffine(reg, M, (reg.shape[1], reg.shape[0]), borderMode=cv2.BORDER_REFLECT)
    crop = rot[pad - span // 2: pad + span // 2, pad - span // 2: pad + span // 2]
    q = cv2.resize(crop, (128, 128), interpolation=cv2.INTER_AREA)
    q = (q - q.min()) / (q.max() - q.min() + 1e-9)
    q = q ** rng.uniform(0.7, 1.4)                       # non-linear depth response
    yy, xx = np.mgrid[0:128, 0:128] / 128.0
    q += rng.normal(0, 0.08) * (xx - .5) + rng.normal(0, 0.08) * (yy - .5)  # residual tilt
    blur = rng.uniform(3.0, 6.0) if a.crude else rng.uniform(0.5, 2.0)
    q = cv2.GaussianBlur(q.astype(np.float32), (0, 0), blur)
    q += rng.normal(0, 0.04 if a.crude else 0.02, q.shape)  # sensor noise
    return q.astype(np.float32), ang, (cx, cy)


# candidates: away from the mosaic edge (so the rotated crop has real data) and optionally held out
x_, y_, w_ = idx.meta[:, 0], idx.meta[:, 1], idx.meta[:, 2]
m_ = (w_ * 1.15 * 0.8).astype(int) + 2
cx_, cy_ = x_ + w_ // 2, y_ + w_ // 2
ok = (cx_ - m_ >= 0) & (cy_ - m_ >= 0) & (cx_ + m_ < W) & (cy_ + m_ < H)
if a.heldout:
    ll = np.array([idx.geo(cx, cy) for cx, cy in zip(cx_, cy_)])
    ok &= np.array([is_heldout(lon, lat) for lon, lat in ll])
cands = np.nonzero(ok)[0]
if len(cands) < a.n:
    raise SystemExit(f"Only {len(cands)} usable windows; lower -n.")
picks = rng.choice(cands, a.n, replace=False)

hits1 = hits5 = 0
ang_err, times, examples = [], [], []
for qi, i in enumerate(picks):
    x, y, w, f = (int(v) for v in idx.meta[i])
    q, ang, (cx, cy) = make_query(x, y, w)
    t0 = time.time()
    qp, res = idx.search(q, k=5)
    times.append(time.time() - t0)
    found = None
    for rank, r in enumerate(res):
        rx, ry = r["x"] + r["w"] / 2, r["y"] + r["w"] / 2
        if math.hypot(rx - cx, ry - cy) < 0.5 * max(w, r["w"]):
            found = rank
            break
    if found is not None:
        hits5 += 1
        hits1 += found == 0
        if found == 0:
            expected = (360 - ang) % 360
            ang_err.append(abs((res[0]["rotation_deg"] - expected + 180) % 360 - 180))
    if len(examples) < 6:
        r = res[0]
        examples.append(np.hstack([render(q, 180),
                                   render(rotate(zscore(qp)[0], r["rotation_deg"]), 180),
                                   render(idx.patch(r["x"], r["y"], r["w"]), 180)]))
    tag = "top-1" if found == 0 else (f"top-{found + 1}" if found is not None else "miss")
    print(f"query {qi + 1:3d}/{a.n}: level x{f}  {tag}")

out = dict(index=a.index, matcher=idx.matcher, windows=int(len(idx.meta)), n=a.n, crude=a.crude,
           heldout=a.heldout, recall_at_1=hits1 / a.n, recall_at_5=hits5 / a.n,
           rotation_error_deg=float(np.median(ang_err)) if ang_err else None,
           search_ms=float(np.median(times) * 1000))

if a.bias and not idx.h.get("synthetic"):
    # random smooth shapes that are not taken from the index: where on Earth do they land?
    lat_w, wt = idx.ground_weight()
    expected = float(wt[np.abs(lat_w) > 60].sum() / wt.sum())
    polar = 0
    for b in range(a.bias):
        g = np.zeros((128, 128), np.float32)
        yy, xx = np.mgrid[0:128, 0:128]
        for _ in range(rng.integers(2, 7)):
            cx, cy, s = rng.uniform(10, 118, 2).tolist() + [rng.uniform(10, 40)]
            g += rng.choice([-1, 1]) * rng.uniform(.4, 1) * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * s * s))
        _, res = idx.search(g, k=1)
        polar += abs(res[0]["lat"]) > 60
    out.update(bias_queries=a.bias, best_match_share_above_60=polar / a.bias,
               indexed_ground_share_above_60=expected)

print("\n=== results ===")
print(f"matcher           {out['matcher']}")
print(f"index size        {out['windows']:,} windows")
print(f"recall@1          {out['recall_at_1']:.0%}")
print(f"recall@5          {out['recall_at_5']:.0%}")
if ang_err:
    print(f"rotation error    median {out['rotation_error_deg']:.0f} deg (top-1 hits)")
print(f"search time       median {out['search_ms']:.0f} ms")
if "bias_queries" in out:
    print(f"polar bias        {out['best_match_share_above_60']:.0%} of random shapes land above 60 deg "
          f"(that band holds {out['indexed_ground_share_above_60']:.0%} of the indexed land)")
if examples:
    grid = np.vstack(examples)
    cv2.putText(grid, "distorted query | turned to north | best match", (8, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    cv2.imwrite(a.examples, grid)
    print(f"examples          {a.examples}")
if a.json:
    with open(a.json, "w") as fh:
        json.dump(out, fh, indent=2)
