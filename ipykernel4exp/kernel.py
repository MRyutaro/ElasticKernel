import logging
import os
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler

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


class ipykernel4exp(IPythonKernel):
    implementation = "ipykernel4test"
    implementation_version = "1.0"
    language = "python"
    language_version = "3.x"
    language_info = {
        "name": "python",
        "mimetype": "text/x-python",
        "file_extension": ".py",
    }
    banner = "ipykernel4exp"

    def __init__(self, **kwargs):
        self.__setup_logger()
        super().__init__(**kwargs)

    def __setup_logger(self):
        """
        ロガーの設定
        """
        # ロガーの設定
        self.logger = logging.getLogger("ipykernel4expLogger")

        # 環境変数からログレベルを取得
        log_level_str = os.environ.get("IPYKERNEL4EXP_LOG_LEVEL", "DEBUG").upper()
        log_level = getattr(logging, log_level_str, logging.DEBUG)
        self.logger.setLevel(log_level)

        formatter = JSTFormatter(
            "[%(asctime)s %(name)s %(filename)s:%(lineno)d %(levelname)s] %(message)s",
            "%Y-%m-%d %H:%M:%S.%f",
        )

        # ログディレクトリが存在しない場合は作成
        log_dir = ".logs"
        os.makedirs(log_dir, exist_ok=True)

        # ローテーティングファイルハンドラー
        rotating_file_handler = RotatingFileHandler(
            os.path.join(log_dir, "ipykernel4exp.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=5,  # 5MBのログサイズでローテーション、5世代保存
        )
        rotating_file_handler.setLevel(log_level)
        rotating_file_handler.setFormatter(formatter)
        self.logger.addHandler(rotating_file_handler)

    def do_shutdown(self, restart):
        """
        カーネル終了時に呼び出されるメソッド
        """
        start_time = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%dT%H:%M:%S.%f%z")
        self.logger.info(f"ipykernel4exp shutdown started at: {start_time}")
        return super().do_shutdown(restart)


if __name__ == "__main__":
    from ipykernel import kernelapp as app

    app.launch_new_instance(kernel_class=ipykernel4exp)
