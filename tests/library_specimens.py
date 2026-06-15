"""Single source of truth for the library checkpoint-coverage matrix (issue #48).

Each :class:`Specimen` describes one library, a deterministic snippet that builds a
representative object from it, and an equality predicate for that object. The
:func:`run_round_trip` harness drives the real ``record_event -> checkpoint ->
load_checkpoint`` path and classifies the result into one of three values:

- ``Migrated``    -- dill serialized the object (the optimized path).
- ``Recomputed``  -- the object is unserializable, but re-running the cell restores it.
- ``Failed``      -- the object could not be restored, or its value did not survive.

Migration is *forced* (``manual_migration_speed = True`` with an effectively infinite
``migration_speed_bps``) so that anything serializable is migrated; whatever still falls
back to the recompute set is genuinely unserializable. See issue #48 for the design.

Run a single specimen in isolation (used by scripts/library_coverage.py for crash
containment)::

    python -m tests.library_specimens <key> <workdir>

which prints one JSON object ``{"key", "classification", "detail"}`` to stdout.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from typing import Callable, List


@dataclass(frozen=True)
class Specimen:
    key: str  # display name in the README table
    module: str  # top-level import name (for importorskip / availability checks)
    pip_name: str  # PyPI distribution name (for the `coverage` dependency group)
    var: str  # variable that holds the representative object after `setup` runs
    setup: str  # deterministic, recomputable code that creates `var`
    equal: Callable[[object, object], bool]  # value-equality for the restored object


# --- equality predicates -------------------------------------------------------------


def _array_equal(a, b):
    import numpy as np

    return np.array_equal(a, b)


def _pandas_equal(a, b):
    return a.equals(b)


def _scipy_sparse_equal(a, b):
    import numpy as np

    return a.shape == b.shape and np.array_equal(a.toarray(), b.toarray())


def _sklearn_equal(a, b):
    import numpy as np

    return np.allclose(a.coef_, b.coef_) and np.allclose(a.intercept_, b.intercept_)


def _mpl_figure_equal(a, b):
    import numpy as np

    ya = a.axes[0].lines[0].get_ydata()
    yb = b.axes[0].lines[0].get_ydata()
    return np.array_equal(ya, yb)


def _seaborn_grid_equal(a, b):
    return type(a) is type(b) and len(list(a.axes.flat)) == len(list(b.axes.flat))


def _requests_response_equal(a, b):
    return a.status_code == b.status_code and a.content == b.content


# --- specimens -----------------------------------------------------------------------

SPECIMENS: List[Specimen] = [
    Specimen(
        key="numpy",
        module="numpy",
        pip_name="numpy",
        var="ek_obj",
        setup="import numpy as np\n"
        "ek_obj = np.arange(12, dtype=np.int64).reshape(3, 4)\n",
        equal=_array_equal,
    ),
    Specimen(
        key="pandas",
        module="pandas",
        pip_name="pandas",
        var="ek_obj",
        setup="import pandas as pd\n"
        'ek_obj = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})\n',
        equal=_pandas_equal,
    ),
    Specimen(
        key="scipy",
        module="scipy",
        pip_name="scipy",
        var="ek_obj",
        setup="import numpy as np\n"
        "from scipy import sparse\n"
        "ek_obj = sparse.csr_matrix(np.eye(4, dtype=np.float64))\n",
        equal=_scipy_sparse_equal,
    ),
    Specimen(
        key="scikit-learn",
        module="sklearn",
        pip_name="scikit-learn",
        var="ek_obj",
        setup="import numpy as np\n"
        "from sklearn.linear_model import LinearRegression\n"
        "_X = np.arange(20, dtype=np.float64).reshape(10, 2)\n"
        "_y = _X[:, 0] * 2.0 + _X[:, 1]\n"
        "ek_obj = LinearRegression().fit(_X, _y)\n",
        equal=_sklearn_equal,
    ),
    Specimen(
        key="matplotlib",
        module="matplotlib",
        pip_name="matplotlib",
        var="ek_obj",
        setup="import matplotlib\n"
        'matplotlib.use("Agg")\n'
        "import matplotlib.pyplot as plt\n"
        "ek_obj, _ax = plt.subplots()\n"
        "_ax.plot([0, 1, 2, 3], [3, 2, 1, 0])\n",
        equal=_mpl_figure_equal,
    ),
    Specimen(
        key="seaborn",
        module="seaborn",
        pip_name="seaborn",
        var="ek_obj",
        setup="import matplotlib\n"
        'matplotlib.use("Agg")\n'
        "import seaborn as sns\n"
        "ek_obj = sns.relplot(x=[1, 2, 3, 4], y=[1, 4, 9, 16])\n",
        equal=_seaborn_grid_equal,
    ),
    Specimen(
        key="opencv (cv2)",
        module="cv2",
        pip_name="opencv-python-headless",
        var="ek_obj",
        setup="import numpy as np\n"
        "import cv2\n"
        "_src = np.full((4, 4, 3), 127, dtype=np.uint8)\n"
        "ek_obj = cv2.cvtColor(_src, cv2.COLOR_BGR2GRAY)\n",
        equal=_array_equal,
    ),
    Specimen(
        key="requests",
        module="requests",
        pip_name="requests",
        var="ek_obj",
        setup="import requests\n"
        "ek_obj = requests.Response()\n"
        "ek_obj.status_code = 200\n"
        'ek_obj._content = b"elastic-kernel"\n'
        'ek_obj.url = "https://example.com"\n',
        equal=_requests_response_equal,
    ),
]

SPECIMENS_BY_KEY = {s.key: s for s in SPECIMENS}


def run_round_trip(spec: Specimen, workdir: str) -> str:
    """Drive record -> checkpoint -> load for ``spec`` and return its classification.

    Returns one of ``"Migrated"``, ``"Recomputed"`` or ``"Failed"``. Raises only on
    truly unexpected harness errors; ordinary failures map to ``"Failed"``.
    """
    from IPython.core.interactiveshell import InteractiveShell

    from elastic_notebook.elastic_notebook import ElasticNotebook

    os.makedirs(workdir, exist_ok=True)

    # --- record + checkpoint, forcing migration of anything serializable ---
    shell1 = InteractiveShell()
    en1 = ElasticNotebook(shell1, workdir)
    en1.manual_migration_speed = True
    en1.migration_speed_bps = 1e12
    en1.selector.migration_speed_bps = 1e12

    pre = set(shell1.user_ns.keys())
    shell1.run_cell(spec.setup)
    if spec.var not in shell1.user_ns:
        return "Failed"  # the snippet itself did not produce the object
    original = shell1.user_ns[spec.var]
    en1.record_event(spec.setup, pre, 0.0, 0.1)

    ckpt = os.path.join(workdir, "checkpoint.pickle")
    if en1.checkpoint(ckpt) is not True:
        return "Failed"
    migrated = spec.var in en1.vss_to_migrate

    # --- restore into a fresh shell and verify the value survived ---
    shell2 = InteractiveShell()
    en2 = ElasticNotebook(shell2, workdir)
    en2.load_checkpoint(ckpt)
    if spec.var not in shell2.user_ns:
        return "Failed"
    restored = shell2.user_ns[spec.var]
    try:
        if not spec.equal(original, restored):
            return "Failed"
    except Exception:
        return "Failed"

    return "Migrated" if migrated else "Recomputed"


def _run_isolated(key: str, workdir: str) -> dict:
    spec = SPECIMENS_BY_KEY[key]
    try:
        __import__(spec.module)
    except Exception as exc:  # library not installed in this environment
        return {
            "key": key,
            "classification": "Skipped",
            "detail": f"not installed: {exc}",
        }
    try:
        # Keep stdout clean for the JSON result: IPython echoes cell expression
        # values (e.g. ``Out[1]: ...``) to stdout, so route them to stderr.
        with contextlib.redirect_stdout(sys.stderr):
            classification = run_round_trip(spec, workdir)
        return {"key": key, "classification": classification, "detail": ""}
    except Exception as exc:  # pragma: no cover - defensive
        return {"key": key, "classification": "Failed", "detail": repr(exc)}


if __name__ == "__main__":
    _key = sys.argv[1]
    _workdir = sys.argv[2] if len(sys.argv) > 2 else tempfile.mkdtemp()
    print(json.dumps(_run_isolated(_key, _workdir)))
