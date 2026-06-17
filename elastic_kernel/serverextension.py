"""Jupyter Server 拡張: 外部オーケストレーター向けの REST チェックポイント/復元 API。

このモジュールは Jupyter Server（JupyterLab の裏で動く Web サーバー）に
``POST /elastic_kernel/checkpoint`` と ``POST /elastic_kernel/restore`` の2つの
エンドポイントを追加する。リクエストは ``kernel_id`` で対象カーネルを指定し、ハンドラは
そのカーネルの control チャネルへカスタムメッセージ（``elastic_checkpoint_request`` /
``elastic_restore_request``）を送り、カーネル側（elastic_kernel.kernel）が返す reply を
HTTP レスポンスとして中継する。

注意:
- このモジュールは Jupyter Server プロセス側でのみロードされる。カーネルプロセスからは
  import されない（kernel.py は jupyter_server に依存しない）。
- 有効化は ``elastic-kernel install --server``（toggle_server_extension_python 経由）で行う。
  そのため常時 ON の jupyter_server_config.d JSON は同梱していない。
"""

import json
import time
from queue import Empty

from jupyter_server.base.handlers import APIHandler
from jupyter_server.utils import url_path_join
from tornado import web

# control チャネルへ送るリクエスト種別と、対応する reply 種別。
_CHECKPOINT = ("elastic_checkpoint_request", "elastic_checkpoint_reply")
_RESTORE = ("elastic_restore_request", "elastic_restore_reply")

# reply を待つデフォルトのタイムアウト（秒）。body の "timeout" で上書き可。
_DEFAULT_TIMEOUT = 120.0


async def _send_and_await(kernel, request_type, reply_type, timeout):
    """対象カーネルの control チャネルへ request_type を送り、reply_type を await して返す。

    新しいクライアント（= JupyterLab とは別の接続）を一時的に開いて control チャネルに
    送る。control チャネルは複数クライアント可で、reply は送信元へルーティングされる。
    クライアントは km.client() で生成されるため署名キーがカーネルと一致する。
    """
    client = kernel.client()
    client.start_channels()
    try:
        msg = client.session.msg(request_type, {})
        msg_id = msg["header"]["msg_id"]
        client.control_channel.send(msg)

        # reply は parent_header.msg_id が一致する control メッセージ。状態通知などが
        # 紛れ込んでも取り違えないよう、msg_id と msg_type で照合する。
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"timeout waiting for {reply_type}")
            reply = await client.get_control_msg(timeout=remaining)
            if (
                reply.get("msg_type") == reply_type
                and reply.get("parent_header", {}).get("msg_id") == msg_id
            ):
                return reply["content"]
    finally:
        client.stop_channels()


class _ElasticBaseHandler(APIHandler):
    """checkpoint/restore 共通の処理。kernel_id 解決 → control 送信 → JSON 応答。"""

    async def _dispatch(self, request_type, reply_type):
        body = self.get_json_body() or {}
        kernel_id = body.get("kernel_id") or self.get_argument("kernel_id", None)
        if not kernel_id:
            raise web.HTTPError(400, "kernel_id is required")

        try:
            kernel = self.kernel_manager.get_kernel(kernel_id)
        except KeyError:
            raise web.HTTPError(404, f"unknown kernel_id: {kernel_id}")

        try:
            timeout = float(body.get("timeout", _DEFAULT_TIMEOUT))
        except (TypeError, ValueError):
            raise web.HTTPError(400, "timeout must be a number")

        try:
            content = await _send_and_await(kernel, request_type, reply_type, timeout)
        except (TimeoutError, Empty):
            raise web.HTTPError(504, "kernel did not reply in time")

        # ok=True は 200、ok=False（plain_kernel_mode / no_checkpoint_file / exception）は 409。
        self.set_status(200 if content.get("ok") else 409)
        self.finish(json.dumps(content))


class CheckpointHandler(_ElasticBaseHandler):
    @web.authenticated
    async def post(self):
        await self._dispatch(*_CHECKPOINT)


class RestoreHandler(_ElasticBaseHandler):
    @web.authenticated
    async def post(self):
        await self._dispatch(*_RESTORE)


def _jupyter_server_extension_points():
    return [{"module": "elastic_kernel.serverextension"}]


def _load_jupyter_server_extension(server_app):
    """Jupyter Server 起動時に呼ばれ、エンドポイントを登録する。"""
    web_app = server_app.web_app
    base_url = web_app.settings["base_url"]
    handlers = [
        (url_path_join(base_url, "elastic_kernel", "checkpoint"), CheckpointHandler),
        (url_path_join(base_url, "elastic_kernel", "restore"), RestoreHandler),
    ]
    web_app.add_handlers(".*$", handlers)
    server_app.log.info(
        "elastic_kernel server extension loaded: "
        "POST /elastic_kernel/checkpoint, POST /elastic_kernel/restore"
    )
