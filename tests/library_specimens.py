"""Single source of truth for the library checkpoint-coverage matrix (issue #48).

Each :class:`Specimen` is one ``(library, object_type)`` pair: a deterministic snippet
that builds a representative object of that type, plus an equality predicate for it. A
library exposes many object types, so several specimens per library widen the coverage
(e.g. numpy is checked as an ndarray, a structured array, a masked array and a
datetime64 array) -- but it is still a sample, not an exhaustive guarantee.

ElasticKernel can restore a checkpointed object in two ways, and a cost optimizer
(min-cut) decides which one to use per object -- neither is merely a "fallback":

- **Migrate**   -- serialize the object with dill and reload it.
- **Recompute** -- re-run the cell that produced it.

:func:`run_paths` exercises *both* restore paths independently by forcing the optimizer's
hand (``manual_migration_speed`` with an effectively infinite or near-zero
``migration_speed_bps``) and reports, for each path, whether the object was reproduced:

- migrate:   ``ok`` (migrated + value matches) / ``unserializable`` (could not serialize,
             so this path is N/A) / ``wrong`` (migrated but value differs) / ``error``.
- recompute: ``ok`` (recomputed + value matches) / ``wrong`` / ``error``.

Run a single specimen in isolation (used by scripts/library_coverage.py for crash
containment)::

    python -m tests.library_specimens <key> <workdir>

which prints one JSON object ``{"key", "library", "object_type", "migrate",
"recompute", "detail"}`` to stdout.
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
    key: str  # unique id, e.g. "numpy-ndarray"
    library: str  # library name in the README table
    object_type: str  # the concrete object type that is checkpointed
    module: str  # top-level import name (for importorskip / availability checks)
    pip_name: str  # PyPI distribution name (for the `coverage` dependency group)
    var: str  # variable that holds the representative object after `setup` runs
    setup: str  # deterministic, recomputable code that creates `var`
    equal: Callable[[object, object], bool]  # value-equality for the restored object


# --- equality predicates -------------------------------------------------------------


def _array_equal(a, b):
    import numpy as np

    return np.array_equal(a, b)


def _masked_equal(a, b):
    import numpy as np

    return np.array_equal(a.filled(0), b.filled(0)) and np.array_equal(
        np.ma.getmaskarray(a), np.ma.getmaskarray(b)
    )


def _pandas_equal(a, b):
    return a.equals(b)


def _scipy_sparse_equal(a, b):
    import numpy as np

    return a.shape == b.shape and np.array_equal(a.toarray(), b.toarray())


def _scipy_frozen_equal(a, b):
    return a.dist.name == b.dist.name and a.args == b.args and a.kwds == b.kwds


def _sklearn_linear_equal(a, b):
    import numpy as np

    return np.allclose(a.coef_, b.coef_) and np.allclose(a.intercept_, b.intercept_)


def _sklearn_scaler_equal(a, b):
    import numpy as np

    return np.allclose(a.mean_, b.mean_) and np.allclose(a.scale_, b.scale_)


def _rf_equal(a, b):
    import numpy as np

    x = np.arange(40, dtype=np.float64).reshape(20, 2)
    return np.array_equal(a.predict(x), b.predict(x))


def _mpl_lines_equal(a, b):
    import numpy as np

    ya = a.axes[0].lines[0].get_ydata()
    yb = b.axes[0].lines[0].get_ydata()
    return np.array_equal(ya, yb)


def _mpl_image_equal(a, b):
    import numpy as np

    return np.array_equal(
        a.axes[0].images[0].get_array(), b.axes[0].images[0].get_array()
    )


def _mpl_axes_equal(a, b):
    return type(a) is type(b) and len(a.collections) == len(b.collections)


def _seaborn_grid_equal(a, b):
    return type(a) is type(b) and len(list(a.axes.flat)) == len(list(b.axes.flat))


def _requests_response_equal(a, b):
    return a.status_code == b.status_code and a.content == b.content


def _requests_session_equal(a, b):
    return type(a) is type(b) and a.headers.get("X-Elastic") == b.headers.get(
        "X-Elastic"
    )


# --- specimens -----------------------------------------------------------------------

SPECIMENS: List[Specimen] = [
    # numpy ---------------------------------------------------------------------------
    Specimen(
        key="numpy-ndarray",
        library="numpy",
        object_type="ndarray",
        module="numpy",
        pip_name="numpy",
        var="ek_obj",
        setup="import numpy as np\n"
        "ek_obj = np.arange(12, dtype=np.int64).reshape(3, 4)\n",
        equal=_array_equal,
    ),
    Specimen(
        key="numpy-structured",
        library="numpy",
        object_type="structured array",
        module="numpy",
        pip_name="numpy",
        var="ek_obj",
        setup="import numpy as np\n"
        'ek_obj = np.array([(1, 2.0), (3, 4.0)], dtype=[("a", "i4"), ("b", "f8")])\n',
        equal=_array_equal,
    ),
    Specimen(
        key="numpy-masked",
        library="numpy",
        object_type="masked array",
        module="numpy",
        pip_name="numpy",
        var="ek_obj",
        setup="import numpy as np\n"
        "ek_obj = np.ma.masked_array([1, 2, 3, 4], mask=[0, 1, 0, 1])\n",
        equal=_masked_equal,
    ),
    Specimen(
        key="numpy-datetime64",
        library="numpy",
        object_type="datetime64 array",
        module="numpy",
        pip_name="numpy",
        var="ek_obj",
        setup="import numpy as np\n"
        'ek_obj = np.array(["2020-01-01", "2020-06-15"], dtype="datetime64[D]")\n',
        equal=_array_equal,
    ),
    # pandas --------------------------------------------------------------------------
    Specimen(
        key="pandas-dataframe",
        library="pandas",
        object_type="DataFrame",
        module="pandas",
        pip_name="pandas",
        var="ek_obj",
        setup="import pandas as pd\n"
        'ek_obj = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})\n',
        equal=_pandas_equal,
    ),
    Specimen(
        key="pandas-series",
        library="pandas",
        object_type="Series",
        module="pandas",
        pip_name="pandas",
        var="ek_obj",
        setup="import pandas as pd\n" 'ek_obj = pd.Series([1.0, 2.0, 3.0], name="x")\n',
        equal=_pandas_equal,
    ),
    Specimen(
        key="pandas-categorical",
        library="pandas",
        object_type="Series (category)",
        module="pandas",
        pip_name="pandas",
        var="ek_obj",
        setup="import pandas as pd\n"
        'ek_obj = pd.Series(["a", "b", "a", "c"], dtype="category")\n',
        equal=_pandas_equal,
    ),
    Specimen(
        key="pandas-timeseries",
        library="pandas",
        object_type="DataFrame (DatetimeIndex)",
        module="pandas",
        pip_name="pandas",
        var="ek_obj",
        setup="import pandas as pd\n"
        'ek_obj = pd.DataFrame({"v": [1, 2, 3]}, '
        'index=pd.date_range("2020-01-01", periods=3, freq="D"))\n',
        equal=_pandas_equal,
    ),
    # scipy ---------------------------------------------------------------------------
    Specimen(
        key="scipy-csr",
        library="scipy",
        object_type="csr_matrix (sparse)",
        module="scipy",
        pip_name="scipy",
        var="ek_obj",
        setup="import numpy as np\n"
        "from scipy import sparse\n"
        "ek_obj = sparse.csr_matrix(np.eye(4, dtype=np.float64))\n",
        equal=_scipy_sparse_equal,
    ),
    Specimen(
        key="scipy-csc",
        library="scipy",
        object_type="csc_matrix (sparse)",
        module="scipy",
        pip_name="scipy",
        var="ek_obj",
        setup="import numpy as np\n"
        "from scipy import sparse\n"
        "ek_obj = sparse.csc_matrix(np.eye(4, dtype=np.float64))\n",
        equal=_scipy_sparse_equal,
    ),
    Specimen(
        key="scipy-frozen-dist",
        library="scipy",
        object_type="stats frozen distribution",
        module="scipy",
        pip_name="scipy",
        var="ek_obj",
        setup="from scipy import stats\n" "ek_obj = stats.norm(loc=0.0, scale=1.0)\n",
        equal=_scipy_frozen_equal,
    ),
    # scikit-learn --------------------------------------------------------------------
    Specimen(
        key="sklearn-linreg",
        library="scikit-learn",
        object_type="LinearRegression (fitted)",
        module="sklearn",
        pip_name="scikit-learn",
        var="ek_obj",
        setup="import numpy as np\n"
        "from sklearn.linear_model import LinearRegression\n"
        "_X = np.arange(20, dtype=np.float64).reshape(10, 2)\n"
        "_y = _X[:, 0] * 2.0 + _X[:, 1]\n"
        "ek_obj = LinearRegression().fit(_X, _y)\n",
        equal=_sklearn_linear_equal,
    ),
    Specimen(
        key="sklearn-scaler",
        library="scikit-learn",
        object_type="StandardScaler (fitted)",
        module="sklearn",
        pip_name="scikit-learn",
        var="ek_obj",
        setup="import numpy as np\n"
        "from sklearn.preprocessing import StandardScaler\n"
        "_X = np.arange(20, dtype=np.float64).reshape(10, 2)\n"
        "ek_obj = StandardScaler().fit(_X)\n",
        equal=_sklearn_scaler_equal,
    ),
    Specimen(
        key="sklearn-randomforest",
        library="scikit-learn",
        object_type="RandomForestClassifier (fitted)",
        module="sklearn",
        pip_name="scikit-learn",
        var="ek_obj",
        setup="import numpy as np\n"
        "from sklearn.ensemble import RandomForestClassifier\n"
        "_X = np.arange(40, dtype=np.float64).reshape(20, 2)\n"
        "_y = np.arange(20) % 2\n"
        "ek_obj = RandomForestClassifier(n_estimators=5, random_state=0).fit(_X, _y)\n",
        equal=_rf_equal,
    ),
    # matplotlib ----------------------------------------------------------------------
    Specimen(
        key="matplotlib-figure-line",
        library="matplotlib",
        object_type="Figure (line plot)",
        module="matplotlib",
        pip_name="matplotlib",
        var="ek_obj",
        setup="import matplotlib\n"
        'matplotlib.use("Agg")\n'
        "import matplotlib.pyplot as plt\n"
        "ek_obj, _ax = plt.subplots()\n"
        "_ax.plot([0, 1, 2, 3], [3, 2, 1, 0])\n",
        equal=_mpl_lines_equal,
    ),
    Specimen(
        key="matplotlib-figure-image",
        library="matplotlib",
        object_type="Figure (imshow)",
        module="matplotlib",
        pip_name="matplotlib",
        var="ek_obj",
        setup="import matplotlib\n"
        'matplotlib.use("Agg")\n'
        "import matplotlib.pyplot as plt\n"
        "import numpy as np\n"
        "ek_obj, _ax = plt.subplots()\n"
        "_ax.imshow(np.arange(16, dtype=np.float64).reshape(4, 4))\n",
        equal=_mpl_image_equal,
    ),
    # seaborn -------------------------------------------------------------------------
    Specimen(
        key="seaborn-facetgrid",
        library="seaborn",
        object_type="FacetGrid",
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
        key="seaborn-axes",
        library="seaborn",
        object_type="Axes (scatterplot)",
        module="seaborn",
        pip_name="seaborn",
        var="ek_obj",
        setup="import matplotlib\n"
        'matplotlib.use("Agg")\n'
        "import seaborn as sns\n"
        "ek_obj = sns.scatterplot(x=[1, 2, 3, 4], y=[4, 3, 2, 1])\n",
        equal=_mpl_axes_equal,
    ),
    # opencv --------------------------------------------------------------------------
    Specimen(
        key="opencv-gray",
        library="opencv (cv2)",
        object_type="ndarray (grayscale image)",
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
        key="opencv-color",
        library="opencv (cv2)",
        object_type="ndarray (color image)",
        module="cv2",
        pip_name="opencv-python-headless",
        var="ek_obj",
        setup="import numpy as np\n"
        "import cv2\n"
        "_src = np.arange(48, dtype=np.uint8).reshape(4, 4, 3)\n"
        "ek_obj = cv2.cvtColor(_src, cv2.COLOR_BGR2RGB)\n",
        equal=_array_equal,
    ),
    # requests ------------------------------------------------------------------------
    Specimen(
        key="requests-response",
        library="requests",
        object_type="Response",
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
    Specimen(
        key="requests-session",
        library="requests",
        object_type="Session",
        module="requests",
        pip_name="requests",
        var="ek_obj",
        setup="import requests\n"
        "ek_obj = requests.Session()\n"
        'ek_obj.headers.update({"X-Elastic": "kernel"})\n',
        equal=_requests_session_equal,
    ),
]

SPECIMENS_BY_KEY = {s.key: s for s in SPECIMENS}

# Object types that ElasticKernel cannot currently checkpoint, with the reason. These are
# documented (shown as ❌ in the coverage table) rather than hidden, and the test gate
# tolerates them instead of asserting success -- but the drift check still guards against
# anything *else* regressing into this state.
#   (none currently -- numpy-datetime64 was fixed in #60.)
KNOWN_LIMITATIONS: set = set()

# Force the optimizer one way or the other. A near-infinite migration speed makes
# migrating effectively free (so anything serializable is migrated); a near-zero speed
# makes migrating ruinously expensive (so everything is recomputed).
_FORCE_SPEED = {"migrate": 1e12, "recompute": 1e-9}


def _one_path(spec: Specimen, workdir: str, force: str) -> str:
    """Run record -> checkpoint -> load for ``spec`` forcing one restore path.

    ``force`` is ``"migrate"`` or ``"recompute"``. See module docstring for return values.
    """
    from IPython.core.interactiveshell import InteractiveShell

    from elastic_notebook.elastic_notebook import ElasticNotebook

    os.makedirs(workdir, exist_ok=True)

    try:
        shell1 = InteractiveShell()
        en1 = ElasticNotebook(shell1, workdir)
        en1.manual_migration_speed = True
        en1.migration_speed_bps = _FORCE_SPEED[force]
        en1.selector.migration_speed_bps = _FORCE_SPEED[force]

        pre = set(shell1.user_ns.keys())
        shell1.run_cell(spec.setup)
        if spec.var not in shell1.user_ns:
            return "error"  # the snippet itself did not produce the object
        original = shell1.user_ns[spec.var]
        en1.record_event(spec.setup, pre, 0.0, 0.1)

        ckpt = os.path.join(workdir, "checkpoint.pickle")
        if en1.checkpoint(ckpt) is not True:
            return "error"
        in_migrate = spec.var in en1.vss_to_migrate

        shell2 = InteractiveShell()
        en2 = ElasticNotebook(shell2, workdir)
        en2.load_checkpoint(ckpt)
        if spec.var not in shell2.user_ns:
            return "wrong"
        restored = shell2.user_ns[spec.var]
    except Exception:
        # ElasticKernel raised while checkpointing/restoring this object (e.g. its hash
        # cannot be computed): a hard limitation, surfaced as a failure in the table.
        return "error"

    try:
        value_ok = bool(spec.equal(original, restored))
    except Exception:
        value_ok = False

    if force == "migrate":
        if not in_migrate:
            # Could not be serialized, so it fell to the recompute set: the migrate
            # path does not apply to this object (it is not a failure).
            return "unserializable"
        return "ok" if value_ok else "wrong"
    return "ok" if value_ok else "wrong"


def run_paths(spec: Specimen, workdir: str) -> dict:
    """Verify both restore paths for ``spec`` and return ``{"migrate", "recompute"}``."""
    return {
        "migrate": _one_path(spec, os.path.join(workdir, "migrate"), "migrate"),
        "recompute": _one_path(spec, os.path.join(workdir, "recompute"), "recompute"),
    }


def _run_isolated(key: str, workdir: str) -> dict:
    spec = SPECIMENS_BY_KEY[key]
    base = {"key": key, "library": spec.library, "object_type": spec.object_type}
    try:
        __import__(spec.module)
    except Exception as exc:  # library not installed in this environment
        return {
            **base,
            "migrate": "skipped",
            "recompute": "skipped",
            "detail": str(exc),
        }
    try:
        # Keep stdout clean for the JSON result: IPython echoes cell expression values
        # (e.g. ``Out[1]: ...``) to stdout, so route them to stderr.
        with contextlib.redirect_stdout(sys.stderr):
            paths = run_paths(spec, workdir)
        return {**base, **paths, "detail": ""}
    except Exception as exc:  # pragma: no cover - defensive
        return {**base, "migrate": "error", "recompute": "error", "detail": repr(exc)}


if __name__ == "__main__":
    _key = sys.argv[1]
    _workdir = sys.argv[2] if len(sys.argv) > 2 else tempfile.mkdtemp()
    print(json.dumps(_run_isolated(_key, _workdir)))
