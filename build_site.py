"""Build the static showcase site for GitHub Pages into docs/.

GitHub Pages can only host static files, so the public site cannot run a search.
It shows the landing page (with real elevation in the hero), the measured results,
and any searches you choose to publish as examples.

  python build_site.py --index data/world_z6
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
a = p.parse_args()

idx = Index(a.index)
sizes = [PATCH * f * meters_per_px(0, idx.h["zoom"]) / 1000 for f in sorted(idx.levels)]
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

page = render_page(len(idx.meta), sizes, idx.matcher, hero=hero_data(idx), static=True, examples=examples)
with open(os.path.join(a.out, "index.html"), "w") as f:
    f.write(page)
open(os.path.join(a.out, ".nojekyll"), "w").close()   # serve files as they are
print(f"[site] {a.out}/index.html with {len(examples)} example(s)")
print("[site] hero:", "real elevation" if '"real"' in page else "procedural (place not in this index)")
