# ElasticKernel

ElasticKernel: An IPython Kernel that automatically saves and restores Jupyter Notebook execution states.

## 使用方法

### Dockerを用いた方法
1. イメージをプルする
```sh
docker pull ghcr.io/mryutaro/elastickernel
```

2. コンテナを起動する
```sh
docker run -p 8888:8888 ghcr.io/mryutaro/elastickernel
```

3. ブラウザからJupyterLabにアクセスする

4. Python 3 (Elastic)のカーネルを選択する

### ローカルでの使用方法

1. ライブラリをインストールする
```sh
$ uv pip install elastic-kernel
```

2. カーネルをインストールする
```sh
$ elastic-kernel install
Elastic Kernel installed from: /path/to/elastic_kernel
```

3. カーネルがインストールされたか確認する
```sh
$ jupyter kernelspec list
Available kernels:
  elastic_kernel    /Users/matsumotoryutaro/Library/Jupyter/kernels/elastic_kernel
```

4. JupyterLabを起動する

5. ブラウザからJupyterLabにアクセスする

6. Python 3 (Elastic)のカーネルを選択する

## PyPi へのアップロード方法（開発者向け）

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
