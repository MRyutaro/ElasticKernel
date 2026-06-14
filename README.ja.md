# ElasticKernel

**カーネルの再起動で Jupyter の変数を失うのは、もう終わりにしましょう。**

ElasticKernel は、ノートブックの実行状態を**自動でチェックポイントし、再起動やクラッシュの後でも復元する**カスタム IPython カーネルです。手動の `pickle.dump` は不要。作業を中断したところからそのまま再開できます。

[![PyPI version](https://img.shields.io/pypi/v/elastic-kernel.svg)](https://pypi.org/project/elastic-kernel/)
[![Downloads](https://static.pepy.tech/personalized-badge/elastic-kernel?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads)](https://pepy.tech/projects/elastic-kernel)
[![Downloads/month](https://static.pepy.tech/personalized-badge/elastic-kernel?period=monthly&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads%2Fmonth)](https://pepy.tech/projects/elastic-kernel)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

> 🇬🇧 The English README is available at [README.md](README.md).

## デモ

どちらの動画も同じ操作です。変数 `a = 1` を定義し、**カーネルを再起動**します。違いはその後に表れます。

<table>
<tr>
<th align="center">標準カーネル（<code>ipykernel</code>）</th>
<th align="center">ElasticKernel</th>
</tr>
<tr>
<td width="50%"><video src="https://github.com/user-attachments/assets/85d7a19c-4a39-4bde-9e56-be67794d67bc" controls muted></video></td>
<td width="50%"><video src="https://github.com/user-attachments/assets/0436488e-9115-4397-a272-967dcc5f527c" controls muted></video></td>
</tr>
<tr>
<td align="center">❌ 再起動後、<code>a</code> は<b>消えています</b>。<code>%whos</code> は <i>「Interactive namespace is empty.」</i> と表示します。</td>
<td align="center">✅ 再起動後も <code>a</code> は<b>自動で復元</b>されます。<code>%whos</code> には引き続き <code>a&nbsp;&nbsp;int&nbsp;&nbsp;1</code> が表示されます。</td>
</tr>
</table>

> 動画がインラインで再生されない場合はクリックしてください: [ipykernel](docs/assets/ipykernel.mp4) · [ElasticKernel](docs/assets/elastickernel.mp4)

## なぜ ElasticKernel なのか

Jupyter ユーザーなら誰もが経験があるはずです。長時間の計算が終わった直後、うっかりカーネルを再起動してしまった（あるいは OOM でクラッシュした）――そして**セッション内の変数がすべて消える**。よくある回避策は、あちこちに `pickle.dump` / `joblib.dump` を書き、手動でロードし直すことです。

ElasticKernel はこの手間をまるごと無くします。

- 🔄 **自動状態復元** — コードを一切変えずに、カーネルの再起動・終了をまたいで変数が保持されます。
- 🧠 **依存関係を理解** — セルと変数の依存関係を追跡し、整合性のある状態を復元します。
- ⚡ **コスト最適化されたチェックポイント** — 各変数について「シリアライズして保存する」か「復元時に再計算する」かを、シリアライズサイズと再計算コストの比較（min-cut 最適化）で決定します。
- 🪄 **ドロップイン** — `Python 3 (ElasticKernel)` カーネルを選ぶだけ。あとのワークフローは今までどおりです。

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
     elastic_kernel    /path/to/Jupyter/kernels/elastic_kernel
   ```

4. JupyterLab を起動する
   ```sh
   $ jupyter lab --ip=0.0.0.0
   ```

5. ブラウザから JupyterLab にアクセスする

6. **Python 3 (ElasticKernel)** のカーネルを選択する

### Docker を用いた方法

1. イメージをプルする
   ```sh
   docker pull ghcr.io/mryutaro/elastickernel
   ```

2. コンテナを起動する
   ```sh
   docker run -p 8888:8888 ghcr.io/mryutaro/elastickernel
   ```

3. ブラウザから JupyterLab にアクセスする

4. **Python 3 (ElasticKernel)** のカーネルを選択する

## 仕組み

ElasticKernel は IPython カーネルを拡張し、各セルの実行を監視します。セルを実行するたびに、変数と「それを生成したセル実行」の**依存関係グラフ**を構築します。カーネルの終了・再起動時には、シリアライズ速度をプロファイルし、コストオプティマイザを実行して変数を *migrate* セット（ディスクへシリアライズ）と *recompute* セット（セル再実行で再生成）に分割し、チェックポイントを書き込みます。次回起動時にはチェックポイントを読み込み、migrate した変数を名前空間に注入し、残りを再計算します。

## ドキュメント

- **開発者向け資料:** [docs/DEVELOPERS.md](docs/DEVELOPERS.md)
- **English README:** [README.md](README.md)

## 発表論文

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

本プロジェクトは、イリノイ大学で開発された [ElasticNotebook](https://github.com/illinoisdata/ElasticNotebook) のコードを含みます。ElasticNotebook は Apache License 2.0 でライセンスされています。

> Zhaoheng Li, Pranav Gor, Rahul Prabhu, Hui Yu, Yuzhou Mao, Yongjoo Park.
> "ElasticNotebook: Enabling Live Migration for Computational Notebooks."
> Proceedings of the VLDB Endowment, Vol. 17, No. 2, pp. 119-133, 2023.

## ライセンス

[Apache License 2.0](LICENSE) のもとで公開されています。
