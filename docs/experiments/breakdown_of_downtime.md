# Breakdown of Downtime

「インポートに着目する以前にまずスタートアップ全体の内訳を見なければいけないのでは？」という指摘があったので実験
nekoで実験
ipykernel，elastickernel0021，elastickernel0027で比較したい
downはせずキャッシュありの状態で実験したい
各手法5回ずつで実験したい
ipynbは001.ipynbを使う
コンテナはrerun, elastickernel0021, elastickernel0027を使えばいいか？

- Checkpoint session state: セッション状態の保存．ElasticKernel.logのログ参照
- Stop Jupyter Notebook: Jupyter Notebookの停止．received signal 15からcontainer diedまで
- Stop container: コンテナの停止．container diedからcontainer cleanupまで．
- Start container: コンテナの起動．container initからcontainer startまで．
- Start Jupyter Notebook: Jupyter Notebookの起動．container startからhttp://127.0.0.1:8888/labが表示されるまでの時間
- Wait for manual reconnection: 手動再接続までの待ち時間．http://127.0.0.1:8888/labからKernel startedまでの時間
- Start Jupyter Kernel except for restoring session state: Jupyter Kernelの起動．（Kernel startedからConnecting to kernel）-（Restore session stateの時間）
- Restore session state: セッション状態の復元．ElasticKernel.logのログ参照

## 手順

ビルド
```
podman build -f Dockerfile-RerunKernel -t jlab-cr-rerun-kernel:latest .

podman build -f Dockerfile-ElasticKernel0021 -t jlab-cr-elastic-kernel-0.0.21:latest .

podman build -f Dockerfile-ElasticKernel0027 -t jlab-cr-elastic-kernel-0.0.27:latest .
```

起動&停止
```
podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name jlab-cr-rerun-kernel jlab-cr-rerun-kernel:latest
podman rm -f jlab-cr-rerun-kernel

podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name jlab-cr-elastic-kernel-0.0.21 jlab-cr-elastic-kernel-0.0.21:latest
podman rm -f jlab-cr-elastic-kernel-0.0.21

podman run -d -p 8888:8888 -v $(pwd)/.workspace:/app --name jlab-cr-elastic-kernel-0.0.27 jlab-cr-elastic-kernel-0.0.27:latest
podman rm -f jlab-cr-elastic-kernel-0.0.27
```

別窓でpodmanのイベントを監視
```
podman events
```

再起動
```
podman stop jlab-cr-rerun-kernel; podman start jlab-cr-rerun-kernel

podman stop jlab-cr-elastic-kernel-0.0.21; podman start jlab-cr-elastic-kernel-0.0.21

podman stop jlab-cr-elastic-kernel-0.0.27; podman start jlab-cr-elastic-kernel-0.0.27
```

ログ表示
```
podman logs --tail 40 jlab-cr-rerun-kernel

podman logs --tail 40 jlab-cr-elastic-kernel-0.0.21

podman logs --tail 40 jlab-cr-elastic-kernel-0.0.27
```
