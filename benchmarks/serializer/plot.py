"""Draw dump_time.png, load_time.png and restore.png from results.json / restore_results.json."""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

res = json.load(open("results.json"))["results"]
workloads = list(dict.fromkeys(r["workload"] for r in res))
sers = list(dict.fromkeys(r["serializer"] for r in res))
colors = plt.cm.tab10(np.arange(len(sers)))
CHOSEN = "cloudpickle, fallback to dill"


def get(w, s, key):
    for r in res:
        if r["workload"] == w and r["serializer"] == s:
            return r[key]


def bars(key, title, fname):
    fig, ax = plt.subplots(figsize=(14, 5.5))
    width = 0.8 / len(sers)
    for i, s in enumerate(sers):
        xs = np.arange(len(workloads)) + i * width
        vals = [get(w, s, key) for w in workloads]
        ys = [v if v is not None else np.nan for v in vals]
        ax.bar(xs, ys, width, label=s, color=colors[i],
               edgecolor="black" if s == CHOSEN else "none", linewidth=1.5)
        for x, v in zip(xs, vals):
            if v is None:
                ax.text(x, 0.02, "fail", transform=ax.get_xaxis_transform(), rotation=90, ha="center", va="bottom", fontsize=7)
    ax.set_yscale("log")
    ax.set_ylabel("seconds (log scale, lower is faster)")
    ax.set_xticks(np.arange(len(workloads)) + 0.4 - width / 2)
    ax.set_xticklabels(workloads, rotation=15, ha="right")
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(fname, dpi=130)


bars("dump_s", "Serialize time per variable group (median of 3)", "dump_time.png")
bars("load_s", "Load time per variable group (median of 3, always dill.loads)", "load_time.png")

# speedup of the chosen serializer over current dill
fig, ax = plt.subplots(figsize=(9, 4))
sp = [get(w, "dill (current)", "dump_s") / get(w, CHOSEN, "dump_s") for w in workloads]
ax.barh(workloads[::-1], sp[::-1], color="tab:green")
for y, v in enumerate(sp[::-1]):
    ax.text(v, y, f" {v:.1f}x", va="center")
ax.axvline(1, color="black", lw=0.8)
ax.set_xlabel("speedup of serialize time vs dill (higher is faster)")
ax.set_title(f"{CHOSEN}")
fig.tight_layout()
fig.savefig("speedup.png", dpi=130)

# restore matrix
rr = json.load(open("restore_results.json"))
objs = list(next(iter(rr.values())).keys())
names = list(rr.keys())
fig, ax = plt.subplots(figsize=(10, 4.5))
grid = np.array([[1.0 if rr[n][o] == "ok" else 0.0 for o in objs] for n in names])
ax.imshow(grid, cmap="RdYlGn", vmin=-0.3, vmax=1.3, aspect="auto")
for i, n in enumerate(names):
    for j, o in enumerate(objs):
        v = rr[n][o]
        ax.text(j, i, "OK" if v == "ok" else v.replace(" (", "\n("), ha="center", va="center", fontsize=8)
ax.set_xticks(range(len(objs)))
ax.set_xticklabels(objs)
ax.set_yticks(range(len(names)))
ax.set_yticklabels(names)
ax.set_title("Dump in one process, load in a fresh one (names defined in __main__ are gone)")
fig.tight_layout()
fig.savefig("restore.png", dpi=130)
