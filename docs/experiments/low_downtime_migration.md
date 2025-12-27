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
- Rerun (RerunKernel): 全て再実行．計算時間が長いとダウンタイムが伸びるはず．
- Dill (DillKernel): メモリ使用量が増えるとダウンタイムが長くなるはず
- CRIU (ipykernel): メモリ使用量が増えるとダウンタイムが長くなるはず
- ElasticNotebook+ (ElasticKernel==0.0.20): JuyterKernelに組み込んだだけのもの．インポート時間が長い．
- ElasticKernel (ElasticKernel==0.0.27): インポート最適化後

## 評価に使うipynb
メモリ使用量の大小，計算時間の大小

- low memory, low compute
    - 変数を定義するだけのipynb．`hello = "world"`
    - ベースラインとして、どの手法でも速いはず
    - ElasticNotebook+やElasticKernelのオーバーヘッドが目立つはず
- low memory, high compute
    - CPUネックな計算を実行．`fibonacci(40)`で大体17秒の計算時間
    - RerunKernelの弱点（再計算時間）を測る
- high memory, low compute
    - 大きな配列を定義するだけのipynb．`x = np.arange(2**27)` (約1GB)
    - 計算はほとんど行わない
    - CRIU/DillKernelの弱点（メモリシリアライズ時間）を測る
- high memory, high compute
    - CPUもメモリも両方使う．行列演算を行うプログラム．
    - ElasticKernelが有利なはず

## 評価方法
5つの手法×4つの対象×10試行=200

### 手順
1. コンテナを起動する
2. 動かす
3. コンテナを止める
4. コンテナを削除する
5. コンテナを起動する
6. この間にユーザーがリロードしとく

### 計測方法
- E2Eの時間を測定する
    - 始まり: 再起動指示を発行した時刻．date "+%Y-%m-%d %H:%M:%S"; <止めるコマンド>で表示された時刻
    - 終わり: Jupyter KernelがConnecting to kernelが表示された時刻．podman logs <コンテナ名>で表示できる

```
# 起動&停止コマンド
podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name jlab-cr-rerun-kernel jlab-cr-rerun-kernel:latest
podman rm -f jlab-cr-rerun-kernel

podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name jlab-cr-dill-kernel jlab-cr-dill-kernel:latest
podman rm -f jlab-cr-dill-kernel

sudo podman run --runtime runc -d -p 8888:8888 --network host -v $(pwd)/.workspace:/app --cap-add=CHECKPOINT_RESTORE --cap-add=SYS_PTRACE --cap-add=SETPCAP --security-opt seccomp=unconfined --name jlab-cr-criu jlab-cr-criu:latest
sudo podman rm -f jlab-cr-criu

podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name jlab-cr-elastic-kernel-0.0.21 jlab-cr-elastic-kernel-0.0.21:latest
podman rm -f jlab-cr-elastic-kernel-0.0.21

podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name jlab-cr-elastic-kernel-0.0.27 jlab-cr-elastic-kernel-0.0.27:latest
podman rm -f jlab-cr-elastic-kernel-0.0.27
```

```
# ログ表示コマンド
podman logs -f jlab-cr-rerun-kernel
podman logs -f jlab-cr-dill-kernel
sudo podman logs -f jlab-cr-criu
podman logs -f jlab-cr-elastic-kernel-0.0.21
podman logs -f jlab-cr-elastic-kernel-0.0.27
```

```
# 停止コマンド
date "+%Y-%m-%d %H:%M:%S"; podman rm -f jlab-cr-rerun-kernel; podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name jlab-cr-rerun-kernel jlab-cr-rerun-kernel:latest
date "+%Y-%m-%d %H:%M:%S"; podman rm -f jlab-cr-dill-kernel; podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name jlab-cr-dill-kernel jlab-cr-dill-kernel:latest
date "+%Y-%m-%d %H:%M:%S"; podman rm -f jlab-cr-criu; podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name jlab-cr-criu jlab-cr-criu:latest
date "+%Y-%m-%d %H:%M:%S"; podman rm -f jlab-cr-elastic-kernel-0.0.21; podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name jlab-cr-elastic-kernel-0.0.21 jlab-cr-elastic-kernel-0.0.21:latest
date "+%Y-%m-%d %H:%M:%S"; podman rm -f jlab-cr-elastic-kernel-0.0.27; podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name jlab-cr-elastic-kernel-0.0.27 jlab-cr-elastic-kernel-0.0.27:latest
```

## メモ

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
# sudo podman exec jlab-cr-criu sync
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
