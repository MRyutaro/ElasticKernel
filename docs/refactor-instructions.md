# ElasticKernel リファクタリング指示書 (refactor-instructions.md)

> この指示書は、コードベース全体（全ソース・設定・CI・docs）を読み込み、検証コマンドを実際に実行した証拠にもとづいて作成された。
> 実装担当モデルは、この指示書に書かれた範囲だけを、書かれた順序で実施すること。
> **証拠なく大きな削除や全面書き換えをしてはならない。**

作成日: 2026-06-11 / 対象コミット: `6622829` (main)

---

## 0. 実装前に確認すべき質問

以下は人間の回答が必要な質問である。**回答がない項目に関連する変更は実装せず、Phase 6（提案のみ）に留めること。** 回答済みの場合はその指示に従う。

### Q1. 死コード候補の削除可否（公開PyPIパッケージのAPI表面に関わる）
本パッケージは PyPI に `elastic-kernel` として公開されており（`pyproject.toml:6`、`.github/workflows/publish-to-pypi.yml`）、外部スクリプト（研究実験用コードなど）が import している可能性がコードからは否定できない。以下はリポジトリ内では完全に未使用だが、削除してよいか:

- `elastic_notebook/core/io/pickle.py` 全体（`is_picklable` 系。リポジトリ内で参照ゼロ）
- `elastic_notebook/core/common/profile_graph_size.py`（参照ゼロ、docstringに "For experiments only"）
- `elastic_notebook/core/common/checkpoint_file.py:106-132` の `to_json_str` / `from_json`（参照ゼロ。`DependencyGraph` はJSON化不能なので実際には動作しない）
- `elastic_kernel/command.py:27-31` の `PostInstallCommand`（setup.py時代の遺物。参照ゼロ。これがあるため `command.py` が `setuptools` をランタイムimportしている）
- `elastic_notebook/elastic_notebook.py:281-306` の `set_migration_speed` / `set_optimizer` と、それのみから使われる `algorithm/baseline.py`・`algorithm/selector.py` の `OptimizerType`（カーネル経由では到達不能。実験用APIの可能性が高い）

**推奨**: 実験ノート等で使っている可能性があるのは `set_optimizer` 系のみ。それ以外は削除して問題ない可能性が高いが、判断は人間に委ねる。

### Q2. CI の自動フォーマットを check-only に変えてよいか
`.github/workflows/format-python-code.yml` は main への push / PR のたびに素の `isort .` + `black .` を実行し、**bot が main に直接 commit & push する**。現状ローカルに isort/flake8 の設定がないため、isort のデフォルト挙動と black が衝突し、`uv run isort --check-only` が5ファイルで失敗する状態になっている（実測）。CI を「フォーマット崩れがあれば fail させるだけ」に変更してよいか。

**推奨**: check-only に変更し、自動 push をやめる（main の履歴汚染・レース・PRブランチへの push 失敗リスクを除去）。

### Q3. エラーになったセルも依存グラフに記録される現行挙動は意図か
`elastic_kernel/kernel.py:302-311` は `super().do_execute()` の結果（成功/失敗）を見ずに `record_event()` を呼ぶため、例外で失敗したセルも依存グラフに「実行されたセル」として記録され、復元時の再計算対象になり得る。これが意図した挙動か、成功時のみ記録すべきか。

**推奨**: 仕様判断が必要。回答があるまで現行挙動を変えない。

### Q4. `do_shutdown(restart=True)`（カーネル再起動）でもチェックポイントを保存する現行挙動は意図か
`elastic_kernel/kernel.py:318-356` は `restart` フラグを無視して常に checkpoint を保存する。再起動時に保存→直後の `__init__` で復元、という動きになる（これが意図的な「再起動しても状態が残る」体験の可能性が高い）。変更しないが、意図の確認だけしたい。

**推奨**: 現行挙動を維持（確認のみ）。

---

## 1. Objective

既存仕様（チェックポイント保存・復元の挙動、ファイル形式、公開エントリーポイント）を一切壊さずに、以下を達成する:

1. **テスト皆無の状態を解消する**（現在テストは1つも存在しない。これが最大の負債）
2. リポジトリ内に実在するバグ・潜在バグのうち、安全に直せるものを修正する
3. 検証コマンド（lint / format / typecheck）を実際に機能する状態に整備する
4. ドキュメントと実態の乖離を解消する
5. 小さな責務分離（ロガー重複の解消など）で今後の変更を容易にする

**見た目の綺麗さは目的ではない。** 無関係な整形・リネーム・「ついで」のリファクタリングは禁止する。

## 2. Project Understanding

