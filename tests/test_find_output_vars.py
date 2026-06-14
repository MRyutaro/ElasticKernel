"""Tests for find_created_deleted_vars (namespace diffing)."""

from elastic_notebook.core.notebook.find_output_vars import find_created_deleted_vars


def test_created_variables():
    created, deleted = find_created_deleted_vars({"x"}, {"x", "y", "z"})
    assert created == {"y", "z"}
    assert deleted == set()


def test_deleted_variables():
    created, deleted = find_created_deleted_vars({"x", "y"}, {"x"})
    assert created == set()
    assert deleted == {"y"}


def test_underscore_names_excluded():
    # Names beginning with '_' (e.g. IPython internals) are ignored in both
    # the created and deleted sets.
    created, deleted = find_created_deleted_vars(
        {"_old", "keep"}, {"keep", "new", "_new"}
    )
    assert created == {"new"}
    assert deleted == set()


def test_no_change():
    created, deleted = find_created_deleted_vars({"a", "b"}, {"a", "b"})
    assert created == set()
    assert deleted == set()
