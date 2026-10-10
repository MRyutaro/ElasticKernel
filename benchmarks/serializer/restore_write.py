"""Process 1: define classes/functions in __main__ (like notebook cells) and dump them with every serializer.

restore_read.py then loads them in a fresh process that has none of these names."""

import dataclasses
import pathlib
import sys

from serializers import CANDIDATES


@dataclasses.dataclass
class Point:
    x: float
    y: float


def double(v):
    return v * 2


def make_objects():
    offset = 10
    return {
        "class instances": [Point(1.0, 2.0), Point(3.0, 4.0)],
        "function": double,
        "lambda with closure": lambda v: v + offset,
        "plain data": {"a": [1, 2, 3]},
    }


d = pathlib.Path(sys.argv[1])
d.mkdir(exist_ok=True)
for sname, (dumps, _) in CANDIDATES.items():
    for oname, obj in make_objects().items():
        f = d / f"{sname}__{oname}".replace("/", "_")
        try:
            f.write_bytes(dumps(obj))
        except Exception as e:
            f.with_suffix(".err").write_text(type(e).__name__)
