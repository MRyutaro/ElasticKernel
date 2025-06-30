# ElasticKernel

IPython Kernel for Jupyter with automatic checkpoint and dependency tracking.

## 使用方法

### ローカルでの使用方法

1. ライブラリをインストールする
```
$ uv pip install elastic-kernel
```

2. カーネルをインストールする
```
$ elastic-kernel install
Elastic Kernel installed from: /path/to/elastic_kernel
```

3. カーネルがインストールされたか確認する
```
$ jupyter kernelspec list
Available kernels:
  elastic_kernel    /Users/matsumotoryutaro/Library/Jupyter/kernels/elastic_kernel
```

4. JupyterLabを起動する

5. Python 3 (Elastic)のカーネルを選択する

## PyPi へのアップロード方法（開発者向け）

### 自動でアップロードする方法

```
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

```
$ uv pip install twine build
$ python -m build
$ python -m twine upload dist/*
```
