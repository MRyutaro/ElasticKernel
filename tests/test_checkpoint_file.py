"""Tests for the CheckpointFile builder (set/get round-trip)."""

from elastic_notebook.core.common.checkpoint_file import CheckpointFile
from elastic_notebook.core.graph.graph import DependencyGraph


def test_builder_sets_and_gets_all_fields():
    graph = DependencyGraph()
    variables = {"a": [1]}
    vss_migrate = {"vs1"}
    vss_recompute = {"vs2"}
    ces_recompute = {"ce1"}
    recomputation_ces = {"ce1": {"ce0"}}
    serialization_order = [["vs1"]]
    udfs = {"f"}

    cf = (
        CheckpointFile()
        .with_dependency_graph(graph)
        .with_variables(variables)
        .with_vss_to_migrate(vss_migrate)
        .with_vss_to_recompute(vss_recompute)
        .with_ces_to_recompute(ces_recompute)
        .with_recomputation_ces(recomputation_ces)
        .with_serialization_order(serialization_order)
        .with_udfs(udfs)
    )

    assert cf.get_dependency_graph() is graph
    assert cf.get_variables() == variables
    assert cf.get_vss_to_migrate() == vss_migrate
    assert cf.get_vss_to_recompute() == vss_recompute
    assert cf.get_ces_to_recompute() == ces_recompute
    assert cf.get_recomputation_ces() == recomputation_ces
    assert cf.get_serialization_order() == serialization_order
    assert cf.get_udfs() == udfs


def test_defaults_are_none():
    cf = CheckpointFile()
    assert cf.get_dependency_graph() is None
    assert cf.get_variables() is None
    assert cf.get_udfs() is None
