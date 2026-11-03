"""Build the static showcase site for GitHub Pages into docs/.

GitHub Pages only hosts static files, so the search runs in the visitor's browser:
the depth model comes from the Hugging Face hub (transformers.js), and this script
exports the terrain index, the learned matcher (ONNX) and a compact 8-bit copy of the
elevation to docs/engine/ (about 45 MB). Photos never leave the visitor's device.

  python build_site.py --index data/world_z6                 # site + in-browser search
  python build_site.py --index data/world_z6 --no-pack       # page only, keep docs/engine as it is
  python build_site.py --index data/world_z6 --static-only   # no search, "run it yourself" instead
  python build_site.py --index data/world_z6 --examples output/20261102_160501_123 output/20261102_161210_456

Then: GitHub repo > Settings > Pages > Deploy from a branch > main, /docs.
Only publish searches whose photos you are happy to make public.
"""
import argparse
import json
import os
import shutil

from s2e.index import Index
from s2e.page import render_page, hero_data
from s2e.terrain import PATCH
from s2e.tiles import meters_per_px

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--index", required=True)
p.add_argument("--examples", nargs="*", default=[], help="output/<time> folders from app.py or run.py to publish")
p.add_argument("--out", default="docs")
p.add_argument("--no-pack", action="store_true", help="don't re-export docs/engine (index unchanged)")
p.add_argument("--static-only", action="store_true", help="no in-browser search")
p.add_argument("--mars", default=None, help="Mars index from build_planet.py (e.g. data/mars_z5): adds an Earth/Mars switch")
a = p.parse_args()

idx = Index(a.index)
sizes = [PATCH * f * idx.mpp(0) / 1000 for f in sorted(idx.levels)]
os.makedirs(a.out, exist_ok=True)

examples = []
ex_root = os.path.join(a.out, "examples")
if a.examples:
    shutil.rmtree(ex_root, ignore_errors=True)
for k, src in enumerate(a.examples, 1):
    src = src.rstrip("/")
    if not os.path.exists(os.path.join(src, "report.html")):
        raise SystemExit(f"{src} has no report.html")
    name = f"example-{k}"
    dst = os.path.join(ex_root, name)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.npy"))
    rep = os.path.join(dst, "report.html")
    html = open(rep).read()
    # links that pointed at the local app now point at the showcase home page
    html = (html.replace('href="/#try"', 'href="../../index.html#try"').replace('href="/"', 'href="../../index.html"')
                .replace("Try another photo", "Back to Sand to Earth").replace("Sculpt another one.", "Make your own."))
    open(rep, "w").write(html)
    res = json.load(open(os.path.join(dst, "result.json")))["results"][0]
    lat, lon = res["lat"], res["lon"]
    examples.append(dict(
        href=f"examples/{name}/report.html",
        photo=f"examples/{name}/photo.jpg" if os.path.exists(os.path.join(dst, "photo.jpg")) else f"examples/{name}/query_heightmap.png",
        match=f"examples/{name}/match_1.png",
        title=f"{abs(lat):.1f}° {'N' if lat >= 0 else 'S'}, {abs(lon):.1f}° {'E' if lon >= 0 else 'W'}",
        sub=f"{res['size_km']:.0f} km across, {max(res['ncc'], 0) * 100:.0f}% shape agreement"))

browser = not a.static_only
if browser:
    from s2e.webpack import export_pack, export_web
    if not a.no_pack or not os.path.exists(os.path.join(a.out, "engine", "index.json")):
        export_pack(idx, a.out)
    if a.mars and not a.no_pack:
        midx = Index(a.mars)
        same = os.path.basename(json.load(open(a.mars + "_emb.json"))["model"]) == os.path.basename(json.load(open(a.index + "_emb.json"))["model"]) \
            if os.path.exists(a.mars + "_emb.json") and os.path.exists(a.index + "_emb.json") else False
        export_pack(midx, a.out, sub=os.path.join("mars", "engine"), shared_matcher="../../engine/matcher.onnx" if same else None)
    export_web(a.out)
page = render_page(len(idx.meta), sizes, idx.matcher, hero=hero_data(idx), static=True, examples=examples,
                   engine="./engine/" if browser else None,
                   mars="./mars/engine/" if browser and a.mars else None)
with open(os.path.join(a.out, "index.html"), "w") as f:
    f.write(page)
open(os.path.join(a.out, ".nojekyll"), "w").close()   # serve files as they are
print(f"[site] {a.out}/index.html with {len(examples)} example(s)"
      + (", search runs in the browser" if browser else ", no search"))
print("[site] hero:", "real elevation" if '"real"' in page else "procedural (place not in this index)")
