"""Add learned embeddings to an index so searches use the trained matcher.

  python embed_index.py --index data/world_z6 --model models/matcher.pt

After this, run.py / app.py / selftest.py pick up the learned matcher automatically
(use --matcher handcrafted in selftest.py to compare against the old one).
"""
import argparse
import datetime as dt
import json
import os
import time

import numpy as np

from s2e.device import add_device_arg, apply_device_arg
from s2e.index import Index
from s2e.learned import load_encoder, embed
from s2e.terrain import zscore

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--index", required=True)
p.add_argument("--model", default="models/matcher.pt")
p.add_argument("--batch", type=int, default=2048)
add_device_arg(p)
a = p.parse_args()
apply_device_arg(a)

idx = Index(a.index, matcher="handcrafted")
enc = load_encoder(a.model)
N = len(idx.meta)
out = None
t0 = time.time()
for s in range(0, N, a.batch):
    z = zscore(np.stack([idx.patch(*m[:3]) for m in idx.meta[s:s + a.batch]]))
    e = embed(enc, z, tta=True).astype(np.float16)
    if out is None:
        out = np.lib.format.open_memmap(a.index + "_emb.npy", mode="w+", dtype=np.float16, shape=(N, e.shape[1]))
    out[s:s + len(e)] = e
    done = min(s + a.batch, N)
    print(f"[embed] {done:,}/{N:,}  ({time.time() - t0:.0f}s)", end="\r")
out.flush()
with open(a.index + "_emb.json", "w") as fh:
    json.dump(dict(model=os.path.abspath(a.model), count=N, dim=int(out.shape[1]),
                   created=dt.datetime.now().isoformat(timespec="seconds")), fh, indent=2)
print(f"\n[embed] done -> {a.index}_emb.npy")
