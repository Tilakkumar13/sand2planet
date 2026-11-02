"""Build and query the terrain index.

Windows are sized and spaced in ground kilometres, not map pixels. Web Mercator
stretches high latitudes (at 70 deg one km covers ~3x the pixels it does at the
equator), so pixel-based windows over-sample Greenland and Siberia and make them
win searches too often. Here a window at latitude phi is PATCH*f/cos(phi) pixels
wide and the stride grows the same way, giving the same ground density everywhere.

Index files (prefix = e.g. data/world_z7):
  <prefix>.json       header (zoom, mosaic path, levels, stride, ...)
  <prefix>_meta.npy   int32 rows [x, y, w, f]: window top-left and size in mosaic px, scale level
  <prefix>_desc.npy   float16 hand-crafted rotation-invariant descriptors
  <prefix>_emb.npy    float16 learned embeddings (optional, from embed_index.py)
"""
import json
import math
import os
import time

import cv2
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from .terrain import PATCH, BLUR_SIGMA, prep, zscore, describe, refine
from .tiles import px_to_lonlat, meters_per_px


def _row_lat(header, y):
    return px_to_lonlat(0, y + header["py0"], header["zoom"])[1]


def iter_windows(header, levels=(1, 2, 4), stride=16, min_land=0.7, min_relief=40.0,
                 lat_aware=True, max_scale=4.0):
    """Yield (meta[N,4], raw[N,P,P], smoothed[N,P,P]) batches, one latitude band at a time."""
    M = np.load(header["mosaic"], mmap_mode="r")
    H, W = M.shape
    synthetic = header.get("synthetic", False)
    for f in levels:
        base = PATCH * f
        y = 0.0
        while True:
            yi = int(round(y))
            s = 1.0
            if lat_aware and not synthetic:
                lat = _row_lat(header, yi + base / 2)
                s = 1.0 / max(math.cos(math.radians(lat)), 1.0 / max_scale)
                lat = _row_lat(header, yi + base * s / 2)
                s = 1.0 / max(math.cos(math.radians(lat)), 1.0 / max_scale)
            w = int(round(base * s))
            if yi + w > H:
                break
            strip = np.asarray(M[yi:yi + w], np.float32)
            ow = int(round(W * PATCH / w))
            small = cv2.resize(strip, (ow, PATCH), interpolation=cv2.INTER_AREA)
            sm = cv2.GaussianBlur(small, (0, 0), BLUR_SIGMA, borderType=cv2.BORDER_REFLECT)
            wr = sliding_window_view(small, (PATCH, PATCH))[0, ::stride]
            ws = sliding_window_view(sm, (PATCH, PATCH))[0, ::stride]
            land = (wr > 0).mean((1, 2))
            relief = wr.std((1, 2))
            keep = np.nonzero((land >= min_land) & (relief >= min_relief))[0]
            if len(keep):
                xs = np.round(keep * stride * w / PATCH).astype(np.int32)
                xs = np.minimum(xs, W - w)
                meta = np.stack([xs, np.full_like(xs, yi), np.full_like(xs, w),
                                 np.full_like(xs, f)], 1).astype(np.int32)
                yield meta, wr[keep], ws[keep]
            y += stride * w / PATCH


def build_index(header, prefix, levels=(1, 2, 4), stride=16, min_land=0.7, min_relief=40.0,
                lat_aware=True, batch=4096):
    descs, metas = [], []
    t0 = time.time()
    count = {f: 0 for f in levels}
    for meta, _, ws in iter_windows(header, levels, stride, min_land, min_relief, lat_aware):
        for s in range(0, len(meta), batch):
            descs.append(describe(zscore(ws[s:s + batch])).astype(np.float16))
        metas.append(meta)
        count[int(meta[0, 3])] += len(meta)
    for f in levels:
        print(f"[index] level x{f}: {count[f]} windows")
    desc = np.concatenate(descs)
    meta = np.concatenate(metas)
    np.save(prefix + "_desc.npy", desc)
    np.save(prefix + "_meta.npy", meta)
    for stale in ("_emb.npy", "_emb.json"):  # embeddings no longer line up with the new windows
        if os.path.exists(prefix + stale):
            os.remove(prefix + stale)
    hdr = dict(header, levels=list(levels), stride=stride, patch=PATCH, count=int(len(desc)),
               lat_aware=lat_aware, min_land=min_land, min_relief=min_relief)
    with open(prefix + ".json", "w") as fh:
        json.dump(hdr, fh, indent=2)
    print(f"[index] total {len(desc):,} windows -> {prefix}_*.npy  ({time.time() - t0:.0f}s)")
    return hdr


