"""Tests for construct_object_hash and compare_fingerprint."""

import numpy as np

from elastic_notebook.core.mutation.fingerprint import (
    compare_fingerprint,
    construct_fingerprint,
)
from elastic_notebook.core.mutation.object_hash import (
    ImmutableObj,
    NpArrayObj,
    construct_object_hash,
)


def test_none_hashes_to_immutable():
    assert construct_object_hash(None) == ImmutableObj()


def test_function_hashes_to_immutable():
    def f():
        return 1

    assert construct_object_hash(f) == ImmutableObj()


def test_primitive_hash_is_deterministic_and_distinct():
    assert construct_object_hash(42) == construct_object_hash(42)
    assert construct_object_hash(42) != construct_object_hash(43)


def test_numpy_array_hash_equality():
    a = np.array([1, 2, 3])
    b = np.array([1, 2, 3])
    c = np.array([1, 2, 4])
    assert construct_object_hash(a) == construct_object_hash(b)
    assert construct_object_hash(a) != construct_object_hash(c)
    assert isinstance(construct_object_hash(a), NpArrayObj)


def test_compare_fingerprint_no_change(profile_dict):
    x = [1, 2, 3]
    fp = construct_fingerprint(x, profile_dict)
    changed, overwritten = compare_fingerprint(fp, x, profile_dict, set())
    assert changed is False
    assert overwritten is False


def test_compare_fingerprint_inplace_modification(profile_dict):
    # Appending mutates the same object -> changed but NOT overwritten.
    x = [1, 2, 3]
    fp = construct_fingerprint(x, profile_dict)
    x.append(4)
    changed, overwritten = compare_fingerprint(fp, x, profile_dict, set())
    assert changed is True
    assert overwritten is False


def test_compare_fingerprint_overwrite(profile_dict):
    # A brand-new object with a different identity -> overwritten.
    x = [1, 2, 3]
    fp = construct_fingerprint(x, profile_dict)
    new_obj = [1, 2, 3, 4]
    changed, overwritten = compare_fingerprint(fp, new_obj, profile_dict, set())
    assert changed is True
    assert overwritten is True


def test_compare_fingerprint_numpy_inplace_value_change(profile_dict):
    # Same array object, same structure, but a changed element value is caught
    # via the object hash (changed, not overwritten).
    a = np.array([1, 2, 3])
    fp = construct_fingerprint(a, profile_dict)
    a[0] = 99
    changed, overwritten = compare_fingerprint(fp, a, profile_dict, set())
    assert changed is True
    assert overwritten is False
