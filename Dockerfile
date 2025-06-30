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

# 依存関係をインストール
RUN uv pip install --system . && \
    elastic-kernel install

WORKDIR /app

CMD ["jupyter", "lab", "--allow-root", "--ip=0.0.0.0"]
