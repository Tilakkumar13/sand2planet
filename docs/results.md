# Matcher comparison

Index `data/world_z6` (88,531 windows), 100 crude-sculpture queries per row, 2026-11-02.

| matcher | queries from | right place first | in top 5 | rotation error | search time |
|---|---|---|---|---|---|
| handcrafted | anywhere | 77% | 81% | 2° | 659 ms |
| handcrafted | held-out regions | 76% | 79% | 2° | 584 ms |
| learned | anywhere | 89% | 92% | 2° | 427 ms |
| learned | held-out regions | 89% | 93% | 2° | 423 ms |
