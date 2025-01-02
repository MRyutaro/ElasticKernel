import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone, timedelta

from elastic.elastic_notebook import ElasticNotebook
from ipykernel.ipkernel import IPythonKernel


class JSTFormatter(logging.Formatter):
    """日本時間（JST）用のログフォーマッター"""
    converter = lambda *args: datetime.now(
        timezone(timedelta(hours=9)))  # UTC+9

    def formatTime(self, record, datefmt=None):
        dt = self.converter()
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


class ElasticKernel(IPythonKernel):
    implementation = 'custom_kernel'
    implementation_version = '1.0'
    language = 'python'
    language_version = '3.x'
    language_info = {
        'name': 'python',
        'mimetype': 'text/x-python',
        'file_extension': '.py',
    }
    banner = "Custom Python Kernel with Hooks"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.logger: logging.Logger
        self.log_file_path: str
        self.checkpoint_file_path: str

        self.__setup_file_path()
        self.__setup_logger()

        self.logger.info("=====================================")
        self.logger.info("Initializing ElasticKernel")
        self.logger.info("=====================================")

        # コマンドライン引数を取得
        # ===========================================
        # !!!!!開発時のみ!!!!!本番環境ではコメントアウトすること!!!!!
        env = os.environ
        self.logger.debug(f"Environment: {env}")
        self.logger.debug(f"Kernel Args: {sys.argv}")
        self.logger.debug(f"kwargs: {kwargs}")
        self.logger.debug(f"self.shell: {self.shell}")
        # ===========================================

        # ElasticNotebookをロードする
        try:
            self.elastic_notebook = ElasticNotebook(self.shell)
            self.logger.info("ElasticNotebook successfully loaded.")
        except Exception as e:
            self.logger.error(f"Error loading ElasticNotebook: {e}")

        # チェックポイントをロードする
        if os.path.exists(self.checkpoint_file_path):
            self.logger.info("Checkpoint file exists. Loading checkpoint.")
            try:
                self.elastic_notebook.load_checkpoint(
                    self.checkpoint_file_path)
                self.logger.debug(
                    f"{self.elastic_notebook.dependency_graph.variable_snapshots=}")
                self.logger.debug(
                    f"{self.shell.user_ns=}")
                self.logger.info("Checkpoint successfully loaded.")
            except Exception as e:
                self.logger.error(f"Error loading checkpoint: {e}")
        else:
            self.logger.info(
                "Checkpoint file does not exist. Skipping loading checkpoint.")

    def __setup_file_path(self):
        # ファイルのパスを設定
        # JPY_SESSION_NAME=/home/vscode/Untitled1.ipynbのような感じ
        # TODO: self.user_nsの'__session__': '/home/vscode/Untitled1.ipynb'にもある
        jupyter_notebook_path = os.environ.get("JPY_SESSION_NAME")
        if jupyter_notebook_path is None:
            root_dir = os.environ.get("HOME")
            if root_dir is None:
                raise ValueError(
                    "JPY_SESSION_NAME or HOME environment variable is not set.")
            jupyter_notebook_name = "Untitled"
        else:
            root_dir = os.path.dirname(jupyter_notebook_path)
            # ファイル名から拡張子を取り除く
            jupyter_notebook_name = os.path.splitext(os.path.basename(jupyter_notebook_path))[0]

        # フォルダの作成
        elastic_kernel_dir = os.path.join(root_dir, ".elastic_kernel")
        os.makedirs(elastic_kernel_dir, exist_ok=True)

        self.log_file_path = os.path.join(
            elastic_kernel_dir, jupyter_notebook_name + ".log")
        self.checkpoint_file_path = os.path.join(
            elastic_kernel_dir, jupyter_notebook_name + ".pickle")

    def __setup_logger(self):
        # ロガーの設定
        self.logger = logging.getLogger("ElasticKernelLogger")
        self.logger.setLevel(logging.DEBUG)  # ログレベルを設定
        # formatter = logging.Formatter(
        #     '[%(asctime)s ElasticKernelLogger %(levelname)s] %(message)s')
        formatter = JSTFormatter(
            '[%(asctime)s ElasticKernelLogger %(levelname)s] %(message)s', "%Y-%m-%d %H:%M:%S"
        )

        # コンソールハンドラー
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # ローテーティングファイルハンドラー
        rotating_file_handler = RotatingFileHandler(
            self.log_file_path, maxBytes=5 * 1024 * 1024, backupCount=5  # 5MBのログサイズでローテーション、5世代保存
        )
        rotating_file_handler.setLevel(logging.DEBUG)
        rotating_file_handler.setFormatter(formatter)
        self.logger.addHandler(rotating_file_handler)

    def __del_from_user_ns_hidden(self):
        # %whoで表示されるようにするために復元した変数をself.shell.user_ns_hiddenから削除する
        self.logger.debug(f"Initial {self.shell.user_ns_hidden=}")
        JPY_SESSION_NAME = os.environ.get("JPY_SESSION_NAME")
        self.logger.debug(f"JPY_SESSION_NAME: {JPY_SESSION_NAME}")
        self.logger.debug(f"user_ns.__session__: {self.shell.user_ns.get('__session__')}")

        variable_snapshots = set(
            self.elastic_notebook.dependency_graph.variable_snapshots)
        user_ns_hidden_keys = set(self.shell.user_ns_hidden.keys())

        # 削除対象の変数名を一括で取得
        variables_to_delete = variable_snapshots & user_ns_hidden_keys

        # 一括で削除
        for variable_name in variables_to_delete:
            self.logger.debug(
                f"Deleting {variable_name} from self.shell.user_ns_hidden")
            del self.shell.user_ns_hidden[variable_name]

        self.logger.debug(f"Final {self.shell.user_ns_hidden=}")

    def __skip_record(self, code):
        skip_magic_commands = ["!", "%", "%%"]
        is_magic_command = any(code.strip().startswith(magic)
                               for magic in skip_magic_commands)
        if is_magic_command:
            return True

        # TODO: bashなどpythonコードではない場合はスキップする

        return False

    def do_execute(self, code, silent, store_history=True, user_expressions=None, allow_stdin=False):
        self.logger.debug(f"Executing Code:\n{code}")
        result = super().do_execute(code, silent, store_history,
                                    user_expressions, allow_stdin)

        if not self.__skip_record(code):
            self.elastic_notebook.record_event(code)
            self.logger.debug("Recording event")
        else:
            self.logger.debug("Skipping record event")

        # TODO: ここで毎回呼ぶのは効率悪いのでは？
        self.__del_from_user_ns_hidden()

        return result

    def do_shutdown(self, restart):
        self.logger.debug("Shutting Down Kernel")
        try:
            self.elastic_notebook.checkpoint(self.checkpoint_file_path)
            self.logger.info("Checkpoint successfully saved.")
        except Exception as e:
            self.logger.error(f"Error saving checkpoint: {e}")
        return super().do_shutdown(restart)


if __name__ == '__main__':
    from ipykernel import kernelapp as app
    app.launch_new_instance(kernel_class=ElasticKernel)