### 何をするものか
ElasticKernel は、Jupyter ノートブックの実行状態（変数）を自動保存・復元するカスタム IPython カーネル。University of Illinois の研究プロジェクト **ElasticNotebook (VLDB 2023/2024)** のコードを取り込み（`elastic_notebook/` 配下の各ファイル先頭に改変表記あり、Apache-2.0）、マジックコマンド手動実行だった原版を「カーネル統合による全自動化」した研究プロジェクトである（`docs/design_docs/differentiation_strategy.md`）。PyPI (`elastic-kernel`) と GHCR (Dockerイメージ) に公開されている。

### 主要なワークフロー
1. **セル実行**: `ElasticKernel.do_execute()` (`elastic_kernel/kernel.py:287`) が実行前の名前空間を取得 → 親クラスでセル実行 → `ElasticNotebook.record_event()` (`elastic_notebook/elastic_notebook.py:138`) が AST 解析(`find_input_vars`)・名前空間差分(`find_created_deleted_vars`)・フィンガープリント比較(`compare_fingerprint`)で入出力変数を特定し、依存グラフ(`DependencyGraph`)を更新する。
2. **チェックポイント（カーネル停止/再起動時）**: `do_shutdown()` → `ElasticNotebook.checkpoint()` → マイグレーション速度をプロファイル(`profile_migration_speed`) → min-cut 最適化(`OptimizerExact.select_vss`, `algorithm/optimizer_exact.py:74`)で「保存する変数」と「再計算する変数」に分割 → `core/io/migrate.py` が dill で `.elastic_kernel/{inode-hash}/checkpoint.pickle` に書き込む。
3. **復元（カーネル起動時）**: `__init__` がチェックポイントファイルの存在を確認 → `load_checkpoint()` → `core/io/recover.py:resume()` がメタデータと変数をロード → `restore_notebook()` が変数を名前空間に注入し、再計算対象セルを `shell.run_cell()` で再実行する。

### エントリーポイント
- カーネル本体: `elastic_kernel/kernel.py` の `ElasticKernel`（`kernel.json` の argv `python -m elastic_kernel.kernel` から起動）
- CLI: `elastic-kernel install` (`elastic_kernel/command.py:main`、`pyproject.toml:48-49`)
- ライブラリ: `from elastic_notebook import ElasticNotebook`（`elastic_notebook/__init__.py` で eager import。**import時間 ~3秒は既知の課題として最適化済み**: `docs/experiments/import_optimization.md`。torch/pandas等を import しない型判定 `object_hash.py:125-206` はこの最適化の成果物なので壊さないこと）

### データの流れ
チェックポイントファイル形式（**互換性を壊してはならない**）: 単一ファイルに dill で「`CheckpointFile` メタデータ → `serialization_order` 順の変数グループのリスト」を**この順で連続 dump** したもの（`migrate.py:108-178`）。読み込みは同じ順で連続 `dill.load`（`recover.py:36-51`）。

### 外部依存
dill / ipykernel / IPython / networkx / numpy / xxhash / jupyter_client / jupyter（`pyproject.toml:15-24`）。psutil はオプショナル（`migrate.py:146-157`、try-import）。DB・認証・課金・通知・外部APIは存在しない。外部I/Oは「ファイルシステム」と「Jupyter Server の `/api/sessions` への HTTP GET」(`kernel.py:140-147`、JPY_SESSION_NAME 不在時のフォールバック)のみ。

### 検証コマンドの現状（2026-06-11 実測）
| コマンド | 結果 |
| --- | --- |
| `uv run black --check elastic_kernel elastic_notebook` | ✅ クリーン（35ファイル） |
| `uv run isort --check-only elastic_kernel elastic_notebook` | ❌ 5ファイル失敗（isort設定なし、blackと非互換） |
| `uv run flake8 elastic_kernel elastic_notebook` | ❌ 163件（157件がE501: 設定なしで79文字制限 vs black 88文字。他は F541×4, E731×2） |
| `uv run mypy elastic_kernel elastic_notebook` | ❌ 29エラー/13ファイル（`uv run mypy` 引数なしはそもそもエラーで動かない。CLAUDE.mdの記載は誤り） |
| テスト | **存在しない**（pytest未導入、CIにテストジョブなし） |
| `uv run python -c "import elastic_kernel.kernel"` | ✅ 成功 |
| `uv run python -c "from elastic_notebook import ElasticNotebook"` | ✅ 成功 |

## 3. Behaviors To Preserve（絶対に壊してはいけない既存挙動）

