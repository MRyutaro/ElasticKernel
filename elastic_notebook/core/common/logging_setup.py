# This file has been modified from the original ElasticNotebook.
# Original: https://github.com/illinoisdata/ElasticNotebook

import logging
import os
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler

# ロガー名・ログファイル名・このフォーマットは ElasticKernel/ElasticNotebook の
# 両方で共有される。object_hash.py 等がロガー名で取得しているため、フォーマットや
# 名前を変更しないこと。
LOG_FORMAT = "[%(asctime)s %(name)s %(filename)s:%(lineno)d %(levelname)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S.%f"


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


def setup_logger(
    name: str,
    log_file_path: str,
    level_env: str = "ELASTIC_KERNEL_LOG_LEVEL",
) -> logging.Logger:
    """
    名前付きロガーに、JST フォーマットのローテーティングファイルハンドラーを設定して返す。

    同一ファイルへのハンドラーが既に存在する場合は二重に追加しない（同一プロセスで
    再初期化した際にハンドラーが増殖するのを防ぐ）。
    """
    logger = logging.getLogger(name)

    # 環境変数からログレベルを取得
    log_level_str = os.environ.get(level_env, "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    logger.setLevel(log_level)

    # 同一ファイルへのハンドラーが既にある場合は二重追加を避ける。
    target = os.path.abspath(log_file_path)
    for handler in logger.handlers:
        if (
            isinstance(handler, RotatingFileHandler)
            and os.path.abspath(getattr(handler, "baseFilename", "")) == target
        ):
            handler.setLevel(log_level)
            return logger

    formatter = JSTFormatter(LOG_FORMAT, DATE_FORMAT)

    # ローテーティングファイルハンドラー
    rotating_file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,  # 5MBのログサイズでローテーション、5世代保存
    )
    rotating_file_handler.setLevel(log_level)
    rotating_file_handler.setFormatter(formatter)
    logger.addHandler(rotating_file_handler)

    return logger
