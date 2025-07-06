import copy
import io
import logging
from inspect import isclass
from types import FunctionType, ModuleType

import lightgbm
import networkx as nx
import numpy as np
import pandas as pd
import scipy
import torch
import xxhash

BASE_TYPES = [type(None), FunctionType]

logger = logging.getLogger("ElasticNotebookLogger")


class ImmutableObj:
    def __init__(self):
        pass

    def __eq__(self, other):
        if isinstance(other, ImmutableObj):
            return True
        return False


# Object representing none.
class NoneObj:
    def __init__(self):
        pass

    def __eq__(self, other):
        if isinstance(other, NoneObj):
            return True
        return False


# Object representing a dataframe.
class DataframeObj:
    def __init__(self):
        pass

    def __eq__(self, other):
        if isinstance(other, DataframeObj):
            return True
        return False


class NxGraphObj:
    def __init__(self, graph):
        self.graph = graph

    def __eq__(self, other):
        if isinstance(other, NxGraphObj):
            return nx.graphs_equal(self.graph, other.graph)
        return False


class NpArrayObj:
    def __init__(self, arraystr):
        self.arraystr = arraystr
        pass

    def __eq__(self, other):
        if isinstance(other, NpArrayObj):
            return self.arraystr == other.arraystr
        return False


class ScipyArrayObj:
    def __init__(self, arraystr):
        self.arraystr = arraystr
        pass

    def __eq__(self, other):
        if isinstance(other, ScipyArrayObj):
            return self.arraystr == other.arraystr
        return False


class TorchTensorObj:
    def __init__(self, arraystr):
        self.arraystr = arraystr
        pass

    def __eq__(self, other):
        if isinstance(other, TorchTensorObj):
            return self.arraystr == other.arraystr
        return False


class ModuleObj:
    def __init__(self):
        pass

    def __eq__(self, other):
        if isinstance(other, ModuleObj):
            return True
        return False


# Object representing general unserializable class.
class UnserializableObj:
    def __init__(self):
        pass

    def __eq__(self, other):
        if isinstance(other, UnserializableObj):
            return True
        return False


class UncomparableObj:
    def __init__(self):
        pass

    def __eq__(self, other):
        if isinstance(other, UncomparableObj):
            return True
        return False


