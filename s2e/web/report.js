// Builds the same results page as s2e/report.py, in the browser, from the search results.
import { render, renderToCanvas, rotate, zscore, resizeArea, gaussBlur, metersPerPx } from "./engine.js";

const COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"];
const coord = (lat, lon) => `${Math.abs(lat).toFixed(2)}° ${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(2)}° ${lon >= 0 ? "E" : "W"}`;
const facing = (b) => COMPASS[Math.floor((((b % 360) + 360) % 360 + 22.5) / 45) % 8];
const gz = (km) => Math.max(5, Math.min(13, Math.round(14.5 - Math.log2(Math.max(km, 1)))));
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const TREK = "https://trek.nasa.gov/tiles/Mars/EQ/";
const MARS_LAYERS = {
  "Viking colour": TREK + "Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
  "MOLA shaded relief": TREK + "Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
};

// Nearest named feature from the IAU Gazetteer: inside it if within its radius, otherwise "near" it.
function marsName(lat, lon, names) {
  if (!names) return null;
  const R = 3396.19, rad = Math.PI / 180;
  const dist = (a, b, c, d) => R * Math.acos(Math.min(1, Math.sin(a * rad) * Math.sin(c * rad) + Math.cos(a * rad) * Math.cos(c * rad) * Math.cos((b - d) * rad)));
  let inside = null, near = null;
  for (const [name, la, lo, diam, type] of names) {
    if (diam < 20) continue;                                  // skip small craters
    const d = dist(lat, lon, la, lo);
    if (d < diam / 2 && (!inside || diam < inside.diam)) inside = { name, diam, type };
    const score = d / Math.sqrt(diam);
    if (diam >= 80 && (!near || score < near.score)) near = { name, score, d };
  }
  if (inside) return inside.name;
  return near ? `Near ${near.name}` : null;
}

function marsLinks(r) {
  const z = Math.max(3, Math.min(9, Math.round(10 - Math.log2(Math.max(r.size_km, 1)))));
  return `<a class="more" href="https://www.google.com/mars/#lat=${r.lat.toFixed(3)}&lon=${r.lon.toFixed(3)}&zoom=${z}" target="_blank" rel="noopener">Open in Google Mars</a>` +
         `<a class="more" href="https://trek.nasa.gov/mars/" target="_blank" rel="noopener">NASA Mars Trek</a>`;
}

// Mars imagery for the 3D view: Trek tiles are equirectangular, the window is Web Mercator, so resample.
async function marsImagery(engine, r, size = 512) {
  const I = engine.info, n = 256 * 2 ** I.zoom;
  const lonlat = (u, v) => {
    const X = r.x + I.px0 + u / size * r.w, Y = r.y + I.py0 + v / size * r.w;
    return [X / n * 360 - 180, Math.atan(Math.sinh(Math.PI * (1 - 2 * Y / n))) * 180 / Math.PI];
  };
  const [lonA, latA] = lonlat(0, 0), [lonB, latB] = lonlat(size, size);
  const span = Math.max(lonB - lonA, 1e-3);
  const zt = Math.max(0, Math.min(7, Math.round(Math.log2(720 / span * size / 512 / 2))));
  const W = 256 * 2 ** (zt + 1), H = 256 * 2 ** zt;
  const px = (lon, lat) => [(lon + 180) / 360 * W, (90 - lat) / 180 * H];
  const [x0, y0] = px(lonA, latA), [x1, y1] = px(lonB, latB);
  const tx0 = Math.floor(x0 / 256), tx1 = Math.floor((x1 - 1) / 256), ty0 = Math.floor(y0 / 256), ty1 = Math.floor((y1 - 1) / 256);
  const cw = (tx1 - tx0 + 1) * 256, ch = (ty1 - ty0 + 1) * 256;
  const big = document.createElement("canvas"); big.width = cw; big.height = ch;
  const g = big.getContext("2d"), url = MARS_LAYERS["Viking colour"], jobs = [];
  for (let ty = ty0; ty <= ty1; ty++) for (let tx = tx0; tx <= tx1; tx++) {
    const nx = W / 256;
    jobs.push(new Promise((res, rej) => {
      const im = new Image(); im.crossOrigin = "anonymous";
      const t = setTimeout(() => rej(new Error("timeout")), 12000);
      im.onload = () => { clearTimeout(t); g.drawImage(im, (tx - tx0) * 256, (ty - ty0) * 256); res(); };
      im.onerror = () => { clearTimeout(t); rej(new Error("tile")); };
      im.src = url.replace("{z}", zt).replace("{y}", ty).replace("{x}", ((tx % nx) + nx) % nx);
    }));
  }
  await Promise.all(jobs);
  const src = g.getImageData(0, 0, cw, ch).data, out = document.createElement("canvas");
  out.width = out.height = size;
  const o = out.getContext("2d"), im = o.createImageData(size, size);
  for (let v = 0; v < size; v++) for (let u = 0; u < size; u++) {
    const [lon, lat] = lonlat(u + 0.5, v + 0.5), [sx, sy] = px(lon, lat);
    const X = Math.min(cw - 1, Math.max(0, Math.floor(sx - tx0 * 256))), Y = Math.min(ch - 1, Math.max(0, Math.floor(sy - ty0 * 256)));
    const i = (Y * cw + X) * 4, j = (v * size + u) * 4;
    im.data[j] = src[i]; im.data[j + 1] = src[i + 1]; im.data[j + 2] = src[i + 2]; im.data[j + 3] = 255;
  }
  o.putImageData(im, 0, 0);
  return out.toDataURL("image/jpeg", 0.88);
}