1. **チェックポイントファイル形式**（上記）。既存ユーザーのディスク上の `checkpoint.pickle` が読めなくなる変更は禁止。`CheckpointFile` のクラス名・属性名・モジュールパス変更も dill の復元を壊すため禁止。同様に `DependencyGraph` / `VariableSnapshot` / `CellExecution` のクラス名・モジュールパス・属性名も変更禁止（pickleに埋め込まれる）。
2. **保存場所の規約**: `.elastic_kernel/{inode番号のSHA256先頭16文字}/checkpoint.pickle`・`ElasticKernel.log`・`ElasticNotebook.log`（`kernel.py:192-224`）。inodeベース命名（リネーム耐性）を維持。
3. **公開エントリーポイント**: `elastic-kernel install` CLI、kernelspec 名 `elastic_kernel`、`kernel.json` の `display_name: "Python 3 (ElasticKernel)"` と argv、`from elastic_notebook import ElasticNotebook`。
4. **環境変数**: `ELASTIC_KERNEL_LOG_LEVEL`（デフォルトINFO）、`JPY_SESSION_NAME` / `JUPYTER_SERVER_URL` / `JUPYTER_BASE_URL` / `JUPYTER_TOKEN` / `KERNEL_ID` の解釈（`kernel.py:116-190`）。
5. **マジックコマンド（`!` `%` `%%` で始まるセル）は依存追跡をスキップ**（`kernel.py:272-285`）。
6. **import時間の最適化**: torch/pandas/polars/lightgbm/scipy を import しないダックタイピング型判定（`object_hash.py:125-206`）。これらのライブラリをトップレベル import に追加してはならない。
7. **チェックポイント失敗時もカーネルの起動・終了は継続する**（例外を握り潰してログに残す方針: `kernel.py:78-79, 108-110, 353-355`）。エラーを上に投げる変更をしない。
8. **依存グラフの意味論**: 変更検出（インプレース変更 vs 上書き、シリアライズ不可オブジェクトの扱い）のロジック（`fingerprint.py:101-186`）は原論文由来のアルゴリズムであり、Phase で明示しない限り触らない。
9. パッケージのビルドと公開フロー: タグ push → PyPI / GHCR 公開（CI）。`uv sync` → `uv run elastic-kernel install` の開発フロー。

## 4. Non-Negotiables（実装上の制約）

- 最初に `git status` を確認する。**既存の未コミット変更（`docs/refactor-goal.md` 等）と自分の変更を混ぜない。**
- 編集前に §2 の表のコマンドを再実行し、baseline の結果を記録する。
- 変更は小さく、戻しやすい単位（1論点=1コミット相当）にする。
- 無関係な整形・ついでのリファクタリング・docstring の言語統一などをしない。
- 既存挙動を勝手に変えない。正しさが不明な場合は実装を止めて質問する。
- 各 Phase ごとに §8 の検証を実施し、結果を記録する。
- 新規依存の追加は dev グループ（pytest 等）のみ許可。ランタイム依存（`[project] dependencies`）は変更しない。
- `elastic_notebook/` は原版ElasticNotebookからの改変コードでApache-2.0のライセンス表記（各ファイル先頭コメント、`elastic_notebook/LICENSE`）を含む。**ライセンス表記・出典コメントを削除しない。**

## 5. Stop And Ask Conditions（実装を止めて質問する条件）

- チェックポイントファイルの形式・内容に影響する変更が必要だと判明したとき
- §0 の Q1〜Q4 に未回答のまま、その領域に手を入れる必要が生じたとき
- テストを書いて初めて「現行実装が明らかに仕様と矛盾する」と判明したとき（テストを実装に合わせて歪めない。報告して質問する）
- `kernel.json`・kernelspec 名・CLI・公開API のシグネチャを変えたくなったとき
- mypy / flake8 対応で型やロジックの実質的変更が必要になったとき（設定・アノテーション追加で済む範囲を超える場合）
- 修正対象のバグについて「現行の誤動作に依存した挙動」が存在しうると気づいたとき

## 6. Baseline Commands

```sh
uv sync                                                  # 依存インストール
uv run python -c "import elastic_kernel.kernel"          # importスモーク
uv run python -c "from elastic_notebook import ElasticNotebook"
uv run black --check elastic_kernel elastic_notebook
uv run isort --check-only elastic_kernel elastic_notebook
uv run flake8 elastic_kernel elastic_notebook
uv run mypy elastic_kernel elastic_notebook
# Phase 1 以降:
uv run pytest
```

注意: `uv run black .` / `isort .` をリポジトリ直下で実行すると、git管理外の `build/`（後述 D-9）まで整形対象になるため、**必ず `elastic_kernel elastic_notebook`（と将来の `tests`）を明示すること。**

## 7. Debt Map

凡例 — 実装可否: ✅=この指示書の範囲で実装してよい / ⚠️=条件付き（記載の範囲のみ） / ❌=提案のみ（Q回答待ち or 設計判断）

### D-1. テストが1つも存在しない ✅（最優先）
- **根拠**: リポジトリに `tests/` なし、pytest 未導入、CIにテストジョブなし。
- **なぜ負債か**: チェックポイント保存・復元という壊れると致命的な機能に安全網がなく、以降のすべての変更のリスクを増幅している。
- **影響範囲**: 全体。**改善案**: Phase 1 参照。**検証**: `uv run pytest` が安定して通ること。

