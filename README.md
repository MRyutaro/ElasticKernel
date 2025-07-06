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

## 開発者向け資料

[ここ](/docs/developers.md)を参考にしてください．
