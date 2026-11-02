"""Train the learned terrain matcher on your Mac (Apple GPU via MPS).

  python train.py --index data/world_z6                     # Mac GPU (MPS), ~15-30 min
  python train.py --index data/world_z6 --preset cpu        # CPU only, smaller model, ~20-40 min on an M3 Air
  python train.py --index data/world_z6 --preset cpu-quick  # CPU smoke test, ~5 min
  python train.py --index data/world_z6 --preset offgrid    # CPU, robust to sandboxes that don't line up with the index

Then add its embeddings to any index and compare:
  python embed_index.py --index data/world_z6 --model models/matcher.pt
  python evaluate.py --index data/world_z6

Training places come only from the non-held-out 10 deg cells (see s2e/split.py),
so tests on held-out cells are fair.
"""
import argparse
import json
import math
import os
import time

import cv2
import numpy as np
import torch
import torch.nn.functional as F

from s2e.index import Index
from s2e.learned import Encoder, make_pairs, pick_device, save_encoder
from s2e.split import is_heldout

PRESETS = {
    # bigger model, for the Mac GPU or a CUDA card
    "gpu": dict(samples=40000, val=2000, steps=6000, batch=384, width=32, eval_every=500, device="auto"),
    # half-width model and smaller batches: 4-5x less work per step, fits a fanless laptop
    "cpu": dict(samples=20000, val=1000, steps=3000, batch=128, width=16, eval_every=500, device="cpu"),
    "cpu-quick": dict(samples=6000, val=500, steps=600, batch=96, width=16, eval_every=200, device="cpu"),
    # real sandboxes: any position (up to 1/8 window off the grid, trained to 0.15) and any size (up to sqrt 2 off)
    "offgrid": dict(samples=16000, val=1000, steps=4000, batch=128, width=16, eval_every=500, device="cpu",
                    context=144, shift=0.15, scale_min=0.7, scale_max=1.42),
}

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--preset", choices=list(PRESETS), default="gpu",
               help="gpu (default), cpu, or cpu-quick. Any option you pass yourself overrides the preset.")
p.add_argument("--index", required=True, help="index to draw training places from (e.g. data/world_z6)")
p.add_argument("--samples", type=int, default=40000, help="training places held in memory")
p.add_argument("--val", type=int, default=2000, help="held-out places for validation")
p.add_argument("--steps", type=int, default=6000)
p.add_argument("--batch", type=int, default=384)
p.add_argument("--lr", type=float, default=2e-3)
p.add_argument("--width", type=int, default=32)
p.add_argument("--dim", type=int, default=128)
p.add_argument("--crude", type=float, default=0.5, help="share of batches shaped like rough sculptures")
p.add_argument("--context", type=int, default=96, help="context side in px; the window is its centre 64 px")
p.add_argument("--shift", type=float, default=0.03, help="max offset of the sculpture from the window, in windows")
p.add_argument("--scale-min", type=float, default=0.85)
p.add_argument("--scale-max", type=float, default=1.15)
p.add_argument("--eval-every", type=int, default=500)
p.add_argument("--out", default="models/matcher.pt")
p.add_argument("--seed", type=int, default=0)
p.add_argument("--device", choices=["auto", "cpu", "mps", "cuda"], default=None)
pre, _ = p.parse_known_args()
p.set_defaults(**PRESETS[pre.preset])
a = p.parse_args()

torch.manual_seed(a.seed)
rng = np.random.default_rng(a.seed)
if a.device and a.device != "auto":
    os.environ["S2E_DEVICE"] = a.device
dev = pick_device()
CTX = a.context                            # context side; the window is the centre 64 px
AUG = dict(shift=a.shift, scale=(a.scale_min, a.scale_max))
idx = Index(a.index, matcher="handcrafted")
H, W = idx.mosaic.shape


