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
- runc: 1.3.4

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
podman build -f Dockerfile-RerunKernel -t jlab-cr-rerun-kernel:latest .
# 起動
podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name jlab-cr-rerun-kernel jlab-cr-rerun-kernel:latest
# 停止
podman rm -f jlab-cr-rerun-kernel
```

### DillKernel

```
# ビルド
podman build -f Dockerfile-DillKernel -t jlab-cr-dill-kernel:latest .
# 起動
podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name jlab-cr-dill-kernel jlab-cr-dill-kernel:latest
# 停止
podman rm -f jlab-cr-dill-kernel
```

### CRIU

```
# ビルド
sudo podman build --network host -f Dockerfile-CRIU -t jlab-cr-criu:latest .
# 起動（チェックポイント用のオプション付き、--runtime runcを追加）
sudo podman run --runtime runc -d -p 8888:8888 --network host -v $(pwd)/.workspace:/app --cap-add=CHECKPOINT_RESTORE --cap-add=SYS_PTRACE --cap-add=SETPCAP --security-opt seccomp=unconfined --name jlab-cr-criu jlab-cr-criu:latest
# ディスクバッファをフラッシュして、未書き込みのノート破損を防ぐ
sudo podman exec jlab-cr-criu sync
# チェックポイント（実行中のコンテナの状態を保存）
# --tcp-established: 接続済みTCPソケットをチェックポイントするために必要
sudo podman container checkpoint --tcp-established jlab-cr-criu --export=$(pwd)/.criu/checkpoint.tar.gz
# チェックポイント後、コンテナは停止されるため削除（リストア前に必要）
sudo podman rm jlab-cr-criu
# リストア（チェックポイントから復元）
# --import: エクスポートされたチェックポイントアーカイブから復元
# --name: 新しいコンテナ名を指定（--import使用時は必須）
# --tcp-established: 接続済みTCPソケットを復元（チェックポイント時に使用した場合）
# --runtime runc: ランタイムを明示的に指定
# 注意: --network hostの設定はチェックポイントファイルから自動的に復元される
sudo podman container restore --import=$(pwd)/.criu/checkpoint.tar.gz --tcp-established --runtime runc
# 停止
sudo podman rm -f jlab-cr-criu
```

### ElasticKernel 0.0.21

```
# ビルド
podman build -f Dockerfile-ElasticKernel0021 -t jlab-cr-elastic-kernel-0.0.21:latest .
# 起動
podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name jlab-cr-elastic-kernel-0.0.21 jlab-cr-elastic-kernel-0.0.21:latest
# 停止
podman rm -f jlab-cr-elastic-kernel-0.0.21
```

### ElasticKernel 0.0.27

```
# ビルド
podman build -f Dockerfile-ElasticKernel0027 -t jlab-cr-elastic-kernel-0.0.27:latest .
# 起動
podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name jlab-cr-elastic-kernel-0.0.27 jlab-cr-elastic-kernel-0.0.27:latest
# 停止
podman rm -f jlab-cr-elastic-kernel-0.0.27
```
