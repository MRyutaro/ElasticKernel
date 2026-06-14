# CLAUDE.md

このファイルは、Claude Code (claude.ai/code) がこのリポジトリで作業する際のガイダンスを提供します。

## プロジェクト概要

ElasticKernelは、Jupyterノートブックの実行状態を自動的に保存・復元するカスタムIPythonカーネルです。セル間の変数依存関係を追跡し、コスト分析に基づいて変数を選択的にマイグレートまたは再計算することで、状態の移行を最適化します。

## 開発コマンド

### 環境セットアップ
```sh
# uvを使用して依存関係をインストール
uv sync

# Jupyterにカーネルをインストール
uv run elastic-kernel install

# カーネルのインストールを確認
jupyter kernelspec list
```

### アプリケーションの実行

**Dockerを使用する場合:**
```sh
docker run -p 8888:8888 ghcr.io/mryutaro/elastickernel
# http://127.0.0.1:8888 でJupyterLabにアクセス
# "Python 3 (ElasticKernel)" カーネルを選択
```

**ローカル開発の場合:**
```sh
# JupyterLabを起動
jupyter lab
# "Python 3 (ElasticKernel)" カーネルを選択
```

### コード品質

```sh
# コードフォーマット
uv run black elastic_kernel elastic_notebook tests
uv run isort elastic_kernel elastic_notebook tests

# リント
uv run flake8 elastic_kernel elastic_notebook tests

# 型チェック
uv run mypy

# テスト
uv run pytest
```

### バージョン管理・リリース（PyPI / GHCR への公開）

リリースは **release-please** で管理する（設定は `release-please-config.json` と `.release-please-manifest.json`、ワークフローは `.github/workflows/release-please.yml`）。

**フロー:**
1. main にマージされたコミット（PR）の **Conventional Commits** から release-please が次バージョンを判定し、`pyproject.toml` のバージョン更新と `CHANGELOG.md` をまとめた**リリース PR を自動作成・更新**する。
2. そのリリース PR を**マージ**すると、`v{version}` タグと GitHub Release が自動で作られる。
3. タグ（`v*.*.*`）を起点に既存の 2 ワークフローが発火して公開する: `publish-to-pypi.yml` → PyPI、`docker-publish.yml` → GHCR（Dockerイメージ）。

**バンプレベルはコミット種別で決まる**（手動指定ではない）:
- `fix:` → **patch**（0.0.28 → 0.0.29）
- `feat:` → **minor**（0.0.28 → 0.1.0）
- `feat!:` / `fix!:` または本文に `BREAKING CHANGE:` → **major**（0.0.28 → 1.0.0）
- `docs:` `refactor:` `chore:` `test:` `ci:` などはリリースに含まれるがバージョンは上げない。
- 特定バージョンへ強制したい場合はコミット本文に `Release-As: 1.0.0` を記載する。
- Squash merge では **PR タイトルが判定に使われる**ため、PR タイトルを Conventional Commits 形式にする。

**前提セットアップ:** GITHUB_TOKEN で作成したタグは他ワークフローを起動できない（GitHub の仕様）。PyPI/GHCR への公開を自動発火させるには、PAT もしくは GitHub App トークンをリポジトリ Secret `RELEASE_PLEASE_TOKEN` に設定する。未設定でもリリース PR 作成・タグ付けは動くが、その場合は公開がトリガーされない。

> 旧来の `bump-my-version`（`.bumpversion.toml`）は手動フォールバックとして残してある。`bump-my-version bump <level>` でローカルからタグを打って `git push --follow-tags` すれば従来どおり公開できる。手動公開（CIを使わない方法）は `docs/DEVELOPERS.md` を参照。

## アーキテクチャ

### 高レベル構造

コードベースは2つの主要パッケージに分かれています：

1. **`elastic_kernel/`** - Jupyterと統合するIPythonカーネルの実装
2. **`elastic_notebook/`** - 依存関係追跡と状態管理のコアロジック

### 主要コンポーネント

**ElasticKernel (elastic_kernel/kernel.py)**
- IPythonKernelを拡張してセル実行をインターセプト
- `do_execute()` にフックして各セル実行前後の変数変更を追跡
- `do_shutdown()` にフックしてカーネル停止時にチェックポイントを保存
- ノートブックごとにinode番号ベースのハッシュを使用してチェックポイントファイル名を生成
- ログは `.elastic_kernel/{hash}/ElasticKernel.log` に保存される

**ElasticNotebook (elastic_notebook/elastic_notebook.py)**
- すべてのチェックポイント・復元操作の中心的なコーディネーター
- `record_event()` を通じて実行を追跡：
  - 変更検出のためのフィンガープリント（IDグラフ + オブジェクトハッシュ）を構築
  - セルごとの入力・出力・変更・削除された変数を特定
  - 変数間の依存関係グラフを更新