def context(x, y, w):
    c = int(round(w * CTX / 64))
    cx, cy = x + w // 2, y + w // 2
    reg = np.asarray(idx.mosaic[cy - c // 2: cy - c // 2 + c, cx - c // 2: cx - c // 2 + c], np.float32)
    return cv2.resize(reg, (CTX, CTX), interpolation=cv2.INTER_AREA)


x_, y_, w_ = idx.meta[:, 0], idx.meta[:, 1], idx.meta[:, 2]
cx_, cy_ = x_ + w_ // 2, y_ + w_ // 2
half = (w_ * CTX / 64 / 2).astype(int) + 2
ok = (cx_ - half >= 0) & (cy_ - half >= 0) & (cx_ + half < W) & (cy_ + half < H)
held = np.array([is_heldout(*idx.geo(cx, cy)) for cx, cy in zip(cx_, cy_)])
train_ids = np.nonzero(ok & ~held)[0]
val_ids = np.nonzero(ok & held)[0]
if len(val_ids) == 0:
    raise SystemExit("No held-out places in this index; use a larger region (e.g. the world index).")
train_ids = rng.choice(train_ids, min(a.samples, len(train_ids)), replace=False)
val_ids = rng.choice(val_ids, min(a.val, len(val_ids)), replace=False)

print(f"[train] preset {a.preset}: width {a.width}, batch {a.batch}, {a.steps} steps")
print(f"[train] device {dev}; loading {len(train_ids):,} training + {len(val_ids):,} held-out places ...")
t0 = time.time()
bank = np.stack([context(*idx.meta[i, :3]) for i in train_ids]).astype(np.float16)
vbank = np.stack([context(*idx.meta[i, :3]) for i in val_ids]).astype(np.float16)
print(f"[train] loaded in {time.time() - t0:.0f}s ({bank.nbytes / 1e6:.0f} MB)")

model = Encoder(width=a.width, dim=a.dim).to(dev)
logit_scale = torch.nn.Parameter(torch.tensor(math.log(1 / 0.07), device=dev))
opt = torch.optim.AdamW(list(model.parameters()) + [logit_scale], lr=a.lr, weight_decay=1e-4)
warm = min(300, a.steps // 10)
sched = torch.optim.lr_scheduler.LambdaLR(
    opt, lambda s: (s + 1) / warm if s < warm else 0.5 * (1 + math.cos(math.pi * (s - warm) / max(1, a.steps - warm))))
print(f"[train] {sum(p.numel() for p in model.parameters()) / 1e6:.2f} M parameters")


def to_dev(arr):
    return torch.from_numpy(arr.astype(np.float32))[:, None].to(dev)


@torch.no_grad()
def validate():
    model.eval()
    g = torch.Generator(device=dev).manual_seed(123)
    qs, ps = [], []
    for s in range(0, len(vbank), 500):
        q, c = make_pairs(to_dev(vbank[s:s + 500]), crude=1.0, generator=g, **AUG)  # judge on rough, off-grid sculptures
        qs.append(model(q)); ps.append(model(c))
    q, c = torch.cat(qs), torch.cat(ps)
    rank = (q @ c.T).argsort(1, descending=True)
    hit = rank == torch.arange(len(q), device=dev)[:, None]
    model.train()
    return hit[:, :1].any(1).float().mean().item(), hit[:, :10].any(1).float().mean().item()


os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
best, history = -1.0, []
r1, r10 = validate()
print(f"[train] untrained: held-out recall@1 {r1:.1%}  @10 {r10:.1%}  (among {len(vbank):,} places)")
t0 = time.time()
for step in range(1, a.steps + 1):
    ids = rng.integers(0, len(bank), a.batch)
    q, c = make_pairs(to_dev(bank[ids]), crude=a.crude, **AUG)
    eq, ec = model(q), model(c)
    logits = logit_scale.exp().clamp(max=100) * eq @ ec.T
    target = torch.arange(a.batch, device=dev)
    loss = 0.5 * (F.cross_entropy(logits, target) + F.cross_entropy(logits.T, target))
    opt.zero_grad(set_to_none=True)
    loss.backward()
    opt.step()
    sched.step()
    if step % 50 == 0:
        print(f"[train] step {step}/{a.steps}  loss {loss.item():.3f}  "
              f"{(time.time() - t0) / step * 1000:.0f} ms/step", end="\r")
    if step % a.eval_every == 0 or step == a.steps:
        r1, r10 = validate()
        history.append(dict(step=step, loss=float(loss.item()), val_r1=r1, val_r10=r10))
        flag = ""
        if r1 > best:
            best = r1
            save_encoder(model, a.out, dict(step=step, val_r1=r1, val_r10=r10, index=a.index, aug=AUG, preset=a.preset))
            flag = "  saved"
        print(f"\n[train] step {step}: held-out recall@1 {r1:.1%}  @10 {r10:.1%}{flag}")

with open(os.path.splitext(a.out)[0] + "_history.json", "w") as fh:
    json.dump(dict(args=vars(a), history=history, best_val_r1=best), fh, indent=2)
print(f"[train] done in {(time.time() - t0) / 60:.1f} min. Best held-out recall@1 {best:.1%} -> {a.out}")
