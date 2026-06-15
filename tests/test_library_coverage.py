"""Checkpoint round-trip coverage for supported data-science libraries (issue #48).

For each ``(library, object_type)`` specimen in
:data:`tests.library_specimens.SPECIMENS`, build the object and verify both ElasticKernel
restore paths:

- ElasticKernel must **never silently restore a wrong value** (data corruption) on either
  path -- this is the hard invariant for every specimen.
- Outside the documented :data:`~tests.library_specimens.KNOWN_LIMITATIONS`, **Recompute**
  must reproduce the object and **Migrate** must either reproduce it or cleanly report it
  as unserializable.

A library that is not installed is skipped; the dedicated `library-coverage` CI workflow
installs the `coverage` dependency group so all specimens actually run there. The
Migrate/Recompute table for the README is produced by ``scripts/library_coverage.py``,
whose drift check guards against any specimen regressing.
"""

import pytest

pytest.importorskip("IPython")

from tests.library_specimens import (  # noqa: E402
    KNOWN_LIMITATIONS,
    SPECIMENS,
    run_paths,
)


@pytest.mark.parametrize("spec", SPECIMENS, ids=[s.key for s in SPECIMENS])
def test_library_restore_paths(spec, tmp_path):
    pytest.importorskip(spec.module)
    result = run_paths(spec, str(tmp_path))
    label = f"{spec.library} / {spec.object_type}"

    # Hard invariant for every object: never silently restore a corrupted value.
    assert result["migrate"] != "wrong", f"{label}: migrate restored a wrong value"
    assert result["recompute"] != "wrong", f"{label}: recompute restored a wrong value"

    if spec.key in KNOWN_LIMITATIONS:
        pytest.xfail(f"{label}: documented limitation ({spec.key})")

    assert (
        result["recompute"] == "ok"
    ), f"{label}: recompute did not reproduce the object (got {result['recompute']!r})"
    assert result["migrate"] in {
        "ok",
        "unserializable",
    }, f"{label}: migrate path is broken (got {result['migrate']!r})"
