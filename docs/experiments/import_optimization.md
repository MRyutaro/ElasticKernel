# 概要
ElasticNotebookのインポート時間の削減を行った．
それについて評価を行う．

# 評価環境
- Python: 3.12.3
- OS: Linux 6.8.0-88-generic (Ubuntu)
- CPU: Intel Xeon Silver 4214R @ 2.40GHz (8 cores)
- Memory: 16GB
- Storage: HDD (/dev/vda, 126GB)
  - Read speed (measured): 74.4 MB/s
    - 測定方法: `sudo dd if=/dev/vda2 of=/dev/null bs=1M count=100 iflag=direct`
    - 結果: 100 MBを1.41秒で読み込み

# 評価手法

## インポート時間の測定
```
time python -c "from elastic_notebook import ElasticNotebook"
```

# 評価ログ1

## ElasticKernel 0.0.20

2.986
3.005
2.955
3.015
3.002
3.020
2.973
2.954
2.997
3.032

```
(tmp) matsumoto@neko:~/tmp$ uv pip show elastic-kernel
Name: elastic-kernel
Version: 0.0.20
Location: /home/matsumoto/tmp/.venv/lib/python3.12/site-packages
Requires: dill, ipykernel, ipython, jupyter, jupyter-client, lightgbm, matplotlib, networkx, numpy, pandas, scipy, seaborn, torch, xxhash
Required-by:

(tmp) matsumoto@neko:~/tmp$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m2.986s
user    0m3.388s
sys     0m0.318s
(tmp) matsumoto@neko:~/tmp$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m3.005s
user    0m3.464s
sys     0m0.306s
(tmp) matsumoto@neko:~/tmp$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m2.955s
user    0m3.400s
sys     0m0.314s
(tmp) matsumoto@neko:~/tmp$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m3.015s
user    0m3.461s
sys     0m0.327s
(tmp) matsumoto@neko:~/tmp$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m3.002s
user    0m3.442s
sys     0m0.325s
(tmp) matsumoto@neko:~/tmp$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m3.020s
user    0m3.391s
sys     0m0.311s
(tmp) matsumoto@neko:~/tmp$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m2.973s
user    0m3.430s
sys     0m0.314s
(tmp) matsumoto@neko:~/tmp$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m2.954s
user    0m3.421s
sys     0m0.309s
(tmp) matsumoto@neko:~/tmp$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m2.997s
user    0m3.449s
sys     0m0.325s
(tmp) matsumoto@neko:~/tmp$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m3.032s
user    0m3.502s
sys     0m0.306s
```

## ElasticKernel 0.0.27
平均: 0.6855
標準偏差: 0.019189841

0.731
0.668
0.703
0.679
0.686
0.693
0.662
0.668
0.679
0.686

```
(elastic-kernel) matsumoto@neko:~/ElasticKernel$ python -c "from elastic_notebook import __version__; print(__version__)"
0.0.27

(elastic-kernel) matsumoto@neko:~/ElasticKernel$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m0.731s
user    0m1.426s
sys     0m0.077s
(elastic-kernel) matsumoto@neko:~/ElasticKernel$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m0.668s
user    0m1.367s
sys     0m0.071s
(elastic-kernel) matsumoto@neko:~/ElasticKernel$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m0.703s
user    0m1.339s
sys     0m0.077s
(elastic-kernel) matsumoto@neko:~/ElasticKernel$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m0.679s
user    0m1.377s
sys     0m0.075s
(elastic-kernel) matsumoto@neko:~/ElasticKernel$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m0.686s
user    0m1.371s
sys     0m0.074s
(elastic-kernel) matsumoto@neko:~/ElasticKernel$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m0.693s
user    0m1.381s
sys     0m0.078s
(elastic-kernel) matsumoto@neko:~/ElasticKernel$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m0.662s
user    0m1.372s
sys     0m0.069s
(elastic-kernel) matsumoto@neko:~/ElasticKernel$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m0.668s
user    0m1.358s
sys     0m0.079s
(elastic-kernel) matsumoto@neko:~/ElasticKernel$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m0.679s
user    0m1.380s
sys     0m0.071s
(elastic-kernel) matsumoto@neko:~/ElasticKernel$ time python -c "from elastic_notebook import ElasticNotebook"

real    0m0.686s
user    0m1.381s
sys     0m0.071s
```


# 評価ログ2

コンテナ再起動だと6sくらいの差だけどこっちの評価だと2.5sくらいの差になっている．  
なぜこの差が生まれるのか？  
コンテナ再起動の方は，一回一回コンテナを削除している．  
そのためキャッシュがない．  
.pycファイルがない場合バイトコードのコンパイルを行う必要がある．  


## ElasticKernel 0.0.21

8.712
9.101
8.348
9.102
8.760
8.805±0.314[s]
変動係数 (CV): 3.57%

```
matsumoto@neko:~/ElasticKernel$ podman exec -it eca176555331 bash
root@eca176555331:/app# time python -c "from elastic_notebook import ElasticNotebook"

real    0m8.712s
user    0m7.436s
sys     0m0.483s
matsumoto@neko:~/ElasticKernel$ podman exec -it b48bd8707825 bash
root@b48bd8707825:/app# time python -c "from elastic_notebook import ElasticNotebook"

real    0m9.101s
user    0m7.447s
sys     0m0.438s
matsumoto@neko:~/ElasticKernel$ podman exec -it 5b870ed9754f bash
root@5b870ed9754f:/app# time python -c "from elastic_notebook import ElasticNotebook"

real    0m8.348s
user    0m7.324s
sys     0m0.509s
matsumoto@neko:~/ElasticKernel$ podman exec -it a77fe3a7bac7 bash
root@a77fe3a7bac7:/app# time python -c "from elastic_notebook import ElasticNotebook"

real    0m9.102s
user    0m7.370s
sys     0m0.479s
matsumoto@neko:~/ElasticKernel$ podman exec -it f8061aa19720 bash
root@f8061aa19720:/app# time python -c "from elastic_notebook import ElasticNotebook"

real    0m8.760s
user    0m7.345s
sys     0m0.451s
```

## ElasticKernel 0.0.27

1.759
1.690
1.613
1.774
1.786
1.724±0.073[s]
変動係数 (CV): 4.21%

```
(elastic-kernel) matsumoto@neko:~/ElasticKernel$ podman exec -it d0e39785e396 bash
root@d0e39785e396:/app# time python -c "from elastic_notebook import ElasticNotebook"

real    0m1.759s
user    0m2.153s
sys     0m0.136s
(elastic-kernel) matsumoto@neko:~/ElasticKernel$ podman exec -it e71dc9bd3f10 bash
root@e71dc9bd3f10:/app# time python -c "from elastic_notebook import ElasticNotebook"

real    0m1.690s
user    0m2.024s
sys     0m0.123s
(elastic-kernel) matsumoto@neko:~/ElasticKernel$ podman exec -it a1e6583fc084 bash
root@a1e6583fc084:/app# time python -c "from elastic_notebook import ElasticNotebook"

real    0m1.613s
user    0m2.069s
sys     0m0.134s
(elastic-kernel) matsumoto@neko:~/ElasticKernel$ podman exec -it abc37b010735 bash
root@abc37b010735:/app# time python -c "from elastic_notebook import ElasticNotebook"

real    0m1.774s
user    0m2.076s
sys     0m0.143s
(elastic-kernel) matsumoto@neko:~/ElasticKernel$ podman exec -it 03b78ab3a66f bash
root@03b78ab3a66f:/app# time python -c "from elastic_notebook import ElasticNotebook"

real    0m1.786s
user    0m2.124s
sys     0m0.133s
```
