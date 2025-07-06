import logging
import sys
import time
from collections.abc import Iterable
from types import FunctionType

import pandas as pd

from elastic_notebook.core.mutation.id_graph import (
    construct_id_graph,
    is_root_equals,
    is_structure_equals,
)
from elastic_notebook.core.mutation.object_hash import (
    DataframeObj,
    ImmutableObj,
    ModuleObj,
    NoneObj,
    NpArrayObj,
    NxGraphObj,
    ScipyArrayObj,
    TorchTensorObj,
    UncomparableObj,
    UnserializableObj,
    construct_object_hash,
)

logger = logging.getLogger("ElasticNotebookLogger")

BASE_TYPES = [
    str,
    int,
    float,
    bool,
    type(None),
    FunctionType,
    ImmutableObj,
    UncomparableObj,
    NoneObj,
    NxGraphObj,
    TorchTensorObj,
    ModuleObj,
    UnserializableObj,
    NpArrayObj,
    ScipyArrayObj,
    DataframeObj,
]


def base_typed(obj, visited):
    """
    Recursive reflection method to convert any object property into a comparable form.
    From: https://stackoverflow.com/questions/1227121/compare-object-instances-for-equality-by-their-attributes
    """
    T = type(obj)
    from_numpy = T.__module__ == "numpy"

    if T in BASE_TYPES or callable(obj) or (from_numpy and not isinstance(T, Iterable)):
        return obj

    visited.add(id(obj))

    if isinstance(obj, Iterable):
        return obj
    d = obj if T is dict else obj.__dict__

    comp_dict = {}
    for k, v in d.items():
        if id(v) not in visited:
            comp_dict[k] = base_typed(v, visited)

    return comp_dict


def deep_equals(*args):
    """
    Extended equality comparison which compares objects recursively by their attributes, i.e., it also works for
    certain user-defined objects with no equality (__eq__) defined.
    """
    return all(
        base_typed(args[0], set()) == base_typed(other, set()) for other in args[1:]
    )


def construct_fingerprint(obj, profile_dict):
    """
    Construct a fingerprint of the object (ID graph + hash).
    """
    # オブジェクトの基本情報をログ
    obj_type = type(obj).__name__
    try:
        obj_size = sys.getsizeof(obj)
        size_str = f"{obj_size} bytes"
    except Exception:
        size_str = "unknown size"

    logger.debug(f"construct_fingerprint: Starting for {obj_type} ({size_str})")

    # ID graph construction
    start = time.time()
    id_graph, id_set = construct_id_graph(obj)
    end = time.time()
    idgraph_time = end - start
    profile_dict["idgraph"] += idgraph_time

    if idgraph_time > 0.1:
        logger.warning(
            f"construct_fingerprint: ID graph construction took {idgraph_time:.3f}s for {obj_type}"
        )
    else:
        logger.debug(
            f"construct_fingerprint: ID graph construction took {idgraph_time:.3f}s"
        )

    # Object hash construction
    start = time.time()
    object_representation = construct_object_hash(obj)
    end = time.time()
    hash_time = end - start
    profile_dict["representation"] += hash_time

    if hash_time > 0.1:
        logger.warning(
            f"construct_fingerprint: Object hash construction took {hash_time:.3f}s for {obj_type}"
        )
    else:
        logger.debug(
            f"construct_fingerprint: Object hash construction took {hash_time:.3f}s"
        )

    total_time = idgraph_time + hash_time
    if total_time > 0.2:
        logger.warning(
            f"construct_fingerprint: Total time {total_time:.3f}s for {obj_type} ({size_str})"
        )

    return [id_graph, id_set, object_representation]


def compare_fingerprint(
    fingerprint_list, new_obj, profile_dict, input_variables_id_graph_union
):
    """
    Check whether an object has been changed by comparing it to its previous fingerprint.
    Uses staged comparison: ID check -> structure check -> value check for performance.
    """
    changed = False
    overwritten = False
    uncomparable = False

    # Stage 1: Quick identity check - if it's the same object in memory, skip expensive checks
    current_obj_id = id(new_obj)
    if (
        hasattr(fingerprint_list[0], "obj_id")
        and fingerprint_list[0].obj_id == current_obj_id
    ):
        # Same object ID - likely unchanged unless it's a mutable object that was modified in place
        if type(new_obj) in [int, float, str, bool, type(None)]:
            logger.debug(
                f"compare_fingerprint: Early return for immutable object (obj_id: {current_obj_id})"
            )
            return (
                False,
                False,
            )  # Immutable objects with same ID are definitely unchanged

    # Hack: check for pandas dataframes and series: if the flag has been flipped back on, the object has been changed.
    if isinstance(new_obj, pd.DataFrame):
        for _, col in new_obj.items():
            if col.__array__().flags.writeable:
                changed = True
                break

    elif isinstance(new_obj, pd.Series):
        if new_obj.__array__().flags.writeable:
            changed = True

    # Stage 2: ID graph check - check whether the structure of the object has changed (i.e. its relation with other objects)
    start = time.time()

    id_graph, id_set = construct_id_graph(new_obj)

    if id_set != fingerprint_list[1] or not is_structure_equals(
        id_graph, fingerprint_list[0]
    ):
        # Distinguish between overwritten variables and modified variables (i.e., x = 1 vs. x[0] = 1)
        if not is_root_equals(id_graph, fingerprint_list[0]):
            overwritten = True
        changed = True
        fingerprint_list[0] = id_graph
        fingerprint_list[1] = id_set

    end = time.time()
    profile_dict["idgraph"] += end - start

    # Stage 3: Value check via object hash - only if structure hasn't changed
    if not changed:
        start = time.time()
        try:
            # Use timeout for large objects to avoid hanging
            new_repr = construct_object_hash(new_obj, timeout_seconds=5.0)

            # Variable is uncomparable
            if isinstance(new_repr, UncomparableObj):
                if id_set.intersection(input_variables_id_graph_union):
                    changed = True
                uncomparable = True
                fingerprint_list[2] = UncomparableObj()
            else:
                if not deep_equals(new_repr, fingerprint_list[2]):
                    # Variable has equality defined; the variable has been modified.
                    if (
                        "__eq__" in type(new_repr).__dict__.keys()
                        or "eq" in type(new_repr).__dict__.keys()
                    ):
                        changed = True
                    else:
                        # Object is uncomparable
                        if id_set.intersection(input_variables_id_graph_union):
                            changed = True
                        uncomparable = True
                        fingerprint_list[2] = UncomparableObj()
        except Exception:
            # Variable is uncomparable
            if id_set.intersection(input_variables_id_graph_union):
                changed = True
            uncomparable = True
            fingerprint_list[2] = UncomparableObj()

    # Update the object hash if either:
    # 1. the object has been completely overwritten
    # 2. the object has been modified, and is of a comparable type (i.e., hashable or unhashable but has equality
    # defined)
    if overwritten or (
        changed
        and not uncomparable
        and not isinstance(fingerprint_list[2], UncomparableObj)
    ):
        fingerprint_list[2] = construct_object_hash(new_obj)
    end = time.time()
    profile_dict["representation"] += end - start

    return changed, overwritten
