// Sand to Planet search engine for the browser.
// A line-by-line port of s2e/depth.py, s2e/terrain.py and Index.search in s2e/index.py,
// running on the files written by s2e/webpack.py. Nothing is uploaded: the photo, the depth
// model and the search all stay in this browser tab.

export const TRANSFORMERS = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1";
const ORT = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.22.0-dev.20250409-89f8206ba4/dist/ort.webgpu.min.mjs";
const DEPTH_MODEL = "onnx-community/depth-anything-v2-small";
const DEPTH = { ready: null, pipe: null, T: null, listeners: new Set() };

const P = 64, N_RINGS = 16, N_ANG = 64, N_HARM = 8, NBINS = 16;
const C = (P - 1) / 2, R_MAX = P / 2 - 1;
const TILE_PX = 256, EARTH_CIRC = 40075016.686;

// ------------------------------------------------------------------ geometry helpers
export const MASK = new Uint8Array(P * P);
const MASK_IDX = [];
for (let y = 0; y < P; y++) for (let x = 0; x < P; x++) {
  if ((x - C) ** 2 + (y - C) ** 2 <= (P / 2 - 0.5) ** 2) { MASK[y * P + x] = 1; MASK_IDX.push(y * P + x); }
}
const NM = MASK_IDX.length;

const POLAR = (() => {
  const n = N_RINGS * N_ANG, i00 = new Int32Array(n), w = new Float32Array(n * 4);
  for (let r = 0; r < N_RINGS; r++) {
    const rad = 2 + (R_MAX - 2) * r / (N_RINGS - 1);
    for (let a = 0; a < N_ANG; a++) {
      const ang = 2 * Math.PI * a / N_ANG, xs = C + rad * Math.cos(ang), ys = C + rad * Math.sin(ang);
      const x0 = Math.floor(xs), y0 = Math.floor(ys), fx = xs - x0, fy = ys - y0, k = r * N_ANG + a;
      i00[k] = y0 * P + x0;
      w[4 * k] = (1 - fx) * (1 - fy); w[4 * k + 1] = fx * (1 - fy); w[4 * k + 2] = (1 - fx) * fy; w[4 * k + 3] = fx * fy;
    }
  }
  return { i00, w };
})();

export function pxToLonLat(x, y, z) {
  const n = TILE_PX * 2 ** z;
  return [x / n * 360 - 180, Math.atan(Math.sinh(Math.PI * (1 - 2 * y / n))) * 180 / Math.PI];
}
export const metersPerPx = (lat, z, circ = EARTH_CIRC) => circ * Math.cos(lat * Math.PI / 180) / (TILE_PX * 2 ** z);

function reflect(p, n) {                       // OpenCV BORDER_REFLECT: fedcba|abcdefgh|hgfedcb
  if (n === 1) return 0;
  while (p < 0 || p >= n) p = p < 0 ? -p - 1 : 2 * n - p - 1;
  return p;
}
function reflect101(p, n) {                    // OpenCV BORDER_REFLECT_101: gfedcb|abcdefgh|gfedcba
  if (n === 1) return 0;
  while (p < 0 || p >= n) p = p < 0 ? -p : 2 * n - p - 2;
  return p;
}

// cv2.resize(..., INTER_AREA) when shrinking: exact box filter, separable.
function areaTab(ssize, dsize) {
  const scale = ssize / dsize, tab = [];
  for (let dx = 0; dx < dsize; dx++) {
    const fsx1 = dx * scale, fsx2 = fsx1 + scale;
    let sx1 = Math.ceil(fsx1), sx2 = Math.floor(fsx2);
    sx2 = Math.min(sx2, ssize - 1); sx1 = Math.min(sx1, sx2);
    const cell = Math.min(scale, ssize - fsx1), row = [];
    if (sx1 - fsx1 > 1e-3) row.push(sx1 - 1, (sx1 - fsx1) / cell);
    for (let sx = sx1; sx < sx2; sx++) row.push(sx, 1 / cell);
    if (fsx2 - sx2 > 1e-3) row.push(sx2, Math.min(Math.min(fsx2 - sx2, 1), cell) / cell);
    tab.push(row);
  }
  return tab;
}
const _tabs = new Map();
function tabFor(s, d) { const k = s * 4096 + d; if (!_tabs.has(k)) _tabs.set(k, areaTab(s, d)); return _tabs.get(k); }

