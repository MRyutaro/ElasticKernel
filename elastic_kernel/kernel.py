import ast
import asyncio
import hashlib
import json
import logging
import os
import time
import traceback
import urllib
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from ipykernel.ipkernel import IPythonKernel

from elastic_notebook import ElasticNotebook
from elastic_notebook.core.common.logging_setup import setup_logger


class ElasticKernel(IPythonKernel):
    implementation = "ElasticKernel"
    implementation_version = "1.0"
    language = "python"
    language_version = "3.x"
    language_info = {
        "name": "python",
        "mimetype": "text/x-python",
        "file_extension": ".py",
    }
    banner = "ElasticKernel"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # __setup_file_path() 内のパス解決フォールバック
        # (__resolve_path_without_jpy_session_name) は JPY_SESSION_NAME 未設定時に
        # self.logger を参照する。これは __setup_logger() より前に実行されるため、
        # ここで先に同名ロガーを取得しておかないと AttributeError でカーネルが即死する。
        # __setup_logger() は同じ "ElasticKernelLogger" にファイルハンドラを設定するので、
        # ここで取得したオブジェクトがそのまま後段で正しく構成される。
        self.logger: logging.Logger = logging.getLogger("ElasticKernelLogger")
        self.log_file_path: str
        self.checkpoint_file_path: str

        # connection_fileからカーネルIDを取得
        connection_file = self.session.config["IPKernelApp"]["connection_file"]
        kernel_id = os.path.splitext(os.path.basename(connection_file))[0].replace(
            "kernel-", ""
        )

        self.__setup_file_path()
        self.__setup_logger()

        self.logger.info("===============================================")
        self.logger.info(f"Initializing ElasticKernel ({kernel_id})")
        self.logger.debug("Session attributes:")
        for key, value in vars(self.session).items():
            self.logger.debug(f"  - {key}: {value}")
        self.logger.info("===============================================")

        # ===========================================
        # デバッグ用
        self.logger.debug(f"kwargs: {kwargs}")
        self.logger.debug(f"self.shell: {self.shell}")
        self.logger.info(f"{self.shell.execution_count=}")  # 実行回数
        # ===========================================

        # ElasticNotebookをロードする
        # 生成に失敗した場合は None のままにし、以降は「追跡なしの素のカーネル」として
        # 動作を継続する（毎セルで AttributeError を吐き続けないようにする）。(D-13)
        self.elastic_notebook = None
        try:
            self.elastic_notebook = ElasticNotebook(
                shell=self.shell,
                log_file_dir=self.log_file_dir,
            )
            self.logger.info("ElasticNotebook successfully loaded.")
        except Exception as e:
            self.logger.error(f"Error loading ElasticNotebook: {e}")
            self.logger.error(
                "Continuing without checkpoint tracking (plain kernel mode)."
            )

        # 起動時の自動復元 / 終了時の自動保存を行うかどうか。
        # ElasticHub のクラウドバースティング等で、オーケストレーターがマイグレーション
        # 対象のカーネルを「手動 checkpoint/restore（control メッセージ）だけで制御したい」
        # ケースがある。そのときは起動時の自動 restore と終了時の自動 save が
        # 転送やハンドシェイクの順序制御を壊すため、環境変数で自動挙動を無効化できる。
        # 通常ユーザーのカーネルは環境変数を付けないのでデフォルト（自動 ON）のまま。
        self.auto_checkpoint = self._auto_checkpoint_from_env(
            os.environ.get("ELASTIC_KERNEL_AUTO_CHECKPOINT")
        )
        self.logger.info(
            f"Auto checkpoint/restore: {'enabled' if self.auto_checkpoint else 'disabled'}"
        )

        # 起動時にチェックポイントファイルがあれば復元する。
        # 復元ロジックは _restore_checkpoint() に共通化されており、外部オーケストレーター
        # からの control メッセージ経由でも同じ処理を再利用する。
        # 自動が無効でも、control メッセージ経由の明示的な restore は引き続き機能する。
        if self.auto_checkpoint:
            self._restore_checkpoint()
        else:
            self.logger.info(
                "Skipping startup auto-restore (auto checkpoint/restore disabled)."
            )

        # 外部オーケストレーターから任意タイミングで保存/復元を発火できるよう、control
        # チャネルにカスタムメッセージハンドラを登録する。control チャネルはセル実行の
        # shell キューとは別系統なので、実行中でも割り込んで処理でき、user_ns にコードを
        # 走らせないためノートブックユーザーには透過（%who を汚染しない）。
        self.control_handlers["elastic_checkpoint_request"] = (
            self._on_checkpoint_request
        )
        self.control_handlers["elastic_restore_request"] = self._on_restore_request

    def __resolve_path_without_jpy_session_name(self):
        """
        JPY_SESSION_NAME が無いときに、/api/sessions から自カーネルに紐づくノートブックの path を推定し、
        (root_dir, jupyter_notebook_name) を返す。
        取得できなければ kernel_id ベースにフォールバック。
        """
        # 1) 自分の kernel_id を connection_file から取得
        try:
            connection_file = self.session.config["IPKernelApp"]["connection_file"]
            kernel_id = os.path.splitext(os.path.basename(connection_file))[0].replace(
                "kernel-", ""
            )
        except Exception:
            kernel_id = os.environ.get("KERNEL_ID", "default")

        self.logger.debug(f"kernel_id: {kernel_id}")
        # 2) Jupyter Server の場所とトークン（必要なら）
        base_url = (
            os.environ.get("JUPYTER_SERVER_URL")
            or os.environ.get("JUPYTER_BASE_URL")
            or "http://127.0.0.1:8888"
        )
        token = os.environ.get("JUPYTER_TOKEN")  # token='' の環境なら未指定でOK

        def _fetch_sessions():
            url = base_url.rstrip("/") + "/api/sessions"
            if token:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}token={urllib.parse.quote(token)}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                return json.loads(resp.read().decode("utf-8"))

        # 3) 自カーネルに紐づく notebook path を探す（作成直後に備え、少しだけリトライ）
        nb_path = None
        for _ in range(10):
            try:
                for s in _fetch_sessions():
                    k = s.get("kernel") or {}
                    if k.get("id") == kernel_id:
                        nb_path = s.get("path") or (s.get("notebook") or {}).get("path")
                        break
                if nb_path:
                    break
            except Exception:
                pass
            time.sleep(0.2)

        # 4) 見つかった path から root_dir と名前を決定（相対パスは cwd 基準で解決）
        self.logger.debug(f"nb_path: {nb_path}")
        if nb_path:
            if os.path.isabs(nb_path):
                root_dir = os.path.dirname(nb_path)
                nb_full_path = nb_path
            else:
                root_dir = os.getcwd()
                nb_full_path = os.path.join(root_dir, nb_path)

            # inode が取れれば安定名、ダメならファイル名、さらにダメなら kernel_id
            if os.path.exists(nb_full_path):
                try:
                    inode = os.stat(nb_full_path).st_ino
                    name = hashlib.sha256(str(inode).encode()).hexdigest()[:16]
                except Exception:
                    name = os.path.splitext(os.path.basename(nb_full_path))[0]
            else:
                name = os.path.splitext(os.path.basename(nb_path))[0]
        else:
            # 5) どうしても取得できないときのフォールバック
            root_dir = os.getcwd()
            name = f"kernel_{kernel_id}"

        self.logger.debug(f"root_dir: {root_dir}")
        self.logger.debug(f"name: {name}")
        return root_dir, name

    def __setup_file_path(self):
        """
        ログやチェックポイントのファイルパスを設定
        """
        # ファイルのパスを設定
        # JPY_SESSION_NAME=/home/vscode/Untitled1.ipynbのような感じ
        jupyter_notebook_path = os.environ.get("JPY_SESSION_NAME")
        if jupyter_notebook_path:
            root_dir = os.path.dirname(jupyter_notebook_path)
            # inode番号を使用してハッシュ値を生成
            try:
                inode = os.stat(jupyter_notebook_path).st_ino
                # inode番号をハッシュ化（SHA256の最初の16文字を使用）
                hash_value = hashlib.sha256(str(inode).encode()).hexdigest()[:16]
                jupyter_notebook_name = hash_value
            except Exception:
                # TODO: #15 セッションを閉じずにファイル名を変えたときの処理を考える
                jupyter_notebook_name = "Untitled"
        else:
            # JPY_SESSION_NAMEが設定されていない場合（API経由での起動など）
            # TODO: self.shell.user_ns['__session__']からノートブックパスを取得できないか？
            root_dir, jupyter_notebook_name = (
                self.__resolve_path_without_jpy_session_name()
            )

        # フォルダの作成
        elastic_kernel_dir = os.path.join(root_dir, ".elastic_kernel")
        os.makedirs(elastic_kernel_dir, exist_ok=True)

        self.log_file_dir = os.path.join(elastic_kernel_dir, jupyter_notebook_name)
        os.makedirs(self.log_file_dir, exist_ok=True)
        self.log_file_path = os.path.join(self.log_file_dir, "ElasticKernel.log")
        self.checkpoint_file_path = os.path.join(self.log_file_dir, "checkpoint.pickle")

    def __setup_logger(self):
        """
        ロガーの設定
        """
        self.logger = setup_logger("ElasticKernelLogger", self.log_file_path)

    # 自動 checkpoint/restore を無効化とみなす環境変数の値（大文字小文字は無視）。
    _FALSY_ENV_VALUES = frozenset({"0", "false", "no", "off"})

    @staticmethod
    def _auto_checkpoint_from_env(value):
        """
        環境変数 ELASTIC_KERNEL_AUTO_CHECKPOINT の値から、起動時の自動復元・終了時の
        自動保存を行うかどうかを判定する。

        未設定（None、デフォルト）なら True（従来どおり自動 ON）。
        "0" / "false" / "no" / "off"（大文字小文字・前後空白は無視）なら False。
        """
        if value is None:
            return True
        return value.strip().lower() not in ElasticKernel._FALSY_ENV_VALUES

    def __del_from_user_ns_hidden(self):
        """
        %whoで表示されるようにするために復元した変数をself.shell.user_ns_hiddenから削除する
        """
        if self.elastic_notebook is None:
            return
        variable_snapshots = set(
            self.elastic_notebook.dependency_graph.variable_snapshots
        )
        user_ns_hidden_keys = set(self.shell.user_ns_hidden.keys())

        # 削除対象の変数名を一括で取得
        variables_to_delete = variable_snapshots & user_ns_hidden_keys

        # 一括で削除
        for variable_name in variables_to_delete:
            self.logger.debug(
                f"Deleting {variable_name} from self.shell.user_ns_hidden"
            )
            del self.shell.user_ns_hidden[variable_name]

    # IPythonがマジック/シェルコマンドを変換した結果として現れる get_ipython() の
    # メソッド名。これらの呼び出ししか含まないセルは「純粋なマジックセル」とみなす。
    __MAGIC_CALL_METHODS = frozenset(
        {"run_line_magic", "run_cell_magic", "system", "getoutput"}
    )

    @staticmethod
    def __is_pure_magic_cell(transformed_code):
        """
        IPythonが変換した後のコードが、マジック/シェルコマンドの呼び出しのみで
        構成されている（=追跡対象のPythonコードを含まない）かどうかを判定する。

        変換不能（SyntaxError）な場合や空セルも True（スキップ）として扱う。
        """
        try:
            tree = ast.parse(transformed_code)
        except SyntaxError:
            return True

        if not tree.body:
            return True

        return all(ElasticKernel.__is_magic_statement(node) for node in tree.body)

    @staticmethod
    def __is_magic_statement(node):
        """
        AST ノードが get_ipython().run_line_magic(...) 等のマジック呼び出し式か判定する。
        """
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            return False
        func = node.value.func
        if (
            not isinstance(func, ast.Attribute)
            or func.attr not in ElasticKernel.__MAGIC_CALL_METHODS
        ):
            return False
        inner = func.value
        return (
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Name)
            and inner.func.id == "get_ipython"
        )

    def __transform_cell(self, code):
        """
        IPython本体と同じ入力変換器でセルを正規のPythonコードへ変換する。
        マジック（%, %%）やシェル（!）は get_ipython() 呼び出しへ展開されるため、
        この結果は ast.parse 可能であり、record_event 側の解析が壊れない。
        変換に失敗した場合は元のコードをそのまま返す。
        """
        try:
            return self.shell.transform_cell(code)
        except Exception:
            return code

    async def do_execute(
        self, code, silent, store_history=True, user_expressions=None, allow_stdin=False
    ):
        """
        セル実行時に呼び出されるメソッド
        """
        self.__del_from_user_ns_hidden()

        self.logger.debug(f"Executing Code:\n{code}")

        # マジック行を含むセルでも記録できるよう、IPythonの入力変換を通した
        # 正規Pythonコードを record_event に渡す（issue #17）。
        transformed_code = self.__transform_cell(code)
        skip_record = self.__is_pure_magic_cell(transformed_code)

        pre_execution_user_ns = (
            set(self.shell.user_ns.keys()) if not skip_record else None
        )
        start_time = time.time() if not skip_record else None

        result = await super().do_execute(
            code, silent, store_history, user_expressions, allow_stdin
        )

        # Q3: 実行が成功したセルのみ記録する。失敗したセルを記録すると、依存グラフに
        # 「実行されたセル」として残り、復元のたびに再計算（再実行）されてしまうため。
        execution_succeeded = isinstance(result, dict) and result.get("status") == "ok"

        if skip_record:
            self.logger.debug("Skipping record event")
        elif not execution_succeeded:
            self.logger.debug("Skipping record event for failed cell execution")
        elif self.elastic_notebook is None:
            self.logger.debug("Skipping record event (ElasticNotebook unavailable)")
        else:
            cell_runtime = time.time() - start_time
            self.logger.debug(f"Cell runtime: {cell_runtime}")
            self.elastic_notebook.record_event(
                transformed_code, pre_execution_user_ns, start_time, cell_runtime
            )
            self.logger.debug("Recording event")

        return result

    def _restore_checkpoint(self):
        """
        self.checkpoint_file_path からチェックポイントを復元する。

        起動時（__init__）と、外部オーケストレーターからの control メッセージの両方から
        呼ばれる共通ロジック。再呼び出し可能（冪等）。結果を dict で返す。

        注意: load_checkpoint は user_ns を上書き・セルを再計算する破壊的操作。発火順序の
        管理は呼び出し側（オーケストレーター）の責務。
        """
        if self.elastic_notebook is None:
            self.logger.info("ElasticNotebook unavailable; cannot restore checkpoint.")
            return {"ok": False, "reason": "plain_kernel_mode"}
        if not os.path.exists(self.checkpoint_file_path):
            self.logger.info(
                "Checkpoint file does not exist. Skipping loading checkpoint."
            )
            return {"ok": False, "reason": "no_checkpoint_file"}

        self.logger.info("Checkpoint file exists. Loading checkpoint.")
        try:
            start_time = datetime.now(timezone(timedelta(hours=9))).strftime(
                "%Y-%m-%dT%H:%M:%S.%f%z"
            )
            self.logger.debug(f"{self.shell.user_ns=}")
            self.logger.info(f"Loading checkpoint started at: {start_time}")

            self.elastic_notebook.load_checkpoint(self.checkpoint_file_path)

            end_time = datetime.now(timezone(timedelta(hours=9))).strftime(
                "%Y-%m-%dT%H:%M:%S.%f%z"
            )
            loading_time = datetime.strptime(
                end_time, "%Y-%m-%dT%H:%M:%S.%f%z"
            ) - datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S.%f%z")
            self.logger.info(f"Loading checkpoint finished at: {end_time}")
            self.logger.info(f"Total loading time: {loading_time}")
            self.logger.debug(f"{self.shell.user_ns=}")
            self.logger.debug(
                f"{self.elastic_notebook.dependency_graph.variable_snapshots=}"
            )
            self.logger.info("Checkpoint successfully loaded.")
            return {
                "ok": True,
                "elapsed_seconds": loading_time.total_seconds(),
                "path": self.checkpoint_file_path,
            }
        except Exception as e:
            self.logger.error(f"Error loading checkpoint: {e}")
            self.logger.error(f"Error details:\n{traceback.format_exc()}")
            return {"ok": False, "reason": "exception", "error": str(e)}

    def _save_checkpoint(self):
        """
        self.checkpoint_file_path へチェックポイントを保存する。

        カーネル終了時（do_shutdown）と、外部オーケストレーターからの control メッセージの
        両方から呼ばれる共通ロジック。再呼び出し可能（冪等）。結果を dict で返す。
        """
        # ElasticNotebook の生成に失敗していた場合はチェックポイントを保存できない。(D-13)
        if self.elastic_notebook is None:
            self.logger.info("ElasticNotebook unavailable; skipping checkpoint save.")
            return {"ok": False, "reason": "plain_kernel_mode"}

        try:
            start_time = datetime.now(timezone(timedelta(hours=9))).strftime(
                "%Y-%m-%dT%H:%M:%S.%f%z"
            )
            self.logger.info(f"Saving checkpoint started at: {start_time}")

            self.elastic_notebook.checkpoint(self.checkpoint_file_path)

            end_time = datetime.now(timezone(timedelta(hours=9))).strftime(
                "%Y-%m-%dT%H:%M:%S.%f%z"
            )
            saving_time = datetime.strptime(
                end_time, "%Y-%m-%dT%H:%M:%S.%f%z"
            ) - datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S.%f%z")
            self.logger.info(f"Saving checkpoint finished at: {end_time}")
            self.logger.info(f"Total saving time: {saving_time}")

            self.logger.info("Checkpoint successfully saved.")
            self.logger.info(
                f"マイグレートする変数の数：{len(self.elastic_notebook.vss_to_migrate)}"
            )
            self.logger.debug(
                f"マイグレートする変数：{self.elastic_notebook.vss_to_migrate}"
            )
            self.logger.info(
                f"再計算する変数の数：{len(self.elastic_notebook.vss_to_recompute)}"
            )
            self.logger.debug(
                f"再計算する変数：{self.elastic_notebook.vss_to_recompute}"
            )
            return {
                "ok": True,
                "elapsed_seconds": saving_time.total_seconds(),
                "path": self.checkpoint_file_path,
                "vss_to_migrate": len(self.elastic_notebook.vss_to_migrate),
                "vss_to_recompute": len(self.elastic_notebook.vss_to_recompute),
            }

        except Exception as e:
            self.logger.error(f"Error saving checkpoint: {e}")
            self.logger.error(f"Error details:\n{traceback.format_exc()}")
            return {"ok": False, "reason": "exception", "error": str(e)}

    async def _run_on_main_loop(self, fn):
        """
        同期関数 fn() を「メインの shell io_loop」上で実行し、その戻り値を await して返す。

        なぜこれが必要か（スレッドの住み分け）:
        - ipykernel では、セル実行 (do_execute) は「メインの shell io_loop」スレッドで動く。
        - 一方、control チャネルのメッセージ（このハンドラ）は「別の control スレッド」で動く。
        - fn には _save_checkpoint / _restore_checkpoint が渡される。これらは self.shell.user_ns
          を読み書きするが、user_ns はセル実行が触っている本体そのもの。control スレッドから
          直接呼ぶと、セル実行中の user_ns を別スレッドが同時に触ることになり、データ競合や
          「半分だけ更新された状態」のスナップショットを生む。

        そこで fn を直接呼ばず、メイン io_loop に「あとで実行して」と予約 (add_callback) する。
        メイン io_loop はセル実行と同じ場所なので、予約された fn は「実行中のセルが無い瞬間」に
        順番が回ってきて実行される。結果として user_ns と排他な状態で保存/復元でき、一貫性が保たれる。

        実装:
        1. asyncio の Future を control 側ループに作る（fn の完了を待つための受け皿）。
        2. fn を包んだ _runner をメイン io_loop に予約する。_runner はメインスレッドで動く。
        3. _runner は fn() の結果（or 例外）を call_soon_threadsafe で control 側ループの Future に
           渡す（スレッドをまたぐので threadsafe 版を使う）。
        4. await fut で、メイン側の fn() が終わるまでこの control ハンドラを中断して待つ。
        """
        # このコルーチンが動いている control 側のイベントループ。Future の所有者になる。
        loop = asyncio.get_running_loop()
        fut = loop.create_future()

        def _runner():
            # ここはメイン io_loop スレッド上。セル実行と排他なので user_ns を安全に触れる。
            try:
                result = fn()
                # 別スレッド(control側)の Future へ結果を渡す。threadsafe でないと壊れる。
                loop.call_soon_threadsafe(fut.set_result, result)
            except (
                Exception
            ) as e:  # メインループ上に例外を漏らさず Future 経由で伝播させる。
                loop.call_soon_threadsafe(fut.set_exception, e)

        # add_callback はスレッドセーフ。メイン io_loop の手が空いたとき（=実行中セルが無い瞬間）に
        # _runner を実行する。control スレッドからメインスレッドへ処理を「橋渡し」している。
        self.io_loop.add_callback(_runner)
        return await fut

    async def _on_checkpoint_request(self, stream, idents, parent):
        """control チャネルの elastic_checkpoint_request ハンドラ。"""
        self.logger.info("Received elastic_checkpoint_request (control channel)")
        try:
            result = await self._run_on_main_loop(self._save_checkpoint)
        except Exception as e:
            result = {"ok": False, "reason": "exception", "error": str(e)}
        self.session.send(
            stream,
            "elastic_checkpoint_reply",
            content=result,
            parent=parent,
            ident=idents,
        )

    async def _on_restore_request(self, stream, idents, parent):
        """control チャネルの elastic_restore_request ハンドラ。"""
        self.logger.info("Received elastic_restore_request (control channel)")
        try:
            result = await self._run_on_main_loop(self._restore_checkpoint)
        except Exception as e:
            result = {"ok": False, "reason": "exception", "error": str(e)}
        self.session.send(
            stream,
            "elastic_restore_reply",
            content=result,
            parent=parent,
            ident=idents,
        )

    def do_shutdown(self, restart):
        """
        カーネル終了時に呼び出されるメソッド
        """
        # 保存ロジックは _save_checkpoint() に共通化。plain-kernel モードの判定もこの中で行い、
        # いずれの場合も通常のシャットダウンを継続する。(D-13)
        # 自動が無効なら終了時の保存はスキップする（control メッセージ経由の明示保存のみ使う）。
        if self.auto_checkpoint:
            self._save_checkpoint()
        else:
            self.logger.info(
                "Skipping shutdown auto-save (auto checkpoint/restore disabled)."
            )
        return super().do_shutdown(restart)


if __name__ == "__main__":
    from ipykernel import kernelapp as app

    app.launch_new_instance(kernel_class=ElasticKernel)
