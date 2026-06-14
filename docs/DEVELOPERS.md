# ElasticKernel for Developers

## 環境変数
| 環境変数 | 説明 |
| --- | --- |
| `ELASTIC_KERNEL_LOG_LEVEL=DEBUG` | デバックモード．詳細なログが表示される． |

```
ELASTIC_KERNEL_LOG_LEVEL=DEBUG jupyter lab
```

## PyPi へのアップロード方法

### 自動でアップロードする方法

```sh
$ uv pip install bump-my-version  # 初回のみ実行する
$ bump-my-version bump {hogehoge}  # コマンドは以下のいずれかから選択する
$ git push --follow-tags  # コミットとタグの両方をプッシュする
```

| コマンド             | 説明                       | バージョン変更例 |
| -------------------- | -------------------------- | ---------------- |
| `bump-my-version bump patch` | パッチバージョンを上げる   | 0.0.1 → 0.0.2    |
| `bump-my-version bump minor` | マイナーバージョンを上げる | 0.1.0 → 0.2.0    |
| `bump-my-version bump major` | メジャーバージョンを上げる | 1.0.0 → 2.0.0    |

### 手動でアップロードする方法

```sh
$ uv pip install twine build
$ python -m build
$ python -m twine upload dist/*
```

## 今後の課題 (Future Work)

### 対応バージョンの明記（CI で検証したい）

現状、README では「動作する Python / JupyterLab / ipykernel のバージョン」を明記していない。
`pyproject.toml` の classifiers には Python 3.8〜3.11 と記載があるが、これは宣言値であって
実際に動作検証されたものではない。

**やりたいこと:**
- 複数の Python バージョン（および主要な `ipykernel` / `jupyterlab` バージョン）で
  チェックポイントの保存・復元が通ることを **CI のテストマトリクスで検証**する。
- 検証が取れたバージョンを README に「Supported versions」として明記し、
  PyPI の `pyversions` バッジ等で可視化する。

**前提:** まずテストスイートの整備が必要（`docs/prompts/refactor-instructions.md` の Phase 1）。
テストが揃ってから GitHub Actions に matrix ビルドを追加する。