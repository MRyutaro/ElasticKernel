# Low Downtime Migration

## 概要
ElasticKernelを用いることでダウンタイムを短くできているかどうかを評価する．

## 評価環境
- Python: 3.12.3
- OS: Linux 6.8.0-88-generic (Ubuntu)
- CPU: Intel Xeon Silver 4214R @ 2.40GHz (8 cores)
- Memory: 16GB
- criu: 4.1.1
- podman: 4.9.3

## 比較
- CRIU (ipykernel): メモリ使用量が増えるとダウンタイムが長くなるはず
- Dill (DillKernel): メモリ使用量が増えるとダウンタイムが長くなるはず
- Rerun (RerunKernel): 全て再実行．計算時間が長いとダウンタイムが伸びるはず．
- ElasticNotebook+(ElasticKernel==0.0.20): JuyterKernelに組み込んだだけのもの．インポート時間が長い．
- ElasticKernel==0.0.27: インポート最適化後

## 評価に使うipynb
メモリ使用量の大小，計算時間の大小

- low memory, low compute
    - 変数を定義するだけのipynb．hello = "world"
- low memory, high compute
    - 
- high memory, low compute
    - 変数を定義するだけのipynb．x = np.arrange(2**28)
- high memory, high compute
    - 

## 評価方法
5つの手法×4つの対象×10試行=200

### RerunKernel

```
# ビルド
podman build -f Dockerfile-RerunKernel -t rerun-kernel:latest .
# 起動
podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name rerun-kernel rerun-kernel:latest
# 停止
podman stop rerun-kernel && podman rm rerun-kernel
```

### DillKernel

```
# ビルド
podman build -f Dockerfile-DillKernel -t dill-kernel:latest .
# 起動
podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name dill-kernel dill-kernel:latest
# 停止
podman stop dill-kernel && podman rm dill-kernel
```

### CRIU
```
```

### ElasticKernel 0.0.20

```
# ビルド
podman build -f Dockerfile-ElasticKernel0020 -t elastic-kernel-0.0.20:latest .
# 起動
podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name elastic-kernel-0.0.20 elastic-kernel-0.0.20:latest
# 停止
podman stop elastic-kernel-0.0.20 && podman rm elastic-kernel-0.0.20
```

### ElasticKernel 0.0.27

```
# ビルド
podman build -f Dockerfile-ElasticKernel0027 -t elastic-kernel-0.0.27:latest .
# 起動
podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name elastic-kernel-0.0.27 elastic-kernel-0.0.27:latest
# 停止
podman stop elastic-kernel-0.0.27 && podman rm elastic-kernel-0.0.27
```
