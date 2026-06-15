"""Checkpoint round-trip coverage for supported data-science libraries (issue #48).

For each library in :data:`tests.library_specimens.SPECIMENS`, build a representative
object and assert it survives a ``record_event -> checkpoint -> load_checkpoint`` round
trip -- either by being migrated (dill-serialized) or recomputed (cell re-run). A library
that is not installed is skipped; the dedicated `library-coverage` CI workflow installs
the `coverage` dependency group so all specimens actually run there.

The three-way Migrated / Recomputed / Failed table for the README is produced by
``scripts/library_coverage.py`` (subprocess-isolated); this test is the pass/fail gate.
"""

import pytest

pytest.importorskip("IPython")

from tests.library_specimens import SPECIMENS, run_round_trip  # noqa: E402


@pytest.mark.parametrize("spec", SPECIMENS, ids=[s.key for s in SPECIMENS])
def test_library_round_trip(spec, tmp_path):
    pytest.importorskip(spec.module)
    classification = run_round_trip(spec, str(tmp_path))
    assert classification in {"Migrated", "Recomputed"}, (
        f"{spec.key}: checkpoint round trip did not restore the object "
        f"(classification={classification!r})"
    )