def construct_object_hash(obj, deepcopy=False, timeout_seconds=5.0):
    """
    Construct an object hash for the object. Uses deep-copy as a fallback.

    Args:
        obj: Object to hash
        deepcopy: Whether to use deepcopy as fallback
        timeout_seconds: Maximum time to spend on hashing before giving up
    """
    import time

    obj_type = type(obj).__name__
    start_time = time.time()

    def check_timeout():
        elapsed = time.time() - start_time
        if elapsed > timeout_seconds:
            logger.warning(
                f"construct_object_hash: Timeout ({timeout_seconds}s) exceeded for {obj_type}"
            )
            raise TimeoutError(f"Hash computation timeout for {obj_type}")
        return elapsed

    if type(obj) in BASE_TYPES:
        logger.debug(f"construct_object_hash: {obj_type} -> ImmutableObj")
        return ImmutableObj()

    if isclass(obj):
        logger.debug(f"construct_object_hash: {obj_type} -> class type")
        return type(obj)

    # Flag hack for Pandas dataframes: each dataframe column is a numpy array.
    # All the writeable flags of these arrays are set to false; if after cell execution, any of these flags are
    # reset to True, we assume that the dataframe has been modified.
    if isinstance(obj, pd.DataFrame):
        logger.debug(
            f"construct_object_hash: {obj_type} -> DataframeObj (pandas DataFrame)"
        )
        for _, col in obj.items():
            col.__array__().flags.writeable = False
        return DataframeObj()

    if isinstance(obj, pd.Series):
        logger.debug(
            f"construct_object_hash: {obj_type} -> DataframeObj (pandas Series)"
        )
        obj.__array__().flags.writeable = False
        return DataframeObj()

    attr_str = getattr(obj, "__module__", None)
    if attr_str and (
        "matplotlib" in attr_str
        or "transformers" in attr_str
        or "networkx" in attr_str
        or "keras" in attr_str
        or "tensorflow" in attr_str
    ):
        logger.debug(
            f"construct_object_hash: {obj_type} -> UncomparableObj (special module: {attr_str})"
        )
        return UncomparableObj()

    # Object is file handle
    if isinstance(obj, io.IOBase):
        logger.debug(
            f"construct_object_hash: {obj_type} -> UncomparableObj (file handle)"
        )
        return UncomparableObj()

    if isinstance(obj, np.ndarray):
        logger.debug(
            f"construct_object_hash: {obj_type} -> NpArrayObj (numpy array shape: {obj.shape})"
        )
        h = xxhash.xxh3_128()
        h.update(np.ascontiguousarray(obj.data))
        str1 = h.intdigest()
        elapsed = time.time() - start_time
        if elapsed > 0.05:
            logger.warning(
                f"construct_object_hash: numpy array hashing took {elapsed:.3f}s"
            )
        return NpArrayObj(str1)

    if isinstance(obj, scipy.sparse.csr_matrix):
        logger.debug(
            f"construct_object_hash: {obj_type} -> ScipyArrayObj (scipy sparse matrix)"
        )
        h = xxhash.xxh3_128()
        h.update(np.ascontiguousarray(obj))
        str1 = h.intdigest()
        elapsed = time.time() - start_time
        if elapsed > 0.05:
            logger.warning(
                f"construct_object_hash: scipy sparse matrix hashing took {elapsed:.3f}s"
            )
        return ScipyArrayObj(str1)

    if isinstance(obj, torch.Tensor):
        logger.debug(
            f"construct_object_hash: {obj_type} -> TorchTensorObj (torch tensor shape: {obj.shape})"
        )
        h = xxhash.xxh3_128()
        h.update(np.ascontiguousarray(obj))
        str1 = h.intdigest()
        elapsed = time.time() - start_time
        if elapsed > 0.05:
            logger.warning(
                f"construct_object_hash: torch tensor hashing took {elapsed:.3f}s"
            )
        return TorchTensorObj(str1)

    if isinstance(obj, ModuleType) or isclass(obj):
        logger.debug(f"construct_object_hash: {obj_type} -> ModuleObj")
        return ModuleObj()

    # Polars dataframes are immutable.
    # if isinstance(obj, pl.DataFrame):
    #    return type(obj)

    # LightGBM dataframes are immutable.
    if isinstance(obj, lightgbm.Dataset):
        logger.debug(f"construct_object_hash: {obj_type} -> type (lightgbm Dataset)")
        return type(obj)

    # Handle large collections efficiently (avoid expensive string conversion)
    if isinstance(obj, (list, tuple, set)):
        try:
            collection_size = len(obj)
            # For large collections (>100k elements), use sampling-based hash
            if collection_size > 100000:
                logger.debug(
                    f"construct_object_hash: {obj_type} -> large collection hash (size: {collection_size})"
                )
                h = xxhash.xxh3_128()

                # Hash collection metadata
                h.update(f"{obj_type}:{collection_size}".encode("utf-8"))

                # Sample elements for hashing (first 100, last 100, and some from middle)
                sample_indices = []
                if collection_size > 0:
                    # First 100 elements
                    sample_indices.extend(range(min(100, collection_size)))
                    # Last 100 elements (if collection is large enough)
                    if collection_size > 200:
                        sample_indices.extend(
                            range(collection_size - 100, collection_size)
                        )
                    # Some elements from middle
                    if collection_size > 1000:
                        middle_start = collection_size // 2 - 50
                        middle_end = collection_size // 2 + 50
                        sample_indices.extend(
                            range(middle_start, min(middle_end, collection_size))
                        )

                # Hash sampled elements
                if isinstance(obj, set):
                    # For sets, convert to list first for indexing
                    obj_list = list(obj)
                    for i in sample_indices[:300]:  # Limit to 300 samples max
                        if i < len(obj_list):
                            h.update(
                                str(
                                    hash(obj_list[i])
                                    if hasattr(obj_list[i], "__hash__")
                                    and obj_list[i].__hash__ is not None
                                    else str(obj_list[i])
                                ).encode("utf-8")
                            )
                else:
                    # For lists and tuples
                    for i in sample_indices[:300]:  # Limit to 300 samples max
                        if i < collection_size:
                            h.update(
                                str(
                                    hash(obj[i])
                                    if hasattr(obj[i], "__hash__")
                                    and obj[i].__hash__ is not None
                                    else str(obj[i])
                                ).encode("utf-8")
                            )

                elapsed = time.time() - start_time
                if elapsed > 0.05:
                    logger.warning(
                        f"construct_object_hash: large collection hashing took {elapsed:.3f}s"
                    )
                return h.intdigest()
        except Exception as e:
            logger.warning(
                f"construct_object_hash: Error in large collection handling for {obj_type}: {e}"
            )
            # Fall through to normal processing

    # Try to hash the object; if the object is unhashable, use deepcopy as fallback.
    try:
        check_timeout()  # Check before starting expensive operations

        h = xxhash.xxh3_128()
        if hasattr(obj, "__bytes__"):
            # Use object's __bytes__ method if available
            logger.debug(
                f"construct_object_hash: {obj_type} -> generic hash (using __bytes__)"
            )
            obj_bytes = bytes(obj)
        elif hasattr(obj, "tobytes"):
            # For numpy-like objects with tobytes method
            logger.debug(
                f"construct_object_hash: {obj_type} -> generic hash (using tobytes)"
            )
            obj_bytes = obj.tobytes()
        else:
            # Fallback to string representation - this can be very slow for large objects
            logger.debug(
                f"construct_object_hash: {obj_type} -> generic hash (using str)"
            )
            check_timeout()  # Check again before expensive string conversion
            obj_bytes = str(obj).encode("utf-8")

        h.update(obj_bytes)
        elapsed = time.time() - start_time
        if elapsed > 0.05:
            logger.warning(
                f"construct_object_hash: generic hashing took {elapsed:.3f}s for {obj_type}"
            )
        return h.intdigest()
    except TimeoutError:
        # Return UncomparableObj for timed-out objects
        logger.warning(
            f"construct_object_hash: {obj_type} -> UncomparableObj (timeout)"
        )
        return UncomparableObj()
    except Exception as e:
        logger.warning(f"construct_object_hash: Error hashing {obj_type}: {e}")
        logger.debug(f"construct_object_hash: {obj_type} -> fallback to deepcopy/obj")
        try:
            if deepcopy:
                return copy.deepcopy(obj)
            else:
                return obj
        except Exception:
            # If object is not even deepcopy-able, mark it as unserializable and assume modified-on-write.
            logger.debug(
                f"construct_object_hash: {obj_type} -> UnserializableObj (deepcopy failed)"
            )
            return UnserializableObj()
