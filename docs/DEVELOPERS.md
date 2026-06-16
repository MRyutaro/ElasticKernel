# ElasticKernel for Developers

## 環境変数
| 環境変数 | 説明 |
| --- | --- |
| `ELASTIC_KERNEL_LOG_LEVEL=DEBUG` | デバックモード．詳細なログが表示される． |

```
ELASTIC_KERNEL_LOG_LEVEL=DEBUG jupyter lab
```

## PyPi へのアップロード方法

### 自動でアップロードする方法（release-please）

バージョン管理・公開は **release-please** で自動化されている。手動でバージョンを上げる必要はない。

1. main にマージされたコミット（PR）の **Conventional Commits**（`fix:` → patch、`feat:` → minor、`BREAKING CHANGE:` → major）から release-please が次バージョンを判定し、リリース PR を自動作成・更新する。
2. そのリリース PR をマージすると `v{version}` タグと GitHub Release が作られ、`publish-to-pypi.yml`（PyPI）と `docker-publish.yml`（GHCR）が発火して公開される。

詳細は `CLAUDE.md` の「バージョン管理・リリース」セクションを参照。

### 手動でアップロードする方法

```sh
$ uv pip install twine build
$ python -m build
$ python -m twine upload dist/*
```