### D-2. recover.py のフォールトトレランス処理が無効化されている（バグ） ⚠️
- **根拠**: `core/io/recover.py:36-53`。変数グループの unpickle 失敗時に `metadata.ces_to_recompute` へ再計算セルを追加する（45-51行）が、直後の53行 `metadata = adapter.read_all(Path(filename))` がファイルを**丸ごと再読込して metadata を上書き**するため、追加が破棄される。コメントと `CheckpointFile.recomputation_ces` の定義（`checkpoint_file.py:40-42` "For fault tolerance"）から、追加を活かすのが意図と判断できる。
- **なぜ負債か**: 「一部の変数が壊れていたら該当セルを再計算で復旧する」という設計意図が機能していない。さらに同じファイルを2回読む（大きなチェックポイントで顕著な無駄）。加えて呼び出し元 `elastic_notebook.py:341-371` の `load_checkpoint` が `FilesystemAdapter().read_all()` で**3回目の全読込**をしている。
- **影響範囲**: 復元パス全体。**変更リスク**: 中。正常系の挙動は変わらないが、異常系（壊れたチェックポイント）の挙動が「黙って変数消失」→「セル再計算」に変わる。これは設計意図への回帰である。
- **改善案**: ① `resume()` は最初に読んだ `metadata` をそのまま使い、53行の再読込を削除。② `resume()` が metadata（または必要フィールド）を返すよう拡張し、`load_checkpoint` の3回目の読込も削除。③ 戻り値・呼び出し規約は `load_checkpoint` 内に閉じているので外部互換性に影響なし。
- **検証**: Phase 1 のラウンドトリップテストに「変数グループの一部を意図的に破壊したファイルを読むと、該当セルが ces_to_recompute に入る」テストを追加してから修正する。
- **実装可否**: ⚠️ テストを先に書いてから実装すること。

### D-3. 検証コマンドが機能していない / CIと設定が衝突 ✅
- **根拠**: §2 の実測。isort・flake8 の設定ファイルが存在せず、`format-python-code.yml` は素の `isort .` を実行（black と非互換）。CLAUDE.md の `uv run mypy`・`uv run flake8` は現状機能しない。mypy 設定もなし。
- **なぜ負債か**: 「リントが通る状態」が定義されておらず、フォーマッタ同士が喧嘩する（CIがmainへ自動pushするため履歴も汚れる）。
- **影響範囲**: 開発フロー全体。**変更リスク**: 低（設定とドキュメントのみ。コード非接触）。
- **改善案**: `pyproject.toml` に `[tool.isort] profile = "black"`、`[tool.flake8]` は flake8 が pyproject 非対応のため `.flake8` ファイルで `max-line-length = 88` / `extend-ignore = E203,E731` / `exclude = build,.venv`。mypy は `[tool.mypy]` で対象を `elastic_kernel`,`elastic_notebook` に限定し、`ignore_missing_imports = true` で外部スタブ起因の19件を抑制（残る実エラーは Phase 5 で個別対応）。CLAUDE.md のコマンド記載を実態に合わせて修正。
- **検証**: `isort --check-only`・`flake8` が0件になること（E501はコード変更なしで解消するはず。F541/E731 は extend-ignore でなくコード修正したくなるが、**F541の修正のみ可**=f接頭辞を外すだけの無害変更。E731 は ignore に入れる）。
- **実装可否**: ✅（ただし CI ワークフロー自体の変更は Q2 回答待ち ❌）

### D-4. 死コード ❌（Q1回答待ち。確定後に削除）
- **根拠と対象**: Q1 のリスト参照。`object_hash.py:264` の `isclass(obj)` も到達不能（217行で先に return 済み）。`profile_variable_size.py:66-74` の `elif isinstance(type(obj), type)` は**常に真**（あらゆるオブジェクトの type は type のインスタンス）なので最後の `else: raise NotImplementedError` も到達不能。さらにその分岐内 `not hasattr(obj, "__sizeof__")` は**常に偽**（全オブジェクトが `__sizeof__` を持つ）なのでカスタムクラスの `__dict__` 再帰は一度も実行されない＝カスタムオブジェクトのサイズは浅い `sys.getsizeof` のみ。
- **なぜ負債か**: 読み手を誤解させ、変更時の調査コストを増やす。`profile_variable_size` の件はサイズ推定の精度（＝最適化の判断）に実害があり得る。
- **影響範囲**: サイズ推定はオプティマイザの migrate/recompute 判断に影響。**変更リスク**: 死コード削除は低、`profile_variable_size` の「修正」は挙動変更（中）。
- **改善案**: Q1 承認後、未使用モジュール・メソッドを削除。`profile_variable_size` の到達不能分岐は**削除のみ**行い、「カスタムクラスを深く測る」修正は挙動が変わるため提案に留める。
- **検証**: 削除後に全テスト・importスモーク・`uv build` が通ること。

