# ElasticKernel

ElasticKernel: An IPython Kernel that automatically saves and restores Jupyter Notebook execution states.

[![PyPI Downloads](https://static.pepy.tech/personalized-badge/elastic-kernel?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads)](https://pepy.tech/projects/elastic-kernel)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/elastic-kernel?period=monthly&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads%2Fmonth)](https://pepy.tech/projects/elastic-kernel)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/elastic-kernel?period=weekly&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads%2Fweek)](https://pepy.tech/projects/elastic-kernel)

## 使用方法

### ローカルでの使用方法

1. ライブラリをインストールする
```sh
$ pip install elastic-kernel
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

```
$ jupyter lab --ip=0.0.0.0
```

5. ブラウザからJupyterLabにアクセスする

6. Python 3 (Elastic)のカーネルを選択する

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

## 開発者向け資料

[ここ](/docs/developers.md)を参考にしてください．

## 発表論文 (Publication)

本プロジェクトは、以下の論文で発表されました。研究や成果物で利用する場合は、こちらを引用してください。

> R. Matsumoto, K. Taniguchi, T. Hayami, K. Takahashi, and S. Date.
> "ElasticHub: A Cost-Efficient JupyterHub Platform via Automated Scaling with Kubernetes on Hybrid Cloud."
> Proceedings of the 16th International Conference on Cloud Computing and Services Science, pp. 261–268, 2026.
> DOI: [10.5220/0014840200004039](https://doi.org/10.5220/0014840200004039)

```bibtex
@inproceedings{matsumoto2026elastichub,
  author    = {Matsumoto, R. and Taniguchi, K. and Hayami, T. and Takahashi, K. and Date, S.},
  title     = {ElasticHub: A Cost-Efficient JupyterHub Platform via Automated Scaling with Kubernetes on Hybrid Cloud},
  booktitle = {Proceedings of the 16th International Conference on Cloud Computing and Services Science},
  year      = {2026},
  pages     = {261--268},
  isbn      = {978-989-758-829-7},
  issn      = {2184-5042},
  doi       = {10.5220/0014840200004039}
}
```

## Acknowledgments

This project includes code from [ElasticNotebook](https://github.com/illinoisdata/ElasticNotebook),
developed at the University of Illinois.
ElasticNotebook is licensed under the Apache License 2.0.

> Zhaoheng Li, Pranav Gor, Rahul Prabhu, Hui Yu, Yuzhou Mao, Yongjoo Park.
> "ElasticNotebook: Enabling Live Migration for Computational Notebooks."
> Proceedings of the VLDB Endowment, Vol. 17, No. 2, pp. 119-133, 2023.
