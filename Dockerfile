FROM python:3.12-slim

WORKDIR /tmp

# システムライブラリをインストール
RUN apt-get update && apt-get install -y \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# uvのセットアップ
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 必要なソースコードをコピー
COPY elastic_kernel/ ./elastic_kernel/
COPY elastic_notebook/ ./elastic_notebook/
COPY pyproject.toml ./
COPY uv.lock ./

# 依存関係をインストール
RUN uv sync --frozen --no-editable && \
    uv run elastic-kernel install

WORKDIR /app

# パスを設定
ENV PATH="/tmp/.venv/bin:$PATH"

# --ip=0.0.0.0 だけだと、表示されるアクセスURLにコンテナのホスト名が使われ、
# ホスト側のブラウザから到達できない。custom_display_url で 127.0.0.1 に固定する。
CMD ["jupyter", "lab", "--allow-root", "--no-browser", "--ip=0.0.0.0", "--port=8888", "--ServerApp.custom_display_url=http://127.0.0.1:8888"]
