# ElasticKernel

## 使い方

1. ライブラリをインストールする
```
pip install elastic-notebook-slim
```

2. カーネルのパスを調べる
```
jupyter kernelspec list
```

2. カーネルのデータを設定する
```
setup.sh <path/to/ElasticKernel> <path/to/kernels>
```

例）
```
setup.sh /tmp/ElasticKernel /usr/local/share/jupyter/kernels
```
