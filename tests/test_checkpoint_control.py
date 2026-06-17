"""Tests for on-demand checkpoint/restore wiring (issue: external orchestrator API).

Covers the kernel-side refactor (_save_checkpoint / _restore_checkpoint), the
control-channel handlers, and the server-extension registration. The methods are
exercised against lightweight stub ``self`` objects so we never spin up a real
IPythonKernel (which needs a connection file and a live ZMQ stack).
"""

import asyncio
import inspect
import logging
import types

import pytest
from ipykernel.ipkernel import IPythonKernel

from elastic_kernel.kernel import ElasticKernel


class _StubNotebook:
    """Minimal stand-in for ElasticNotebook used by save/restore."""

    def __init__(self):
        self.vss_to_migrate = ["a", "b"]
        self.vss_to_recompute = ["c"]
        self.checkpoint_calls = []
        self.load_calls = []
        self.dependency_graph = types.SimpleNamespace(variable_snapshots={})

    def checkpoint(self, path):
        self.checkpoint_calls.append(path)

    def load_checkpoint(self, path):
        self.load_calls.append(path)


def _stub_self(elastic_notebook, checkpoint_file_path):
    """A bare object carrying only the attributes save/restore touch."""
    return types.SimpleNamespace(
        logger=logging.getLogger("elastic-test"),
        elastic_notebook=elastic_notebook,
        checkpoint_file_path=checkpoint_file_path,
        shell=types.SimpleNamespace(user_ns={}),
    )


# --------------------------------------------------------------------------- #
# _save_checkpoint
# --------------------------------------------------------------------------- #
def test_save_plain_kernel_mode():
    s = _stub_self(None, "/nonexistent/checkpoint.pickle")
    assert ElasticKernel._save_checkpoint(s) == {
        "ok": False,
        "reason": "plain_kernel_mode",
    }


def test_save_success(tmp_path):
    nb = _StubNotebook()
    path = str(tmp_path / "checkpoint.pickle")
    s = _stub_self(nb, path)

    result = ElasticKernel._save_checkpoint(s)

    assert result["ok"] is True
    assert result["path"] == path
    assert result["vss_to_migrate"] == 2
    assert result["vss_to_recompute"] == 1
    assert "elapsed_seconds" in result
    assert nb.checkpoint_calls == [path]


def test_save_exception_is_caught(tmp_path):
    nb = _StubNotebook()

    def _boom(_path):
        raise RuntimeError("disk full")

    nb.checkpoint = _boom
    s = _stub_self(nb, str(tmp_path / "checkpoint.pickle"))

    result = ElasticKernel._save_checkpoint(s)

    assert result["ok"] is False
    assert result["reason"] == "exception"
    assert "disk full" in result["error"]


# --------------------------------------------------------------------------- #
# _restore_checkpoint
# --------------------------------------------------------------------------- #
def test_restore_plain_kernel_mode():
    s = _stub_self(None, "/whatever/checkpoint.pickle")
    assert ElasticKernel._restore_checkpoint(s) == {
        "ok": False,
        "reason": "plain_kernel_mode",
    }


def test_restore_no_checkpoint_file(tmp_path):
    nb = _StubNotebook()
    s = _stub_self(nb, str(tmp_path / "missing.pickle"))

    result = ElasticKernel._restore_checkpoint(s)

    assert result == {"ok": False, "reason": "no_checkpoint_file"}
    assert nb.load_calls == []


def test_restore_success(tmp_path):
    nb = _StubNotebook()
    path = tmp_path / "checkpoint.pickle"
    path.write_bytes(b"x")  # only needs to exist
    s = _stub_self(nb, str(path))

    result = ElasticKernel._restore_checkpoint(s)

    assert result["ok"] is True
    assert result["path"] == str(path)
    assert nb.load_calls == [str(path)]


# --------------------------------------------------------------------------- #
# control-channel handlers
# --------------------------------------------------------------------------- #
def test_control_handlers_are_coroutines():
    assert inspect.iscoroutinefunction(ElasticKernel._on_checkpoint_request)
    assert inspect.iscoroutinefunction(ElasticKernel._on_restore_request)


class _FakeIOLoop:
    """Marshals add_callback onto the running asyncio loop (mimics the main loop)."""

    def __init__(self, loop):
        self._loop = loop

    def add_callback(self, fn):
        self._loop.call_soon(fn)


def _run_handler(handler, s):
    """Drive an async control handler to completion via asyncio.run()."""

    async def _run():
        loop = asyncio.get_running_loop()
        s.io_loop = _FakeIOLoop(loop)
        # Bind the real helpers onto the stub so the handler can reuse them.
        s._save_checkpoint = lambda: ElasticKernel._save_checkpoint(s)
        s._restore_checkpoint = lambda: ElasticKernel._restore_checkpoint(s)
        s._run_on_main_loop = lambda fn: ElasticKernel._run_on_main_loop(s, fn)
        await handler(s, "stream", b"ident", {"header": {"msg_id": "req-1"}})

    asyncio.run(_run())


