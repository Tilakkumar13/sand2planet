// Builds the same results page as s2e/report.py, in the browser, from the search results.
import { render, renderToCanvas, rotate, zscore, resizeArea, gaussBlur, metersPerPx } from "./engine.js";

const COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"];
const coord = (lat, lon) => `${Math.abs(lat).toFixed(2)}° ${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(2)}° ${lon >= 0 ? "E" : "W"}`;
const facing = (b) => COMPASS[Math.floor((((b % 360) + 360) % 360 + 22.5) / 45) % 8];
const gz = (km) => Math.max(5, Math.min(13, Math.round(14.5 - Math.log2(Math.max(km, 1)))));
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function links(r) {
  const g = `https://www.google.com/maps/@${r.lat.toFixed(5)},${r.lon.toFixed(5)},${gz(r.size_km)}z/data=!3m1!1e3`;
  const e = `https://earth.google.com/web/@${r.lat.toFixed(5)},${r.lon.toFixed(5)},0a,${Math.round(r.size_km * 1400)}d,35y,0h,45t,0r`;
  return `<a class="more" href="${g}" target="_blank" rel="noopener">Satellite view</a>` +
         `<a class="more" href="${e}" target="_blank" rel="noopener">Open in Google Earth</a>`;
}

// photo canvas -> size x size JPEG, optionally mirrored and turned like terrain.rotate (BORDER_REFLECT)
function photoJpeg(photo, size, angle = 0, flip = false) {
  const c = document.createElement("canvas"); c.width = c.height = size;
  const ctx = c.getContext("2d");
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(photo, 0, 0, size, size);
  if (!angle && !flip) return c.toDataURL("image/jpeg", 0.88);
  const src = ctx.getImageData(0, 0, size, size).data, out = ctx.createImageData(size, size);
  const a = Math.cos(angle * Math.PI / 180), b = Math.sin(angle * Math.PI / 180), m = (size - 1) / 2;
  const R = (p) => { while (p < 0 || p >= size) p = p < 0 ? -p - 1 : 2 * size - p - 1; return p; };
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    let sx = a * (x - m) - b * (y - m) + m, sy = b * (x - m) + a * (y - m) + m;
    const x0 = Math.floor(sx), y0 = Math.floor(sy), fx = sx - x0, fy = sy - y0;
    const px = (xx, yy) => { let X = R(xx); if (flip) X = size - 1 - X; return (R(yy) * size + X) * 4; };
    const i00 = px(x0, y0), i10 = px(x0 + 1, y0), i01 = px(x0, y0 + 1), i11 = px(x0 + 1, y0 + 1), o = (y * size + x) * 4;
    for (let k = 0; k < 3; k++)
      out.data[o + k] = (src[i00 + k] * (1 - fx) + src[i10 + k] * fx) * (1 - fy) + (src[i01 + k] * (1 - fx) + src[i11 + k] * fx) * fy;
    out.data[o + 3] = 255;
  }
  ctx.putImageData(out, 0, 0);
  return c.toDataURL("image/jpeg", 0.88);
}

const K12 = (() => {                           // cv2.GaussianBlur(sigma=1.2) kernel, 11 taps
  const n = 11, k = new Float64Array(n); let s = 0;
  for (let i = 0; i < n; i++) { k[i] = Math.exp(-((i - 5) ** 2) / (2 * 1.44)); s += k[i]; }
  return k.map((v) => v / s);
})();
const reflect101 = (p, n) => { while (p < 0 || p >= n) p = p < 0 ? -p : 2 * n - p - 2; return p; };

function sceneData(engine, q, r, photo) {
  const raw = engine.rawPatch(r.x, r.y, r.w);
  const real = gaussBlur(resizeArea(raw, r.w, r.w, 128, 128), 128, 128, K12, reflect101);
  const sculpt = rotate(q, 64, r.rotation_deg, r.flipped);
  const I = engine.info;
  return {
    synthetic: false, km: r.size_km, zoom: I.zoom, gx: r.x + I.px0, gy: r.y + I.py0, w: r.w,
    real: { n: 128, h: Array.from(real, (v) => Math.round(v)) },
    sculpt: { n: 64, h: Array.from(sculpt, (v) => Math.round(v * 1e4) / 1e4) },
    realRelief: render(real, 128, 512, "image/jpeg"), sculptRelief: render(sculpt, 64, 512, "image/jpeg"),
    photo: photo ? photoJpeg(photo, 512, r.rotation_deg, r.flipped) : null,
    s2: engine.parts.s2, esri: engine.parts.esri,
  };
}