### D-5. `select_vss` のインターフェース不整合（baselines は呼ばれたら確実に落ちる） ⚠️
- **根拠**: `notebook/checkpoint.py:115` は `vss_to_migrate, ces_to_recompute = selector.select_vss(notebook_name, optimizer_name)` と2値アンパック+引数2個で呼ぶ。`algorithm/selector.py:35` の基底は `select_vss(self)`、`algorithm/baseline.py:17,33` は引数なしで**1つの set を返す**。さらに `checkpoint.py:185` は `selector.recomputation_ces` を参照するが、これは `OptimizerExact` にしか存在しない。mypy も検出済み（`Too many arguments for "select_vss" of "Selector"`）。`OptimizerExact.select_vss` の引数 `notebook_name`/`optimizer_name` は実験用の名残で未使用（`optimizer_exact.py:74`）。
- **なぜ負債か**: 型・契約の曖昧さ。`set_optimizer("migrate_all")` を呼んだ瞬間に checkpoint が TypeError で全滅する。
- **影響範囲**: `set_optimizer` 利用時のみ（デフォルトパスは OptimizerExact 固定なので現在は顕在化しない）。
- **改善案**: 基底 `Selector.select_vss()` を「`(vss_to_migrate: set, ces_to_recompute: set)` を返す引数なしメソッド」に統一し、`recomputation_ces = {}` を基底 `__init__` へ移動。baselines は `(選択集合, 適切な ces 集合)` を返すよう修正（MigrateAll は空 set、RecomputeAll は全 active CE…ではなく**全 active VS の出力 CE の再計算前提集合**。ここの正しい値はコードから一意に決まらないため、自明でなければ MigrateAll のみ直し RecomputeAll は質問に切り替える）。`checkpoint.py` 側は引数なし呼び出しに変更し、`notebook_name`/`optimizer_name` は**シグネチャから消さず**未使用のまま残す（実験用引数のため。削除は Q1 と同じ判断に含める）。
- **検証**: Phase 1 のオプティマイザ単体テスト + `set_optimizer("migrate_all")` 経由の checkpoint テスト。
- **実装可否**: ⚠️ デフォルトパス（OptimizerExact）の入出力が変わらないことをテストで固定してから。

### D-6. 暗黙のサブモジュール import に依存（潜在バグ） ✅
- **根拠**: `elastic_kernel/kernel.py` は `import logging` のみで `logging.handlers.RotatingFileHandler`（244行）を、`import urllib` のみで `urllib.request` / `urllib.parse`（141-146行）を使用。実測で `import logging; hasattr(logging, 'handlers')` → `False`、`import urllib; hasattr(urllib, 'request')` → `False`。現在は ipykernel が先にこれらを import しているため偶然動いている。
- **なぜ負債か**: ipykernel の内部実装が変わるだけで `AttributeError` でカーネルが起動不能になる。
- **影響範囲**: カーネル起動とログ設定。**変更リスク**: 極小。
- **改善案**: `import logging.handlers`、`import urllib.parse`、`import urllib.request` を明示追加。
- **検証**: importスモーク + Phase 1 のロガー設定テスト。

### D-7. ロガー設定と JSTFormatter の重複 ✅
- **根拠**: `kernel.py:15-26` と `elastic_notebook.py:36-47` に同一の `JSTFormatter`、`kernel.py:226-251` と `elastic_notebook.py:105-127` にほぼ同一の `__setup_logger`。
- **なぜ負債か**: 重複。フォーマット変更が2箇所修正になる。JST固定もここに局所化されていない。
- **影響範囲**: ログのみ。**変更リスク**: 低（ログファイル名・ロガー名 `ElasticKernelLogger`/`ElasticNotebookLogger`・フォーマットを変えなければ挙動同一）。`object_hash.py:16` 等が `logging.getLogger("ElasticNotebookLogger")` を名前で取得しているため、**ロガー名は変更禁止**。
- **改善案**: `elastic_kernel/logging_setup.py`（または `elastic_notebook/core/common/`。import方向は `elastic_kernel → elastic_notebook` の一方向なので後者が無難）に `JSTFormatter` と `setup_logger(name, log_file_path, level_env="ELASTIC_KERNEL_LOG_LEVEL") -> Logger` を抽出し、両者から使う。多重ハンドラ追加防止（同一ファイルへのハンドラ重複チェック）も併せて入れる（現状、同一プロセスで再 init するとハンドラが増殖する）。
- **検証**: ログファイルが従来どおり2本（ElasticKernel.log / ElasticNotebook.log）生成され、フォーマットが同一であること。

