"""Download global elevation and build the searchable terrain index.

Examples
  python build_index.py --zoom 7 --bbox 4 43 17 49 --name alps        # one region, ~1 min
  python build_index.py --zoom 6 --name world_z6                       # whole planet, ~5 min
  python build_index.py --zoom 7 --levels 1 2 4 8 --name world_z7      # finer planet, ~20 min, ~1.5 GB
  python build_index.py --synthetic --name synthetic                   # offline fake planet

Window sizes at the equator (they stay the same in km at every latitude):
  zoom 6: level 1 = 156 km, 2 = 313 km, 4 = 626 km
  zoom 7: level 1 =  78 km, 2 = 156 km, 4 = 313 km, 8 = 626 km
"""
import argparse
import os

from s2e.tiles import build_terrarium_mosaic, synthetic_mosaic
from s2e.index import build_index

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("--zoom", type=int, default=6, help="Terrain Tiles zoom (6 = ~2.4 km/px, 7 = ~1.2 km/px at the equator)")
p.add_argument("--bbox", type=float, nargs=4, metavar=("LON_MIN", "LAT_MIN", "LON_MAX", "LAT_MAX"),
               default=[-180, -60, 180, 78], help="region to index (default: all land except Antarctica)")
p.add_argument("--levels", type=int, nargs="+", default=[1, 2, 4], help="window scales (1 = 64 px at the equator)")
p.add_argument("--stride", type=int, default=16, help="window step, in 64-px window units")
p.add_argument("--min-relief", type=float, default=40.0, help="skip flatter windows (metres std)")
p.add_argument("--no-lat-aware", action="store_true", help="old pixel-based windows (over-samples the poles)")
p.add_argument("--synthetic", action="store_true", help="fake planet for offline testing")
p.add_argument("--name", default="world_z6")
p.add_argument("--data", default="data")
a = p.parse_args()

os.makedirs(a.data, exist_ok=True)
hdr = synthetic_mosaic(a.data) if a.synthetic else build_terrarium_mosaic(a.zoom, a.bbox, a.data)
build_index(hdr, os.path.join(a.data, a.name), levels=tuple(a.levels), stride=a.stride,
            min_relief=a.min_relief, lat_aware=not a.no_lat_aware)
