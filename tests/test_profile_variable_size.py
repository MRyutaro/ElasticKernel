"""Tests for profile_variable_size, including the D-4 accuracy fix.

D-4: previously a custom class instance was measured only by the shallow
sys.getsizeof(instance), because the branch that recursed into __dict__ was
unreachable. Now the attributes stored in __dict__ are counted too.
"""

from elastic_notebook.core.common.profile_variable_size import profile_variable_size


class _Holder:
    pass


def test_primitive_and_collection_sizes_are_positive():
    assert profile_variable_size(42) > 0
    assert profile_variable_size([1, 2, 3]) > 0


def test_custom_object_attributes_are_counted():
    # The instance carrying a large attribute must measure larger than an empty
    # one — i.e. __dict__ contents are included (D-4).
    big = _Holder()
    big.payload = [0] * 5000
    small = _Holder()
    small.payload = []
    assert profile_variable_size(big) > profile_variable_size(small)


def test_custom_object_at_least_as_large_as_its_attribute():
    holder = _Holder()
    holder.payload = list(range(2000))
    assert profile_variable_size(holder) >= profile_variable_size(holder.payload)