### D-8. `do_execute` の冗長性 ✅ / 失敗セルの記録 ❌
- **根拠**: `kernel.py:296-314` で `self.__skip_record(code)` を3回呼ぶ。また実行結果の成否を見ずに `record_event` する（Q3）。
- **改善案**: skip判定を1回にする（✅・挙動同一）。成否での分岐は Q3 回答待ち（❌）。
- **検証**: マジックコマンドスキップのテスト。

### D-9. パッケージング設定の欠陥 ✅
- **根拠**: ① `pyproject.toml:51-52` の `packages.find` が `where=["."]` で include 制限なし → ローカルの `build/` 等も発見対象になり、実際にリポジトリ内に `build/lib/build/lib/build/lib/build/lib/...` という**4重ネストのビルド残骸**が存在する（git管理外）。② `MANIFEST.in:2` が存在しない `elastic_notebook_slim/LICENSE` を参照（実在は `elastic_notebook/LICENSE`）。③ README.md:54 のリンク `/docs/developers.md` は実在ファイル `docs/DEVELOPERS.md` と大文字小文字不一致（GitHub上でリンク切れ）。
- **なぜ負債か**: ②は sdist にライセンスファイルが入らない（公開物の不備）。①はローカルビルドのたびに肥大化した不正パッケージを作るリスク。
- **影響範囲**: 配布物。**変更リスク**: 低。
- **改善案**: `[tool.setuptools.packages.find] include = ["elastic_kernel*", "elastic_notebook*"]` を追加。MANIFEST.in を `include elastic_notebook/LICENSE` に修正。README のリンクを `/docs/DEVELOPERS.md` に修正。ローカルの `build/`・`elastic_kernel.egg-info/` は git 管理外なので**削除してよい**（`rm -rf build elastic_kernel.egg-info`）。
- **検証**: `uv run python -m build`（または `uv build`）で sdist/wheel を作り、`tar tf` / `unzip -l` で中身に `build/` が入らず LICENSE が入ることを確認。

### D-10. ドキュメントと実態の乖離 ✅
- **根拠**: CLAUDE.md は「`docker compose up`」を案内するが compose ファイルは存在しない（git履歴上、過去に削除済み）。CLAUDE.md は `bump2version` を案内するが実際は `bump-my-version`（`.bumpversion.toml`、`docs/DEVELOPERS.md`）。CLAUDE.md の「カーネル選択名 Python 3 (Elastic)」と README の表記も、実際の `kernel.json:2` の `"Python 3 (ElasticKernel)"` と不一致。`uv run mypy`（引数なし）は動かない。
- **改善案**: CLAUDE.md / README.md の記載を実態へ修正（compose 記述を `docker run` ベースへ、コマンド名・表示名・検証コマンドを修正）。`kernel.json` 側は変更しない（ユーザー可視のID）。
- **検証**: 記載コマンドを上から順に実行して全て動くこと。

### D-11. `profile_migration_speed` の危険なシェル実行と無意味な読み取り計測 ⚠️
- **根拠**: `core/common/profile_migration_speed.py:22,61` が `os.system("rm -rf {} && mkdir {}".format(testing_dir, ...))` を使用。ノートブックのディレクトリパスにスペースや特殊文字が含まれると（macOSでは普通にあり得る）壊れる・最悪意図しないパスを削除する。また「read speed」計測（42-45, 53-56行）は**ファイルを open して close するだけで1バイトも読んでいない**。
- **なぜ負債か**: セキュリティ/安全性の境界（シェル文字列結合）と、計測値の妥当性（オプティマイザの入力になる）。
- **改善案**: ✅ `os.system` を `shutil.rmtree(testing_dir, ignore_errors=True)` + `os.makedirs` に置換（挙動同一で安全）。❌ 読み取り計測の修正は migration_speed の値を変え、オプティマイザの判断を変えるため**提案のみ**（修正案: `in_file.read()` を計測に含める）。
- **検証**: スペースを含むディレクトリでの checkpoint テスト（Phase 1 に追加）。

### D-12. `checkpoint()` の O(n²) 重複判定と KeyError リスク ❌
- **根拠**: `notebook/checkpoint.py:82-88` が全 active 変数ペアの総当たりで `fingerprint_dict[name][1]` を参照。`fingerprint_dict` に名前がない場合 KeyError（61行の分岐は in チェックをするのに85行はしない非対称）。
- **提案のみ**: ガード追加は安全に見えるが「fingerprint がない active VS」が実際に発生する条件の確認（record_event との不変条件）が先。テスト整備後に再評価する。

