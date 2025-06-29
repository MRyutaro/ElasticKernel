import logging
import os
import time
import traceback
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler

from ipykernel.ipkernel import IPythonKernel

from elastic_notebook import ElasticNotebook


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

        self.logger: logging.Logger
        self.log_file_path: str
        self.checkpoint_file_path: str

        self.__setup_file_path()
        self.__setup_logger()

        # connection_fileからカーネルIDを取得
        connection_file = self.session.config["IPKernelApp"]["connection_file"]
        kernel_id = os.path.splitext(os.path.basename(connection_file))[0].replace(
            "kernel-", ""
        )

        self.logger.info("===============================================")
        self.logger.info(f"Initializing ElasticKernel ({kernel_id})")
        self.logger.debug("Session attributes:")
        for key, value in vars(self.session).items():
            self.logger.debug(f"  - {key}: {value}")
        self.logger.info("===============================================")

        # コマンドライン引数を取得
        # ===========================================
        # !!!!!開発時のみ!!!!!本番環境ではコメントアウトすること!!!!!
        # env = os.environ
        # self.logger.debug(f"Environment: {env}")
        # self.logger.debug(f"Kernel Args: {sys.argv}")
        # self.logger.debug(f"kwargs: {kwargs}")
        # self.logger.debug(f"self.shell: {self.shell}")
        # ===========================================

        # ElasticNotebookをロードする
        try:
            self.elastic_notebook = ElasticNotebook(self.shell)
            self.logger.info("ElasticNotebook successfully loaded.")
        except Exception as e:
            self.logger.error(f"Error loading ElasticNotebook: {e}")

        # ElasticNotebookのログファイルのパスを設定する
        self.elastic_notebook.set_write_log_location(self.log_file_dir)

        # チェックポイントファイルをロードする
        if os.path.exists(self.checkpoint_file_path):
            self.logger.info("Checkpoint file exists. Loading checkpoint.")
            try:
                start_time = datetime.now(timezone(timedelta(hours=9)))
                self.logger.info(f"Loading checkpoint started at: {start_time}")

                self.elastic_notebook.load_checkpoint(self.checkpoint_file_path)

                end_time = datetime.now(timezone(timedelta(hours=9)))
                loading_time = end_time - start_time
                self.logger.info(f"Loading checkpoint finished at: {end_time}")
                self.logger.info(f"Total loading time: {loading_time}")

                self.logger.debug(
                    f"{self.elastic_notebook.dependency_graph.variable_snapshots=}"
                )
                self.logger.debug(f"{self.shell.user_ns=}")
                self.logger.info("Checkpoint successfully loaded.")

            except Exception as e:
                self.logger.error(f"Error loading checkpoint: {e}")
                self.logger.error(f"Error details:\n{traceback.format_exc()}")
        else:
            self.logger.info(
                "Checkpoint file does not exist. Skipping loading checkpoint."
            )

    def __setup_file_path(self):
        # ファイルのパスを設定
        # JPY_SESSION_NAME=/home/vscode/Untitled1.ipynbのような感じ
        jupyter_notebook_path = os.environ.get("JPY_SESSION_NAME")
        if jupyter_notebook_path is None:
            root_dir = os.environ.get("HOME")
            if root_dir is None:
                raise ValueError(
                    "JPY_SESSION_NAME or HOME environment variable is not set."
                )
            jupyter_notebook_name = "Untitled"
        else:
            root_dir = os.path.dirname(jupyter_notebook_path)
            # ファイル名から拡張子を取り除く
            jupyter_notebook_name = os.path.splitext(
                os.path.basename(jupyter_notebook_path)
            )[0]

        # フォルダの作成
        elastic_kernel_dir = os.path.join(root_dir, ".elastic_kernel")
        os.makedirs(elastic_kernel_dir, exist_ok=True)

        self.log_file_dir = os.path.join(elastic_kernel_dir, jupyter_notebook_name)
        os.makedirs(self.log_file_dir, exist_ok=True)
        self.log_file_path = os.path.join(self.log_file_dir, "ElasticKernel.log")
        self.checkpoint_file_path = os.path.join(self.log_file_dir, "checkpoint.pickle")

    def __setup_logger(self):
        # ロガーの設定
        self.logger = logging.getLogger("ElasticKernelLogger")

        # 環境変数からログレベルを取得
        log_level_str = os.environ.get("ELASTIC_KERNEL_LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        self.logger.setLevel(log_level)

        formatter = JSTFormatter(
            "[%(asctime)s ElasticKernelLogger %(levelname)s] %(message)s",
            "%Y-%m-%d %H:%M:%S.%f",
        )

        # ローテーティングファイルハンドラー
        rotating_file_handler = RotatingFileHandler(
            self.log_file_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,  # 5MBのログサイズでローテーション、5世代保存
        )
        rotating_file_handler.setLevel(log_level)
        rotating_file_handler.setFormatter(formatter)
        self.logger.addHandler(rotating_file_handler)

    def __del_from_user_ns_hidden(self):
        # %whoで表示されるようにするために復元した変数をself.shell.user_ns_hiddenから削除する
        self.logger.debug(f"Initial {self.shell.user_ns_hidden=}")

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

        self.logger.debug(f"Final {self.shell.user_ns_hidden=}")

    def __skip_record(self, code):
        skip_magic_commands = ["!", "%", "%%"]
        is_magic_command = any(
            code.strip().startswith(magic) for magic in skip_magic_commands
        )
        if is_magic_command:
            return True

        # TODO: bashなどpythonコードではない場合はスキップする

        return False

    async def do_execute(
        self, code, silent, store_history=True, user_expressions=None, allow_stdin=False
    ):
        self.__del_from_user_ns_hidden()

        self.logger.debug(f"Pre execution user_ns: {self.shell.user_ns}")
        self.logger.debug(f"Executing Code:\n{code}")

        pre_execution_user_ns = (
            set(self.shell.user_ns.keys()) if not self.__skip_record(code) else None
        )
        start_time = time.time() if not self.__skip_record(code) else None

        result = await super().do_execute(
            code, silent, store_history, user_expressions, allow_stdin
        )
        self.logger.debug(f"Post execution user_ns: {self.shell.user_ns}")

        if not self.__skip_record(code):
            cell_runtime = time.time() - start_time
            self.elastic_notebook.record_event(
                code, pre_execution_user_ns, start_time, cell_runtime
            )
            self.logger.debug("Recording event")
        else:
            self.logger.debug("Skipping record event")

        return result

    def do_shutdown(self, restart):
        self.logger.debug("Shutting Down Kernel")
        try:
            start_time = datetime.now(timezone(timedelta(hours=9)))
            self.logger.info(f"Saving checkpoint started at: {start_time}")

            self.elastic_notebook.checkpoint(self.checkpoint_file_path)

            end_time = datetime.now(timezone(timedelta(hours=9)))
            saving_time = end_time - start_time
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

        except Exception as e:
            self.logger.error(f"Error saving checkpoint: {e}")
            self.logger.error(f"Error details:\n{traceback.format_exc()}")
        return super().do_shutdown(restart)


if __name__ == "__main__":
    from ipykernel import kernelapp as app

    app.launch_new_instance(kernel_class=ElasticKernel)
