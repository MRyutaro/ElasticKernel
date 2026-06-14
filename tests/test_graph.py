"""Tests for DependencyGraph and update_graph."""

from elastic_notebook.core.graph.graph import DependencyGraph
from elastic_notebook.core.notebook.update_graph import update_graph


def test_variable_snapshot_versioning():
    g = DependencyGraph()
    vs0 = g.create_variable_snapshot("x", False)
    vs1 = g.create_variable_snapshot("x", False)
    assert vs0.version == 0
    assert vs1.version == 1
    assert g.variable_snapshots["x"] == [vs0, vs1]


def test_add_cell_execution_wires_edges():
    g = DependencyGraph()
    src = g.create_variable_snapshot("a", False)
    dst = g.create_variable_snapshot("b", False)
    g.add_cell_execution("b = a", 0.5, 0.0, {src}, {dst})

    ce = g.cell_executions[0]
    assert ce.cell_num == 0
    assert ce in src.input_ces
    assert dst.output_ce is ce


def test_cell_num_increments():
    g = DependencyGraph()
    g.add_cell_execution("c1", 0.0, 0.0, set(), set())
    g.add_cell_execution("c2", 0.0, 0.0, set(), set())
    assert [ce.cell_num for ce in g.cell_executions] == [0, 1]


def test_update_graph_connects_input_to_new_output():
    g = DependencyGraph()
    # Cell 0 creates x.
    update_graph("x = 1", 0.1, 0.0, set(), {"x"}, set(), g)
    # Cell 1 reads x and creates y.
    update_graph("y = x", 0.1, 0.0, {"x"}, {"y"}, set(), g)

    assert len(g.cell_executions) == 2
    vs_x = g.variable_snapshots["x"][-1]
    vs_y = g.variable_snapshots["y"][-1]
    ce1 = g.cell_executions[1]

    # The second CE depends on x and produces y.
    assert ce1 in vs_x.input_ces
    assert vs_y.output_ce is ce1


def test_update_graph_deletion_marks_vs_deleted():
    g = DependencyGraph()
    update_graph("x = 1", 0.1, 0.0, set(), {"x"}, set(), g)
    update_graph("del x", 0.1, 0.0, set(), set(), {"x"}, g)

    # A new VS is created for the deletion, flagged as deleted.
    deletion_vs = g.variable_snapshots["x"][-1]
    assert deletion_vs.deleted is True
