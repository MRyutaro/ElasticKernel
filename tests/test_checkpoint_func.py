"""Tests for the checkpoint() orchestration function.

D-12: the overlapping-VS detection referenced fingerprint_dict[name] without an
`in` guard, which would raise KeyError if an active VS lacked a fingerprint
entry. The guard makes checkpoint() tolerate a missing fingerprint.
"""

from elastic_notebook.algorithm.optimizer_exact import OptimizerExact
from elastic_notebook.core.graph.graph import DependencyGraph
from elastic_notebook.core.mutation.fingerprint import construct_fingerprint
from elastic_notebook.core.notebook.checkpoint import checkpoint


def test_checkpoint_tolerates_missing_fingerprint(tmp_path, fake_shell):
    g = DependencyGraph()
    vs_x = g.create_variable_snapshot("x", False)
    vs_y = g.create_variable_snapshot("y", False)
    g.add_cell_execution("x = [1, 2, 3]; y = [4, 5, 6]", 0.1, 0.0, set(), {vs_x, vs_y})

    shell = fake_shell({"x": [1, 2, 3], "y": [4, 5, 6]})
    profile_dict = {"idgraph": 0.0, "representation": 0.0}
    # Only x has a fingerprint; y is intentionally missing (D-12 guard target).
    fingerprint_dict = {"x": construct_fingerprint(shell.user_ns["x"], profile_dict)}

    selector = OptimizerExact(migration_speed_bps=1)
    path = str(tmp_path / "ckpt.pickle")

    # Must not raise KeyError despite y missing from fingerprint_dict.
    migrate_success, _, _ = checkpoint(
        g, shell, fingerprint_dict, selector, set(), path, profile_dict
    )
    assert migrate_success is True
