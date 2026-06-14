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