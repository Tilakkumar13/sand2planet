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

from .terrain import PATCH, BLUR_SIGMA, prep, zscore, describe, refine, rotate
from .tiles import px_to_lonlat, meters_per_px


def _local(path, prefix, sub=""):
    """Paths in index headers are absolute on the machine that built them. If the file is not
    there (index copied to another computer or a server), look next to the index instead."""
    if os.path.exists(path):
        return path
    here = os.path.join(os.path.dirname(os.path.abspath(prefix)), sub, os.path.basename(path))
    return here if os.path.exists(here) else path


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
            # on Earth, skip windows that are mostly sea; other planets have no sea level
            land = (wr > 0).mean((1, 2)) if header.get("body", "earth") == "earth" else np.ones(len(wr))
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
        self.mosaic = np.load(_local(self.h["mosaic"], prefix), mmap_mode="r")
        self.levels = set(self.h["levels"])
        self.emb = None
        self.encoder = None
        if matcher in ("auto", "learned") and os.path.exists(prefix + "_emb.npy"):
            try:
                from .learned import load_encoder
                info = json.load(open(prefix + "_emb.json"))
                path = model or _local(info["model"], prefix, os.path.join("..", "models"))
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
    @property
    def body(self):
        return self.h.get("body", "earth")

    def mpp(self, lat):
        """metres per mosaic pixel at this latitude, on this planet"""
        from .tiles import EARTH_CIRC
        return meters_per_px(lat, self.h["zoom"], self.h.get("circumference", EARTH_CIRC))

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

    # The index is a grid: windows every 1/4 window, in sizes that double. A real sandbox sits anywhere and
    # covers any area, so the best candidates are re-fitted: slid by up to 1/4 window, resized by up to sqrt(2)
    # either way and turned a little, keeping whatever fits the sculpture best.
    def _refit_boxes(self, cx, cy, w, shifts, scales):
        H, W = self.mosaic.shape
        out = []
        for sc in scales:
            ws = int(round(w * sc))
            for dy in shifts:
                for dx in shifts:
                    nx, ny = int(round(cx + dx * w - ws / 2)), int(round(cy + dy * w - ws / 2))
                    if 0 <= nx and 0 <= ny and nx + ws <= W and ny + ws <= H:
                        out.append((nx, ny, ws, dx, dy, sc))
        return out

    def _refine(self, qz, x, y, w, angle, flipped, rot_step):
        """Coarse to fine: 27 windows (shift 0 or 1/4 window either way, size x0.71/1/1.41), then 27 around the best
        (1/8 window, x0.84/1.19 steps), then the angle +-2 steps."""
        from .terrain import _masked_unit
        cx, cy = x + w / 2, y + w / 2
        q0 = _masked_unit(rotate(qz, angle, flipped)[None])[0]
        best = (-1.0, None, None, None)                      # ncc, box, unit vector, (dx, dy, sc)
        stages = [((-0.25, 0.0, 0.25), (0.71, 1.0, 1.41))]
        for st in range(2):
            if st == 1:
                if best[3] is None:
                    break
                bdx, bdy, bsc = best[3]
                stages = [(None, None)]
            boxes = (self._refit_boxes(cx, cy, w, *stages[0]) if st == 0 else
                     [b for b in self._refit_boxes(cx + bdx * w, cy + bdy * w, w, (-0.125, 0.0, 0.125),
                                                   (bsc / 1.19, bsc, bsc * 1.19))])
            if not boxes:
                break
            C = _masked_unit(zscore(np.stack([self.patch(nx, ny, ws) for nx, ny, ws, *_ in boxes])))
            s0 = C @ q0
            b = int(np.argmax(s0))
            if s0[b] > best[0]:
                nx, ny, ws, dx, dy, sc = boxes[b]
                if st == 1:   # shifts in stage 2 are relative to the stage-1 centre
                    dx, dy, sc = bdx + dx, bdy + dy, sc
                best = (float(s0[b]), (nx, ny, ws), C[b], (dx, dy, sc))
        if best[1] is None:
            return (-1.0, angle, (x, y, w))
        res = (best[0], angle, best[1])
        for da in (-2 * rot_step, -rot_step, rot_step, 2 * rot_step):
            a = (angle + da) % 360
            v = float(best[2] @ _masked_unit(rotate(qz, a, flipped)[None])[0])
            if v > res[0]:
                res = (v, a, best[1])
        return res

    def search(self, height, k=5, shortlist=None, rot_step=6, allow_flip=False, levels=None, refit=60):
        q = prep(height)
        qz = zscore(q)[0]
        qd = describe(qz)[0]
        d_sim = self._scores(self.desc, qd)
        qe = None
        if self.emb is not None:
            from .learned import embed
            qe = embed(self.encoder, qz[None], tta=True)[0]
            e_sim = self._scores(self.emb, qe)
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
        geom = {}                                             # j -> refined (x, y, w)
        if refit:
            ncc, ang = ncc.copy(), ang.copy()
            for j in order[:refit]:
                x, y, w, _ = (int(v) for v in self.meta[pool[j]])
                best = self._refine(qz, x, y, w, int(ang[j]), bool(fl[j]), rot_step)
                if best[0] > ncc[j]:
                    ncc[j], ang[j] = best[0], best[1]
                    geom[j] = best[2]
            if geom and self.emb is not None:                  # re-score the refitted windows with the matcher too
                from .learned import embed
                js = list(geom)
                pz = zscore(np.stack([self.patch(*geom[j]) for j in js]))
                pe = embed(self.encoder, pz, tta=True) @ qe
                pd = describe(pz) @ qd
                for j, ev, dv in zip(js, pe, pd):
                    first[j] = max(first[j], 0.45 * ev + 0.1 * dv)
            score = first + w_ncc * ncc
            order = np.argsort(-score)

        results, kept = [], []
        for j in order:
            x, y, w, f = (int(v) for v in self.meta[pool[j]])
            if j in geom:
                x, y, w = geom[j]
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
        km = w * self.mpp(lat) / 1000.0
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