export function resizeArea(src, sw, sh, dw, dh) {
  if (sw === dw && sh === dh) return Float32Array.from(src);
  const tx = tabFor(sw, dw), ty = tabFor(sh, dh), tmp = new Float32Array(sh * dw), out = new Float32Array(dw * dh);
  for (let y = 0; y < sh; y++) {
    const o = y * sw;
    for (let x = 0; x < dw; x++) { const t = tx[x]; let s = 0; for (let k = 0; k < t.length; k += 2) s += src[o + t[k]] * t[k + 1]; tmp[y * dw + x] = s; }
  }
  for (let y = 0; y < dh; y++) {
    const t = ty[y];
    for (let x = 0; x < dw; x++) { let s = 0; for (let k = 0; k < t.length; k += 2) s += tmp[t[k] * dw + x] * t[k + 1]; out[y * dw + x] = s; }
  }
  return out;
}

function gaussKernel(sigma) {
  const n = Math.round(sigma * 4 * 2 + 1) | 1, k = new Float64Array(n), h = (n - 1) / 2;
  let s = 0;
  for (let i = 0; i < n; i++) { k[i] = Math.exp(-((i - h) ** 2) / (2 * sigma * sigma)); s += k[i]; }
  for (let i = 0; i < n; i++) k[i] /= s;
  return k;
}
const K1 = gaussKernel(1.0);
export function gaussBlur(src, w, h, kernel = K1, border = reflect) {
  const r = (kernel.length - 1) / 2, tmp = new Float32Array(w * h), out = new Float32Array(w * h);
  const bx = new Int32Array(w + 2 * r), by = new Int32Array(h + 2 * r);
  for (let i = -r; i < w + r; i++) bx[i + r] = border(i, w);
  for (let i = -r; i < h + r; i++) by[i + r] = border(i, h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    let s = 0; for (let k = 0; k < kernel.length; k++) s += src[y * w + bx[x + k]] * kernel[k]; tmp[y * w + x] = s;
  }
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    let s = 0; for (let k = 0; k < kernel.length; k++) s += tmp[by[y + k] * w + x] * kernel[k]; out[y * w + x] = s;
  }
  return out;
}

// terrain.prep: any square height map -> smoothed 64x64
export function prep(h, n) { return gaussBlur(n === P ? h : resizeArea(h, n, n, P, P), P, P); }

export function zscore(p) {
  let mu = 0; for (const i of MASK_IDX) mu += p[i]; mu /= NM;
  let v = 0; for (const i of MASK_IDX) v += (p[i] - mu) ** 2;
  const sd = Math.sqrt(v / NM) + 1e-6, out = new Float32Array(p.length);
  for (let i = 0; i < p.length; i++) out[i] = (p[i] - mu) / sd;
  return out;
}

function grad(f, w, h, axis) {                 // numpy.gradient along rows (axis 0) or columns (axis 1)
  const g = new Float32Array(w * h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = y * w + x;
    if (axis === 1) g[i] = x === 0 ? f[i + 1] - f[i] : x === w - 1 ? f[i] - f[i - 1] : (f[i + 1] - f[i - 1]) / 2;
    else g[i] = y === 0 ? f[i + w] - f[i] : y === h - 1 ? f[i] - f[i - w] : (f[i + w] - f[i - w]) / 2;
  }
  return g;
}

function hist(vals, lo, hi) {
  const h = new Float32Array(NBINS), k = NBINS / (hi - lo);
  for (const v of vals) { let b = Math.trunc((v - lo) * k); b = b < 0 ? 0 : b > NBINS - 1 ? NBINS - 1 : b; h[b]++; }
  for (let i = 0; i < NBINS; i++) h[i] = Math.sqrt(h[i] / vals.length);
  return h;
}
function l2(a, wgt = 1) {
  let s = 0; for (const v of a) s += v * v; s = Math.sqrt(s) + 1e-9;
  for (let i = 0; i < a.length; i++) a[i] = a[i] / s * wgt;
  return a;
}

