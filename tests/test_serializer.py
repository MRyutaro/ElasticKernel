"""serializer.dump: cloudpickle first, dill fallback, and restore in a fresh process."""

import io
import subprocess
import sys
import textwrap

import dill

from elastic_notebook.core.io import serializer


def test_roundtrip_plain_data():
    buf = io.BytesIO()
    obj = {"a": [1, 2, {"b": "c"}], "n": 3.5}
    serializer.dump(obj, buf)
    buf.seek(0)
    assert dill.load(buf) == obj


def test_multiple_dumps_in_one_file_load_in_order():
    buf = io.BytesIO()
    serializer.dump([1, 2], buf)
    serializer.dump({"x": 1}, buf)
    buf.seek(0)
    assert dill.load(buf) == [1, 2]
    assert dill.load(buf) == {"x": 1}


def test_falls_back_to_dill_and_leaves_no_partial_bytes(monkeypatch):
    def broken(obj, file, *a, **k):
        file.write(b"partial garbage")
        raise RuntimeError("cloudpickle cannot handle this")

    monkeypatch.setattr(serializer.cloudpickle, "dump", broken)
    buf = io.BytesIO()
    serializer.dump("before", buf)
    serializer.dump([1, 2, 3], buf)
    buf.seek(0)
    assert dill.load(buf) == "before"
    assert dill.load(buf) == [1, 2, 3]


def test_main_classes_and_lambdas_restore_in_a_fresh_process(tmp_path):
    """The standard pickle stores __main__ classes by name and the load then fails."""
    out = tmp_path / "group.pkl"
    writer = textwrap.dedent(f"""
        from elastic_notebook.core.io import serializer

        class Point:
            def __init__(self, x):
                self.x = x

        offset = 10
        with open({str(out)!r}, "wb") as f:
            serializer.dump([Point(3), lambda v: v + offset], f)
        """)
    subprocess.run([sys.executable, "-c", writer], check=True)
    reader = textwrap.dedent(f"""
        import dill
        with open({str(out)!r}, "rb") as f:
            point, fn = dill.load(f)
        assert point.x == 3 and fn(1) == 11
        """)
    subprocess.run([sys.executable, "-c", reader], check=True)
