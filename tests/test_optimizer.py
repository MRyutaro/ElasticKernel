"""Tests for OptimizerExact.select_vss on small synthetic graphs.

These pin the default checkpoint path's migrate-vs-recompute decision.
"""

from elastic_notebook.algorithm.optimizer_exact import OptimizerExact
from elastic_notebook.core.graph.graph import DependencyGraph


def _single_var_graph(size, cell_runtime):
    """Graph: one cell with no inputs producing a single variable `x`."""
    g = DependencyGraph()
    vs = g.create_variable_snapshot("x", False)
    g.add_cell_execution("x = f()", cell_runtime, 0.0, set(), {vs})
    vs.size = size
    return g, vs


def _run(graph, active_vs, migration_speed_bps=1):
    opt = OptimizerExact(migration_speed_bps=migration_speed_bps)
    opt.dependency_graph = graph
    opt.active_vss = {active_vs}
    opt.overlapping_vss = set()
    return opt.select_vss()


def test_large_variable_cheap_recompute_is_recomputed():
    # Huge migration cost, tiny recomputation cost -> recompute, do not migrate.
    g, vs = _single_var_graph(size=1_000_000, cell_runtime=0.001)
    vss_to_migrate, ces_to_recompute = _run(g, vs)
    assert vss_to_migrate == set()
    assert ces_to_recompute == {g.cell_executions[0]}


def test_expensive_cell_small_variable_is_migrated():
    # Tiny migration cost, huge recomputation cost -> migrate, do not recompute.
    g, vs = _single_var_graph(size=1, cell_runtime=1_000_000)
    vss_to_migrate, ces_to_recompute = _run(g, vs)
    assert vss_to_migrate == {vs}
    assert ces_to_recompute == set()