class Index:
    def __init__(self, prefix, matcher="auto", model=None):
        self.prefix = prefix
        with open(prefix + ".json") as fh:
            self.h = json.load(fh)
        self.desc = np.load(prefix + "_desc.npy", mmap_mode="r")
        meta = np.load(prefix + "_meta.npy")
        if meta.shape[1] == 3:  # indexes built before v0.4: [x, y, f]
            meta = np.stack([meta[:, 0], meta[:, 1], PATCH * meta[:, 2], meta[:, 2]], 1).astype(np.int32)
        self.meta = meta
        self.mosaic = np.load(self.h["mosaic"], mmap_mode="r")
        self.levels = set(self.h["levels"])
        self.emb = None
        self.encoder = None
        if matcher in ("auto", "learned") and os.path.exists(prefix + "_emb.npy"):
            try:
                from .learned import load_encoder
                info = json.load(open(prefix + "_emb.json"))
                path = model or info["model"]
                self.encoder = load_encoder(path)
                self.emb = np.load(prefix + "_emb.npy", mmap_mode="r")
                print(f"[index] learned matcher: {os.path.basename(path)}")
            except Exception as e:  # torch missing, model moved, ...
                if matcher == "learned":
                    raise
                print(f"[index] learned matcher unavailable ({e}); using hand-crafted descriptor")
        elif matcher == "learned":
            raise SystemExit(f"No learned embeddings for {prefix}. Run embed_index.py first.")
        self.matcher = "learned" if self.emb is not None else "handcrafted"

    # ------------------------------------------------------------ geometry
    def raw_patch(self, x, y, w, pad=0):
        H, W = self.mosaic.shape
        y0, y1 = max(y - pad, 0), min(y + w + pad, H)
        x0, x1 = max(x - pad, 0), min(x + w + pad, W)
        return np.asarray(self.mosaic[y0:y1, x0:x1], np.float32)

    def patch(self, x, y, w, f=None):
        return prep(self.raw_patch(x, y, w))

    def geo(self, cx, cy):
        """Mosaic pixel -> (lon, lat)."""
        return px_to_lonlat(cx + self.h["px0"], cy + self.h["py0"], self.h["zoom"])

    def ground_weight(self):
        """Ground area each window stands for (for bias statistics)."""
        x, y, w = self.meta[:, 0], self.meta[:, 1], self.meta[:, 2]
        lat = np.array([self.geo(0, yy + ww / 2)[1] for yy, ww in zip(y, w)])
        step = self.h.get("stride", 16) * w / PATCH
        return lat, (step * np.cos(np.radians(lat))) ** 2

    # ------------------------------------------------------------ search
    def _scores(self, mat, q):
        N = len(mat)
        out = np.empty(N, np.float32)
        for s in range(0, N, 250_000):
            out[s:s + 250_000] = np.asarray(mat[s:s + 250_000], np.float32) @ q
        return out

    def search(self, height, k=5, shortlist=None, rot_step=6, allow_flip=False, levels=None):
        q = prep(height)
        qz = zscore(q)[0]
        d_sim = self._scores(self.desc, describe(qz)[0])
        if self.emb is not None:
            from .learned import embed
            e_sim = self._scores(self.emb, embed(self.encoder, qz[None], tta=True)[0])
            sl = min(shortlist or 2500, len(e_sim))
            sd = max(1, sl // 4)
            # union of both shortlists keeps the hand-crafted view as a safety net
            pool = np.union1d(np.argpartition(-e_sim, sl - 1)[:sl],
                              np.argpartition(-d_sim, sd - 1)[:sd])
            first = 0.45 * e_sim[pool] + 0.1 * d_sim[pool]
            w_ncc = 0.45
        else:
            sl = shortlist or 4000
            sl = min(sl, len(d_sim))
            pool = np.argpartition(-d_sim, sl - 1)[:sl]
            first = 0.3 * d_sim[pool]
            w_ncc = 0.7
        if levels:
            keep = np.isin(self.meta[pool, 3], list(levels))
            pool, first = pool[keep], first[keep]
        cands = np.stack([self.patch(*self.meta[i, :3]) for i in pool])
        ncc, ang, fl = refine(qz, zscore(cands), rot_step, allow_flip)
        score = first + w_ncc * ncc
        order = np.argsort(-score)

        results, kept = [], []
        for j in order:
            x, y, w, f = (int(v) for v in self.meta[pool[j]])
            cx, cy = x + w / 2, y + w / 2
            if any(math.hypot(cx - kx, cy - ky) < 0.6 * max(w, kw) for kx, ky, kw in kept):
                continue
            kept.append((cx, cy, w))
            results.append(self._result(x, y, w, f, float(score[j]), float(ncc[j]),
                                        float(d_sim[pool[j]]), int(ang[j]), bool(fl[j])))
            if len(results) == k:
                break
        return q, results

    def _result(self, x, y, w, f, score, ncc, sim, angle, flipped):
        cx, cy = x + w / 2, y + w / 2
        lon, lat = self.geo(cx, cy)
        km = w * meters_per_px(lat, self.h["zoom"]) / 1000.0
        a = math.radians(angle)
        corners = []
        for dx, dy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:
            ox, oy = dx * w / 2, dy * w / 2
            if flipped:
                ox = -ox
            rx = ox * math.cos(a) + oy * math.sin(a)
            ry = -ox * math.sin(a) + oy * math.cos(a)
            corners.append(self.geo(cx + rx, cy + ry))
        top_bearing = (360 - angle) % 360
        return dict(lon=lon, lat=lat, x=x, y=y, w=w, level=f, size_km=km, score=score,
                    ncc=ncc, desc_sim=sim, rotation_deg=angle, flipped=flipped,
                    top_edge_bearing_deg=top_bearing, matcher=self.matcher,
                    corners_lonlat=[[c[0], c[1]] for c in corners])
