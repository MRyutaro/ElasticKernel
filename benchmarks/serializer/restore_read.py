"""Process 2: a fresh __main__ with no Point / double. Load what restore_write.py dumped."""

import json
import pathlib
import sys

from serializers import CANDIDATES

NAMES = ["class instances", "function", "lambda with closure", "plain data"]


def check(name, obj):
    if name == "class instances":
        return [(p.x, p.y) for p in obj] == [(1.0, 2.0), (3.0, 4.0)]
    if name == "function":
        return obj(4) == 8
    if name == "lambda with closure":
        return obj(1) == 11
    return obj == {"a": [1, 2, 3]}


d = pathlib.Path(sys.argv[1])
out = {}
for sname, (_, loads) in CANDIDATES.items():
    for oname in NAMES:
        f = d / f"{sname}__{oname}".replace("/", "_")
        if f.with_suffix(".err").exists():
            res = "dump failed"
        else:
            try:
                res = "ok" if check(oname, loads(f.read_bytes())) else "wrong value"
            except Exception as e:
                res = f"load failed ({type(e).__name__})"
        out.setdefault(sname, {})[oname] = res
json.dump(out, open("restore_results.json", "w"), indent=1)
for s, r in out.items():
    print(s, r)
