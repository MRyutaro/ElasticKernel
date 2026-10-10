"""Time dumps/loads of each serializer on each workload; write results.json."""

import dataclasses
import json
import statistics
import sys
import time

import cloudpickle
import dill
import numpy as np
import pandas as pd
from serializers import CANDIDATES
from workloads import WORKLOADS

REPEAT = 3


@dataclasses.dataclass
class Point:  # a class defined in the notebook (__main__)
    x: float
    y: float
    tag: str


def user_class_instances(n):
    return [Point(float(i), i * 0.5, f"p{i}") for i in range(n)]


def lambdas(n):
    return [(lambda k=k: k * 2) for k in range(n)]


WORKLOADS = WORKLOADS + [
    ("user-class instances (300k)", user_class_instances, (300_000,)),
    ("lambdas (20k)", lambdas, (20_000,)),
]


def timed(fn, *a):
    t = time.perf_counter()
    r = fn(*a)
    return time.perf_counter() - t, r


results = []
for label, build, args in WORKLOADS:
    obj = build(*args)
    for name, (dumps, loads) in CANDIDATES.items():
        d_times, l_times = [], []
        size = None
        err = None
        for _ in range(REPEAT):
            try:
                dt, data = timed(dumps, obj)
                lt, _ = timed(loads, data)
            except Exception as e:  # e.g. pickling lambdas
                err = f"{type(e).__name__}: {e}"[:120]
                break
            d_times.append(dt)
            l_times.append(lt)
            size = len(data)
        row = dict(
            workload=label,
            serializer=name,
            size_mb=(size or 0) / 1e6,
            dump_s=statistics.median(d_times) if d_times else None,
            load_s=statistics.median(l_times) if l_times else None,
            error=err,
        )
        results.append(row)
        print(
            f"{label:32s} {name:40s} dump={row['dump_s']} load={row['load_s']} size={row['size_mb']:.1f}MB {err or ''}",
            flush=True,
        )
    del obj

json.dump(
    dict(
        python=sys.version,
        dill=dill.__version__,
        cloudpickle=cloudpickle.__version__,
        numpy=np.__version__,
        pandas=pd.__version__,
        results=results,
    ),
    open("results.json", "w"),
    indent=1,
)