// terrain.describe: z-scored 64x64 -> 176-d rotation-invariant descriptor
const COSK = [], SINK = [];
for (let k = 0; k < N_HARM; k++) {
  COSK.push(Float64Array.from({ length: N_ANG }, (_, n) => Math.cos(2 * Math.PI * k * n / N_ANG)));
  SINK.push(Float64Array.from({ length: N_ANG }, (_, n) => Math.sin(2 * Math.PI * k * n / N_ANG)));
}
export function describe(z) {
  const polar = new Float32Array(N_RINGS * N_ANG), { i00, w } = POLAR;
  for (let k = 0; k < polar.length; k++) {
    const i = i00[k];
    polar[k] = z[i] * w[4 * k] + z[i + 1] * w[4 * k + 1] + z[i + P] * w[4 * k + 2] + z[i + P + 1] * w[4 * k + 3];
  }
  const rings = new Float32Array(N_RINGS * N_HARM);
  for (let r = 0; r < N_RINGS; r++) {
    const o = r * N_ANG;
    let mean = 0; for (let n = 0; n < N_ANG; n++) mean += polar[o + n];
    rings[r * N_HARM] = mean / N_ANG;
    for (let k = 1; k < N_HARM; k++) {
      let re = 0, im = 0;
      for (let n = 0; n < N_ANG; n++) { re += polar[o + n] * COSK[k][n]; im -= polar[o + n] * SINK[k][n]; }
      rings[r * N_HARM + k] = Math.hypot(re, im) / N_ANG;
    }
  }
  const gy = grad(z, P, P, 0), gx = grad(z, P, P, 1);
  const cx = grad(gx, P, P, 1), cy = grad(gy, P, P, 0);
  const slope = new Float32Array(NM), curv = new Float32Array(NM), hyps = new Float32Array(NM);
  MASK_IDX.forEach((i, j) => { slope[j] = Math.hypot(gx[i], gy[i]); curv[j] = cx[i] + cy[i]; hyps[j] = z[i]; });
  const parts = [l2(rings, 1.0), l2(hist(hyps, -2.5, 2.5), 0.6), l2(hist(slope, 0, 0.45), 0.5), l2(hist(curv, -0.06, 0.06), 0.4)];
  const out = new Float32Array(176); let o = 0;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return l2(out);
}

// terrain.rotate: counter-clockwise about the centre, like cv2.warpAffine (bilinear, BORDER_REFLECT)
export function rotate(img, n, angleDeg, flip = false) {
  const src = flip ? flipH(img, n) : img, out = new Float32Array(n * n);
  const a = Math.cos(angleDeg * Math.PI / 180), b = Math.sin(angleDeg * Math.PI / 180), c = (n - 1) / 2;
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
    const sx = a * (x - c) - b * (y - c) + c, sy = b * (x - c) + a * (y - c) + c;
    const X = Math.round(sx * 32), Y = Math.round(sy * 32);          // OpenCV's 1/32-pixel tables
    const x0 = X >> 5, y0 = Y >> 5, fx = (X & 31) / 32, fy = (Y & 31) / 32;
    const xa = reflect(x0, n), xb = reflect(x0 + 1, n), ya = reflect(y0, n), yb = reflect(y0 + 1, n);
    out[y * n + x] = (src[ya * n + xa] * (1 - fx) + src[ya * n + xb] * fx) * (1 - fy) + (src[yb * n + xa] * (1 - fx) + src[yb * n + xb] * fx) * fy;
  }
  return out;
}
function flipH(img, n) {
  const o = new Float32Array(n * n);
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) o[y * n + x] = img[y * n + n - 1 - x];
  return o;
}

function maskedUnit(p) {
  const v = new Float32Array(NM); let m = 0;
  for (let j = 0; j < NM; j++) { v[j] = p[MASK_IDX[j]]; m += v[j]; }
  m /= NM; let s = 0;
  for (let j = 0; j < NM; j++) { v[j] -= m; s += v[j] * v[j]; }
  s = Math.sqrt(s) + 1e-9; for (let j = 0; j < NM; j++) v[j] /= s;
  return v;
}

function rot90(z, k) {                         // numpy/torch rot90 (counter-clockwise), k times
  let a = z;
  for (let t = 0; t < k; t++) { const o = new Float32Array(P * P); for (let i = 0; i < P; i++) for (let j = 0; j < P; j++) o[i * P + j] = a[j * P + P - 1 - i]; a = o; }
  return a;
}

