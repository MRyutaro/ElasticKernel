"""Serializer candidates compared in this benchmark.

Each entry maps a name to (dumps, loads). All take/return bytes so that the CPU cost of
serializing is separated from the cost of writing the file (which is the same for all).
"""
import pickle

import cloudpickle
import dill

PROTOCOL = pickle.HIGHEST_PROTOCOL


def _pickle_with_main_scan(obj, fallback):
    """Fast C pickle first. Fall back when it fails or when it refers to ``__main__``.

    The standard pickle stores classes/functions defined in the notebook (``__main__``)
    by name. That dump succeeds, but a fresh kernel has no such name, so loading fails.
    The name ``__main__`` shows up in the byte stream, so a plain bytes search finds it.
    """
    try:
        data = pickle.dumps(obj, protocol=PROTOCOL)
    except Exception:
        return fallback(obj)
    if b"__main__" in data:
        return fallback(obj)
    return data


def _dill_dumps(obj):
    return dill.dumps(obj, protocol=PROTOCOL)


def _cloudpickle_dumps(obj):
    return cloudpickle.dumps(obj, protocol=PROTOCOL)


def _pickle_dumps(obj):
    return pickle.dumps(obj, protocol=PROTOCOL)


def _pickle_then_exception_fallback(obj):
    try:
        return pickle.dumps(obj, protocol=PROTOCOL)
    except Exception:
        return dill.dumps(obj, protocol=PROTOCOL)


def _cloudpickle_then_dill(obj):
    try:
        return cloudpickle.dumps(obj, protocol=PROTOCOL)
    except Exception:
        return dill.dumps(obj, protocol=PROTOCOL)


def _dill_byref(obj):
    return dill.dumps(obj, protocol=PROTOCOL, byref=True)


# Loading always goes through dill.loads, as the checkpoint reader does. cloudpickle's output
# is a normal pickle stream, so dill can read it.
CANDIDATES = {
    "dill (current)": (_dill_dumps, dill.loads),
    "dill (byref=True)": (_dill_byref, dill.loads),
    "pickle (C)": (_pickle_dumps, dill.loads),
    "cloudpickle": (_cloudpickle_dumps, dill.loads),
    "pickle, fallback on error": (_pickle_then_exception_fallback, dill.loads),
    "pickle + __main__ scan -> dill": (
        lambda o: _pickle_with_main_scan(o, _dill_dumps),
        dill.loads,
    ),
    "pickle + __main__ scan -> cloudpickle": (
        lambda o: _pickle_with_main_scan(o, _cloudpickle_dumps),
        dill.loads,
    ),
    "cloudpickle, fallback to dill": (_cloudpickle_then_dill, dill.loads),
}
