"""Learned terrain matcher: a small CNN with a polar-Fourier head.

Idea: the hand-crafted descriptor samples heights on polar rings and keeps the
magnitude of an angular Fourier transform, which does not change when the
patch rotates. Here a CNN first learns what to look at (ridges, valleys,
drainage), then the same polar-Fourier trick is applied to its feature maps.
Training is contrastive (InfoNCE): a distorted, rotated "sculpture" of a place
must land next to the clean north-up window of that place and far from every
other place in the batch.

All augmentation runs on the GPU (Apple MPS on a Mac).
"""
import math

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from .terrain import PATCH, MASK, BLUR_SIGMA

_MASK_T = torch.from_numpy(MASK.astype(np.float32))[None, None]


def pick_device():
    from .device import device_name, setup_cpu_threads
    name = device_name()
    if name == "cpu":
        setup_cpu_threads()
    return torch.device(name)


# ---------------------------------------------------------------- model
class Block(nn.Module):
    def __init__(self, cin, cout, stride=1):
        super().__init__()
        self.c1 = nn.Conv2d(cin, cout, 3, stride, 1, bias=False)
        self.b1 = nn.BatchNorm2d(cout)
        self.c2 = nn.Conv2d(cout, cout, 3, 1, 1, bias=False)
        self.b2 = nn.BatchNorm2d(cout)
        self.skip = None
        if stride != 1 or cin != cout:
            self.skip = nn.Sequential(nn.Conv2d(cin, cout, 1, stride, bias=False), nn.BatchNorm2d(cout))

    def forward(self, x):
        y = F.relu(self.b1(self.c1(x)))
        y = self.b2(self.c2(y))
        return F.relu(y + (x if self.skip is None else self.skip(x)))


class PolarFourierHead(nn.Module):
    """Sample feature maps on polar rings and keep angular Fourier magnitudes (rotation invariant)."""

    def __init__(self, cin, c=64, radii=6, angles=32, harmonics=6, dim=128):
        super().__init__()
        self.reduce = nn.Sequential(nn.Conv2d(cin, c, 1, bias=False), nn.BatchNorm2d(c))
        r = torch.linspace(0.1, 0.92, radii)
        t = torch.arange(angles) * (2 * math.pi / angles)
        grid = torch.stack([r[:, None] * torch.cos(t)[None], r[:, None] * torch.sin(t)[None]], -1)
        self.register_buffer("grid", grid[None])                       # (1, R, A, 2)
        k = torch.arange(harmonics)
        ang = t[:, None] * k[None]
        self.register_buffer("cos", torch.cos(ang))                    # (A, H)
        self.register_buffer("sin", torch.sin(ang))
        self.angles = angles
        feat = c * radii * harmonics + c
        self.fc = nn.Sequential(nn.Linear(feat, 512), nn.BatchNorm1d(512), nn.ReLU(), nn.Linear(512, dim))

    def forward(self, f):
        f = self.reduce(f)
        B = f.shape[0]
        s = F.grid_sample(f, self.grid.expand(B, -1, -1, -1), mode="bilinear", align_corners=False)  # (B,C,R,A)
        re, im = s @ self.cos, s @ self.sin
        mag = torch.sqrt(re * re + im * im + 1e-6) / self.angles
        mag = torch.cat([s.mean(-1, keepdim=True), mag[..., 1:]], -1)  # keep the signed ring mean
        x = torch.cat([mag.flatten(1), f.mean((2, 3))], 1)
        return F.normalize(self.fc(x), dim=1)


class Encoder(nn.Module):
    def __init__(self, width=32, dim=128):
        super().__init__()
        w = width
        self.config = dict(width=width, dim=dim)
        self.stem = nn.Sequential(nn.Conv2d(1, w, 3, 1, 1, bias=False), nn.BatchNorm2d(w), nn.ReLU())
        self.body = nn.Sequential(Block(w, w), Block(w, 2 * w, 2), Block(2 * w, 2 * w),
                                  Block(2 * w, 4 * w, 2), Block(4 * w, 4 * w))      # 64 -> 16 px
        self.head = PolarFourierHead(4 * w, dim=dim)
        self.register_buffer("mask", _MASK_T.clone())

    def forward(self, x):                                              # x: (B,1,64,64) z-scored
        return self.head(self.body(self.stem(x * self.mask)))


_CACHE = {}


def load_encoder(path, device=None):
    key = (str(path), str(device))
    if key not in _CACHE:
        ck = torch.load(path, map_location="cpu", weights_only=True)
        m = Encoder(**ck["config"])
        m.load_state_dict(ck["state"])
        dev = device or pick_device()
        _CACHE[key] = m.to(dev).eval()
    return _CACHE[key]


def save_encoder(model, path, extra=None):
    torch.save(dict(config=model.config, state=model.state_dict(), **(extra or {})), path)


