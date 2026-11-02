"""Export the search index as static files, so the public site can search in the browser.

Writes into <out>/engine/:
  index.json       sizes, map geometry and search settings
  meta.bin.gz      int32 [N,4] windows (x, y, w, level), gzip
  emb.bin          int8 [N,D] learned embeddings, then float32 [N] row scales
  mosaic.bin.gz    elevation of every 256 px map tile that a window touches, gzip:
                   uint8 per tile (lo + v * scale metres), stored as MED-predictor residuals
  matcher.onnx     the learned encoder (batch of 4 rotations in, 4 embeddings out)

Quantising heights to 8 bits per tile and embeddings to 8 bits per row did not change a single
top-1 result in a 60-query held-out test (see browser_check.py).
"""
import gzip
import json
import os

import numpy as np

TILE = 256


def _med_residual(q):
    """PNG/LOCO-I style median edge predictor; residuals compress far better than raw heights."""
    q = q.astype(np.int16)
    a = np.zeros_like(q); b = np.zeros_like(q); c = np.zeros_like(q)
    a[:, 1:] = q[:, :-1]; b[1:, :] = q[:-1, :]; c[1:, 1:] = q[:-1, :-1]
    hi, lo = np.maximum(a, b), np.minimum(a, b)
    p = np.where(c >= hi, lo, np.where(c <= lo, hi, a + b - c))
    return ((q - p) & 255).astype(np.uint8)


def quantise_tile(t):
    t = np.asarray(t, np.float32)
    lo, hi = float(t.min()), float(t.max())
    scale = (hi - lo) / 255.0 or 1.0
    return np.round((t - lo) / scale).astype(np.uint8), lo, scale


def needed_tiles(meta, T=TILE):
    need = set()
    for x, y, w, _ in meta:
        for ty in range(y // T, (y + w - 1) // T + 1):
            for tx in range(x // T, (x + w - 1) // T + 1):
                need.add((int(ty), int(tx)))
    return sorted(need)


def export_onnx(encoder, path):
    import torch
    enc = encoder.to("cpu").eval()
    x = torch.randn(4, 1, 64, 64)
    torch.onnx.export(enc, (x,), path, input_names=["z"], output_names=["e"], opset_version=17, dynamo=False)


def export_pack(index, out_dir, log=print):
    from .terrain import PATCH, BLUR_SIGMA
    if index.emb is None:
        raise SystemExit("The browser version needs the learned matcher. Run embed_index.py first.")
    eng = os.path.join(out_dir, "engine")
    os.makedirs(eng, exist_ok=True)
    meta = np.ascontiguousarray(index.meta, np.int32)
    M = index.mosaic
    H, W = M.shape

    # elevation tiles
    tiles = needed_tiles(meta)
    tab, chunks = [], []
    for ty, tx in tiles:
        t = M[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE]
        if t.shape != (TILE, TILE):  # bottom/right edge: pad by repeating the last row/column
            t = np.pad(np.asarray(t), ((0, TILE - t.shape[0]), (0, TILE - t.shape[1])), mode="edge")
        q, lo, scale = quantise_tile(t)
        tab.append([ty, tx, round(lo, 3), round(scale, 6)])
        chunks.append(_med_residual(q).tobytes())
    with gzip.open(os.path.join(eng, "mosaic.bin.gz"), "wb", compresslevel=9) as f:
        f.write(b"".join(chunks))

    # embeddings, 8 bit per row
    emb = np.asarray(index.emb, np.float32)
    sc = np.abs(emb).max(1) / 127.0
    sc[sc == 0] = 1.0
    q = np.round(emb / sc[:, None]).astype(np.int8)
    with open(os.path.join(eng, "emb.bin"), "wb") as f:
        f.write(q.tobytes()); f.write(sc.astype(np.float32).tobytes())
    with gzip.open(os.path.join(eng, "meta.bin.gz"), "wb", compresslevel=9) as f:
        f.write(meta.tobytes())

    export_onnx(index.encoder, os.path.join(eng, "matcher.onnx"))

    info = dict(version=1, count=int(len(meta)), dim=int(emb.shape[1]), zoom=index.h["zoom"],
                px0=index.h["px0"], py0=index.h["py0"], H=int(H), W=int(W), tile=TILE, tiles=tab,
                levels=sorted(index.levels), patch=PATCH, blur=BLUR_SIGMA,
                bytes=sum(os.path.getsize(os.path.join(eng, n)) for n in ("meta.bin.gz", "emb.bin", "mosaic.bin.gz", "matcher.onnx")),
                shortlist=2500, weights=dict(emb=0.45, desc=0.1, ncc=0.45), rot_step=6)
    with open(os.path.join(eng, "index.json"), "w") as f:
        json.dump(info, f, separators=(",", ":"))
    sizes = {n: os.path.getsize(os.path.join(eng, n)) / 1e6 for n in os.listdir(eng)}
    log("[pack] " + ", ".join(f"{n} {s:.1f} MB" for n, s in sorted(sizes.items())))
    return info


def export_web(out_dir):
    """Copy the browser engine and the results-page template (filled with the shared look) to <out>/engine/."""
    import shutil
    from . import report as R
    from .style import FONTS, BASE_CSS, MARK_SVG, IMPORTMAP, REVEAL_JS
    eng = os.path.join(out_dir, "engine")
    os.makedirs(eng, exist_ok=True)
    here = os.path.join(os.path.dirname(__file__), "web")
    for name in ("engine.js", "report.js"):
        shutil.copy(os.path.join(here, name), eng)
    tpl = (R.TEMPLATE.replace("%%FONTS%%", FONTS).replace("%%CSS%%", BASE_CSS).replace("%%MARK%%", MARK_SVG)
           .replace("%%IMPORTMAP%%", IMPORTMAP).replace("%%REVEAL%%", REVEAL_JS)
           .replace("%%S2%%", R.S2_URL).replace("%%ESRI%%", R.ESRI_URL).replace("%%TOPO%%", R.TOPO_URL)
           .replace("%%S2ATTR%%", json.dumps(R.S2_ATTR)[1:-1]))
    with open(os.path.join(eng, "report.json"), "w") as f:
        json.dump(dict(template=tpl, three=R.THREE_SECTION, map=R.MAP_SECTION, s2=R.S2_URL, esri=R.ESRI_URL), f)
