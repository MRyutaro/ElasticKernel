# ElasticKernel

## 使い方

1. ライブラリをインストールする
```
pip install elastic-notebook-slim
```

2. カーネルをインストールする
```
jupyter kernelspec install --user elastic_kernel
```


## PyPi へのアップロード方法

### 自動でアップロードする方法

```
uv pip install -e .  # 初回のみ実行する
bump2version {hogehoge}  # コマンドは以下のいずれかから選択する
git push --follow-tags  # コミットとタグの両方をプッシュする
```

| コマンド             | 説明                       | バージョン変更例 |
| -------------------- | -------------------------- | ---------------- |
| `bump2version patch` | パッチバージョンを上げる   | 0.0.1 → 0.0.2    |
| `bump2version minor` | マイナーバージョンを上げる | 0.1.0 → 0.2.0    |
| `bump2version major` | メジャーバージョンを上げる | 1.0.0 → 2.0.0    |

### 手動でアップロードする方法

```
uv pip install twine build
python -m build
python -m twine upload dist/*
```