const MARS_MAP_JS = `
  const layers = ${JSON.stringify(MARS_LAYERS)};
  const base = {};
  for (const [k, u] of Object.entries(layers)) base[k] = L.tileLayer(u, {maxNativeZoom: k.startsWith("Viking") ? 7 : 6, maxZoom: 9, noWrap: true,
    attribution: "Mars: NASA/JPL/USGS (Viking MDIM 2.1), NASA/GSFC (MOLA), via NASA Mars Trek"});
  map = L.map("map", {crs: L.CRS.EPSG4326, layers: [base["Viking colour"]], scrollWheelZoom: false});
  L.control.layers(base).addTo(map);`;                       // no scale bar: Leaflet would measure it on an Earth-sized sphere

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

// Plain-language reasons the photo can't give a meaningful match (thresholds checked on test images).
export function photoWarnings(c) {
  if (!c) return [];
  const w = [];
  if (c.transparent > 0.05) w.push("Part of the image is transparent, which reads as a flat black floor.");
  if (c.checker > 0.05) w.push("It has a checkerboard background, the kind stock images use to show transparency, which reads as a flat floor with a grid on it.");
  if (c.contrast < 6) w.push("It is almost one flat colour, so there is no shape to read.");
  if (c.tilt > 0.8) w.push("Most of its depth is one big slope, as in a photo taken from the side or at a low angle.");
  if (c.flat > 0.45) w.push("A large part of it is flat and empty, like sky or a plain background.");
  return w;
}

