"""Tests for the ID graph (identity-structure tracking)."""

from elastic_notebook.core.mutation.id_graph import (
    construct_id_graph,
    is_root_equals,
    is_structure_equals,
)


def test_list_structure_equal_to_itself():
    x = [1, 2, 3]
    g1, ids1 = construct_id_graph(x)
    g2, ids2 = construct_id_graph(x)
    assert ids1 == ids2
    assert is_structure_equals(g1, g2)
    assert is_root_equals(g1, g2)


def test_nested_list_ids_include_children():
    inner = [1, 2]
    outer = [inner]
    _, ids = construct_id_graph(outer)
    # Both the outer and the (non-primitive) inner list are reachable.
    assert id(outer) in ids
    assert id(inner) in ids


def test_dict_keys_and_values_tracked():
    k = (1, 2)  # non-primitive key (tuple)
    v = [3, 4]  # non-primitive value
    d = {k: v}
    _, ids = construct_id_graph(d)
    assert id(d) in ids
    assert id(k) in ids
    assert id(v) in ids


def test_shared_reference_recorded_once():
    shared = [0]
    container = [shared, shared]
    g, ids = construct_id_graph(container)
    # The shared object appears once in the id set.
    assert id(shared) in ids
    # The two child nodes point at the same node object (cycle/shared handling).
    assert g.child_nodes[0] is g.child_nodes[1]


def test_cyclic_reference_terminates():
    a = []
    a.append(a)  # self-referential list
    g, ids = construct_id_graph(a)
    assert id(a) in ids
    # The single child node is the node itself (handled via visited set).
    assert g.child_nodes[0] is g


def test_different_objects_not_root_equal():
    # Keep both objects alive so CPython cannot reuse the first list's id for
    # the second (which would make their root nodes compare equal).
    a = [1, 2, 3]
    b = [1, 2, 3]  # equal value, different identity
    g1, _ = construct_id_graph(a)
    g2, _ = construct_id_graph(b)
    assert not is_root_equals(g1, g2)


def test_none_graphs():
    g_none, ids = construct_id_graph(None)
    assert g_none is None
    assert ids == set()
    assert is_structure_equals(None, None)
    assert is_root_equals(None, None)
    assert not is_root_equals(None, construct_id_graph([1])[0])