### D-13. 初期化失敗時のフェイルセーフ欠如 ❌
- **根拠**: `kernel.py:72-79` で `ElasticNotebook` 生成失敗を握り潰すが、その後 `do_execute` 等が `self.elastic_notebook` に無条件アクセスするため、結局すべてのセル実行で AttributeError を吐き続ける。
- **提案のみ**: 「追跡なしの素のカーネルとして動作継続する」ガードを入れるのが妥当だが、エラー時のUX方針（ユーザーへの通知方法）はプロダクト判断のため提案に留める。

### D-14. 命名・配置の分かりにくさ ❌（提案のみ）
- `core/io/pickle.py` が標準ライブラリ名と衝突する名前。`CellExecution` のdocstring「Raw cell cell.」等のコピペ痕。`elastic_kernel/command.py` がインストーラと CLI を混在。`fingerprint.py` と `object_hash.py` で別内容の `BASE_TYPES` 定数が重複する名前。いずれも実害が小さく、リネームは履歴を汚すため提案のみ。

## 8. Implementation Phases

各 Phase の終わりに §8 末尾の検証を実行し、結果を記録してから次へ進む。**Phase 内で問題が出たら、その Phase 内で解決するか、revert して質問する。**

### Phase 0: 現状確認（変更なし）
1. `git status` を確認。未コミットの `docs/refactor-goal.md`・`docs/refactor-instructions.md` には触れない。作業ブランチを切る（例: `refactor/phase1-tests`）。
2. §6 の Baseline Commands を全て実行し、結果（件数・エラー要約）を記録する。§2 の表と大きく食い違う場合は質問する。

### Phase 1: 安全網の構築（テスト導入。プロダクションコード変更禁止）
1. dev依存に `pytest` を追加（`uv add --dev pytest`）。`tests/` を作成。
2. 以下のユニットテストを書く（実装に合わせて書く。**実装が直感に反していても、現行挙動をそのまま固定する**。矛盾を見つけたら Stop And Ask）:
   - `find_input_vars`: 単純参照 / AugAssign / 関数内ローカル / global宣言 / UDF再帰
   - `find_created_deleted_vars`: 作成・削除・アンダースコア除外
   - `construct_id_graph` / `is_structure_equals` / `is_root_equals`: list/dict/ネスト/循環参照/共有参照
   - `construct_object_hash` / `compare_fingerprint`: プリミティブ、numpy配列、インプレース変更 vs 上書きの判別
   - `DependencyGraph` + `update_graph`: バージョン採番、エッジ接続
   - `OptimizerExact.select_vss`: 小さな合成グラフで「サイズ極大変数→再計算」「実行時間極大セル→マイグレート」の2ケース
   - `CheckpointFile`: ビルダーの set/get
   - `migrate` → `resume` ラウンドトリップ: ダミー shell（`types.SimpleNamespace(user_ns={...})` で可。`migrate.py` は `shell.user_ns` しか使わない）と手組みの小さな `DependencyGraph` で、一時ディレクトリに書いて読み戻し、変数値・udfs・ces_to_recompute が一致すること
   - 異常系: 上記ラウンドトリップのファイル末尾の変数グループ部分を破壊し、`resume` が例外を出さず読めるところまで読むこと（**この時点では「ces_to_recompute に反映されない」現行バグ挙動をテストで明示し、`# D-2: 現行は破棄される。修正後に反転する` とコメントする**）
   - `ElasticKernel.__skip_record` 相当のロジック: `!`/`%`/`%%` 始まりスキップ（メソッドが private name-mangled のためテスト用に Phase 4 でメソッド抽出するまでは `_ElasticKernel__skip_record` 経由で可。ただしカーネルのインスタンス化は重いので、このテストは Phase 4 まで保留してもよい）
3. （推奨・可能なら）統合テスト: `InteractiveShell.instance()`（IPython）上で `ElasticNotebook` を生成し、`record_event` → `checkpoint` → 新しい `ElasticNotebook` で `load_checkpoint` → `shell.user_ns` に変数が戻ることを確認。Jupyter サーバ不要で動くはず。動かない場合は無理せずスキップし、理由を報告する。
4. CIにテストジョブを追加するかは Q2 と独立に可（新規ワークフロー `test.yml`: `uv sync && uv run pytest`）。既存ワークフローは触らない。

### Phase 2: 設定とドキュメントの整備（コードロジック非接触）
1. D-3: isort（profile=black）・`.flake8`（max-line-length=88, extend-ignore=E203,E731, exclude=build,.venv,dist）・mypy（対象限定+ignore_missing_imports）の設定追加。
2. D-9: `packages.find` の include 追加、MANIFEST.in 修正、README リンク修正。ローカルの `build/`・`elastic_kernel.egg-info/` を削除。
3. D-10: CLAUDE.md / README の実態乖離を修正（compose, bump-my-version, mypy/flake8 コマンド, カーネル表示名）。
4. 検証: `isort --check-only`・`flake8` が 0 件（F541 の4件のみ、f接頭辞を外す最小修正をしてよい）。`uv build` で配布物の中身を確認。`pytest` グリーン維持。

