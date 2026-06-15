"""Checkpoint round-trip coverage for supported data-science libraries (issue #48).

For each library in :data:`tests.library_specimens.SPECIMENS`, build a representative
object and verify both ElasticKernel restore paths:

- **Recompute** must always reproduce the object (re-running a deterministic cell is the
  safety net that guarantees nothing is lost).
- **Migrate** must either reproduce it (serializable) or cleanly report it as
  unserializable -- it must never silently restore a *wrong* value.

A library that is not installed is skipped; the dedicated `library-coverage` CI workflow
installs the `coverage` dependency group so all specimens actually run there. The
Migrate/Recompute table for the README is produced by ``scripts/library_coverage.py``.
"""

import pytest

pytest.importorskip("IPython")

from tests.library_specimens import SPECIMENS, run_paths  # noqa: E402


@pytest.mark.parametrize("spec", SPECIMENS, ids=[s.key for s in SPECIMENS])
def test_library_restore_paths(spec, tmp_path):
    pytest.importorskip(spec.module)
    result = run_paths(spec, str(tmp_path))

    assert result["recompute"] == "ok", (
        f"{spec.key} ({spec.object_type}): recompute did not reproduce the object "
        f"(got {result['recompute']!r})"
    )
    assert result["migrate"] in {"ok", "unserializable"}, (
        f"{spec.key} ({spec.object_type}): migrate path is broken "
        f"(got {result['migrate']!r})"
    )
