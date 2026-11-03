"""Build a terrain index for Mars, so a sculpture can be found on another planet.

  python build_planet.py                        # Mars: download, mosaic, index, embeddings, place names (~10 min)
  python build_planet.py --skip-download        # rebuild from the files already in data/mars/

Elevation: MGS MOLA MEGDR, 32 pixels per degree (~1.85 km at the equator), from the PDS Geosciences
Node. It is re-projected to Web Mercator so the whole pipeline (latitude-aware windows, rotation search,
maps) works exactly as on Earth. Place names: IAU Gazetteer of Planetary Nomenclature (USGS).

The learned matcher was trained on Earth only. Mars terrain (craters, dichotomy scarps, volcanoes) is not
what it learned, so check it with:  python selftest.py --index data/mars_z5 --crude --offgrid
"""
import argparse
import io
import json
import math
import os
import struct
import subprocess
import sys
import urllib.request
import zipfile

import cv2
import numpy as np

MOLA = "https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg032/megt90n000fb.img"
MOLA_PPD, MOLA_SHAPE = 32, (5760, 11520)                 # lines, samples; big-endian int16 metres; lon 0..360 E
NAMES = "https://asc-planetarynames-data.s3.us-west-2.amazonaws.com/MARS_nomenclature_center_pts.zip"
MARS_CIRC = 2 * math.pi * 3396190.0                       # equatorial radius of the MOLA areoid reference

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--zoom", type=int, default=5, help="Web Mercator zoom (5 = 2.6 km/px on Mars, like zoom 6 on Earth)")
p.add_argument("--max-lat", type=float, default=80.0)
p.add_argument("--data", default="data")
p.add_argument("--name", default="mars_z5")
p.add_argument("--model", default=None, help="matcher for the embeddings (default: the one the Earth index uses)")
p.add_argument("--skip-download", action="store_true")
a = p.parse_args()

raw_dir = os.path.join(a.data, "mars")
os.makedirs(raw_dir, exist_ok=True)


def download(url, path):
    if os.path.exists(path) or a.skip_download:
        return path
    print(f"[mars] downloading {url.rsplit('/', 1)[-1]} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "sand2planet/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(path + ".part", "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
            got += len(b)
            if total:
                print(f"[mars]   {got / 1e6:.0f} / {total / 1e6:.0f} MB", end="\r")
    os.replace(path + ".part", path)
    print()
    return path


# ---------------------------------------------------------------- elevation -> Web Mercator mosaic
img = download(MOLA, os.path.join(raw_dir, "megt90n000fb.img"))
eq = np.fromfile(img, dtype=">i2").reshape(MOLA_SHAPE).astype(np.float32)
eq = np.roll(eq, MOLA_SHAPE[1] // 2, axis=1)            # columns now run from 180 W to 180 E
n = 256 * 2 ** a.zoom
eq = cv2.resize(eq, (n, MOLA_SHAPE[0]), interpolation=cv2.INTER_AREA)   # match the mosaic width


def merc_y(lat):
    r = math.radians(lat)
    return (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n


y0, y1 = int(math.floor(merc_y(a.max_lat))), int(math.ceil(merc_y(-a.max_lat)))
ys = np.arange(y0, y1) + 0.5
lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * ys / n))))
src_row = ((90.0 - lat) * MOLA_PPD - 0.5).astype(np.float32)
map_x = np.tile(np.arange(n, dtype=np.float32), (len(ys), 1))
map_y = np.repeat(src_row[:, None], n, axis=1)
merc = cv2.remap(eq, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
mosaic_path = os.path.abspath(os.path.join(a.data, f"mosaic_mars_z{a.zoom}.npy"))
np.save(mosaic_path, np.round(merc).astype(np.int16))
print(f"[mars] mosaic {merc.shape[1]} x {merc.shape[0]} px, {merc.min():.0f} to {merc.max():.0f} m -> {mosaic_path}")

# ---------------------------------------------------------------- index
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s2e.index import build_index  # noqa: E402

hdr = dict(source="mola_megdr_32ppd", body="mars", circumference=MARS_CIRC, synthetic=False,
           zoom=a.zoom, px0=0, py0=y0, mosaic=mosaic_path)
prefix = os.path.join(a.data, a.name)
build_index(hdr, prefix, levels=(1, 2, 4), stride=16, min_land=0.0, min_relief=40.0, lat_aware=True)

# ---------------------------------------------------------------- learned embeddings
model = a.model
if model is None:
    earth = os.path.join(a.data, "world_z6_emb.json")
    model = json.load(open(earth))["model"] if os.path.exists(earth) else "models/matcher.pt"
if os.path.exists(model) or os.path.exists(os.path.join("models", os.path.basename(model))):
    if not os.path.exists(model):
        model = os.path.join("models", os.path.basename(model))
    subprocess.run([sys.executable, "embed_index.py", "--index", prefix, "--model", model], check=True)
else:
    print(f"[mars] no matcher at {model}; the Mars index will use the hand-crafted descriptor")


# ---------------------------------------------------------------- place names (dBase file inside the zip)
def read_dbf(data):
    nrec, hlen, rlen = struct.unpack("<xxxxIHH", data[:12])
    fields, pos = [], 32
    while data[pos] != 0x0D:
        name = data[pos:pos + 11].split(b"\0")[0].decode("latin-1")
        fields.append((name, data[pos + 16]))
        pos += 32
    rows = []
    for i in range(nrec):
        rec, off, row = data[hlen + i * rlen: hlen + (i + 1) * rlen], 1, {}
        for name, size in fields:
            row[name.lower()] = rec[off:off + size].decode("utf-8", "replace").strip()
            off += size
        rows.append(row)
    return rows


try:
    z = download(NAMES, os.path.join(raw_dir, "MARS_nomenclature_center_pts.zip"))
    with zipfile.ZipFile(z) as zf:
        rows = read_dbf(zf.read(next(n for n in zf.namelist() if n.lower().endswith(".dbf"))))
    pick = lambda r, *ks: next((r[k] for k in ks if r.get(k)), "")
    names = []
    for r in rows:
        try:
            lat_, lon_ = float(pick(r, "center_lat", "lat")), float(pick(r, "center_lon", "lon"))
            diam = float(pick(r, "diameter", "diam") or 0)
        except ValueError:
            continue
        if lon_ > 180:
            lon_ -= 360
        names.append([pick(r, "clean_name", "name"), round(lat_, 3), round(lon_, 3), round(diam, 1),
                      pick(r, "type", "feature_ty", "featuretyp")])
    names.sort(key=lambda t: -t[3])
    with open(prefix + "_names.json", "w") as f:
        json.dump(names, f, separators=(",", ":"))
    print(f"[mars] {len(names):,} named features -> {prefix}_names.json")
except Exception as e:
    print(f"[mars] place names unavailable ({e}); results will show coordinates only")

print(f"\n[mars] done. Check it:  python selftest.py --index {prefix} --crude --offgrid")
