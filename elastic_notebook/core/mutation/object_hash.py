import copy
import io
import logging
from inspect import isclass
from types import FunctionType, ModuleType

import networkx as nx
import numpy as np
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


def is_torch_tensor(obj):
    """
    PyTorch を import せずに torch.Tensor かどうかを判定する。

    Returns:
        bool: True if obj is torch.Tensor, False otherwise.
    """
    cls = type(obj)
    return (
        getattr(cls, "__module__", "").startswith("torch")
        and getattr(cls, "__name__", "") == "Tensor"
    )


def is_lightgbm_dataset(obj):
    """
    LightGBM を import せずに lightgbm.Dataset かどうかを判定する。

    Returns:
        bool: True if obj is lightgbm.Dataset, False otherwise.
    """
    cls = type(obj)
    return (
        getattr(cls, "__module__", "").startswith("lightgbm")
        and getattr(cls, "__name__", "") == "Dataset"
    )


def is_polars_dataframe(obj):
    """
    Polars を import せずに pl.DataFrame かどうかを判定する。

    Returns:
        bool: True if obj is pl.DataFrame, False otherwise.
    """
    cls = type(obj)
    return (
        getattr(cls, "__module__", "").startswith("polars")
        and getattr(cls, "__name__", "") == "DataFrame"
    )


def is_pandas_dataframe(obj):
    """
    Pandas を import せずに pd.DataFrame かどうかを判定する。

    Returns:
        bool: True if obj is pd.DataFrame, False otherwise.
    """
    cls = type(obj)
    return (
        getattr(cls, "__module__", "").startswith("pandas")
        and getattr(cls, "__name__", "") == "DataFrame"
    )


def is_pandas_series(obj):
    """
    Pandas を import せずに pd.Series かどうかを判定する。

    Returns:
        bool: True if obj is pd.Series, False otherwise.
    """
    cls = type(obj)
    return (
        getattr(cls, "__module__", "").startswith("pandas")
        and getattr(cls, "__name__", "") == "Series"
    )


def is_scipy_sparse_csr_matrix(obj):
    """
    SciPy を import せずに scipy.sparse.csr_matrix かどうかを判定する。

    Returns:
        bool: True if obj is scipy.sparse.csr_matrix, False otherwise.
    """
    cls = type(obj)
    return (
        getattr(cls, "__module__", "").startswith("scipy.sparse")
        and getattr(cls, "__name__", "") == "csr_matrix"
    )


def construct_object_hash(obj, deepcopy=False):
    """
    Construct an object hash for the object. Uses deep-copy as a fallback.
    """

    if type(obj) in BASE_TYPES:
        return ImmutableObj()

    if isclass(obj):
        return type(obj)

    # Flag hack for Pandas dataframes: each dataframe column is a numpy array.
    # All the writeable flags of these arrays are set to false; if after cell execution, any of these flags are
    # reset to True, we assume that the dataframe has been modified.
    if is_pandas_dataframe(obj):
        for _, col in obj.items():
            col.__array__().flags.writeable = False
        return DataframeObj()

    if is_pandas_series(obj):
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
        return UncomparableObj()

    # Object is file handle
    if isinstance(obj, io.IOBase):
        return UncomparableObj()

    if isinstance(obj, np.ndarray):
        h = xxhash.xxh3_128()
        h.update(np.ascontiguousarray(obj.data))
        str1 = h.intdigest()
        return NpArrayObj(str1)

    if is_scipy_sparse_csr_matrix(obj):
        h = xxhash.xxh3_128()
        h.update(np.ascontiguousarray(obj))
        str1 = h.intdigest()
        return ScipyArrayObj(str1)

    if is_torch_tensor(obj):
        h = xxhash.xxh3_128()
        h.update(np.ascontiguousarray(obj))
        str1 = h.intdigest()
        return TorchTensorObj(str1)

    if isinstance(obj, ModuleType) or isclass(obj):
        return ModuleObj()

    if is_polars_dataframe(obj) or is_lightgbm_dataset(obj):
        return type(obj)

    # Try to hash the object; if the object is unhashable, use deepcopy as fallback.
    try:
        h = xxhash.xxh3_128()
        if hasattr(obj, "__bytes__"):
            # Use object's __bytes__ method if available
            obj_bytes = bytes(obj)
        elif hasattr(obj, "tobytes"):
            # For numpy-like objects with tobytes method
            obj_bytes = obj.tobytes()
        else:
            # Fallback to string representation
            obj_bytes = str(obj).encode("utf-8")

        h.update(obj_bytes)
        return h.intdigest()
    except Exception as e:
        logger.error(f"Error hashing object: {obj}")
        logger.error(f"Error: {e}")
        try:
            if deepcopy:
                return copy.deepcopy(obj)
            else:
                return obj
        except Exception:
            # If object is not even deepcopy-able, mark it as unserializable and assume modified-on-write.
            return UnserializableObj()
