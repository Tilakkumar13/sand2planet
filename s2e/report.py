"""Write result.json (for TouchDesigner) and the HTML results sheet."""
import base64
import datetime as dt
import html
import json
import os

import cv2
import numpy as np

from .terrain import render, rotate, zscore
from .style import FONTS, BASE_CSS, MARK_SVG

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
        big = i == 1
        size = 360 if big else 120
        gm = f"https://www.google.com/maps/@{r['lat']:.5f},{r['lon']:.5f},{_gz(r['size_km'])}z/data=!3m1!1e3"
        ge = (f"https://earth.google.com/web/@{r['lat']:.5f},{r['lon']:.5f},0a,"
              f"{r['size_km'] * 1400:.0f}d,35y,0h,45t,0r")
        links = "" if synthetic else (f'<a href="{gm}" target="_blank" rel="noopener">Satellite view</a>'
                                      f'<a href="{ge}" target="_blank" rel="noopener">Google Earth in 3D</a>')
        rows.append(dict(
            i=i, lat=r["lat"], lon=r["lon"], coord=_coord(r["lat"], r["lon"]),
            km=round(r["size_km"]), agree=round(max(r["ncc"], 0) * 100),
            facing=_facing(r["top_edge_bearing_deg"]), bearing=round(r["top_edge_bearing_deg"]),
            flipped=r["flipped"], links=links,
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
    photo_img = (f'<figure><img src="{_b64(cv2.resize(photo, (240, 240)), ".jpg")}" alt="">'
                 f'<figcaption>Your photo</figcaption></figure>') if photo is not None else ""
    lead = ""
    if best:
        mirror = " The match uses the mirror image of your photo." if best["flipped"] else ""
        lead = f"""
      <section class="best">
        <div class="best-text">
          <p class="kicker">Best match</p>
          <h1 class="place" data-geo="0">{best['coord']}</h1>
          <p class="coord num" data-coord="0" hidden>{best['coord']}</p>
          <p class="explain">A stretch of terrain about <b class="num">{best['km']} km</b> across that agrees with your sculpture's shape at
            <b class="num">{best['agree']}%</b>. Placed on the map, the top edge of your sandbox faces
            <b>{best['facing']}</b> <span class="num">({best['bearing']}°)</span>.{mirror}</p>
          <div class="links">{best['links']}</div>
        </div>
        <div class="pair">
          <figure><img src="{best['mine']}" alt="Your sculpture as terrain, turned to north"><figcaption>Your sculpture, turned to north</figcaption></figure>
          <figure><img src="{best['real']}" alt="The matching real terrain"><figcaption>The real terrain</figcaption></figure>
        </div>
      </section>"""

    other_html = "".join(f"""
        <li class="row" data-i="{o['i'] - 1}" tabindex="0">
          <span class="rank num">{o['i']}</span>
          <span class="thumbs"><img src="{o['mine']}" alt=""><img src="{o['real']}" alt=""></span>
          <span class="where"><span class="place" data-geo="{o['i'] - 1}">{o['coord']}</span>
            <span class="sub num" data-coord="{o['i'] - 1}" hidden>{o['coord']}</span></span>
          <span class="stat num">{o['km']} km<small>across</small></span>
          <span class="stat num">{o['agree']}%<small>shape agreement</small></span>
          <span class="go">{o['links']}</span>
        </li>""" for o in others)

    page = (TEMPLATE
            .replace("%%FONTS%%", FONTS).replace("%%CSS%%", BASE_CSS).replace("%%MARK%%", MARK_SVG)
            .replace("%%PHOTO%%", photo_img)
            .replace("%%QUERY%%", _b64(render(query, 240)))
            .replace("%%WHEN%%", dt.datetime.now().strftime("%d %b %Y, %H:%M"))
            .replace("%%BEST%%", lead)
            .replace("%%THREE%%", THREE_SECTION if scene else "")
            .replace("%%SCENE%%", json.dumps(scene).replace("</", "<\\/") if scene else "null")
            .replace("%%MAP%%", "" if synthetic else '<div class="map-wrap neatline"><div id="map"></div></div>')
            .replace("%%OTHERS%%", other_html)
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
    tex_s = render(sculpt, 512)
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
        realRelief=_b64(render(real, 512), ".jpg"), sculptRelief=_b64(tex_s, ".jpg"),
        photo=_b64(ph, ".jpg") if photo is not None else None,
        s2=S2_URL, esri=ESRI_URL)


def _gz(km):
    return max(5, min(13, int(round(14.5 - np.log2(max(km, 1))))))


THREE_SECTION = """
  <section class="three" aria-label="3D comparison">
    <div class="three-head">
      <div><h2>Side by side in 3D</h2><p>Drag to turn, scroll or pinch to zoom.</p></div>
      <div class="ctrl">
        <div class="seg" role="group" aria-label="Surface">
          <button type="button" data-surface="imagery" aria-pressed="true">Imagery</button>
          <button type="button" data-surface="relief" aria-pressed="false">Shaded relief</button>
        </div>
        <label>Height <input type="range" id="ex" min="1" max="60" step="1" value="10"><output id="exv">×10</output></label>
      </div>
    </div>
    <div class="stage neatline" id="stage">
      <div class="loading" id="loading3d">Building the 3D view</div>
      <canvas id="c3d" aria-label="Your sculpture and the matching real terrain as 3D surfaces"></canvas>
      <p class="note" id="note3d" hidden></p>
      <div class="caps"><span>Your sculpture, turned to north</span><span class="place" data-geo="0">Best match</span></div>
    </div>
  </section>
<script type="application/json" id="scene">%%SCENE%%</script>
<script type="importmap">{"imports": {"three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
  "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"}}</script>
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
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 50);
camera.position.set(0, 1.05, 1.75);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true; controls.target.set(0, 0.02, 0);
controls.minDistance = 0.6; controls.maxDistance = 5; controls.maxPolarAngle = Math.PI * 0.48;
controls.autoRotate = !reduce; controls.autoRotateSpeed = 0.5;
controls.addEventListener("start", () => { controls.autoRotate = false; });

scene.add(new THREE.HemisphereLight(0xffffff, 0x556655, 1.4));
const sun = new THREE.DirectionalLight(0xffffff, 2.0);
sun.position.set(-1, 1.2, -1);                       // north-west light, as on printed relief maps
scene.add(sun);

// circular cut, like a core sample
const am = document.createElement("canvas"); am.width = am.height = 256;
const ac = am.getContext("2d"); ac.fillStyle = "#000"; ac.fillRect(0, 0, 256, 256);
ac.fillStyle = "#fff"; ac.beginPath(); ac.arc(128, 128, 126, 0, Math.PI * 2); ac.fill();
const alphaMap = new THREE.CanvasTexture(am);

function stats(a) { let m = 0; for (const v of a) m += v; m /= a.length; let s = 0; for (const v of a) s += (v - m) ** 2; return [m, Math.sqrt(s / a.length)]; }
const [rm, rs] = stats(D.real.h), [sm, ss] = stats(D.sculpt.h);
const metres = 1 / (D.km * 1000);                     // scene units per metre (disc = 1 unit across)
let rmin = Infinity, rmax = -Infinity; for (const v of D.real.h) { rmin = Math.min(rmin, v); rmax = Math.max(rmax, v); }
const ex0 = Math.max(1, Math.min(60, Math.round(0.16 / Math.max((rmax - rmin) * metres, 1e-6))));

function surface(n, heights, x) {
  const g = new THREE.PlaneGeometry(1, 1, n - 1, n - 1);
  g.rotateX(-Math.PI / 2);
  const mat = new THREE.MeshStandardMaterial({ roughness: 0.95, metalness: 0, alphaMap, alphaTest: 0.5, side: THREE.DoubleSide });
  const mesh = new THREE.Mesh(g, mat);
  mesh.position.x = x; mesh.userData.h = heights; scene.add(mesh);
  return mesh;
}
const sculpt = surface(D.sculpt.n, D.sculpt.h.map(v => (v - sm) / (ss || 1) * rs), -0.6);  // same relief spread as the real place
const real = surface(D.real.n, D.real.h.map(v => v - rm), 0.6);
const base = new THREE.MeshStandardMaterial({ color: 0xb9b2a4, roughness: 1 });
for (const x of [-0.6, 0.6]) { const c = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 0.02, 96), base); c.position.set(x, -0.012, 0); scene.add(c); }

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
  const ctx = out.getContext("2d"), s = 1024 / size;
  const jobs = [];
  for (let ty = Math.floor(gy / 256); ty <= Math.floor((gy + size - 1) / 256); ty++)
    for (let tx = Math.floor(gx / 256); tx <= Math.floor((gx + size - 1) / 256); tx++) {
      const url = template.replace("{z}", zt).replace("{x}", ((tx % n) + n) % n).replace("{y}", ty);
      jobs.push(loadImg(url).then(im => ctx.drawImage(im, (tx * 256 - gx) * s, (ty * 256 - gy) * s, 256 * s, 256 * s)));
    }
  await Promise.all(jobs);
  ctx.getImageData(0, 0, 1, 1);                       // throws if the tiles were not shareable (CORS)
  const t = new THREE.CanvasTexture(out); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  return t;
}

const T = {};
async function prepare() {
  [T.sRelief, T.rRelief, T.sPhoto] = await Promise.all([tex(D.sculptRelief), tex(D.realRelief), D.photo ? tex(D.photo) : null]);
  if (!D.synthetic) {
    for (const [name, url] of [["Sentinel-2", D.s2], ["Esri", D.esri]]) {
      try { T.rSat = await imagery(url); T.satName = name; break; } catch (e) { /* try the next source */ }
    }
  }
}
function setSurface(kind) {
  document.querySelectorAll("[data-surface]").forEach(b => b.setAttribute("aria-pressed", b.dataset.surface === kind));
  const img = kind === "imagery";
  sculpt.material.map = (img && T.sPhoto) || T.sRelief;
  real.material.map = (img && T.rSat) || T.rRelief;
  [sculpt, real].forEach(m => m.material.needsUpdate = true);
  note.hidden = !(img && !T.rSat && !D.synthetic);
  note.textContent = "Satellite imagery could not be loaded here, so the real place shows shaded relief.";
}
document.querySelectorAll("[data-surface]").forEach(b => b.addEventListener("click", () => setSurface(b.dataset.surface)));

function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  renderer.setSize(w, h, false); camera.aspect = w / h;
  camera.position.setLength(w < 600 ? 2.6 : 1.95); camera.updateProjectionMatrix();
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
%%FONTS%%
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
%%CSS%%
.wrap { max-width: 1240px; margin: 0 auto; padding: 0 28px; }
.top { display: flex; justify-content: space-between; align-items: center; padding: 22px 0; gap: 16px; }
.top .btn { padding: 11px 16px; font-size: 15px; }
.input { display: flex; gap: 16px; align-items: flex-end; padding: 10px 0 30px; border-bottom: 1px solid var(--ink); flex-wrap: wrap; }
.input figure { margin: 0; }
.input img { width: 112px; height: 112px; object-fit: cover; border-radius: var(--radius-s); display: block; }
figcaption { font-size: 13px; color: var(--ink-3); margin-top: 6px; }
.input .when { margin-left: auto; color: var(--ink-3); font-size: 14px; }

.best { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); gap: 48px; align-items: center; padding: 46px 0 40px; }
.kicker { margin: 0 0 6px; color: var(--forest); font-weight: 600; font-size: 16px; }
.best h1 { font-size: clamp(34px, 4.4vw, 60px); line-height: 1.02; margin: 0 0 10px; letter-spacing: -0.01em; }
.coord { margin: 0 0 22px; color: var(--ink-3); font-size: 15px; }
.explain { color: var(--ink-2); font-size: 18px; margin: 0 0 22px; max-width: 30em; }
.explain b { color: var(--ink); font-weight: 600; }
.links { display: flex; gap: 20px; flex-wrap: wrap; font-weight: 500; }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.pair figure { margin: 0; }
.pair img { width: 100%; aspect-ratio: 1; display: block; border-radius: 3px; }

.three { padding: 10px 0 50px; }
.three-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 20px; flex-wrap: wrap; margin-bottom: 14px; }
.three-head h2 { font-size: 24px; font-weight: 700; letter-spacing: -0.015em; margin: 0 0 4px; }
.three-head p { margin: 0; color: var(--ink-3); }
.ctrl { display: flex; gap: 20px; align-items: center; flex-wrap: wrap; font-size: 14px; color: var(--ink-2); }
.seg { display: inline-flex; border: 1px solid var(--rule); border-radius: var(--radius-s); overflow: hidden; }
.seg button { font: 500 14px var(--sans); border: 0; background: var(--sheet); color: var(--ink-2); padding: 8px 14px; cursor: pointer; }
.seg button + button { border-left: 1px solid var(--rule); }
.seg button[aria-pressed="true"] { background: var(--ink); color: var(--paper); }
.ctrl label { display: flex; gap: 10px; align-items: center; }
.ctrl input[type=range] { accent-color: var(--glacier); width: 140px; }
.ctrl output { min-width: 3.2em; font-variant-numeric: tabular-nums; color: var(--ink); }
.stage { position: relative; height: 560px; background: var(--sheet); }
.stage canvas { position: absolute; inset: 3px; width: calc(100% - 6px) !important; height: calc(100% - 6px) !important; display: block; cursor: grab; touch-action: none; }
.stage canvas:active { cursor: grabbing; }
.stage .caps { position: absolute; left: 3px; right: 3px; bottom: 14px; display: grid; grid-template-columns: 1fr 1fr; pointer-events: none; }
.stage .caps span { text-align: center; font-size: 14px; color: var(--ink-2); }
.stage .caps .place { font-size: 17px; color: var(--ink); }
.stage .note { position: absolute; top: 14px; left: 16px; font-size: 13px; color: var(--ink-3); }
.stage .loading { position: absolute; inset: 0; display: grid; place-items: center; color: var(--ink-3); font-size: 15px; }
@media (max-width: 900px) { .stage { height: 420px; } .ctrl input[type=range] { width: 110px; } }

.map-wrap { margin: 6px 0 50px; }
#map { height: 520px; }
.leaflet-container { font: 13px var(--sans); background: var(--paper); }

.others h2 { font-size: 24px; font-weight: 700; letter-spacing: -0.015em; margin: 0 0 6px; }
.others > p { margin: 0 0 18px; color: var(--ink-3); }
.others[hidden] { display: none; }
ol.list { list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--rule); }
.row { display: grid; grid-template-columns: 34px 252px minmax(0, 1fr) 90px 120px auto; gap: 18px; align-items: center;
       padding: 14px 6px; border-bottom: 1px solid var(--rule); cursor: pointer; border-radius: 2px; }
.row:hover, .row.active { background: color-mix(in srgb, var(--glacier) 6%, transparent); }
.rank { color: var(--ink-3); font-weight: 600; }
.thumbs { display: flex; gap: 6px; }
.thumbs img { width: 120px; height: 120px; border-radius: 2px; display: block; }
.where .place { display: block; font-size: 21px; line-height: 1.2; }
.where .sub { display: block; font-size: 13.5px; color: var(--ink-3); margin-top: 3px; }
.stat { color: var(--ink-2); font-size: 15px; }
.go { display: flex; flex-direction: column; gap: 4px; font-size: 14px; }
.stat small { display: block; font-size: 12.5px; color: var(--ink-3); }
[hidden] { display: none !important; }

footer { border-top: 1px solid var(--rule); margin-top: 70px; }
footer .wrap { padding-top: 22px; padding-bottom: 36px; color: var(--ink-3); font-size: 14px; }

@media (max-width: 900px) {
  .wrap { padding: 0 16px; }
  .best { grid-template-columns: 1fr; gap: 26px; padding-top: 30px; }
  #map { height: 380px; }
  .row { grid-template-columns: 26px minmax(0, 1fr) auto; grid-template-areas: "r t t" "r w s"; row-gap: 10px; }
  .rank { grid-area: r; align-self: start; }
  .thumbs { grid-area: t; } .thumbs img { width: 96px; height: 96px; }
  .where { grid-area: w; } .stat:nth-of-type(1) { grid-area: s; } .stat + .stat, .go { display: none; }
}
</style></head>
<body>
<div class="wrap">
  <header class="top">
    <a class="mark" href="/" id="home">%%MARK%%Sand to Earth</a>
    <a class="btn" href="/" id="again">Try another photo</a>
  </header>
  <div class="input">
    %%PHOTO%%
    <figure><img src="%%QUERY%%" alt=""><figcaption>Read as terrain</figcaption></figure>
    <span class="when">%%WHEN%%</span>
  </div>
  %%BEST%%
  %%THREE%%
  %%MAP%%
  <section class="others" %%HAS_OTHERS%%>
    <h2>Other close matches</h2>
    <p>Select one to show it on the map.</p>
    <ol class="list">%%OTHERS%%</ol>
  </section>
</div>
<footer><div class="wrap">
  Imagery: Sentinel-2 cloudless 2016 by EOX IT Services GmbH, CC BY 4.0. Elevation: AWS Terrain Tiles.
  Place names: OpenStreetMap contributors via Nominatim.
</div></footer>
<script>
const synthetic = %%SYNTH%%, polys = %%POLYS%%, points = %%POINTS%%;
// When opened as a file (webcam mode), there is no app to go back to.
if (location.protocol === "file:") { document.getElementById("again").style.display = "none"; document.getElementById("home").removeAttribute("href"); }

let shapes = [], map = null;
if (!synthetic && window.L) {
  const css = getComputedStyle(document.documentElement);
  const best = css.getPropertyValue("--forest").trim(), other = "#ffffff", edge = css.getPropertyValue("--contour").trim();
  const s2 = L.tileLayer("%%S2%%", {maxZoom: 15, attribution: "%%S2ATTR%%"});
  const esri = L.tileLayer("%%ESRI%%", {maxZoom: 18, attribution: "Imagery © Esri"});
  const topo = L.tileLayer("%%TOPO%%", {maxZoom: 17, subdomains: "abc", attribution: "© OpenTopoMap (CC-BY-SA)"});
  map = L.map("map", {layers: [s2], worldCopyJump: true, scrollWheelZoom: false});
  L.control.layers({"Sentinel-2": s2, "Esri imagery": esri, "Topographic": topo}).addTo(map);
  L.control.scale({imperial: false}).addTo(map);
  shapes = polys.map((p, i) => {
    const poly = L.polygon(p, {color: i ? other : best, weight: i ? 1.5 : 3, fillOpacity: i ? .04 : .12, dashArray: i ? "4 4" : null})
      .bindTooltip(i ? "Match " + (i + 1) : "Best match").addTo(map);
    L.polyline([p[0], p[1]], {color: "#E3B23C", weight: 5, opacity: .95}).bindTooltip("Top edge of your sandbox").addTo(map);
    return poly;
  });
  map.fitBounds(shapes[0].getBounds().pad(1.4));
}
document.querySelectorAll(".row").forEach(row => {
  const pick = () => {
    document.querySelectorAll(".row").forEach(r => r.classList.remove("active")); row.classList.add("active");
    if (map) { map.fitBounds(shapes[+row.dataset.i].getBounds().pad(1.4)); document.getElementById("map").scrollIntoView({behavior: "smooth", block: "center"}); }
  };
  row.addEventListener("click", e => { if (e.target.tagName !== "A") pick(); });
  row.addEventListener("keydown", e => { if (e.key === "Enter") pick(); });
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
      if (name) document.querySelectorAll(`[data-geo="${i}"]`).forEach(el => {
        el.textContent = name;
        if (i === 0) document.title = name + " · Sand to Earth";
      });
      if (name) document.querySelectorAll(`[data-coord="${i}"]`).forEach(el => el.hidden = false);
    } catch (e) { /* keep the coordinates */ }
    await new Promise(res => setTimeout(res, 1100));
  }
})();
</script>
</body></html>
"""
