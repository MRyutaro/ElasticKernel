"""Tests for ElasticKernel.__skip_record (magic-command skip logic).

__skip_record does not use instance state, so it can be exercised via the
name-mangled function without constructing a (heavy) kernel instance.
"""

from elastic_kernel.kernel import ElasticKernel

# Name-mangled access to the private method.
_skip_record = ElasticKernel._ElasticKernel__skip_record


def test_shell_command_is_skipped():
    assert _skip_record(None, "!ls -la") is True


def test_line_magic_is_skipped():
    assert _skip_record(None, "%timeit foo()") is True


def test_cell_magic_is_skipped():
    assert _skip_record(None, "%%bash\necho hi") is True


def test_leading_whitespace_still_skipped():
    assert _skip_record(None, "   %matplotlib inline") is True


def test_plain_python_is_recorded():
    assert _skip_record(None, "x = 1") is False


def test_string_with_percent_inside_is_recorded():
    # The magic check only looks at the (stripped) start of the cell.
    assert _skip_record(None, "y = '100%'") is False
