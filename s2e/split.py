"""Geographic train / test split for the learned matcher.

The planet is cut into 10 x 10 degree cells and one cell in five is held out.
The model never trains on held-out cells, so testing there measures whether it
learned terrain in general rather than memorising places.
"""
import math

CELL_DEG = 10
MOD = 5


def is_heldout(lon, lat):
    i = int(math.floor((lon + 180) / CELL_DEG))
    j = int(math.floor((lat + 90) / CELL_DEG))
    return ((i * 73856093) ^ (j * 19349663)) % MOD == 0
