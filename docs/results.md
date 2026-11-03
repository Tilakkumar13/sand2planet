# Matcher comparison

Index `data/world_z6` (88,531 windows), 100 crude-sculpture queries per row (300 for the learned "placed anywhere" row), 2026-11-03.

Every query comes from a region held out of training. "Lined up" sandboxes are centred on an indexed
window at almost its size (the easy case); "placed anywhere" sandboxes can sit anywhere and cover any
area, like a real one.

| matcher | sandbox | right place first | in top 5 | rotation error | search time |
|---|---|---|---|---|---|
| handcrafted | lined up | 86% | 89% | 2° | 1264 ms |
| handcrafted | placed anywhere | 28% | 41% | 3° | 1226 ms |
| learned | lined up | 93% | 97% | 2° | 1788 ms |
| learned | placed anywhere | 69% | 75% | 3° | 1812 ms |

The learned "placed anywhere" row is from a larger run (300 queries, seed 3); 100-query runs with other seeds gave 63–80 %.
None of these tests includes reading depth from a photo: they start from a distorted height map.

## Mars

Index `data/mars_z5` (102,915 windows from MGS MOLA, 2.6 km/px), 100 crude-sculpture queries per row, learned matcher
trained on Earth only (every Mars place is new to it).

| matcher | sandbox | right place first | in top 5 | rotation error |
|---|---|---|---|---|
| learned (Earth) | lined up | 82% | 88% | 2° |
| learned (Earth) | placed anywhere | 51% | 59% | 4° |
