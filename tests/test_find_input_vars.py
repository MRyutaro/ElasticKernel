"""Tests for find_input_vars (AST-based input variable detection).

Pins current behavior; do not change production code to satisfy these.
"""

from elastic_notebook.core.notebook.find_input_vars import find_input_vars


def _udf_helper():
    # Defined at module level so inspect.getsource() returns unindented source
    # (as a real notebook-defined UDF would be).
    return w + [0]  # noqa: F821 — `w` is resolved from user_ns at analysis time


def test_simple_reference(fake_shell):
    shell = fake_shell({"x": 1})
    inputs, fdefs = find_input_vars("y = x + 1", {"x"}, shell, set())
    assert inputs == {"x"}
    assert fdefs == set()


def test_assignment_target_is_not_input(fake_shell):
    # The assignment target `y` is a Store, not a Load, so it is not an input.
    shell = fake_shell({"x": 1})
    inputs, _ = find_input_vars("y = x + 1", {"x"}, shell, set())
    assert "y" not in inputs


def test_input_filtered_by_existing_variables(fake_shell):
    # `q` is read but is not an existing variable, so it is dropped.
    shell = fake_shell({"x": 1})
    inputs, _ = find_input_vars("z = x + q", {"x"}, shell, set())
    assert inputs == {"x"}


def test_aug_assign_counts_as_input(fake_shell):
    shell = fake_shell({"x": 1})
    inputs, _ = find_input_vars("x += 1", {"x"}, shell, set())
    assert inputs == {"x"}


def test_global_declaration_and_nonprimitive_local_read(fake_shell):
    # Inside a function, a non-primitive name read from the namespace is still
    # treated as an input; the `global` target is not.
    shell = fake_shell({"x": [1, 2, 3]})
    code = "def f():\n    global z\n    z = x\n"
    inputs, fdefs = find_input_vars(code, {"x"}, shell, set())
    assert inputs == {"x"}
    assert fdefs == {"f"}


def test_primitive_local_read_is_skipped(fake_shell):
    # A primitive read in local scope (not declared global) is intentionally
    # NOT counted as an input by the original ElasticNotebook heuristic.
    shell = fake_shell({"x": 1})
    code = "def f():\n    z = x\n    return z\n"
    inputs, _ = find_input_vars(code, {"x"}, shell, set())
    assert "x" not in inputs


def test_function_def_is_reported(fake_shell):
    shell = fake_shell({})
    code = "def myfunc():\n    return 1\n"
    inputs, fdefs = find_input_vars(code, set(), shell, set())
    assert fdefs == {"myfunc"}


def test_udf_recursion_finds_nested_input(fake_shell):
    # The cell calls helper(); helper reads non-primitive `w`. The recursion
    # into the UDF source should surface `w` as an input.
    shell = fake_shell({"helper": _udf_helper, "w": [1, 2, 3]})
    inputs, _ = find_input_vars("helper()", {"w", "helper"}, shell, {"helper"})
    assert "w" in inputs