def test_checkpoint_handler_sends_reply(tmp_path):
    nb = _StubNotebook()
    path = str(tmp_path / "checkpoint.pickle")
    sent = []

    s = _stub_self(nb, path)
    s.session = types.SimpleNamespace(
        send=lambda stream, msg_type, content, parent, ident: sent.append(
            (msg_type, content, parent, ident)
        )
    )

    _run_handler(ElasticKernel._on_checkpoint_request, s)

    assert len(sent) == 1
    msg_type, content, parent, ident = sent[0]
    assert msg_type == "elastic_checkpoint_reply"
    assert content["ok"] is True
    assert parent == {"header": {"msg_id": "req-1"}}
    assert ident == b"ident"
    # The save actually ran on the (faked) main loop.
    assert nb.checkpoint_calls == [path]


def test_restore_handler_sends_reply(tmp_path):
    nb = _StubNotebook()
    path = tmp_path / "checkpoint.pickle"
    path.write_bytes(b"x")
    sent = []

    s = _stub_self(nb, str(path))
    s.session = types.SimpleNamespace(
        send=lambda stream, msg_type, content, parent, ident: sent.append(
            (msg_type, content)
        )
    )

    _run_handler(ElasticKernel._on_restore_request, s)

    assert len(sent) == 1
    msg_type, content = sent[0]
    assert msg_type == "elastic_restore_reply"
    assert content["ok"] is True
    assert nb.load_calls == [str(path)]


# --------------------------------------------------------------------------- #
# server extension
# --------------------------------------------------------------------------- #
def test_server_extension_points():
    pytest.importorskip("jupyter_server")
    from elastic_kernel import serverextension

    assert serverextension._jupyter_server_extension_points() == [
        {"module": "elastic_kernel.serverextension"}
    ]


def test_load_registers_handlers():
    pytest.importorskip("jupyter_server")
    from elastic_kernel import serverextension

    registered = []

    class _FakeWebApp:
        settings = {"base_url": "/"}

        def add_handlers(self, host_pattern, handlers):
            registered.extend(handlers)

    fake_app = types.SimpleNamespace(
        web_app=_FakeWebApp(), log=logging.getLogger("test")
    )

    serverextension._load_jupyter_server_extension(fake_app)

    paths = [pattern for pattern, _handler in registered]
    assert any("checkpoint" in p for p in paths)
    assert any("restore" in p for p in paths)


# --------------------------------------------------------------------------- #
# auto checkpoint/restore toggle (ELASTIC_KERNEL_AUTO_CHECKPOINT)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value, expected",
    [
        (None, True),  # 未設定はデフォルト ON
        ("", True),  # 空文字も ON 扱い（明示的な falsy 値のみ OFF）
        ("1", True),
        ("true", True),
        ("yes", True),
        ("0", False),
        ("false", False),
        ("False", False),  # 大文字小文字は無視
        ("  OFF  ", False),  # 前後空白は無視
        ("no", False),
    ],
)
def test_auto_checkpoint_from_env(value, expected):
    assert ElasticKernel._auto_checkpoint_from_env(value) is expected


def _shutdown_stub(auto_checkpoint):
    """do_shutdown のゲーティングだけを検証するための最小インスタンス。"""
    obj = ElasticKernel.__new__(ElasticKernel)  # __init__ を回避（ZMQ 不要）
    obj.auto_checkpoint = auto_checkpoint
    obj.logger = logging.getLogger("elastic-test")
    obj._save_checkpoint_calls = []
    obj._save_checkpoint = lambda: obj._save_checkpoint_calls.append(True)
    return obj


def test_do_shutdown_saves_when_auto_enabled(monkeypatch):
    super_calls = []
    monkeypatch.setattr(
        IPythonKernel, "do_shutdown", lambda self, restart: super_calls.append(restart)
    )
    obj = _shutdown_stub(auto_checkpoint=True)

    ElasticKernel.do_shutdown(obj, False)

    assert obj._save_checkpoint_calls == [True]
    assert super_calls == [False]  # 通常のシャットダウンは継続する


def test_do_shutdown_skips_save_when_auto_disabled(monkeypatch):
    super_calls = []
    monkeypatch.setattr(
        IPythonKernel, "do_shutdown", lambda self, restart: super_calls.append(restart)
    )
    obj = _shutdown_stub(auto_checkpoint=False)

    ElasticKernel.do_shutdown(obj, True)

    assert obj._save_checkpoint_calls == []  # 自動保存はスキップ
    assert super_calls == [True]  # それでも通常のシャットダウンは継続する
