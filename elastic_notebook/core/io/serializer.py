"""Serialize checkpoint payloads: cloudpickle first, dill as a fallback.

dill's Pickler is written in pure Python, so it is far slower than the C pickler when the
data is many small Python objects (about 20x on a list of dicts). cloudpickle runs on the C
pickler and only hooks in for classes and functions, which it stores by value. That is the
reason we used dill in the first place: classes and functions defined in the notebook
(``__main__``) must be restorable in a fresh kernel. The standard pickle stores those by
name, so the dump succeeds but the load fails.

Loading stays on ``dill.load``: it reads cloudpickle's output (a normal pickle stream) and
old checkpoints written by dill alike.
"""

import logging

import cloudpickle
import dill

logger = logging.getLogger(__name__)


def dump(obj, file) -> None:
    """Write ``obj`` to ``file`` (binary, seekable), leaving nothing behind on failure."""
    start = file.tell()
    try:
        cloudpickle.dump(obj, file)
    except Exception as e:
        logger.debug(
            f"cloudpickle failed ({type(e).__name__}: {e}); retrying with dill"
        )
        file.seek(start)
        file.truncate()
        dill.dump(obj, file)


def dumps(obj) -> bytes:
    try:
        return cloudpickle.dumps(obj)
    except Exception as e:
        logger.debug(
            f"cloudpickle failed ({type(e).__name__}: {e}); retrying with dill"
        )
        return dill.dumps(obj)
