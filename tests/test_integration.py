"""End-to-end integration test: record_event -> checkpoint -> load_checkpoint.

Runs without a Jupyter server by driving a real IPython InteractiveShell
directly. If the IPython shell cannot be constructed in this environment, the
test skips.
"""

import pytest

pytest.importorskip("IPython")

from IPython.core.interactiveshell import InteractiveShell  # noqa: E402

from elastic_notebook.elastic_notebook import ElasticNotebook  # noqa: E402


def _run_and_record(shell, en, code):
    pre = set(shell.user_ns.keys())
    shell.run_cell(code)
    en.record_event(code, pre, 0.0, 0.1)


def test_record_checkpoint_restore_round_trip(tmp_path):
    try:
        shell1 = InteractiveShell()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Could not construct InteractiveShell: {exc}")

    en1 = ElasticNotebook(shell1, str(tmp_path))
    _run_and_record(shell1, en1, "x = 42")
    _run_and_record(shell1, en1, "import numpy\na = numpy.arange(10)")

    path = str(tmp_path / "checkpoint.pickle")
    assert en1.checkpoint(path) is True

    # Restore into a fresh shell/notebook.
    shell2 = InteractiveShell()
    en2 = ElasticNotebook(shell2, str(tmp_path))
    en2.load_checkpoint(path)

    assert shell2.user_ns["x"] == 42
    assert list(shell2.user_ns["a"]) == list(range(10))
