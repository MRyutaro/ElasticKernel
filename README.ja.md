# ElasticKernel

**カーネルの再起動で Jupyter の変数を失うのは、もう終わりにしましょう。**

ElasticKernel は、ノートブックの実行状態を**自動でチェックポイントし、再起動やクラッシュの後でも復元する**カスタム IPython カーネルです。手動の `pickle.dump` は不要。作業を中断したところからそのまま再開できます。

[![PyPI version](https://img.shields.io/pypi/v/elastic-kernel.svg)](https://pypi.org/project/elastic-kernel/)
[![Python versions](https://img.shields.io/pypi/pyversions/elastic-kernel.svg)](https://pypi.org/project/elastic-kernel/)
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
<td width="50%"><video src="https://github.com/user-attachments/assets/9ba4d267-20e8-4b06-a3ea-869c19687f81" controls muted></video></td>
<td width="50%"><video src="https://github.com/user-attachments/assets/9f3c7acc-2ae9-4f98-873c-60f37f1a434e" controls muted></video></td>
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

## 対応バージョン

ElasticKernel は push / pull request のたびに、複数の Python バージョンからなる CI マトリクスで
テストされます。チェックポイントの**保存 → 復元の往復**（`record_event → checkpoint →
load_checkpoint`）が各バージョンで通ることを検証しています。

| コンポーネント | 検証済みバージョン |
| --- | --- |
| Python | 3.9, 3.10, 3.11, 3.12, 3.13 |
| ipykernel / jupyterlab | 上記各 Python と互換な最新リリース（`uv sync` が解決） |

> Python 3.8 は 2024 年 10 月に EOL を迎えたため、テスト対象から外しています。バージョン
> マトリクスは [`.github/workflows/test.yml`](.github/workflows/test.yml) にあります。

## 対応ライブラリ

ElasticKernel はチェックポイントしたオブジェクトを 2 通りの方法で復元でき、どちらを使うかは
チェックポイント時にコスト最適化（min-cut）が**オブジェクトごとに**決めます。どちらか一方が
単なるフォールバックというわけではありません。

- **Migrate（移行）** — dill でシリアライズして再ロードする。
- **Recompute（再計算）** — そのオブジェクトを生成したセルを再実行する。

CI は以下の**各ライブラリについて複数の代表的なオブジェクト型**を検証し（ライブラリには
多様なオブジェクト型があるため、サンプル検証であってライブラリ全体の保証ではありません）、
各復元パスでそれぞれのオブジェクトが再現できるかを示します。

凡例:

- ✅ — このパスで正しく復元できた。
- ➖ — シリアライズ不可のため Migrate は対象外（ElasticKernel は Recompute を使用）。
- ❌ — 失敗（復元できない、または既知の限界）。

この表は [`scripts/library_coverage.py`](scripts/library_coverage.py) が生成し、
[`library-coverage`](.github/workflows/library-coverage.yml) ワークフローが同期します。

<!-- BEGIN LIBRARY COVERAGE -->
| Library | Object | Migrate | Recompute | Verified version |
| --- | --- | :---: | :---: | --- |
| numpy | `ndarray` | ✅ | ✅ | 2.3.4 |
|  | `structured array` | ✅ | ✅ | 2.3.4 |
|  | `masked array` | ✅ | ✅ | 2.3.4 |
|  | `datetime64 array` | ✅ | ✅ | 2.3.4 |
| pandas | `DataFrame` | ✅ | ✅ | 3.0.3 |
|  | `Series` | ✅ | ✅ | 3.0.3 |
|  | `Series (category)` | ✅ | ✅ | 3.0.3 |
|  | `DataFrame (DatetimeIndex)` | ✅ | ✅ | 3.0.3 |
| scipy | `csr_matrix (sparse)` | ✅ | ✅ | 1.17.1 |
|  | `csc_matrix (sparse)` | ✅ | ✅ | 1.17.1 |
|  | `stats frozen distribution` | ✅ | ✅ | 1.17.1 |
| scikit-learn | `LinearRegression (fitted)` | ✅ | ✅ | 1.9.0 |
|  | `StandardScaler (fitted)` | ✅ | ✅ | 1.9.0 |
|  | `RandomForestClassifier (fitted)` | ✅ | ✅ | 1.9.0 |
| matplotlib | `Figure (line plot)` | ✅ | ✅ | 3.11.0 |
|  | `Figure (imshow)` | ✅ | ✅ | 3.11.0 |
| seaborn | `FacetGrid` | ✅ | ✅ | 0.13.2 |
|  | `Axes (scatterplot)` | ✅ | ✅ | 0.13.2 |
| opencv (cv2) | `ndarray (grayscale image)` | ✅ | ✅ | 4.13.0.92 |
|  | `ndarray (color image)` | ✅ | ✅ | 4.13.0.92 |
| requests | `Response` | ✅ | ✅ | 2.32.5 |
|  | `Session` | ✅ | ✅ | 2.32.5 |
<!-- END LIBRARY COVERAGE -->

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