- `checkpoint()` を通じてチェックポイントを最適化：
  - ファイルシステムへのマイグレーション速度をプロファイリング
  - オプティマイザーを実行してマイグレートする変数と再計算する変数を決定
  - 選択された変数とメタデータをシリアライズ

**Dependency Graph (elastic_notebook/core/graph/)**
- `DependencyGraph`: 以下の関係を維持：
  - `VariableSnapshot` (VS): 特定時点の変数
  - `CellExecution` (CE): 変数を作成・変更するセル実行
- グラフのエッジは依存関係を表現：変数Bが変数Aを使用する場合、AのVSからBのVSへのエッジが存在

**Mutation Detection (elastic_notebook/core/mutation/)**
- `fingerprint.py`: 変更検出のためのオブジェクトフィンガープリントを作成・比較
  - フィンガープリント = (object_hash, id_graph, representation)
  - IDグラフはシリアライズ不可能なオブジェクトの識別関係を追跡
- `object_hash.py`: xxhashを使用してコンテンツハッシュを計算
- 特殊ケースを処理：シリアライズ不可能なオブジェクト、インプレース変更、参照の変更

**Checkpointing (elastic_notebook/core/io/)**
- `migrate.py`: チェックポイント作成のコアロジック
  - オプティマイザーアルゴリズムを実行してマイグレーション vs 再計算戦略を決定
  - dillを使用して選択された変数をシリアライズ
  - メタデータ（依存関係グラフ、UDF、最適化の決定）を保存
- `recover.py`: チェックポイントからノートブック状態を復元
  - メタデータとマイグレートされた変数をロード
  - チェックポイント戦略に基づいて再計算するセルを特定
- `filesystem_adapter.py`: チェックポイントのファイルI/Oを処理

**Optimization Algorithms (elastic_notebook/algorithm/)**
- `optimizer_exact.py`: OptimizerExact - 以下に基づいて最適なマイグレーション・再計算の分割を見つける：
  - マイグレーションコスト: 変数サイズ / マイグレーション速度
  - 再計算コスト: セル実行時間
- `baseline.py`: ベースライン戦略（全てマイグレート、全て再計算）
- マイグレーション速度はチェックポイントディレクトリにテストデータを書き込んで動的にプロファイリング

### 実行フロー

**セル実行:**
1. ユーザーがJupyterでセルを実行
2. `ElasticKernel.do_execute()` が実行前の名前空間をキャプチャ
3. 親のIPythonKernelを通じてセルが実行される
4. `ElasticNotebook.record_event()` が変更を分析：
   - AST解析を通じて入力変数を検出
   - 名前空間の差分から作成・削除された変数を検出
   - フィンガープリント比較から変更された変数を検出
   - 新しいエッジで依存関係グラフを更新
5. ユーザーに結果を返す

**チェックポイント（カーネル停止時）:**
1. `ElasticKernel.do_shutdown()` がチェックポイントをトリガー
2. `ElasticNotebook.checkpoint()`:
   - ファイルシステムへのマイグレーション速度をプロファイリング
   - オプティマイザーを実行して変数をマイグレートセットと再計算セットに分割
   - マイグレートされた変数とメタデータを `.elastic_kernel/{hash}/checkpoint.pickle` にシリアライズ

**復元（カーネル起動時）:**
1. `ElasticKernel.__init__()` がチェックポイントファイルをチェック
2. `ElasticNotebook.load_checkpoint()`:
   - メタデータとマイグレートされた変数をデシリアライズ
   - マイグレートされた変数をカーネルの名前空間に注入
   - 再計算セットの変数のためにセルを再計算
   - 依存関係グラフの状態を復元

## 重要な注意事項

- チェックポイントファイルはファイル名ではなくノートブックのinode番号のハッシュを使用（セッション継続中はリネームに対応）
- 環境変数 `ELASTIC_KERNEL_LOG_LEVEL` でログの詳細度を制御（デフォルト: INFO）
- マジックコマンド（!, %, %%）は意図的に依存関係追跡からスキップされる
- dillをシリアライゼーションに使用（Pythonオブジェクトに対してpickleより強力）
- マイグレーション速度のプロファイリングは `alpha` パラメータを使用してコストスケーリングを調整

## 開発時のテスト

カーネルの変更をテストするには：
1. コードを変更
2. カーネルを再インストール: `uv run elastic-kernel install`
3. Jupyterカーネルを再起動（ノートブックだけでなく）
4. `.elastic_kernel/{hash}/ElasticKernel.log` でログを確認
