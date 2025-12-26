import hashlib
import json
import logging
import logging.handlers
import os
import time
import traceback
import urllib
from datetime import datetime, timedelta, timezone

import dill
from ipykernel.ipkernel import IPythonKernel


class JSTFormatter(logging.Formatter):
    """日本時間（JST）用のログフォーマッター"""

    def converter(self, timestamp):
        dt = datetime.fromtimestamp(timestamp)
        return dt.astimezone(timezone(timedelta(hours=9)))  # UTC+9

    def formatTime(self, record, datefmt=None):
        dt = self.converter(record.created)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # マイクロ秒を3桁まで表示


class DillKernel(IPythonKernel):
    implementation = "DillKernel"
    implementation_version = "1.0"
    language = "python"
    language_version = "3.x"
    language_info = {
        "name": "python",
        "mimetype": "text/x-python",
        "file_extension": ".py",
    }
    banner = "DillKernel"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.logger: logging.Logger
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
        self.logger.info(f"Initializing DillKernel ({kernel_id})")
        self.logger.debug("Session attributes:")
        for key, value in vars(self.session).items():
            self.logger.debug(f"  - {key}: {value}")
        self.logger.info("===============================================")

        # 古い一時ファイルをクリーンアップ（前回の保存処理が中断された場合に備えて）
        temp_file = self.checkpoint_file_path + ".tmp"
        if os.path.exists(temp_file):
            self.logger.warning(f"Found leftover temporary file: {temp_file}. Removing it.")
            try:
                os.remove(temp_file)
            except Exception as e:
                self.logger.warning(f"Failed to remove temporary file: {e}")

        # チェックポイントファイルをロードする
        if os.path.exists(self.checkpoint_file_path):
            # ファイルサイズをチェック（空ファイルでないことを確認）
            file_size = os.path.getsize(self.checkpoint_file_path)
            if file_size == 0:
                self.logger.warning("Checkpoint file exists but is empty. Skipping loading checkpoint.")
                # 空のファイルを削除
                try:
                    os.remove(self.checkpoint_file_path)
                except Exception:
                    pass
            else:
                self.logger.info(f"Checkpoint file exists (size: {file_size} bytes). Loading checkpoint.")
                try:
                    start_time = datetime.now(timezone(timedelta(hours=9))).strftime(
                        "%Y-%m-%dT%H:%M:%S.%f%z"
                    )
                    self.logger.debug(f"{self.shell.user_ns=}")
                    self.logger.info(f"Loading checkpoint started at: {start_time}")

                    with open(self.checkpoint_file_path, "rb") as f:
                        saved_state = dill.load(f)

                    # 保存された変数を復元
                    self.logger.info(f"Checkpoint contains {len(saved_state)} variables: {list(saved_state.keys())}")
                    restored_count = 0
                    restored_variable_names = set()
                    for var_name, var_value in saved_state.items():
                        try:
                            self.logger.info(f"Restoring variable: {var_name} (type: {type(var_value).__name__})")
                            self.shell.user_ns[var_name] = var_value
                            restored_variable_names.add(var_name)
                            restored_count += 1
                        except Exception as e:
                            self.logger.warning(f"Failed to restore variable '{var_name}': {e}")

                    # 復元した変数をuser_ns_hiddenから削除（%whosで表示されるようにするため）
                    # 内部変数は除外する
                    self.logger.info(f"Restored variable names: {restored_variable_names}")
                    self.__del_from_user_ns_hidden(restored_variable_names)

                    end_time = datetime.now(timezone(timedelta(hours=9))).strftime(
                        "%Y-%m-%dT%H:%M:%S.%f%z"
                    )
                    loading_time = datetime.strptime(
                        end_time, "%Y-%m-%dT%H:%M:%S.%f%z"
                    ) - datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S.%f%z")
                    self.logger.info(f"Loading checkpoint finished at: {end_time}")
                    self.logger.info(f"Total loading time: {loading_time}")
                    self.logger.info(f"Restored {restored_count}/{len(saved_state)} variables")
                    # 復元後のuser_nsの内容を確認（ユーザー定義変数のみ）
                    user_defined_vars = {
                        k: v for k, v in self.shell.user_ns.items()
                        if not self.__is_internal_variable(k)
                    }
                    self.logger.info(f"User-defined variables in user_ns after restore: {list(user_defined_vars.keys())}")
                    self.logger.debug(f"{self.shell.user_ns=}")
                    self.logger.info("Checkpoint successfully loaded.")

                except EOFError as e:
                    self.logger.error(f"Checkpoint file is corrupted (EOFError): {e}")
                    self.logger.error("Removing corrupted checkpoint file.")
                    try:
                        os.remove(self.checkpoint_file_path)
                    except Exception:
                        pass
                except Exception as e:
                    self.logger.error(f"Error loading checkpoint: {e}")
                    self.logger.error(f"Error details:\n{traceback.format_exc()}")
        else:
            self.logger.info(
                "Checkpoint file does not exist. Skipping loading checkpoint."
            )

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
        dill_kernel_dir = os.path.join(root_dir, ".dill_kernel")
        os.makedirs(dill_kernel_dir, exist_ok=True)

        self.log_file_dir = os.path.join(dill_kernel_dir, jupyter_notebook_name)
        os.makedirs(self.log_file_dir, exist_ok=True)
        self.log_file_path = os.path.join(self.log_file_dir, "DillKernel.log")
        self.checkpoint_file_path = os.path.join(
            self.log_file_dir, "checkpoint.dill"
        )

    def __setup_logger(self):
        """
        ロガーの設定
        """
        # ロガーの設定
        self.logger = logging.getLogger("DillKernelLogger")

        # 環境変数からログレベルを取得
        log_level_str = os.environ.get("DILL_KERNEL_LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        self.logger.setLevel(log_level)

        formatter = JSTFormatter(
            "[%(asctime)s %(name)s %(filename)s:%(lineno)d %(levelname)s] %(message)s",
            "%Y-%m-%d %H:%M:%S.%f",
        )

        # ローテーティングファイルハンドラー
        rotating_file_handler = logging.handlers.RotatingFileHandler(
            self.log_file_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,  # 5MBのログサイズでローテーション、5世代保存
        )
        rotating_file_handler.setLevel(log_level)
        rotating_file_handler.setFormatter(formatter)
        self.logger.addHandler(rotating_file_handler)

    def __try_pickle_variable(self, var_name, var_value):
        """
        変数をpickleしてみて、可能かどうかを判定
        実際にpickleしてエラーが発生しないか確認する
        """
        try:
            import io
            buffer = io.BytesIO()
            dill.dump(var_value, buffer)
            return True, None
        except Exception as e:
            return False, str(e)

    def __is_internal_variable(self, var_name):
        """
        IPythonの内部変数かどうかを判定する
        """
        # アンダースコアで始まる変数（_i*, _*など）
        if var_name.startswith('_'):
            return True
        
        # IPythonの組み込み変数
        internal_vars = {
            'In', 'Out', 'exit', 'quit', 'open', 'get_ipython',
            '__name__', '__doc__', '__package__', '__loader__', '__spec__',
            '__builtin__', '__builtins__', '_ih', '_oh', '_dh'
        }
        if var_name in internal_vars:
            return True
        
        return False

    def __del_from_user_ns_hidden(self, variable_names=None):
        """
        %whosで表示されるようにするために変数をself.shell.user_ns_hiddenから削除する
        variable_namesがNoneの場合は、user_nsに存在するユーザー定義変数のみを対象とする
        """
        if variable_names is None:
            # user_nsに存在するユーザー定義変数のみを対象とする（内部変数を除外）
            variable_names = {
                var_name for var_name in self.shell.user_ns.keys()
                if not self.__is_internal_variable(var_name)
            }
        else:
            # 指定された変数名から内部変数を除外
            variable_names = {
                var_name for var_name in variable_names
                if not self.__is_internal_variable(var_name)
            }
        
        user_ns_hidden_keys = set(self.shell.user_ns_hidden.keys())
        variables_to_delete = variable_names & user_ns_hidden_keys

        # 一括で削除
        for variable_name in variables_to_delete:
            self.logger.debug(
                f"Deleting {variable_name} from self.shell.user_ns_hidden"
            )
            del self.shell.user_ns_hidden[variable_name]

    async def do_execute(
        self, code, silent, store_history=True, user_expressions=None, allow_stdin=False
    ):
        """
        セル実行時に呼び出されるメソッド
        """
        # 実行前に既存の変数をuser_ns_hiddenから削除（復元された変数が表示されるようにするため）
        self.__del_from_user_ns_hidden()
        
        # 実行前の変数名を取得
        pre_execution_vars = set(self.shell.user_ns.keys())
        
        self.logger.debug(f"Executing Code:\n{code}")

        # 親クラスのdo_executeを呼び出してコードを実行
        result = await super().do_execute(
            code, silent, store_history, user_expressions, allow_stdin
        )

        # 実行後の変数名を取得
        post_execution_vars = set(self.shell.user_ns.keys())
        # 新しく追加された変数をuser_ns_hiddenから削除（%whosで表示されるようにするため）
        newly_added_vars = post_execution_vars - pre_execution_vars
        if newly_added_vars:
            self.__del_from_user_ns_hidden(newly_added_vars)
        
        # 念のため、実行後に再度全ての変数を確認（IPythonが実行中にuser_ns_hiddenに追加する可能性があるため）
        self.__del_from_user_ns_hidden()

        return result

    def do_shutdown(self, restart):
        """
        カーネル終了時に呼び出されるメソッド
        """
        try:
            start_time = datetime.now(timezone(timedelta(hours=9))).strftime(
                "%Y-%m-%dT%H:%M:%S.%f%z"
            )
            self.logger.info(f"Saving checkpoint started at: {start_time}")

            # 全ての変数をdillで保存
            # 内部変数は除外（__is_internal_variable()を使用）
            user_vars = {
                k: v
                for k, v in self.shell.user_ns.items()
                if not self.__is_internal_variable(k)
            }
            self.logger.info(f"Found {len(user_vars)} user-defined variables to save: {list(user_vars.keys())}")
            
            # 各変数を個別にpickleして、可能なものだけを保存
            pickleable_vars = {}
            skipped_vars = []
            
            for var_name, var_value in user_vars.items():
                can_pickle, error_msg = self.__try_pickle_variable(var_name, var_value)
                if can_pickle:
                    pickleable_vars[var_name] = var_value
                else:
                    skipped_vars.append((var_name, error_msg))
                    self.logger.warning(f"Skipping variable '{var_name}': {error_msg}")
            
            if skipped_vars:
                self.logger.info(f"Skipped {len(skipped_vars)} unpickleable variables")
                for var_name, error_msg in skipped_vars:
                    self.logger.debug(f"  - {var_name}: {error_msg}")
            
            if not pickleable_vars:
                self.logger.warning("No pickleable variables to save. Skipping checkpoint save.")
                return super().do_shutdown(restart)
            
            # 一時ファイルに保存してから移動（アトミックな操作）
            temp_file = self.checkpoint_file_path + ".tmp"
            with open(temp_file, "wb") as f:
                dill.dump(pickleable_vars, f)
            
            # 成功したら元のファイルを置き換え
            os.replace(temp_file, self.checkpoint_file_path)

            end_time = datetime.now(timezone(timedelta(hours=9))).strftime(
                "%Y-%m-%dT%H:%M:%S.%f%z"
            )
            saving_time = datetime.strptime(
                end_time, "%Y-%m-%dT%H:%M:%S.%f%z"
            ) - datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S.%f%z")
            self.logger.info(f"Saving checkpoint finished at: {end_time}")
            self.logger.info(f"Total saving time: {saving_time}")
            self.logger.info(f"Saved {len(pickleable_vars)} variables")
            self.logger.info("Checkpoint successfully saved.")

        except Exception as e:
            self.logger.error(f"Error saving checkpoint: {e}")
            self.logger.error(f"Error details:\n{traceback.format_exc()}")
            # エラー時は一時ファイルを削除
            temp_file = self.checkpoint_file_path + ".tmp"
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
        return super().do_shutdown(restart)


if __name__ == "__main__":
    from ipykernel import kernelapp as app

    app.launch_new_instance(kernel_class=DillKernel)
