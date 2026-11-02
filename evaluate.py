"""Compare the hand-crafted and learned matchers and write docs/results.md.

  python evaluate.py --index data/world_z6
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys

p = argparse.ArgumentParser()
p.add_argument("--index", required=True)
p.add_argument("-n", type=int, default=100)
p.add_argument("--out", default="docs/results.md")
a = p.parse_args()

has_learned = os.path.exists(a.index + "_emb.npy")
# all rows use regions held out of training; "placed anywhere" is the realistic case (see selftest.py --offgrid)
runs = [("handcrafted", False), ("handcrafted", True)]
if has_learned:
    runs += [("learned", False), ("learned", True)]
os.makedirs("docs", exist_ok=True)
rows = []
for matcher, off in runs:
    held = True
    tag = f"{matcher}{'_offgrid' if off else ''}"
    js = f"docs/.eval_{tag}.json"
    cmd = [sys.executable, "selftest.py", "--index", a.index, "--crude", "-n", str(a.n),
           "--matcher", matcher, "--json", js, "--examples", f"docs/examples_{tag}.png"]
    cmd.append("--heldout")
    if off:
        cmd.append("--offgrid")
    print(f"[eval] {tag} ...")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    rows.append(json.load(open(js)))
    os.remove(js)

lines = [f"# Matcher comparison", "",
         f"Index `{a.index}` ({rows[0]['windows']:,} windows), {a.n} crude-sculpture queries per row, "
         f"{dt.date.today().isoformat()}.", "",
         "Every query comes from a region held out of training. \"Lined up\" sandboxes are centred on an indexed",
         "window at almost its size (the easy case); \"placed anywhere\" sandboxes can sit anywhere and cover any",
         "area, like a real one.", "",
         "| matcher | sandbox | right place first | in top 5 | rotation error | search time |",
         "|---|---|---|---|---|---|"]
for r in rows:
    lines.append(f"| {r['matcher']} | {'placed anywhere' if r.get('offgrid') else 'lined up'} | "
                 f"{r['recall_at_1']:.0%} | {r['recall_at_5']:.0%} | "
                 f"{r['rotation_error_deg']:.0f}° | {r['search_ms']:.0f} ms |")
if not has_learned:
    lines += ["", "No learned embeddings yet: run `train.py` and `embed_index.py` first."]
with open(a.out, "w") as fh:
    fh.write("\n".join(lines) + "\n")
print("\n".join(lines))
print(f"\n[eval] written to {a.out}")
