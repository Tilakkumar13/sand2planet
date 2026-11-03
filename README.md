# Sand to Planet

Shape a landscape out of sand or clay, take one photo of it from above, and find the place
on Earth, or on Mars, whose real terrain matches it. Results show the match on Sentinel-2 imagery, with
your sandbox outline and orientation drawn on the real place, and both surfaces side by side
in 3D.

```
photo ─► Depth Anything V2 ─► height map ─► global terrain index ─► rotation search ─► report
         (monocular depth)      (64×64)       learned CNN or            (finds the     map + 3D
                                              hand-crafted fingerprint   compass angle)
```

The project sits between GIS, computer vision and remote sensing. Projected AR sandboxes and
tangible GIS tools already exist, and so does query-by-example search over DEMs (see
[prior work](#prior-work)). What is new here is closing the loop: a shape made by hand goes in,
and a real place anywhere on the planet comes out.

## Quick start (macOS, Apple Silicon)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python build_index.py --zoom 6 --name world_z6
python app.py --index data/world_z6
```

`build_index.py` downloads public elevation tiles (no account needed) and takes about
5 minutes. `app.py` opens the upload page at `http://localhost:8000`. Start it with `--lan`
to open it from your phone on the same Wi-Fi and use the phone camera.

## The public site searches in your browser

[tilakkumar13.github.io/sand2planet](https://tilakkumar13.github.io/sand2planet/) runs the whole pipeline on
the visitor's device, so photos are never uploaded and there is no server to pay for or wake up:

- **Depth:** Depth Anything V2 Small through [transformers.js](https://huggingface.co/docs/transformers.js) (8-bit, about 27 MB).
- **Matcher:** the learned encoder exported to ONNX and run with ONNX Runtime Web.
- **Index:** 8-bit embeddings and an 8-bit-per-tile copy of the elevation mosaic (about 45 MB in `docs/engine/`).
- **Search and results page:** a JavaScript port of `Index.search` and `report.py` (`s2e/web/`).

The port was checked against the Python code on 30 simulated sculptures from held-out regions: the same top-5
places and the same rotation in every case. Quantising the index did not change any top-1 result in a
60-query test. Rebuild the site after changing the index or retraining:

```bash
python build_site.py --index data/world_z6        # page + docs/engine (needs torch for the ONNX export)
```

## Going further

| step | command | time on an M-series Mac |
|---|---|---|
| finer global index | `python build_index.py --zoom 7 --levels 1 2 4 8 --name world_z7` | ~20 min, ~1.5 GB |
| train the learned matcher | `python train.py --index data/world_z6` | ~15–30 min |
| attach it to an index | `python embed_index.py --index data/world_z7 --model models/matcher.pt` | a few min |
| compare both matchers | `python evaluate.py --index data/world_z7` | a few min, writes `docs/results.md` |

After `embed_index.py`, `app.py`, `run.py` and `selftest.py` use the learned matcher
automatically. Pass `--matcher handcrafted` to any of them to switch back.

### Running on CPU only (e.g. MacBook Air)

Everything runs on the CPU. Add `--device cpu` to any script, or set it once per Terminal
window with `export S2E_DEVICE=cpu`. Searching is plain NumPy and always runs on the CPU;
only the depth model and the learned matcher use PyTorch.

For training, use the smaller CPU preset. It halves the network width (1.45 M parameters) and
uses smaller batches, about 4–5× less work per step:

```bash
python train.py --index data/world_z6 --preset cpu          # 3,000 steps
python train.py --index data/world_z6 --preset cpu-quick    # 600 steps, to check it works
```

A MacBook Air has no fan and slows down after several minutes of full load. Keep it plugged
in on a hard surface. Training saves the best checkpoint as it goes, so stopping it with
Ctrl+C still leaves a usable `models/matcher.pt`.

## How it works

### 1. Photo to height map
Depth Anything V2 (small, runs on the Mac GPU) estimates relative depth from a single photo.
Closer to the camera means higher terrain. A plane fit removes leftover camera tilt, and the
result is resized to a 64×64 height map and z-scored, so a 10 cm clay hill and a 3,000 m
mountain range become directly comparable.

### 2. A fair index of the planet
Elevation comes from the [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/)
(SRTM, ETOPO1 and national DEMs) in Web Mercator. Mercator stretches high latitudes: at 70°,
one kilometre covers almost three times as many pixels as at the equator. Windows measured in
pixels therefore over-sample Greenland and Siberia, which then win searches far too often.

Windows here are sized and spaced in **kilometres**: at latitude φ a window is `64·f / cos φ`
pixels wide, and the step grows the same way. On a test planet this cut the share of random
shapes landing above 60° from **76 %** to **23 %**. That band holds 12–17 % of the land.
`selftest.py --bias 200` measures the same thing on real data.

### 3. Shortlist: two matchers
The search first scores every window in the index and keeps a few thousand candidates.

- **Hand-crafted fingerprint.** Heights are sampled on polar rings around the centre, and
  each ring keeps the magnitude of its angular Fourier transform, which does not change when the
  patch rotates (the idea behind Fourier–Mellin matching). Histograms of height, slope and
  curvature are added.
- **Learned matcher.** A small residual CNN learns what to look at (ridges, valleys, drainage
  patterns), then the same polar-Fourier trick is applied to its feature maps, so the embedding
  is rotation-invariant by construction rather than by luck. It is trained contrastively
  (InfoNCE): a distorted "sculpture" of a place has to land next to the clean window of that
  place and away from every other place in the batch. The distortions simulate what a camera
  and clay do: random rotation and scale, a non-linear depth response, tilt, a bowl-shaped
  lens error, smooth depth-model warping, heavy blur for rough hand-made shapes, and noise. All
  augmentation runs on the GPU.

### 4. Re-rank and find the angle
Each candidate is compared with the query rotated in 6° steps using normalised
cross-correlation. The best angle tells you which compass direction your sandbox's top edge
faces on the real map.

## Evaluation

`selftest.py` takes real places from regions the learned matcher never trained on, turns each one into a fake
sculpture (random rotation, a bent height curve, tilt, heavy blur, noise) and checks whether the search finds the
original place again. `--offgrid` is the realistic version: the sandbox can sit anywhere and cover any area, instead
of lining up with an indexed window. `evaluate.py` writes the table below to `docs/results.md`.

| matcher | sandbox | right place first | in top 5 |
|---|---|---|---|
| hand-crafted | lined up | 86 % | 89 % |
| hand-crafted | placed anywhere | 28 % | 41 % |
| learned | lined up | 93 % | 97 % |
| learned | placed anywhere | **69 %** | 75 % |

The first learned model was only trained on lined-up examples and found 8 % of realistically placed sandboxes. Two
changes brought that to 69 %: training on sandboxes shifted and resized against the index grid
(`train.py --preset offgrid`), and re-fitting the best candidates (slide, resize, turn) before the final ranking.

These tests start from a height map. Reading depth from a photo of real sand is not part of them yet, and is the
next thing to measure.

## Mars

`build_planet.py` downloads the MGS MOLA elevation map of Mars (32 pixels per degree), re-projects it to Web
Mercator and builds a 102,915-window index, plus the IAU place names. The public site has an Earth / Mars switch;
Mars results are named from the IAU Gazetteer and mapped on NASA Mars Trek tiles.

The matcher was trained on Earth only. On Mars it finds the right place first in 82 % of lined-up and 51 % of
realistically placed tests, against 93 % and 69 % on Earth. A matcher trained on Mars terrain is the next step.

## The results page

- The best match is named after the real region (through OpenStreetMap Nominatim), with its size, shape agreement and the direction your sandbox faces.
- **Side by side in 3D:** your sculpture (draped with your photo) next to the real terrain (draped with Sentinel-2 imagery stitched from tiles), both turned to north at the same relief scale. You can switch to shaded relief and change the height exaggeration.
- A map with Sentinel-2, Esri and topographic layers shows all matches, with the sandbox outline and its top edge.
- `result.json` holds coordinates, size and rotation for TouchDesigner or other tools.

## Other ways to search

```bash
python run.py --index data/world_z6                         # live webcam: R = region, SPACE = search
python run.py --index data/world_z6 --image sculpture.jpg   # one photo, no browser upload
python run.py --index data/world_z6 --heightmap dem.png     # a ready-made height map
```

## Tips for good photos

- Shoot straight down, in soft even light, with hands out of the frame.
- Build big, clear forms such as ridges, valleys and peaks. Fine texture is smoothed away anyway.
- Matte, light-coloured modelling clay works better than shiny or wet sand.
- If peaks come out as pits, tick **Swap hills and valleys** (`--invert`).

## Project layout

```
app.py            upload web app
run.py            webcam / photo / height map from the command line
build_index.py    download elevation, build the index
train.py          train the learned matcher
embed_index.py    add learned embeddings to an index
selftest.py       accuracy, rotation error, polar bias
evaluate.py       matcher comparison table
s2e/
  terrain.py      normalisation, hand-crafted descriptor, rotation search, rendering
  index.py        latitude-aware windows, index search
  learned.py      CNN + polar-Fourier head, GPU augmentation
  split.py        geographic train / test split
  device.py       CPU / Mac GPU choice (--device, S2E_DEVICE)
  depth.py        photo → height map
  tiles.py        AWS Terrain Tiles mosaic
  report.py       results page with map and 3D
  page.py style.py  upload page and shared look
```

## Prior work

- Augmented Reality Sandbox (Kreylos, UC Davis): scans sand with a depth camera and projects contours onto it.
- Tangible Landscape (NC State): sculpt sand to match a known place, with GIS analysis projected back.
- Content-based landscape retrieval (Jasiewicz, Netzel & Stepinski, 2013) and LSE Wisconsin (Haffner et al., 2023): query-by-example DEM search, digital and regional.
- GEAR (2026): Siamese-network retrieval of terrain analogues (Mariana Trench ↔ Tibetan Plateau).
- terravector (GitHub): DEM patch similarity search with HNSW.
- US patent 11,961,183: game height map → real-world terrain search.

## Roadmap

- Projection back onto the sand through TouchDesigner, rotated by `rotation_deg`.
- Live mode: search every few seconds while someone sculpts.
- Mars and the Moon (MOLA / LOLA elevation).
- Fine-tuning the matcher on real photos of real sculptures.

## Credits

Elevation: AWS Terrain Tiles (Mapzen / Tilezen). Imagery: Sentinel-2 cloudless 2016 by EOX IT
Services GmbH (contains modified Copernicus Sentinel data), CC BY 4.0. Depth: Depth Anything V2.
Place names: OpenStreetMap contributors via Nominatim. 3D: three.js.

Built by [Tilak Kumar](https://tilakkumar13.github.io/), MSc Geospatial Technologies, Institute for Geoinformatics, University of Münster.

**Live site:** https://tilakkumar13.github.io/sand2planet/ (Earth) and https://tilakkumar13.github.io/sand2planet/mars/ (Mars)
