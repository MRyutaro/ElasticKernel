# ElasticKernel

**Never lose your Jupyter variables to a kernel restart again.**

ElasticKernel is a custom IPython kernel that **automatically checkpoints your notebook's execution state and restores it after a restart or crash** — no manual `pickle.dump` required. Pick up exactly where you left off.

[![PyPI version](https://img.shields.io/pypi/v/elastic-kernel.svg)](https://pypi.org/project/elastic-kernel/)
[![Python versions](https://img.shields.io/pypi/pyversions/elastic-kernel.svg)](https://pypi.org/project/elastic-kernel/)
[![Downloads](https://static.pepy.tech/personalized-badge/elastic-kernel?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads)](https://pepy.tech/projects/elastic-kernel)
[![Downloads/month](https://static.pepy.tech/personalized-badge/elastic-kernel?period=monthly&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads%2Fmonth)](https://pepy.tech/projects/elastic-kernel)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

> 🇯🇵 日本語版は [README.ja.md](README.ja.md) を参照してください。

## Demo

The same workflow in both clips: define a variable `a = 1`, then **restart the kernel**. The difference is what happens next.

<table>
<tr>
<th align="center">Standard kernel (<code>ipykernel</code>)</th>
<th align="center">ElasticKernel</th>
</tr>
<tr>
<td width="50%"><video src="https://github.com/user-attachments/assets/9ba4d267-20e8-4b06-a3ea-869c19687f81" controls muted></video></td>
<td width="50%"><video src="https://github.com/user-attachments/assets/9f3c7acc-2ae9-4f98-873c-60f37f1a434e" controls muted></video></td>
</tr>
<tr>
<td align="center">❌ After the restart, <code>a</code> is <b>gone</b> — <code>%whos</code> reports <i>"Interactive namespace is empty."</i></td>
<td align="center">✅ After the restart, <code>a</code> is <b>automatically restored</b> — <code>%whos</code> still shows <code>a&nbsp;&nbsp;int&nbsp;&nbsp;1</code>.</td>
</tr>
</table>

> If the videos don't play inline, click them to view: [ipykernel](docs/assets/ipykernel.mp4) · [ElasticKernel](docs/assets/elastickernel.mp4).

## Why ElasticKernel?

Every Jupyter user has been there: a long computation finishes, then an accidental kernel
restart (or an out-of-memory crash) wipes **every variable in your session**. The usual
workaround is scattering `pickle.dump` / `joblib.dump` calls everywhere and remembering to
reload them by hand.

ElasticKernel removes that chore entirely:

- 🔄 **Automatic state recovery** — your variables survive kernel restarts and shutdowns, with zero changes to your code.
- 🧠 **Dependency-aware** — tracks how cells and variables depend on one another to restore a consistent state.
- ⚡ **Cost-optimized checkpoints** — for each variable it decides whether to *serialize* it or *recompute* it on restore, based on serialization size vs. recomputation cost (a min-cut optimization).
- 🪄 **Drop-in** — just pick the `Python 3 (ElasticKernel)` kernel; the rest of your workflow is unchanged.

## Installation & Usage

### Local

1. Install the package:
   ```sh
   $ pip install elastic-kernel
   ```

2. Install the kernel:
   ```sh
   $ elastic-kernel install
   Elastic Kernel installed from: /path/to/elastic_kernel
   ```

3. Verify the kernel is installed:
   ```sh
   $ jupyter kernelspec list
   Available kernels:
     elastic_kernel    /path/to/Jupyter/kernels/elastic_kernel
   ```

4. Launch JupyterLab:
   ```sh
   $ jupyter lab --ip=0.0.0.0
   ```

5. Open JupyterLab in your browser.

6. Select the **Python 3 (ElasticKernel)** kernel.

### Docker

1. Pull the image:
   ```sh
   docker pull ghcr.io/mryutaro/elastickernel
   ```

2. Start a container:
   ```sh
   docker run -p 8888:8888 ghcr.io/mryutaro/elastickernel
   ```

3. Open JupyterLab in your browser.

4. Select the **Python 3 (ElasticKernel)** kernel.

## Supported versions

ElasticKernel is tested on every push and pull request against a CI matrix of Python
versions. The checkpoint **save → restore round trip** (`record_event → checkpoint →
load_checkpoint`) is verified on each of them.

| Component | Verified versions |
| --- | --- |
| Python | 3.9, 3.10, 3.11, 3.12, 3.13 |
| ipykernel / jupyterlab | latest release compatible with each Python above (resolved by `uv sync`) |

> Python 3.8 reached end-of-life in October 2024 and is no longer tested. The version
> matrix lives in [`.github/workflows/test.yml`](.github/workflows/test.yml).

## Supported libraries

ElasticKernel can restore a checkpointed object two ways, and a cost optimizer (min-cut)
picks one **per object** at checkpoint time — neither is merely a fallback:

- **Migrate** — serialize the object with dill and reload it.
- **Recompute** — re-run the cell that produced it.

CI verifies **several representative object types per library** below — a library exposes
many types, so this is a sample rather than a whole-library guarantee — and reports
whether each restore path reproduces each one.

Legend:

- ✅ — restored correctly via this path.
- ➖ — not serializable, so the Migrate path does not apply (ElasticKernel uses Recompute instead).
- ❌ — failed: the object could not be restored, or it is a known limitation.

The table is generated by [`scripts/library_coverage.py`](scripts/library_coverage.py) and
kept in sync by the [`library-coverage`](.github/workflows/library-coverage.yml) workflow.

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

## How It Works

ElasticKernel extends the IPython kernel to observe each cell execution. As you run cells it
builds a **dependency graph** of variables and the cell executions that produce them. When the
kernel shuts down or restarts, it profiles serialization speed, runs a cost optimizer to split
variables into a *migrate* set (serialized to disk) and a *recompute* set (regenerated by
re-running cells), and writes a checkpoint. On the next start it loads the checkpoint, injects
the migrated variables back into your namespace, and recomputes the rest.

## Documentation

- **Developer guide:** [docs/DEVELOPERS.md](docs/DEVELOPERS.md)
- **日本語 README:** [README.ja.md](README.ja.md)

## Publication

This project was presented in the following paper. If you use ElasticKernel in your research,
please cite:

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
developed at the University of Illinois. ElasticNotebook is licensed under the Apache License 2.0.

> Zhaoheng Li, Pranav Gor, Rahul Prabhu, Hui Yu, Yuzhou Mao, Yongjoo Park.
> "ElasticNotebook: Enabling Live Migration for Computational Notebooks."
> Proceedings of the VLDB Endowment, Vol. 17, No. 2, pp. 119-133, 2023.

## License

Licensed under the [Apache License 2.0](LICENSE).