### Phase 3: 明らかに安全なコード修正（挙動同一）
1. D-6: `import logging.handlers` / `import urllib.parse` / `import urllib.request` の明示化。
2. D-11(前半): `os.system` → `shutil.rmtree` + `os.makedirs`。スペース入りパスのテストを追加。
3. D-8(前半): `__skip_record` の呼び出しを1回に。
4. 検証: 全テスト + importスモーク。

### Phase 4: 小さな責務分離と確定バグ修正
1. D-7: ロガー設定の共通化（ロガー名・ファイル名・フォーマット不変。ハンドラ増殖防止を追加）。
2. D-2: recover.py の再読込バグ修正（①53行の上書き削除、② `load_checkpoint` の3回目読込の解消）。Phase 1 の異常系テストの期待値を「ces_to_recompute に反映される」に反転させる。正常系ラウンドトリップが不変であることを確認。
3. D-5: `select_vss` 契約の統一（OptimizerExact のデフォルト経路の入出力不変をテストで担保。RecomputeAll の正しい戻り値が自明でなければその部分のみ Stop And Ask）。
4. 検証: 全テスト + 可能なら統合テスト + 実機確認（§9 の手動手順）。

### Phase 5: 残りの低リスク改善（任意・時間があれば）
1. mypy 実エラー（型アノテーション追加で解決する var-annotated / assignment の約10件）を、ロジック変更なしの範囲で解消。`int` フィールドに `np.inf` を代入する箇所（`variable_snapshot.py:35` の `size=0` と `checkpoint.py:64` の `np.inf`）は型を `float` に直すのみ可。
2. D-12 のガード追加は、Phase 1 のテストで不変条件を確認できた場合のみ。

### Phase 6: 提案のみ（実装禁止。レポートに含める）
- Q1〜Q4 の回答待ち事項（死コード削除、CI check-only化、失敗セル記録、restart時checkpoint）
- D-4 の `profile_variable_size` 精度修正、D-11 後半（read計測修正）、D-13 フェイルセーフ、D-14 命名整理
- 大きな設計変更（増分チェックポイント等、`docs/design_docs/` のロードマップ項目）

## 9. Verification Requirements

各 Phase 完了時に以下を全て実行し、結果（成功/失敗、件数）を記録する:

```sh
uv run pytest
uv run black --check elastic_kernel elastic_notebook tests
uv run isort --check-only elastic_kernel elastic_notebook tests   # Phase 2 以降
uv run flake8 elastic_kernel elastic_notebook tests               # Phase 2 以降
uv run mypy elastic_kernel elastic_notebook                       # 件数が baseline(29) から増えないこと
uv run python -c "import elastic_kernel.kernel"
uv build   # Phase 2 以降、配布物の中身も確認
```

**実機確認**（Phase 4 完了時に必須。それ以外は任意）:
1. `uv run elastic-kernel install` → `jupyter kernelspec list` に `elastic_kernel` が出る
2. `jupyter lab`（または `jupyter console --kernel elastic_kernel`）で変数を定義（例: `x = 42` と `import numpy; a = numpy.arange(10)`）
3. カーネルを再起動し、`x`・`a` が復元されること、`%who` に表示されることを確認
4. `.elastic_kernel/{hash}/ElasticKernel.log` にエラーがないことを確認

## 10. Reporting Format

最終報告には以下を含める:

1. **Phaseごとの実施内容**: 変更ファイル一覧、各変更の1行要約、対応する Debt ID
2. **実行したコマンドと結果**: §9 の全コマンドの最終実行結果（baseline との差分: flake8 163→N 件、mypy 29→N 件、テスト 0→N 件）
3. **挙動差分の宣言**: 「意図して変えた挙動」（D-2 異常系のみのはず）と「変えていないことをテストで確認した挙動」を分けて明記
4. **Stop And Ask に該当した事項**とその扱い
5. **Phase 6 提案リスト**（Q1〜Q4への推奨回答含む）
6. 最後に実行したコマンドとその生の結果

## 11. Out-of-scope Items（やらないこと）

- 増分チェックポイント機能の実装（`docs/design_docs/differentiation_strategy.md` のロードマップ）
- リバースプロキシ/CRIU/コンテナマイグレーション関連（`docs/design_docs/reverse_proxy_seamless_migration.md`）
- チェックポイントファイル形式の変更・バージョニング導入
- 依存ライブラリの追加・更新・削除（dev の pytest を除く）、Python 対応バージョンの変更
- `elastic_notebook` のアルゴリズム（fingerprint/id_graph/min-cut）の精度・性能改善
- パッケージ名・モジュール名・kernelspec 名のリネーム
- import 時間の追加最適化
- ログメッセージの文言・言語の統一（日英混在は現状維持）