@torch.no_grad()
def embed(model, z, tta=True, batch=1024):
    """z-scored patches (N,64,64) -> L2-normalised embeddings (N,D). tta averages 4 right-angle turns."""
    dev = next(model.parameters()).device
    out = []
    for s in range(0, len(z), batch):
        x = torch.from_numpy(np.ascontiguousarray(z[s:s + batch], np.float32))[:, None].to(dev)
        e = sum(model(torch.rot90(x, k, (2, 3))) for k in range(4)) if tta else model(x)
        out.append(F.normalize(e, dim=1).float().cpu().numpy())
    return np.concatenate(out)


# ---------------------------------------------------------------- augmentation (GPU)
def _gauss_blur(x, sigma):
    """Per-sample Gaussian blur. x (B,1,H,W), sigma (B,) in pixels."""
    B, _, H, W = x.shape
    r = int(math.ceil(3 * float(sigma.max())))
    r = max(1, min(r, 15))
    t = torch.arange(-r, r + 1, device=x.device, dtype=x.dtype)
    k = torch.exp(-(t[None] ** 2) / (2 * sigma[:, None].clamp(min=0.3) ** 2))
    k = k / k.sum(1, keepdim=True)
    y = F.pad(x.view(1, B, H, W), (r, r, r, r), mode="reflect")
    y = F.conv2d(y, k.view(B, 1, 1, -1), groups=B)
    y = F.conv2d(y, k.view(B, 1, -1, 1), groups=B)
    return y.view(B, 1, H, W)


def masked_zscore(x, mask):
    m = mask.expand_as(x)
    n = m.sum((2, 3), keepdim=True)
    mu = (x * m).sum((2, 3), keepdim=True) / n
    sd = torch.sqrt((((x - mu) * m) ** 2).sum((2, 3), keepdim=True) / n + 1e-8)
    return (x - mu) / sd * m


def make_pairs(ctx, crude=0.5, generator=None, shift=0.03, scale=(0.85, 1.15)):
    """ctx: (B,1,C,C) terrain context, the indexed window is its centre 64/C. Returns (sculpture, clean), both (B,1,64,64).

    The sculpture is a rotated copy of an area `scale` times the window, centred up to `shift` windows away from it:
    a real sandbox never lines up exactly with the index grid (off by up to 1/8 window, and up to sqrt(2) in size)."""
    B, _, C, _ = ctx.shape
    dev, dt = ctx.device, ctx.dtype
    g = generator
    U = lambda *s: torch.rand(*s, device=dev, dtype=dt, generator=g)
    N = lambda *s: torch.randn(*s, device=dev, dtype=dt, generator=g)
    mask = _MASK_T.to(dev, dt)

    o = (C - PATCH) // 2
    clean = _gauss_blur(ctx[:, :, o:o + PATCH, o:o + PATCH], torch.full((B,), BLUR_SIGMA, device=dev, dtype=dt))
    clean = masked_zscore(clean, mask)

    th = U(B) * 2 * math.pi
    sc = torch.exp(math.log(scale[0]) + (math.log(scale[1]) - math.log(scale[0])) * U(B))
    a = (PATCH / C) * sc
    win = 2 * PATCH / C                                                       # window width in grid units
    tx, ty = (U(B) - .5) * 2 * shift * win, (U(B) - .5) * 2 * shift * win
    A = torch.stack([torch.stack([a * torch.cos(th), -a * torch.sin(th), tx], 1),
                     torch.stack([a * torch.sin(th), a * torch.cos(th), ty], 1)], 1)
    grid = F.affine_grid(A, (B, 1, PATCH, PATCH), align_corners=False)
    q = F.grid_sample(ctx, grid, mode="bilinear", padding_mode="reflection", align_corners=False)

    lo = q.amin((2, 3), keepdim=True)
    hi = q.amax((2, 3), keepdim=True)
    q = (q - lo) / (hi - lo + 1e-6)
    q = q.clamp(1e-4, 1) ** (0.6 + U(B, 1, 1, 1))                         # non-linear depth response
    yy, xx = torch.meshgrid(torch.linspace(-.5, .5, PATCH, device=dev, dtype=dt),
                            torch.linspace(-.5, .5, PATCH, device=dev, dtype=dt), indexing="ij")
    q = q + 0.1 * N(B, 1, 1, 1) * xx + 0.1 * N(B, 1, 1, 1) * yy             # camera tilt left over
    q = q + 0.15 * N(B, 1, 1, 1) * (xx ** 2 + yy ** 2)                       # lens / table bowl
    low = F.interpolate(N(B, 1, 4, 4), size=(PATCH, PATCH), mode="bicubic", align_corners=False)
    q = q + 0.12 * U(B, 1, 1, 1) * low                                       # depth-model warp
    rough = U(B) < crude
    sig = torch.where(rough, 2.5 + 3.5 * U(B), 0.5 + 2.0 * U(B))
    q = _gauss_blur(q, sig)                                                  # hands can't sculpt detail
    q = q + 0.05 * U(B, 1, 1, 1) * N(B, 1, PATCH, PATCH)                     # sensor noise
    q = _gauss_blur(q, torch.full((B,), BLUR_SIGMA, device=dev, dtype=dt))
    return masked_zscore(q, mask), clean