export async function buildReport(engine, parts, { query, results, photo, home, checks = null }) {
  const mars = engine.info.body === "mars";
  engine.parts = parts;
  const qz = zscore(query);
  const rows = results.map((r, k) => {
    const i = k + 1, size = i === 1 ? 520 : 240, real = engine.patch(r.x, r.y, r.w), aligned = rotate(qz, 64, r.rotation_deg, r.flipped);
    return { i, coord: coord(r.lat, r.lon), km: Math.round(r.size_km), agree: Math.round(Math.max(r.ncc, 0) * 100),
             facing: facing(r.top_edge_bearing_deg), flipped: r.flipped, links: mars ? marsLinks(r) : links(r),
             mine: render(aligned, 64, size), real: render(real, 64, size) };
  });
  const best = rows[0], others = rows.slice(1);
  const warn = photoWarnings(checks);
  let hero = "", trio = "";
  if (best) {
    const a = best.agree, mirror = best.flipped ? " The match uses the mirror image of your photo." : "";
    // Tested on shapes that exist nowhere (random blobs, side-on silhouettes): they reach 85-95 % too.
    // So the number says how alike the shapes are, never that this is the place you made.
    const where = mars ? "on Mars" : "on Earth";
    const eyebrow = warn.length ? `Closest shape ${where}, but see the note below`
                  : a >= 70 ? `The most similar terrain ${where}` : `The closest terrain ${where}, a loose fit`;
    const fit = a >= 70 ? "a close fit" : a >= 45 ? "a rough fit" : "a loose fit";
    const note = warn.length ? `
      <div class="warnbox reveal"><p><strong>This photo probably isn't a top-down shot of sand.</strong> ${warn.join(" ")}
        So this place is just the nearest shape out of ${engine.info.count.toLocaleString("en")} and doesn't mean much.
        For a real result, shape sand in a tray and photograph it from straight above, in side light.</p></div>` : "";
    hero = `
  <section class="rhero dark">
    <div class="wrap">
      <p class="eyebrow reveal">${eyebrow}</p>
      <h1 class="place grad reveal" data-geo="0">${best.coord}</h1>
      <p class="coords num reveal" data-coord="0" hidden>${best.coord}</p>
      <p class="lede reveal">A stretch of terrain about <span class="w num">${best.km} km</span> across, ${fit}
        for your sculpture's shape (<span class="w num">${best.agree}%</span> shape similarity). On the map, the top edge of your sandbox
        faces <span class="w">${best.facing}</span>.${mirror}</p>
      <p class="caveat reveal">Similar shapes turn up all over a planet, so treat this as a look-alike, not proof it's the place you made.</p>${note}
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
        <p class="facts num">${o.km} km across, ${o.agree}% shape similarity</p>
        <div class="links">${o.links}</div>
      </li>`).join("");
  const scene = results.length ? sceneData(engine, query, results[0], photo) : null;
  if (scene && mars) {
    scene.s2 = scene.esri = null;
    try { scene.sat = await marsImagery(engine, results[0]); } catch (e) { scene.sat = null; }
  }
  const when = new Date().toLocaleString("en-GB", { day: "2-digit", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" }).replace(" at ", ", ");
  const json = JSON.stringify({ time: new Date().toISOString().slice(0, 19), synthetic: false, searched_in: "browser",
                                results, imagery_tile_url: parts.s2 }, null, 2);
  const download = `<a href="data:application/json;charset=utf-8,${encodeURIComponent(json)}" download="result.json" style="color:inherit;text-decoration:underline">result.json</a>`;
  const html = parts.template
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
  return mars ? marsPage(html, engine, results) : html;
}

function marsPage(html, engine, results) {
  // map: NASA Trek tiles in plate carree instead of Earth imagery in Web Mercator
  const a = html.indexOf('  const s2 = L.tileLayer('), b = html.indexOf('  shapes = polys.map(');
  if (a > 0 && b > a) html = html.slice(0, a) + MARS_MAP_JS + "\n" + html.slice(b);
  html = html.replace("Your sandbox, drawn to scale on Sentinel-2 imagery.", "Your sandbox, drawn to scale on Viking and MOLA maps of Mars.");
  // names: IAU Gazetteer instead of OpenStreetMap
  const labels = results.map((r) => marsName(r.lat, r.lon, engine.names));
  const n0 = html.indexOf("// Name the places"), n1 = html.indexOf("</script>", n0);
  if (n0 > 0) html = html.slice(0, n0) + `const labels = ${JSON.stringify(labels).replace(/</g, "\\u003c")};
labels.forEach((name, i) => { if (!name) return;
  document.querySelectorAll('[data-geo="' + i + '"]').forEach(el => { el.textContent = name; });
  document.querySelectorAll('[data-coord="' + i + '"]').forEach(el => el.hidden = false);
  if (i === 0) document.title = name + " · Sand to Planet · Mars"; });
` + html.slice(n1);
  return html.replace(/<footer class="foot">[\s\S]*?<\/footer>/, `<footer class="foot"><div class="wrap">
  <p>Mars elevation: MGS MOLA MEGDR (NASA/GSFC/PDS). Imagery: Viking MDIM 2.1 and MOLA shaded relief via NASA Mars Trek.
    Names: IAU Gazetteer of Planetary Nomenclature (USGS). 3D: three.js.</p>
</div></footer>`);
}