// depth.to_heightmap
function percentile(sorted, q) {
  const pos = q / 100 * (sorted.length - 1), lo = Math.floor(pos), f = pos - lo;
  return lo + 1 < sorted.length ? sorted[lo] * (1 - f) + sorted[lo + 1] * f : sorted[lo];
}
export function toHeightmap(depth, w, h, invert = false, size = 128) {
  const d = new Float64Array(w * h);
  for (let i = 0; i < d.length; i++) d[i] = invert ? -depth[i] : depth[i];
  const s = Float64Array.from(d).sort(), lo = percentile(s, 1), hi = percentile(s, 99);
  // remove the camera-tilt plane: least squares on [1, x, y]
  let n = 0, sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0, sz = 0, sxz = 0, syz = 0;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const v = Math.min(Math.max(d[y * w + x], lo), hi), X = x / w - 0.5, Y = y / h - 0.5;
    d[y * w + x] = v; n++; sx += X; sy += Y; sxx += X * X; syy += Y * Y; sxy += X * Y; sz += v; sxz += X * v; syz += Y * v;
  }
  const [c0, c1, c2] = solve3([[n, sx, sy], [sx, sxx, sxy], [sy, sxy, syy]], [sz, sxz, syz]);
  const f = new Float32Array(w * h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) f[y * w + x] = d[y * w + x] - (c0 + c1 * (x / w - 0.5) + c2 * (y / h - 0.5));
  const r = resizeArea(f, w, h, size, size);
  let mn = Infinity, mx = -Infinity; for (const v of r) { if (v < mn) mn = v; if (v > mx) mx = v; }
  for (let i = 0; i < r.length; i++) r[i] = (r[i] - mn) / (mx - mn + 1e-9);
  return r;
}
function solve3(A, b) {
  const M = A.map((r, i) => [...r, b[i]]);
  for (let c = 0; c < 3; c++) {
    let p = c; for (let r = c + 1; r < 3; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    [M[c], M[p]] = [M[p], M[c]];
    for (let r = 0; r < 3; r++) if (r !== c) { const f = M[r][c] / M[c][c]; for (let k = c; k < 4; k++) M[r][k] -= f * M[c][k]; }
  }
  return [M[0][3] / M[0][0], M[1][3] / M[1][1], M[2][3] / M[2][2]];
}

// ------------------------------------------------------------------ data loading
async function fetchBytes(url, onBytes) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Could not load ${url.split("/").pop()} (${r.status}).`);
  const total = +r.headers.get("Content-Length") || 0, reader = r.body.getReader(), parts = [];
  let got = 0;
  for (;;) { const { done, value } = await reader.read(); if (done) break; parts.push(value); got += value.length; onBytes && onBytes(value.length, total); }
  const out = new Uint8Array(got); let o = 0; for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
}
async function gunzip(bytes) {
  if (bytes[0] !== 0x1f || bytes[1] !== 0x8b) return bytes;   // server already decoded it
  const s = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
  return new Uint8Array(await new Response(s).arrayBuffer());
}

export class Engine {
  constructor(base, opts = {}) { this.base = base.replace(/\/?$/, "/"); this.opts = opts; this.ready = null; this.depthReady = null; }

  // Downloads are shared by both callers; progress is reported in bytes across all files.
  load(onProgress = () => {}) {
    if (this.ready) return this.ready;
    this.ready = (async () => {
      const info = this.info = await (await fetch(this.base + "index.json")).json();
      const ort = this.ort = this.opts.ort || await import(ORT);
      if (!this.opts.ort) ort.env.wasm.wasmPaths = `${TRANSFORMERS}/dist/`;   // same wasm file as the depth model: downloaded once
      ort.env.wasm.numThreads = 1;
      const tick = (n) => onProgress("index", n);
      const [meta, emb, mos, onnx] = await Promise.all([
        fetchBytes(this.base + "meta.bin.gz", tick).then(gunzip),
        fetchBytes(this.base + "emb.bin", tick),
        fetchBytes(this.base + "mosaic.bin.gz", tick).then(gunzip),
        fetchBytes(new URL(info.matcher || "matcher.onnx", new URL(this.base, globalThis.location?.href)).href, tick),
      ]);
      this.names = info.names ? await (await fetch(this.base + info.names)).json() : null;
      this.meta = new Int32Array(meta.buffer, meta.byteOffset, meta.byteLength / 4);
      const N = info.count, D = info.dim;
      this.emb = new Int8Array(emb.buffer, emb.byteOffset, N * D);
      this.embScale = new Float32Array(emb.buffer.slice(emb.byteOffset + N * D, emb.byteOffset + N * D + 4 * N));
      this.decodeMosaic(mos);
      this.session = await ort.InferenceSession.create(onnx, { executionProviders: ["wasm"] });
    })();
    this.ready.catch(() => { this.ready = null; });
    return this.ready;
  }

  decodeMosaic(res) {                          // undo the MED predictor, tile by tile
    const T = this.info.tile, nt = this.info.tiles.length, ntx = Math.ceil(this.info.W / T);
    this.tiles = new Uint8Array(nt * T * T);
    this.tileLo = new Float32Array(nt); this.tileScale = new Float32Array(nt);
    this.tileOf = new Int32Array(Math.ceil(this.info.H / T) * ntx).fill(-1);
    this.ntx = ntx;
    this.info.tiles.forEach(([ty, tx, lo, sc], k) => {
      this.tileOf[ty * ntx + tx] = k; this.tileLo[k] = lo; this.tileScale[k] = sc;
      const o = k * T * T;
      for (let y = 0; y < T; y++) for (let x = 0; x < T; x++) {
        const i = o + y * T + x;
        const a = x > 0 ? this.tiles[i - 1] : 0, b = y > 0 ? this.tiles[i - T] : 0, c = x > 0 && y > 0 ? this.tiles[i - T - 1] : 0;
        const hi = a > b ? a : b, lo = a < b ? a : b;
        const p = c >= hi ? lo : c <= lo ? hi : a + b - c;
        this.tiles[i] = (res[i] + p) & 255;
      }
    });
  }

  rawPatch(x, y, w) {                          // Index.raw_patch from the 8-bit tiles, in metres
    const T = this.info.tile, out = new Float32Array(w * w);
    for (let yy = 0; yy < w; yy++) {
      const gy = y + yy, ty = (gy / T) | 0, oy = gy - ty * T;
      for (let xx = 0; xx < w;) {
        const gx = x + xx, tx = (gx / T) | 0, ox = gx - tx * T;
        const k = gx >= this.info.W || gy >= this.info.H || gy < 0 ? -1 : this.tileOf[ty * this.ntx + tx];
        const run = Math.min(T - ox, w - xx);
        if (k < 0) { xx += run; continue; }
        const lo = this.tileLo[k], sc = this.tileScale[k], base = k * T * T + oy * T + ox, o = yy * w + xx;
        for (let i = 0; i < run; i++) out[o + i] = lo + this.tiles[base + i] * sc;
        xx += run;
      }
    }
    return out;
  }
  patch(x, y, w) { return prep(this.rawPatch(x, y, w), w); }
  geo(cx, cy) { return pxToLonLat(cx + this.info.px0, cy + this.info.py0, this.info.zoom); }

  // ---------------------------------------------------------------- depth
  // One depth model per page, shared by every planet's engine.
  loadDepth(onProgress = () => {}) {
    if (!DEPTH.ready) {
      DEPTH.ready = (async () => {
        DEPTH.T = await import(TRANSFORMERS);
        DEPTH.T.env.allowLocalModels = false;
        const seen = new Map();
        DEPTH.pipe = await DEPTH.T.pipeline("depth-estimation", DEPTH_MODEL, {
          dtype: "q8", device: "wasm",
          progress_callback: (p) => {
            if (p.status !== "progress" || !p.total) return;
            const prev = seen.get(p.file) || 0; seen.set(p.file, p.loaded);
            DEPTH.listeners.forEach((f) => f("depth", p.loaded - prev, p.total, p.file));
          },
        });
      })();
      DEPTH.ready.catch(() => { DEPTH.ready = null; });
    }
    DEPTH.listeners.add(onProgress);
    return DEPTH.ready.then(() => { this.T = DEPTH.T; this.depth = DEPTH.pipe; }).finally(() => DEPTH.listeners.delete(onProgress));
  }

  // photo (square canvas) -> 128x128 height map in 0..1
  async heightFromCanvas(canvas, invert = false) {
    await this.loadDepth();
    const ctx = canvas.getContext("2d"), { width: w, height: h } = canvas, px = ctx.getImageData(0, 0, w, h).data;
    const rgb = new Uint8ClampedArray(w * h * 3);
    for (let i = 0, j = 0; i < px.length; i += 4, j += 3) { rgb[j] = px[i]; rgb[j + 1] = px[i + 1]; rgb[j + 2] = px[i + 2]; }
    const out = await this.depth(new this.T.RawImage(rgb, w, h, 3));
    const t = out.predicted_depth, dims = t.dims.slice(-2);
    return toHeightmap(t.data, dims[1], dims[0], invert);
  }

  // ---------------------------------------------------------------- search (Index.search)
  async embed(qz) {
    const x = new Float32Array(4 * P * P);
    for (let k = 0; k < 4; k++) x.set(rot90(qz, k), k * P * P);
    const r = await this.session.run({ z: new this.ort.Tensor("float32", x, [4, 1, P, P]) });
    const D = this.info.dim, e = new Float32Array(D);
    for (let k = 0; k < 4; k++) for (let d = 0; d < D; d++) e[d] += r.e.data[k * D + d];
    return l2(e);
  }

  async search(height, { k = 5, allowFlip = false, onStage = () => {} } = {}) {
    const info = this.info, N = info.count, D = info.dim, wts = info.weights;
    const q = prep(height, 128), qz = zscore(q);
    const e = await this.embed(qz);
    const eSim = new Float32Array(N);
    for (let i = 0; i < N; i++) { let s = 0; const o = i * D; for (let d = 0; d < D; d++) s += this.emb[o + d] * e[d]; eSim[i] = s * this.embScale[i]; }
    const sl = Math.min(info.shortlist, N);
    const pool = topK(eSim, sl);
    onStage(2);
    await new Promise((r) => setTimeout(r, 0));

    const qd = describe(qz);
    const variants = [];
    for (const fl of allowFlip ? [false, true] : [false])
      for (let a = 0; a < 360; a += info.rot_step) variants.push({ a, fl, v: maskedUnit(rotate(qz, P, a, fl)) });
    const scored = [];
    let n = 0;
    for (const i of pool) {
      if (++n % 200 === 0) await new Promise((r) => setTimeout(r, 0));     // keep the page responsive
      const x = this.meta[4 * i], y = this.meta[4 * i + 1], w = this.meta[4 * i + 2];
      const cz = zscore(this.patch(x, y, w)), cd = describe(cz), cu = maskedUnit(cz);
      let dp = 0; for (let j = 0; j < 176; j++) dp += cd[j] * qd[j];
      let best = -Infinity, bv = null;
      for (const v of variants) { let s = 0; const vv = v.v; for (let j = 0; j < NM; j++) s += cu[j] * vv[j]; if (s > best) { best = s; bv = v; } }
      const first = wts.emb * eSim[i] + wts.desc * dp;
      scored.push({ i, first, score: first + wts.ncc * best, ncc: best, desc: dp, angle: bv.a, flipped: bv.fl });
    }
    scored.sort((a, b) => b.score - a.score);
    onStage(3);
    await this.refit(qz, e, qd, scored.slice(0, info.refit || 60), info.rot_step);
    scored.sort((a, b) => b.score - a.score);
    const results = [], kept = [];
    for (const s of scored) {
      const f = this.meta[4 * s.i + 3];
      const [x, y, w] = s.geom || [this.meta[4 * s.i], this.meta[4 * s.i + 1], this.meta[4 * s.i + 2]];
      const cx = x + w / 2, cy = y + w / 2;
      if (kept.some(([kx, ky, kw]) => Math.hypot(cx - kx, cy - ky) < 0.6 * Math.max(w, kw))) continue;
      kept.push([cx, cy, w]);
      results.push(this.result(x, y, w, f, s));
      if (results.length === k) break;
    }
    return { query: q, results };
  }

  // Index.search's refit: the index is a grid (every 1/4 window, sizes that double) but a sandbox can sit
  // anywhere at any size, so the best candidates are slid by up to 1/4 window, resized by up to sqrt(2)
  // and turned a little; refitted windows are then scored again by the matcher.
  async refit(qz, qe, qd, top, step) {
    const H = this.info.H, W = this.info.W, re = [];
    let n = 0;
    for (const s of top) {
      if (++n % 10 === 0) await new Promise((r) => setTimeout(r, 0));
      const x = this.meta[4 * s.i], y = this.meta[4 * s.i + 1], w = this.meta[4 * s.i + 2], cx = x + w / 2, cy = y + w / 2;
      // read the neighbourhood once, at no more than 128 px per window
      const half = Math.ceil(w * (0.25 + 0.71) + 2), rx = Math.max(0, Math.round(cx - half)), ry = Math.max(0, Math.round(cy - half));
      const rw = Math.min(W - rx, 2 * half), rh = Math.min(H - ry, 2 * half);
      if (rw < w || rh < w) continue;
      const k = Math.max(1, w / 128), lw = Math.max(1, Math.round(rw / k)), lh = Math.max(1, Math.round(rh / k));
      const raw = this.rawPatch(rx, ry, Math.max(rw, rh)), side = Math.max(rw, rh);
      const reg = k > 1 ? resizeArea(raw, side, side, Math.round(side / k), Math.round(side / k)) : raw, rs = k > 1 ? Math.round(side / k) : side;
      const q0 = maskedUnit(rotate(qz, P, s.angle, s.flipped));
      let best = -Infinity, bb = null, bu = null, bz = null, bsh = null;
      const tryBoxes = (ccx, ccy, shifts, scales) => {
        for (const sc of scales) {
          const ws = Math.round(w * sc);
          for (const dy of shifts) for (const dx of shifts) {
            const nx = Math.round(ccx + dx * w - ws / 2), ny = Math.round(ccy + dy * w - ws / 2);
            if (nx < 0 || ny < 0 || nx + ws > W || ny + ws > H) continue;
            const ox = Math.round((nx - rx) / k), oy = Math.round((ny - ry) / k), ow = Math.max(8, Math.round(ws / k));
            if (ox < 0 || oy < 0 || ox + ow > rs || oy + ow > rs) continue;
            const sub = new Float32Array(ow * ow);
            for (let yy = 0; yy < ow; yy++) sub.set(reg.subarray((oy + yy) * rs + ox, (oy + yy) * rs + ox + ow), yy * ow);
            const cz = zscore(prep(sub, ow)), cu = maskedUnit(cz);
            let v = 0; for (let j = 0; j < NM; j++) v += cu[j] * q0[j];
            if (v > best) { best = v; bb = [nx, ny, ws]; bu = cu; bz = cz; bsh = [ccx + dx * w, ccy + dy * w, sc]; }
          }
        }
      };
      // coarse to fine, like Index._refine: 27 windows, then 27 around the best, then the angle
      tryBoxes(cx, cy, [-0.25, 0, 0.25], [0.71, 1, 1.41]);
      if (bsh) { const [bx, by, bs] = bsh; tryBoxes(bx, by, [-0.125, 0, 0.125], [bs / 1.19, bs, bs * 1.19]); }
      if (!bb) continue;
      let ba = s.angle;
      for (const da of [-2 * step, -step, step, 2 * step]) {
        const a = ((s.angle + da) % 360 + 360) % 360, qu = maskedUnit(rotate(qz, P, a, s.flipped));
        let v = 0; for (let j = 0; j < NM; j++) v += bu[j] * qu[j];
        if (v > best) { best = v; ba = a; }
      }
      if (best > s.ncc) { s.ncc = best; s.angle = ba; s.geom = bb; s.z = bz; re.push(s); }
    }
    if (re.length) {                                   // matcher scores for the refitted windows
      const x = new Float32Array(re.length * 4 * P * P);
      re.forEach((s, j) => { for (let r = 0; r < 4; r++) x.set(rot90(s.z, r), (j * 4 + r) * P * P); });
      const out = await this.session.run({ z: new this.ort.Tensor("float32", x, [re.length * 4, 1, P, P]) });
      const D = this.info.dim, wts = this.info.weights;
      re.forEach((s, j) => {
        const e = new Float32Array(D);
        for (let r = 0; r < 4; r++) for (let d = 0; d < D; d++) e[d] += out.e.data[(j * 4 + r) * D + d];
        l2(e);
        let ev = 0; for (let d = 0; d < D; d++) ev += e[d] * qe[d];
        const cd = describe(s.z); let dv = 0; for (let t = 0; t < 176; t++) dv += cd[t] * qd[t];
        s.first = Math.max(s.first, wts.emb * ev + wts.desc * dv);
        delete s.z;
      });
    }
    for (const s of top) s.score = s.first + this.info.weights.ncc * s.ncc;
  }

  result(x, y, w, f, s) {
    const cx = x + w / 2, cy = y + w / 2, [lon, lat] = this.geo(cx, cy);
    const km = w * metersPerPx(lat, this.info.zoom, this.info.circ) / 1000, a = s.angle * Math.PI / 180, corners = [];
    for (const [dx, dy] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
      let ox = dx * w / 2, oy = dy * w / 2; if (s.flipped) ox = -ox;
      const rx = ox * Math.cos(a) + oy * Math.sin(a), ry = -ox * Math.sin(a) + oy * Math.cos(a);
      corners.push(this.geo(cx + rx, cy + ry));
    }
    return { lon, lat, x, y, w, level: f, size_km: km, score: s.score, ncc: s.ncc, desc_sim: s.desc,
             rotation_deg: s.angle, flipped: s.flipped, top_edge_bearing_deg: (360 - s.angle) % 360,
             matcher: "learned", body: this.info.body || "earth", corners_lonlat: corners };
  }
}

function topK(arr, k) {                        // indices of the k largest values
  const idx = Uint32Array.from({ length: arr.length }, (_, i) => i);
  // quickselect on a copy of the scores
  const v = Float32Array.from(arr);
  let lo = 0, hi = v.length - 1;
  while (lo < hi) {
    const pivot = v[(lo + hi) >> 1]; let i = lo, j = hi;
    while (i <= j) {
      while (v[i] > pivot) i++;
      while (v[j] < pivot) j--;
      if (i <= j) { [v[i], v[j]] = [v[j], v[i]]; [idx[i], idx[j]] = [idx[j], idx[i]]; i++; j--; }
    }
    if (k - 1 <= j) hi = j; else if (k - 1 >= i) lo = i; else break;
  }
  return Array.from(idx.subarray(0, k));
}

// ------------------------------------------------------------------ pictures (terrain.render)
const LUT = (() => {
  const stops = [[0, [60, 110, 40]], [0.35, [140, 170, 80]], [0.6, [200, 180, 110]], [0.8, [150, 110, 80]], [1, [245, 245, 245]]];
  const lut = new Uint8Array(256 * 3);
  for (let i = 0; i < 256; i++) {
    const t = i / 255;
    for (let s = 0; s < stops.length - 1; s++) {
      const [t0, c0] = stops[s], [t1, c1] = stops[s + 1];
      if (t >= t0 && t <= t1) { const k = (t - t0) / (t1 - t0); for (let c = 0; c < 3; c++) lut[i * 3 + c] = Math.trunc(c0[c] * (1 - k) + c1[c] * k); break; }
    }
  }
  return lut;
})();

function cubicW(t) {                           // OpenCV bicubic, A = -0.75
  const A = -0.75;
  return [((A * (t + 1) - 5 * A) * (t + 1) + 8 * A) * (t + 1) - 4 * A, ((A + 2) * t - (A + 3)) * t * t + 1,
          ((A + 2) * (1 - t) - (A + 3)) * (1 - t) * (1 - t) + 1, 0].map((v, i, a) => (i === 3 ? 1 - a[0] - a[1] - a[2] : v));
}
export function resizeCubic(src, n, m) {
  const out = new Float32Array(m * m), sc = n / m, tmp = new Float32Array(n * m);
  const idx = [], wt = [];
  for (let d = 0; d < m; d++) {
    const fx = (d + 0.5) * sc - 0.5, x0 = Math.floor(fx), w = cubicW(fx - x0);
    idx.push([x0 - 1, x0, x0 + 1, x0 + 2].map((p) => Math.min(Math.max(p, 0), n - 1))); wt.push(w);
  }
  for (let y = 0; y < n; y++) for (let x = 0; x < m; x++) { let s = 0; for (let k = 0; k < 4; k++) s += src[y * n + idx[x][k]] * wt[x][k]; tmp[y * m + x] = s; }
  for (let y = 0; y < m; y++) for (let x = 0; x < m; x++) { let s = 0; for (let k = 0; k < 4; k++) s += tmp[idx[y][k] * m + x] * wt[y][k]; out[y * m + x] = s; }
  return out;
}

export function renderToCanvas(h, n, size) {
  const r = resizeCubic(h, n, size);
  let mn = Infinity, mx = -Infinity; for (const v of r) { if (v < mn) mn = v; if (v > mx) mx = v; }
  const zf = 0.35 * size / ((mx - mn) || 1), hz = r.map((v) => v * zf);
  const gy = grad(hz, size, size, 0), gx = grad(hz, size, size, 1);
  const azr = (360 - 315 + 90) * Math.PI / 180, altr = 45 * Math.PI / 180;
  const cv = document.createElement("canvas"); cv.width = cv.height = size;
  const ctx = cv.getContext("2d"), img = ctx.createImageData(size, size);
  for (let i = 0; i < size * size; i++) {
    const slope = Math.PI / 2 - Math.atan(Math.hypot(gx[i], gy[i])), aspect = Math.atan2(-gx[i], gy[i]);
    let hs = Math.sin(altr) * Math.sin(slope) + Math.cos(altr) * Math.cos(slope) * Math.cos(azr - aspect);
    hs = Math.min(Math.max(hs, 0), 1);
    const li = Math.trunc((r[i] - mn) / (mx - mn + 1e-9) * 255) * 3, f = 0.35 + 0.75 * hs;
    for (let c = 0; c < 3; c++) img.data[i * 4 + c] = Math.min(255, Math.max(0, Math.trunc(LUT[li + c] * f)));
    img.data[i * 4 + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  return cv;
}
export const render = (h, n, size, type = "image/png") => renderToCanvas(h, n, size).toDataURL(type, 0.9);