export function buildReport(engine, parts, { query, results, photo, home }) {
  engine.parts = parts;
  const qz = zscore(query);
  const rows = results.map((r, k) => {
    const i = k + 1, size = i === 1 ? 520 : 240, real = engine.patch(r.x, r.y, r.w), aligned = rotate(qz, 64, r.rotation_deg, r.flipped);
    return { i, coord: coord(r.lat, r.lon), km: Math.round(r.size_km), agree: Math.round(Math.max(r.ncc, 0) * 100),
             facing: facing(r.top_edge_bearing_deg), flipped: r.flipped, links: links(r),
             mine: render(aligned, 64, size), real: render(real, 64, size) };
  });
  const best = rows[0], others = rows.slice(1);
  let hero = "", trio = "";
  if (best) {
    const a = best.agree, mirror = best.flipped ? " The match uses the mirror image of your photo." : "";
    const [eyebrow, strength] = a >= 70 ? ["Your landscape exists in", "a strong match"]
      : a >= 45 ? ["Your landscape looks most like", "a fair match"] : ["The closest place, but a loose fit, is", "a loose match"];
    hero = `
  <section class="rhero dark">
    <div class="wrap">
      <p class="eyebrow reveal">${eyebrow}</p>
      <h1 class="place grad reveal" data-geo="0">${best.coord}</h1>
      <p class="coords num reveal" data-coord="0" hidden>${best.coord}</p>
      <p class="lede reveal">A stretch of terrain about <span class="w num">${best.km} km</span> across, ${strength}
        for your sculpture's shape (<span class="w num">${best.agree}%</span> agreement). On the map, the top edge of your sandbox
        faces <span class="w">${best.facing}</span>.${mirror}</p>
      <div class="links reveal">${best.links}</div>
    </div>
  </section>`;
    const photoFig = photo ? `<figure class="reveal"><img src="${photoJpeg(photo, 520)}" alt="Your photo">` +
      `<figcaption>Your photo</figcaption></figure><span class="arrow" aria-hidden="true"></span>` : "";
    trio = `
  <section class="trio dark">
    <div class="wide">
      <div class="row">
        ${photoFig}
        <figure class="reveal"><img src="${best.mine}" alt="Your sculpture read as terrain, turned to north"><figcaption>Read as terrain, turned to north</figcaption></figure>
        <span class="arrow" aria-hidden="true"></span>
        <figure class="reveal"><img src="${best.real}" alt="The matching real terrain"><figcaption>The real place</figcaption></figure>
      </div>
    </div>
  </section>`;
  }
  const cards = others.map((o) => `
      <li class="mcard" data-i="${o.i - 1}" tabindex="0">
        <div class="pics"><img src="${o.mine}" alt=""><img src="${o.real}" alt=""></div>
        <p class="rank num">No. ${o.i}</p>
        <h3 data-geo="${o.i - 1}">${o.coord}</h3>
        <p class="sub num" data-coord="${o.i - 1}" hidden>${o.coord}</p>
        <p class="facts num">${o.km} km across, ${o.agree}% shape match</p>
        <div class="links">${o.links}</div>
      </li>`).join("");
  const scene = results.length ? sceneData(engine, query, results[0], photo) : null;
  const when = new Date().toLocaleString("en-GB", { day: "2-digit", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" }).replace(" at ", ", ");
  const json = JSON.stringify({ time: new Date().toISOString().slice(0, 19), synthetic: false, searched_in: "browser",
                                results, imagery_tile_url: parts.s2 }, null, 2);
  const download = `<a href="data:application/json;charset=utf-8,${encodeURIComponent(json)}" download="result.json" style="color:inherit;text-decoration:underline">result.json</a>`;
  return parts.template
    .replace("%%HERO%%", () => hero).replace("%%TRIO%%", () => trio)
    .replace("%%THREE%%", () => (scene ? parts.three : ""))
    .replace("%%SCENE%%", () => (scene ? JSON.stringify(scene).replace(/<\//g, "<\\/") : "null"))
    .replace("%%MAP%%", () => parts.map).replace("%%OTHERS%%", () => cards)
    .replace("%%HAS_OTHERS%%", others.length ? "" : "hidden")
    .replace("%%WHEN%%", esc(when))
    .replace("Each result is also saved as result.json for TouchDesigner.",
             () => `Searched entirely in your browser: your photo was never uploaded. Coordinates and rotation for TouchDesigner: ${download}.`)
    .replace("%%POLYS%%", () => JSON.stringify(results.map((r) => r.corners_lonlat.map((c) => [c[1], c[0]]))))
    .replace("%%POINTS%%", () => JSON.stringify(results.map((r) => [r.lat, r.lon])))
    .replace("%%SYNTH%%", "false")
    .replaceAll('href="/#try"', `href="${home}#try"`).replaceAll('href="/"', `href="${home}"`);
}
