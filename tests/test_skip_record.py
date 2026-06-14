"""Tests for ElasticKernel's record-skip logic (issue #17).

The skip decision is now made by transforming the cell with IPython's input
transformer (the same one ``InteractiveShell.transform_cell`` uses) and then
checking, via AST analysis, whether the cell contains anything other than
magic/shell command calls. We exercise that path here without constructing a
(heavy) kernel instance by transforming the cell ourselves and calling the
static analysis helper directly.
"""

from IPython.core.inputtransformer2 import TransformerManager

from elastic_kernel.kernel import ElasticKernel

# Name-mangled access to the static analysis helper.
_is_pure_magic_cell = ElasticKernel._ElasticKernel__is_pure_magic_cell

_transformer = TransformerManager()


def _skip(code):
    """Transform the raw cell the way the kernel does, then decide to skip."""
    return _is_pure_magic_cell(_transformer.transform_cell(code))


def test_shell_command_is_skipped():
    assert _skip("!ls -la") is True


def test_line_magic_is_skipped():
    assert _skip("%timeit foo()") is True


def test_cell_magic_is_skipped():
    assert _skip("%%bash\necho hi") is True


def test_leading_whitespace_still_skipped():
    assert _skip("   %matplotlib inline") is True


def test_plain_python_is_recorded():
    assert _skip("x = 1") is False


def test_string_with_percent_inside_is_recorded():
    assert _skip("y = '100%'") is False


def test_magic_line_mixed_with_python_is_recorded():
    # issue #17: a magic line followed by real code must NOT skip the whole cell.
    assert _skip("%time\na = [0] * (2 ** 25)") is False


def test_shell_line_mixed_with_python_is_recorded():
    assert _skip("!echo hi\nb = 42") is False


def test_empty_cell_is_skipped():
    assert _skip("") is True
    assert _skip("   \n  ") is True


def test_multiple_magics_only_is_skipped():
    assert _skip("%matplotlib inline\n%load_ext autoreload") is True
