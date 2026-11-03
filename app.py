"""Photo-upload web app: drop a photo of your sculpture, get the matching place on Earth.

  python app.py --index data/world_z6            # http://localhost:8000 on this Mac
  python app.py --index data/world_z6 --lan      # also reachable from your phone on the same Wi-Fi
  python app.py --index data/world_z6 --public   # public server, e.g. on your own host

With --lan, open the printed address on your phone and use "Take photo" to shoot
the sculpture straight from above. Only standard-library web serving is used.

--public listens on all interfaces, allows the GitHub Pages site to send photos here
(CORS), deletes uploaded photos and results after --keep-minutes, and points the
"Try another photo" links back to --home.
"""
import argparse
import datetime as dt
import json
import os
import shutil
import socket
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

import cv2
import numpy as np

from s2e.device import add_device_arg, apply_device_arg
from s2e.index import Index
from s2e.depth import depth_anything, shading_depth, to_heightmap, square_crop
from s2e.report import write_outputs
from s2e.page import render_page, hero_data

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--index", required=True)
p.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
p.add_argument("--lan", action="store_true", help="listen on the local network (phone access)")
p.add_argument("--public", action="store_true", help="run as a public server (CORS, auto-delete, no browser)")
p.add_argument("--home", default=os.environ.get("S2E_HOME", "https://tilakkumar13.github.io/sand2earth/"),
               help="with --public: where 'Try another photo' leads")
p.add_argument("--keep-minutes", type=float, default=30, help="with --public: delete results after this long")
p.add_argument("--depth", choices=["dav2", "shading"], default="dav2")
p.add_argument("--out", default="output")
p.add_argument("--no-browser", action="store_true")
p.add_argument("--matcher", choices=["auto", "learned", "handcrafted"], default="auto")
add_device_arg(p)
a = p.parse_args()
apply_device_arg(a)

print("[app] loading index ...")
IDX = Index(a.index, matcher=a.matcher)
print(f"[app] {len(IDX.desc):,} terrain patches ready")
LOCK = threading.Lock()  # one depth model, one search at a time
OUT = os.path.abspath(a.out)
os.makedirs(OUT, exist_ok=True)
MAX_UPLOAD = 25 * 1024 * 1024
from s2e.tiles import meters_per_px
from s2e.terrain import PATCH
_sizes = [PATCH * f * IDX.mpp(0) / 1000 for f in sorted(IDX.levels)]
PAGE = render_page(len(IDX.meta), _sizes, IDX.matcher, hero=hero_data(IDX), public=a.public)

if a.public and a.depth == "dav2":  # load the depth model now, not on the first visitor's request
    depth_anything(np.zeros((64, 64, 3), np.uint8))


def run_search(data, invert, flip, detrend):
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not read that image. Try a JPG or PNG (iPhone HEIC photos: share as JPG).")
    long_side = max(img.shape[:2])
    if long_side > 1600:  # phone photos are huge; depth model works at ~518 px anyway
        s = 1600 / long_side
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    img = square_crop(img)
    with LOCK:
        d = depth_anything(img) if a.depth == "dav2" else shading_depth(img)
        h = to_heightmap(d, invert=invert, detrend_order=detrend)
        q, res = IDX.search(h, k=5, allow_flip=flip)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        write_outputs(os.path.join(OUT, stamp), IDX, q, res, img)
    return stamp, res


def cleanup_loop():
    """Public mode: uploaded photos and their results are removed after --keep-minutes."""
    while True:
        cutoff = time.time() - a.keep_minutes * 60
        for name in os.listdir(OUT):
            path = os.path.join(OUT, name)
            try:
                if os.path.isdir(path) and os.path.getmtime(path) < cutoff:
                    shutil.rmtree(path, ignore_errors=True)
            except OSError:
                pass
        time.sleep(60)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype, cache=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if cache:
            self.send_header("Cache-Control", cache)
        if a.public:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # CORS preflight from the GitHub Pages site
        self.send_response(204)
        if a.public:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if path == "/health":
            return self._send(200, json.dumps({"ok": True, "places": len(IDX.meta), "matcher": IDX.matcher}),
                              "application/json", cache="no-store")
        if path.startswith("/out/"):
            rel = unquote(path[len("/out/"):])
            full = os.path.abspath(os.path.join(OUT, rel))
            if not full.startswith(OUT + os.sep) or not os.path.isfile(full):
                if a.public and path.endswith("report.html"):
                    return self._send(404, EXPIRED, "text/html; charset=utf-8")
                return self._send(404, "not found", "text/plain")
            ext = os.path.splitext(full)[1].lower()
            ctype = {".html": "text/html; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg",
                     ".json": "application/json"}.get(ext, "application/octet-stream")
            with open(full, "rb") as f:
                body = f.read()
            if a.public and ext == ".html":
                body = (body.decode("utf-8").replace('href="/#try"', f'href="{a.home}#try"')
                        .replace('href="/"', f'href="{a.home}"'))
            return self._send(200, body, ctype, cache="private, no-store" if a.public else None)
        self._send(404, "not found", "text/plain")

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/search":
            return self._send(404, "not found", "text/plain")
        n = int(self.headers.get("Content-Length", 0))
        if n <= 0 or n > MAX_UPLOAD:
            return self._send(413, json.dumps({"error": "Photo missing or larger than 25 MB."}), "application/json")
        data = self.rfile.read(n)
        qs = parse_qs(u.query)
        flag = lambda k: qs.get(k, ["0"])[0] == "1"
        try:
            detrend = int(qs.get("detrend", ["1"])[0])
            stamp, res = run_search(data, flag("invert"), flag("flip"), detrend if detrend in (0, 1, 2) else 1)
        except Exception as e:  # report the problem to the page instead of a blank 500
            print(f"[app] error: {e}")
            return self._send(400, json.dumps({"error": str(e)}), "application/json")
        top = res[0] if res else {}
        print(f"[app] {stamp}: best {top.get('lat', 0):.2f}, {top.get('lon', 0):.2f}")
        self._send(200, json.dumps({"report": f"/out/{stamp}/report.html", "results": res}),
                   "application/json")


EXPIRED = f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sand to Earth</title><body style="font:17px/1.5 -apple-system,system-ui,sans-serif;max-width:520px;margin:18vh auto;padding:0 24px;color:#1d1d1f">
<h1 style="font-size:32px;margin:0 0 8px">This result has expired.</h1>
<p style="color:#6e6e73">Photos and results are deleted after {a.keep_minutes:.0f} minutes. Run a new search to see it again.</p>
<p><a href="{a.home}#try" style="color:#0066cc">Try another photo</a></p></body>"""


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


host = "0.0.0.0" if (a.lan or a.public) else "127.0.0.1"
srv = ThreadingHTTPServer((host, a.port), Handler)
url = f"http://localhost:{a.port}"
print(f"[app] open {url}")
if a.public:
    threading.Thread(target=cleanup_loop, daemon=True).start()
    print(f"[app] public mode: results deleted after {a.keep_minutes:.0f} min, links home to {a.home}")
if a.lan and lan_ip():
    print(f"[app] on your phone (same Wi-Fi): http://{lan_ip()}:{a.port}")
if not (a.no_browser or a.public):
    webbrowser.open(url)
try:
    srv.serve_forever()
except KeyboardInterrupt:
    print("\n[app] stopped")
