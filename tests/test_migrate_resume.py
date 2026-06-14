"""Round-trip tests for migrate() -> resume() and the fault-tolerance path.

The checkpoint file format (dill: metadata, then one variable group per entry
in serialization_order) must not change. These tests guard it.
"""

import dill
import numpy as np

from elastic_notebook.core.common.checkpoint_file import CheckpointFile
from elastic_notebook.core.graph.graph import DependencyGraph
from elastic_notebook.core.io.migrate import migrate
from elastic_notebook.core.io.recover import resume


def _flatten(variables):
    """variables is {cell_num: [(vs, obj), ...]} -> {name: obj}."""
    return {vs.name: obj for pairs in variables.values() for (vs, obj) in pairs}


def test_migrate_resume_round_trip(fake_shell, tmp_path):
    g = DependencyGraph()
    vs_x = g.create_variable_snapshot("x", False)
    vs_a = g.create_variable_snapshot("a", False)
    g.add_cell_execution("x = 42; a = arange(3)", 0.1, 0.0, set(), {vs_x, vs_a})

    shell = fake_shell({"x": 42, "a": np.arange(3)})
    path = str(tmp_path / "checkpoint.pickle")

    migrate(
        graph=g,
        shell=shell,
        vss_to_migrate={vs_x, vs_a},
        vss_to_recompute=set(),
        ces_to_recompute=set(),
        udfs={"foo"},
        recomputation_ces={},
        overlapping_vss=set(),
        filename=path,
    )

    graph2, variables, ces_to_recompute, udfs = resume(path)

    recovered = _flatten(variables)
    assert recovered["x"] == 42
    assert np.array_equal(recovered["a"], np.arange(3))
    assert udfs == {"foo"}
    assert ces_to_recompute == set()
    assert isinstance(graph2, DependencyGraph)


def test_resume_returns_ces_to_recompute_from_file(fake_shell, tmp_path):
    # ces_to_recompute written to the checkpoint is returned on resume.
    g = DependencyGraph()
    vs_x = g.create_variable_snapshot("x", False)
    g.add_cell_execution("x = 42", 0.1, 0.0, set(), {vs_x})
    ce0 = g.cell_executions[0]

    shell = fake_shell({"x": 42})
    path = str(tmp_path / "checkpoint.pickle")

    migrate(
        graph=g,
        shell=shell,
        vss_to_migrate={vs_x},
        vss_to_recompute=set(),
        ces_to_recompute={ce0},
        udfs=set(),
        recomputation_ces={},
        overlapping_vss=set(),
        filename=path,
    )

    _, _, ces_to_recompute, _ = resume(path)
    assert len(ces_to_recompute) == 1
    assert next(iter(ces_to_recompute)).cell_num == 0


def test_resume_tolerates_corrupt_variable_group(tmp_path):
    """A variable group that fails to unpickle must not crash resume().

    D-2: the current implementation re-reads the whole file at recover.py:53,
    which OVERWRITES the in-memory metadata and therefore DISCARDS the
    ces_to_recompute additions made in the except-branch. So the fault-tolerance
    fallback is effectively a no-op today. This test pins that buggy behavior;
    it must be flipped (ces_to_recompute should contain ce0) once D-2 is fixed
    in Phase 4.
    """
    g = DependencyGraph()
    vs_x = g.create_variable_snapshot("x", False)
    g.add_cell_execution("x = 1", 0.1, 0.0, set(), {vs_x})
    ce0 = g.cell_executions[0]

    metadata = (
        CheckpointFile()
        .with_dependency_graph(g)
        .with_variables({})
        .with_vss_to_migrate({vs_x})
        .with_vss_to_recompute(set())
        .with_ces_to_recompute(set())
        .with_recomputation_ces({ce0: {ce0}})
        .with_serialization_order([[vs_x]])
        .with_udfs(set())
    )

    path = tmp_path / "corrupt.pickle"
    with open(path, "wb") as f:
        dill.dump(metadata, f)
        # Where the first variable group should be: write non-pickle garbage.
        f.write(b"this is not a valid pickle stream")

    # resume must not raise even though the variable group is unreadable.
    _, variables, ces_to_recompute, _ = resume(str(path))

    # No variables were recovered.
    assert dict(variables) == {}
    # D-2 (current/buggy): the recompute fallback is discarded by the re-read.
    # Flip this assertion to `len(ces_to_recompute) == 1` after fixing D-2.
    assert ces_to_recompute == set()
