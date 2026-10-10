"""Workloads: one variable group each, built to a rough target size."""
import numpy as np
import pandas as pd


def list_of_dict(n):
    return [{"id": i, "name": f"row{i}", "v": [i, i + 1.5]} for i in range(n)]


def ndarray(mb):
    return np.random.rand(mb * 1024 * 1024 // 8)


def dataframe_numeric(mb):
    rows = mb * 1024 * 1024 // (8 * 4)
    return pd.DataFrame(np.random.rand(rows, 4), columns=list("abcd"))


def dataframe_strings(n):
    return pd.DataFrame({"id": np.arange(n), "name": [f"user_{i}" for i in range(n)]})


def dict_of_lists(n):
    return {f"key{i}": list(range(20)) for i in range(n)}


# (label, builder, args). Sizes chosen so every workload is tens of MB.
WORKLOADS = [
    ("ndarray 100MB", ndarray, (100,)),
    ("DataFrame numeric 100MB", dataframe_numeric, (100,)),
    ("DataFrame strings 500k rows", dataframe_strings, (500_000,)),
    ("list of dict (300k)", list_of_dict, (300_000,)),
    ("dict of lists (100k)", dict_of_lists, (100_000,)),
]
# Workloads that must be defined in the running script (its __main__), like notebook cells,
# live in bench.py / restore_check.py.
