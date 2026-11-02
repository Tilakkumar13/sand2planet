"""Write result.json (for TouchDesigner) and the HTML results page."""
import base64
import datetime as dt
import html
import json
import os

import cv2
import numpy as np

from .terrain import render, rotate, zscore
from .style import FONTS, BASE_CSS, MARK_SVG, IMPORTMAP, REVEAL_JS

S2_URL = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg"
S2_ATTR = ('<a href="https://s2maps.eu">Sentinel-2 cloudless 2016</a> by EOX IT Services GmbH '
           '(contains modified Copernicus Sentinel data 2016)')
ESRI_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
TOPO_URL = "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png"

COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]


def _b64(img, ext=".png"):
    ok, buf = cv2.imencode(ext, img)
    mime = "image/png" if ext == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(buf.tobytes()).decode()


def _coord(lat, lon):
    return f"{abs(lat):.2f}° {'N' if lat >= 0 else 'S'}, {abs(lon):.2f}° {'E' if lon >= 0 else 'W'}"


def _facing(bearing):
    return COMPASS[int(((bearing % 360) + 22.5) // 45) % 8]


def _links(r, synthetic):
    if synthetic:
        return ""
    gm = f"https://www.google.com/maps/@{r['lat']:.5f},{r['lon']:.5f},{_gz(r['size_km'])}z/data=!3m1!1e3"
    ge = (f"https://earth.google.com/web/@{r['lat']:.5f},{r['lon']:.5f},0a,"
          f"{r['size_km'] * 1400:.0f}d,35y,0h,45t,0r")
    return (f'<a class="more" href="{gm}" target="_blank" rel="noopener">Satellite view</a>'
            f'<a class="more" href="{ge}" target="_blank" rel="noopener">Open in Google Earth</a>')


def write_outputs(out_dir, index, query, results, photo=None):
    os.makedirs(out_dir, exist_ok=True)
    synthetic = index.h.get("synthetic", False)
    qz = zscore(query)[0]

    rows = []
    for i, r in enumerate(results, 1):
        real = index.patch(r["x"], r["y"], r["w"])
        aligned = rotate(qz, r["rotation_deg"], r["flipped"])
        r["match_png"] = f"match_{i}.png"
        cv2.imwrite(os.path.join(out_dir, r["match_png"]), render(real, 512))
        size = 520 if i == 1 else 240
        rows.append(dict(
            i=i, coord=_coord(r["lat"], r["lon"]), km=round(r["size_km"]),
            agree=round(max(r["ncc"], 0) * 100), facing=_facing(r["top_edge_bearing_deg"]),
            bearing=round(r["top_edge_bearing_deg"]), flipped=r["flipped"], links=_links(r, synthetic),
            mine=_b64(render(aligned, size)), real=_b64(render(real, size))))

    res_json = dict(time=dt.datetime.now().isoformat(timespec="seconds"),
                    synthetic=synthetic, results=results, imagery_tile_url=S2_URL)
    with open(os.path.join(out_dir, "result.json"), "w") as f:
        json.dump(res_json, f, indent=2)
    cv2.imwrite(os.path.join(out_dir, "query_heightmap.png"), render(query, 512))
    np.save(os.path.join(out_dir, "query_heightmap.npy"), query)
    if photo is not None:
        cv2.imwrite(os.path.join(out_dir, "photo.jpg"), photo)

    best = rows[0] if rows else None
    others = rows[1:]
    scene = _scene_data(index, query, results[0], photo, synthetic) if results else None

    hero = ""
    trio = ""
    if best:
        mirror = " The match uses the mirror image of your photo." if best["flipped"] else ""
        a = best["agree"]
        if a >= 70:
            eyebrow, strength = "Your landscape exists in", "a strong match"
        elif a >= 45:
            eyebrow, strength = "Your landscape looks most like", "a fair match"
        else:
            eyebrow, strength = "The closest place, but a loose fit, is", "a loose match"
        hero = f"""
  <section class="rhero dark">
    <div class="wrap">
      <p class="eyebrow reveal">{eyebrow}</p>
      <h1 class="place grad reveal" data-geo="0">{best['coord']}</h1>
      <p class="coords num reveal" data-coord="0" hidden>{best['coord']}</p>
      <p class="lede reveal">A stretch of terrain about <span class="w num">{best['km']} km</span> across, {strength}
        for your sculpture's shape (<span class="w num">{best['agree']}%</span> agreement). On the map, the top edge of your sandbox
        faces <span class="w">{best['facing']}</span>.{mirror}</p>
      <div class="links reveal">{best['links']}</div>
    </div>
  </section>"""
        photo_fig = (f'<figure class="reveal"><img src="{_b64(cv2.resize(photo, (520, 520)), ".jpg")}" alt="Your photo">'
                     f'<figcaption>Your photo</figcaption></figure><span class="arrow" aria-hidden="true"></span>') if photo is not None else ""
        trio = f"""
  <section class="trio dark">
    <div class="wide">
      <div class="row">
        {photo_fig}
        <figure class="reveal"><img src="{best['mine']}" alt="Your sculpture read as terrain, turned to north"><figcaption>Read as terrain, turned to north</figcaption></figure>
        <span class="arrow" aria-hidden="true"></span>
        <figure class="reveal"><img src="{best['real']}" alt="The matching real terrain"><figcaption>The real place</figcaption></figure>
      </div>
    </div>
  </section>"""

    cards = "".join(f"""
      <li class="mcard" data-i="{o['i'] - 1}" tabindex="0">
        <div class="pics"><img src="{o['mine']}" alt=""><img src="{o['real']}" alt=""></div>
        <p class="rank num">No. {o['i']}</p>
        <h3 data-geo="{o['i'] - 1}">{o['coord']}</h3>
        <p class="sub num" data-coord="{o['i'] - 1}" hidden>{o['coord']}</p>
        <p class="facts num">{o['km']} km across, {o['agree']}% shape match</p>
        <div class="links">{o['links']}</div>
      </li>""" for o in others)

    page = (TEMPLATE
            .replace("%%FONTS%%", FONTS).replace("%%CSS%%", BASE_CSS).replace("%%MARK%%", MARK_SVG)
            .replace("%%IMPORTMAP%%", IMPORTMAP if scene else "").replace("%%REVEAL%%", REVEAL_JS)
            .replace("%%WHEN%%", dt.datetime.now().strftime("%d %B %Y, %H:%M"))
            .replace("%%HERO%%", hero).replace("%%TRIO%%", trio)
            .replace("%%THREE%%", THREE_SECTION if scene else "")
            .replace("%%SCENE%%", json.dumps(scene).replace("</", "<\\/") if scene else "null")
            .replace("%%MAP%%", "" if synthetic else MAP_SECTION)
            .replace("%%OTHERS%%", cards)
            .replace("%%HAS_OTHERS%%", "" if others else "hidden")
            .replace("%%POLYS%%", json.dumps([[[c[1], c[0]] for c in r["corners_lonlat"]] for r in results]))
            .replace("%%POINTS%%", json.dumps([[r["lat"], r["lon"]] for r in results]))
            .replace("%%SYNTH%%", "true" if synthetic else "false")
            .replace("%%S2%%", S2_URL).replace("%%ESRI%%", ESRI_URL).replace("%%TOPO%%", TOPO_URL)
            .replace("%%S2ATTR%%", html.escape(S2_ATTR, quote=True)))
    path = os.path.join(out_dir, "report.html")
    with open(path, "w") as f:
        f.write(page)
    return path


def _scene_data(index, query, r, photo, synthetic):
    """Heights and textures for the 3D comparison of the best match."""
    real = cv2.resize(index.raw_patch(r["x"], r["y"], r["w"]), (128, 128), interpolation=cv2.INTER_AREA)
    real = cv2.GaussianBlur(real, (0, 0), 1.2)  # same level of detail as the sculpture it is compared with
    sculpt = rotate(query, r["rotation_deg"], r["flipped"])
    ph = None
    if photo is not None:
        ph = cv2.resize(photo, (512, 512), interpolation=cv2.INTER_AREA)
        if r["flipped"]:
            ph = ph[:, ::-1]
        M = cv2.getRotationMatrix2D((255.5, 255.5), r["rotation_deg"], 1.0)
        ph = cv2.warpAffine(np.ascontiguousarray(ph), M, (512, 512), borderMode=cv2.BORDER_REFLECT)
    return dict(
        synthetic=synthetic, km=r["size_km"], zoom=index.h["zoom"],
        gx=r["x"] + index.h["px0"], gy=r["y"] + index.h["py0"], w=r["w"],
        real=dict(n=128, h=np.round(real).astype(int).ravel().tolist()),
        sculpt=dict(n=sculpt.shape[0], h=np.round(sculpt, 4).ravel().tolist()),
        realRelief=_b64(render(real, 512), ".jpg"), sculptRelief=_b64(render(sculpt, 512), ".jpg"),
        photo=_b64(ph, ".jpg") if ph is not None else None,
        s2=S2_URL, esri=ESRI_URL)


def _gz(km):
    return max(5, min(13, int(round(14.5 - np.log2(max(km, 1))))))


MAP_SECTION = """
  <section class="mapsec light" id="map-section">
    <div class="wide">
      <div class="head reveal"><h2 class="section-title">On the map.</h2>
        <p class="lede">Your sandbox, drawn to scale on Sentinel-2 imagery. The yellow edge is its top side.</p></div>
      <div class="maptile reveal"><div id="map"></div></div>
    </div>
  </section>"""


THREE_SECTION = """
  <section class="three dark" aria-label="3D comparison">
    <div class="wide">
      <div class="head reveal"><h2 class="section-title">Side by side.</h2>
        <p class="lede">Your sculpture and the real place, at the same scale. Drag to turn.</p></div>
    </div>
    <div class="stage" id="stage">
      <div class="loading" id="loading3d">Building the 3D view</div>
      <canvas id="c3d" aria-label="Your sculpture and the matching real terrain as 3D surfaces"></canvas>
      <div class="caps"><span>Your sculpture</span><span data-geo="0">The real place</span></div>
    </div>
    <div class="ctrl reveal">
      <div class="seg" role="group" aria-label="Surface">
        <button type="button" data-surface="imagery" aria-pressed="true">Imagery</button>
        <button type="button" data-surface="relief" aria-pressed="false">Relief</button>
      </div>
      <label class="slider">Height <input type="range" id="ex" min="1" max="60" step="1" value="10"><output id="exv">×10</output></label>
    </div>
    <p class="note3d" id="note3d" hidden></p>
  </section>
<script type="application/json" id="scene">%%SCENE%%</script>
<script type="module">
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const D = JSON.parse(document.getElementById("scene").textContent);
const stage = document.getElementById("stage"), canvas = document.getElementById("c3d");
const note = document.getElementById("note3d");
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(32, 1, 0.01, 50);
camera.position.set(0, 1.15, 1.9);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true; controls.target.set(0, 0.02, 0); controls.enableZoom = false;
controls.maxPolarAngle = Math.PI * 0.47; controls.minPolarAngle = Math.PI * 0.12;
controls.autoRotate = !reduce; controls.autoRotateSpeed = 0.45;
controls.addEventListener("start", () => { controls.autoRotate = false; });

scene.add(new THREE.HemisphereLight(0xfff4e6, 0x202428, 1.3));
const sun = new THREE.DirectionalLight(0xffffff, 2.4); sun.position.set(-1, 1.3, -1); scene.add(sun);
const rim = new THREE.DirectionalLight(0x8fb8ff, .6); rim.position.set(1.5, .8, 1.5); scene.add(rim);

const am = document.createElement("canvas"); am.width = am.height = 256;
const ac = am.getContext("2d"); ac.fillStyle = "#000"; ac.fillRect(0, 0, 256, 256);
ac.fillStyle = "#fff"; ac.beginPath(); ac.arc(128, 128, 127, 0, Math.PI * 2); ac.fill();
const alphaMap = new THREE.CanvasTexture(am);

function stats(a) { let m = 0; for (const v of a) m += v; m /= a.length; let s = 0; for (const v of a) s += (v - m) ** 2; return [m, Math.sqrt(s / a.length)]; }
const [rm, rs] = stats(D.real.h), [sm, ss] = stats(D.sculpt.h);
const metres = 1 / (D.km * 1000);
let rmin = Infinity, rmax = -Infinity; for (const v of D.real.h) { rmin = Math.min(rmin, v); rmax = Math.max(rmax, v); }
const ex0 = Math.max(1, Math.min(60, Math.round(0.16 / Math.max((rmax - rmin) * metres, 1e-6))));

function surface(n, heights, x) {
  const g = new THREE.PlaneGeometry(1, 1, n - 1, n - 1); g.rotateX(-Math.PI / 2);
  const mat = new THREE.MeshStandardMaterial({ roughness: 0.92, metalness: 0, alphaMap, alphaTest: 0.5, side: THREE.DoubleSide });
  const mesh = new THREE.Mesh(g, mat); mesh.position.x = x; mesh.userData.h = heights; scene.add(mesh);
  const base = new THREE.Mesh(new THREE.CylinderGeometry(.5, .49, .05, 120, 1, true),
    new THREE.MeshStandardMaterial({ color: 0x1c1c1e, roughness: .6, metalness: .2, side: THREE.DoubleSide }));
  base.position.set(x, -.025, 0); scene.add(base);
  const sh = new THREE.Mesh(new THREE.CircleGeometry(.66, 64), new THREE.MeshBasicMaterial({ color: 0, transparent: true, opacity: .5 }));
  sh.rotation.x = -Math.PI / 2; sh.position.set(x, -.051, 0); scene.add(sh);
  return mesh;
}
const sculpt = surface(D.sculpt.n, D.sculpt.h.map(v => (v - sm) / (ss || 1) * rs), -0.62);
const real = surface(D.real.n, D.real.h.map(v => v - rm), 0.62);

function setHeight(ex) {
  for (const m of [sculpt, real]) {
    const pos = m.geometry.attributes.position, h = m.userData.h;
    let lo = Infinity; for (const v of h) lo = Math.min(lo, v);
    for (let i = 0; i < pos.count; i++) pos.setY(i, (h[i] - lo) * metres * ex);
    pos.needsUpdate = true; m.geometry.computeVertexNormals();
  }
  document.getElementById("exv").textContent = "×" + ex;
}
const exInput = document.getElementById("ex");
exInput.value = ex0; setHeight(ex0);
exInput.addEventListener("input", () => setHeight(+exInput.value));

const loader = new THREE.TextureLoader();
function tex(src) { return new Promise(res => loader.load(src, t => { t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; res(t); }, undefined, () => res(null))); }
function loadImg(url) {
  return new Promise((res, rej) => {
    const im = new Image(); im.crossOrigin = "anonymous";
    const t = setTimeout(() => rej(new Error("timeout")), 12000);
    im.onload = () => { clearTimeout(t); res(im); }; im.onerror = () => { clearTimeout(t); rej(new Error("tile")); };
    im.src = url;
  });
}
async function imagery(template) {
  // The window is axis-aligned in Web Mercator pixels, so the matching satellite tiles can be stitched exactly.
  let zt = Math.round(D.zoom + Math.log2(1024 / D.w)); zt = Math.max(2, Math.min(13, zt));
  const k = 2 ** (zt - D.zoom), gx = D.gx * k, gy = D.gy * k, size = D.w * k, n = 2 ** zt;
  const out = document.createElement("canvas"); out.width = out.height = 1024;
  const ctx = out.getContext("2d"), s = 1024 / size, jobs = [];
  for (let ty = Math.floor(gy / 256); ty <= Math.floor((gy + size - 1) / 256); ty++)
    for (let tx = Math.floor(gx / 256); tx <= Math.floor((gx + size - 1) / 256); tx++) {
      const url = template.replace("{z}", zt).replace("{x}", ((tx % n) + n) % n).replace("{y}", ty);
      jobs.push(loadImg(url).then(im => ctx.drawImage(im, (tx * 256 - gx) * s, (ty * 256 - gy) * s, 256 * s, 256 * s)));
    }
  await Promise.all(jobs);
  ctx.getImageData(0, 0, 1, 1);
  const t = new THREE.CanvasTexture(out); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  return t;
}
const T = {};
async function prepare() {
  [T.sRelief, T.rRelief, T.sPhoto] = await Promise.all([tex(D.sculptRelief), tex(D.realRelief), D.photo ? tex(D.photo) : null]);
  if (!D.synthetic) {
    for (const url of [D.s2, D.esri]) { try { T.rSat = await imagery(url); break; } catch (e) { } }
  }
}
function setSurface(kind) {
  document.querySelectorAll("[data-surface]").forEach(b => b.setAttribute("aria-pressed", b.dataset.surface === kind));
  const img = kind === "imagery";
  sculpt.material.map = (img && T.sPhoto) || T.sRelief;
  real.material.map = (img && T.rSat) || T.rRelief;
  [sculpt, real].forEach(m => m.material.needsUpdate = true);
  note.hidden = !(img && !T.rSat && !D.synthetic);
  note.textContent = "Satellite imagery could not be loaded, so the real place shows shaded relief.";
}
document.querySelectorAll("[data-surface]").forEach(b => b.addEventListener("click", () => setSurface(b.dataset.surface)));
function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  renderer.setSize(w, h, false); camera.aspect = w / h;
  camera.position.setLength(w < 600 ? 3.3 : 2.25); camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(stage);
let visible = false;
new IntersectionObserver(es => { visible = es[0].isIntersecting; }).observe(stage);
renderer.setAnimationLoop(() => { if (!visible) return; controls.update(); renderer.render(scene, camera); });
await prepare();
setSurface("imagery");
document.getElementById("loading3d").remove();
</script>
"""


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Your match · Sand to Earth</title>
<meta name="theme-color" content="#000000">
%%FONTS%%
%%IMPORTMAP%%
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
%%CSS%%
body { background: #000; }
.head { text-align: center; margin-bottom: 48px; }
.head .lede { margin: 14px auto 0; max-width: 30em; }

.rhero { padding: calc(var(--nav-h) + 110px) 0 70px; text-align: center; }
.eyebrow { font-size: clamp(21px, 2.2vw, 28px); font-weight: 600; letter-spacing: -0.005em; color: var(--on-dark-2); margin: 0 0 10px; }
.place { font-size: clamp(48px, 8.4vw, 112px); line-height: 1.02; font-weight: 700; letter-spacing: -0.03em; margin: 0 auto; max-width: 11em; }
.coords { margin: 18px 0 0; color: var(--on-dark-2); font-size: 17px; }
.rhero .lede { margin: 30px auto 0; max-width: 32em; }
.rhero .lede .w { color: #fff; }
.links { display: flex; gap: 28px; justify-content: center; flex-wrap: wrap; margin-top: 26px; }

.trio { padding: 30px 0 120px; }
.trio .row { display: flex; align-items: center; justify-content: center; gap: 26px; }
.trio figure { margin: 0; flex: 1 1 0; max-width: 330px; }
.trio img { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: var(--r-m); }
.trio figcaption { margin-top: 12px; text-align: center; color: var(--on-dark-2); font-size: 14px; }
.trio .arrow { flex: none; width: 28px; height: 28px; margin-bottom: 28px; border-radius: 50%; background: #1d1d1f; position: relative; }
.trio .arrow::after { content: ""; position: absolute; left: 9px; top: 10px; width: 7px; height: 7px; border: solid var(--on-dark-2);
  border-width: 2px 2px 0 0; transform: rotate(45deg); }

.three { padding: 120px 0 110px; background: #000; }
.stage { position: relative; height: min(68vh, 620px); max-width: 1440px; margin: 0 auto; }
.stage canvas { position: absolute; inset: 0; width: 100% !important; height: 100% !important; cursor: grab; touch-action: pan-y; }
.stage canvas:active { cursor: grabbing; }
.stage .caps { position: absolute; left: 0; right: 0; bottom: 8px; display: grid; grid-template-columns: 1fr 1fr; pointer-events: none;
  text-align: center; color: var(--on-dark-2); font-size: 15px; }
.stage .loading { position: absolute; inset: 0; display: grid; place-items: center; color: var(--on-dark-2); }
.ctrl { display: flex; gap: 26px; justify-content: center; align-items: center; flex-wrap: wrap; margin-top: 28px; color: var(--on-dark-2); font-size: 14px; }
.seg { display: inline-flex; background: #1d1d1f; border-radius: 980px; padding: 3px; }
.seg button { font: 500 14px var(--sans); border: 0; background: transparent; color: var(--on-dark-2); padding: 7px 18px; border-radius: 980px; cursor: pointer;
  transition: background .25s var(--ease), color .25s var(--ease); }
.seg button[aria-pressed="true"] { background: #424245; color: #fff; }
.slider { display: flex; gap: 12px; align-items: center; }
.slider input { -webkit-appearance: none; appearance: none; width: 150px; height: 4px; border-radius: 2px; background: #424245; }
.slider input::-webkit-slider-thumb { -webkit-appearance: none; width: 22px; height: 22px; border-radius: 50%; background: #fff; box-shadow: 0 2px 6px rgba(0,0,0,.4); }
.slider input::-moz-range-thumb { width: 22px; height: 22px; border: 0; border-radius: 50%; background: #fff; }
.slider output { min-width: 3em; color: #fff; font-variant-numeric: tabular-nums; }
.note3d { text-align: center; color: var(--on-dark-2); font-size: 14px; margin: 14px 0 0; }

.mapsec { padding: 120px 0; }
.maptile { border-radius: var(--r-l); overflow: hidden; box-shadow: 0 30px 80px -40px rgba(0,0,0,.3); }
#map { height: min(70vh, 620px); }
.leaflet-container { font: 13px var(--sans); background: #dfe3e8; }

.others { padding: 120px 0 130px; background: var(--white); }
.others[hidden] { display: none; }
.rail { list-style: none; margin: 0; padding: 4px 22px 30px; display: grid; grid-auto-flow: column; grid-auto-columns: minmax(280px, 340px);
  gap: 20px; overflow-x: auto; scroll-snap-type: x mandatory; scrollbar-width: none; justify-content: safe center; }
.rail::-webkit-scrollbar { display: none; }
.mcard { scroll-snap-align: center; background: var(--light); border-radius: var(--r-l); padding: 22px 22px 26px; cursor: pointer;
  transition: transform .35s var(--ease), box-shadow .35s var(--ease); }
.mcard:hover, .mcard.active { transform: scale(1.015); box-shadow: 0 20px 40px -24px rgba(0,0,0,.35); }
.mcard .pics { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 18px; }
.mcard .pics img { width: 100%; aspect-ratio: 1; border-radius: 12px; }
.mcard .rank { margin: 0 0 4px; color: var(--ink-3); font-size: 14px; font-weight: 600; }
.mcard h3 { margin: 0; font-size: 24px; line-height: 1.17; font-weight: 700; letter-spacing: 0.009em; }
.mcard .sub { margin: 4px 0 0; color: var(--ink-3); font-size: 14px; }
.mcard .facts { margin: 10px 0 0; color: var(--ink-2); font-size: 15px; }
.mcard .links { justify-content: flex-start; gap: 18px; margin-top: 14px; font-size: 15px; }
.mcard .more { font-size: 15px; }
[hidden] { display: none !important; }

.again { padding: 110px 0 120px; text-align: center; background: var(--light); }
.again .section-title { margin-bottom: 26px; }
.again p { color: var(--ink-2); margin: 0 0 30px; }

@media (max-width: 734px) {
  .rhero { padding-top: calc(var(--nav-h) + 70px); }
  .trio .row { flex-wrap: wrap; gap: 16px; }
  .trio figure { flex: 1 1 40%; }
  .trio .arrow { display: none; }
  .three, .mapsec, .others, .again { padding: 80px 0; }
  .stage { height: 420px; }
}
</style></head>
<body>
<nav class="gnav" aria-label="Sand to Earth">
  <div class="in">
    <a class="brand" href="/" id="home">%%MARK%%Sand to Earth</a>
    <div class="links"><a class="pill small" href="/#try" id="again-nav">Try another photo</a></div>
  </div>
</nav>
%%HERO%%
%%TRIO%%
%%THREE%%
%%MAP%%
<section class="others" %%HAS_OTHERS%%>
  <div class="wide"><div class="head reveal"><h2 class="section-title">More places like yours.</h2>
    <p class="lede">The next closest matches. Select one to see it on the map.</p></div></div>
  <ol class="rail">%%OTHERS%%</ol>
</section>
<section class="again" id="again">
  <div class="wrap reveal">
    <h2 class="section-title">Sculpt another one.</h2>
    <p>Searched %%WHEN%%. Each result is also saved as result.json for TouchDesigner.</p>
    <a class="pill" href="/#try" id="again-btn">Try another photo</a>
  </div>
</section>
<footer class="foot"><div class="wrap">
  <p>Imagery: Sentinel-2 cloudless 2016 by EOX IT Services GmbH, CC BY 4.0. Elevation: AWS Terrain Tiles.
    Place names: OpenStreetMap contributors via Nominatim. 3D: three.js.</p>
</div></footer>
<script>
const synthetic = %%SYNTH%%, polys = %%POLYS%%, points = %%POINTS%%;
if (location.protocol === "file:") {  // opened from disk (webcam mode): no app to go back to
  ["again-nav", "again"].forEach(id => document.getElementById(id).style.display = "none");
  document.getElementById("home").removeAttribute("href");
}
let shapes = [], map = null;
if (!synthetic && window.L && document.getElementById("map")) {
  const s2 = L.tileLayer("%%S2%%", {maxZoom: 15, attribution: "%%S2ATTR%%"});
  const esri = L.tileLayer("%%ESRI%%", {maxZoom: 18, attribution: "Imagery © Esri"});
  const topo = L.tileLayer("%%TOPO%%", {maxZoom: 17, subdomains: "abc", attribution: "© OpenTopoMap (CC-BY-SA)"});
  map = L.map("map", {layers: [s2], worldCopyJump: true, scrollWheelZoom: false});
  L.control.layers({"Sentinel-2": s2, "Esri imagery": esri, "Topographic": topo}).addTo(map);
  L.control.scale({imperial: false}).addTo(map);
  shapes = polys.map((p, i) => {
    const poly = L.polygon(p, {color: i ? "#ffffff" : "#34c759", weight: i ? 1.5 : 3, fillOpacity: i ? .04 : .12, dashArray: i ? "4 4" : null})
      .bindTooltip(i ? "Match " + (i + 1) : "Best match").addTo(map);
    L.polyline([p[0], p[1]], {color: "#ffd60a", weight: 5, opacity: .95}).bindTooltip("Top edge of your sandbox").addTo(map);
    return poly;
  });
  map.fitBounds(shapes[0].getBounds().pad(1.4));
}
document.querySelectorAll(".mcard").forEach(card => {
  const pick = () => {
    document.querySelectorAll(".mcard").forEach(c => c.classList.remove("active")); card.classList.add("active");
    if (map) { map.fitBounds(shapes[+card.dataset.i].getBounds().pad(1.4));
      document.getElementById("map-section").scrollIntoView({behavior: "smooth", block: "start"}); }
  };
  card.addEventListener("click", e => { if (e.target.tagName !== "A") pick(); });
  card.addEventListener("keydown", e => { if (e.key === "Enter") pick(); });
});
// Name the places (OpenStreetMap Nominatim; one request per second, as its usage policy asks).
if (!synthetic) (async () => {
  for (let i = 0; i < points.length; i++) {
    const [lat, lon] = points[i];
    try {
      const r = await fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=6&accept-language=en&lat=${lat}&lon=${lon}`);
      const j = await r.json(), a = j.address || {};
      const near = a.state || a.region || a.county || a.province || a.archipelago || a.island;
      const name = [near, a.country].filter(Boolean).join(", ");
      if (name) {
        document.querySelectorAll(`[data-geo="${i}"]`).forEach(el => { el.textContent = name; });
        document.querySelectorAll(`[data-coord="${i}"]`).forEach(el => el.hidden = false);
        if (i === 0) document.title = name + " · Sand to Earth";
      }
    } catch (e) { /* keep the coordinates */ }
    await new Promise(res => setTimeout(res, 1100));
  }
})();
</script>
%%REVEAL%%
</body></html>
"""
