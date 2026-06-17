# 任意タイミングのチェックポイント / 復元 API

ElasticKernel は通常、**カーネルの停止時にチェックポイントを保存**し、**起動時に復元**する。
これに加えて、外部のオーケストレーションシステムから **任意のタイミングで保存 / 復元を発火**
できる API を提供する。

> **自動 checkpoint/restore の無効化**: 外部オーケストレーターがマイグレーションを完全に
> 制御したいカーネル（ElasticHub のクラウドバースティングでクラウド→オンプレへ移すケース等）
> では、起動時の自動復元・終了時の自動保存が転送やハンドシェイクの順序制御を壊すことがある。
> その場合はカーネル起動時に環境変数 `ELASTIC_KERNEL_AUTO_CHECKPOINT=0` を設定すると、
> 自動の保存・復元を両方とも無効化できる（このページの明示 API は引き続き機能する）。
> 詳細は[自動挙動の切り替え](#自動挙動の切り替え)を参照。

- 発火は外部からの明示指示のみ（タイマーや自動発火ではない）。
- ノートブックのエンドユーザーには**透過**（マジックコマンド不要・`user_ns` や `%who` を汚さない）。
- 保存処理はカーネルのメインループに乗せて実行されるため、走行中のセルと競合せず一貫した
  スナップショットになる。

仕組みは2層に分かれる:

```
外部オーケストレーター
   │  HTTP POST /elastic_kernel/checkpoint  {kernel_id}
   ▼
Jupyter Server 拡張（カーネルと同一ホストで同居）
   │  control チャネルに custom message
   ▼
カーネル本体  →  チェックポイント保存 / 復元
   ▼
   結果(JSON)を HTTP レスポンスとして返す
```

---

## 有効化

REST API はオプトイン。デフォルトでは無効。

```sh
# 依存込みでインストール（jupyter_server を含む）
pip install "elastic-kernel[server]"

# カーネル登録に加えて REST API（Jupyter Server 拡張）を有効化
elastic-kernel install --server
```

`elastic-kernel install`（`--server` なし）の場合はカーネルのみ登録され、REST API は無効のまま。

有効化の確認:

```sh
jupyter server extension list
# elastic_kernel.serverextension  enabled  OK
```

無効化:

```sh
jupyter server extension disable elastic_kernel.serverextension
```

---

## エンドポイント

いずれも `POST`。Jupyter Server のトークン認証を使うため、`Authorization: token <TOKEN>`
ヘッダを付ける（トークン認証なら XSRF ヘッダは不要）。

| メソッド・パス | 説明 |
| --- | --- |
| `POST /elastic_kernel/checkpoint` | 対象カーネルの現在の状態を保存する |
| `POST /elastic_kernel/restore` | 対象カーネルをチェックポイントから復元する（**破壊的**: `user_ns` を上書きする） |

### リクエストボディ（JSON）

| フィールド | 必須 | 説明 |
| --- | --- | --- |
| `kernel_id` | ○ | 対象カーネルの ID。`GET /api/kernels` や `GET /api/sessions` から取得する |
| `timeout` | – | カーネルからの応答を待つ秒数（デフォルト 120） |

### レスポンス

| ステータス | 意味 |
| --- | --- |
| `200` | 成功。ボディは `{"ok": true, "elapsed_seconds": ..., "path": ..., ...}` |
| `409` | カーネルは生きているが実行できない（`plain_kernel_mode` / `no_checkpoint_file` / `exception`）。ボディの `reason` を参照 |
| `400` | `kernel_id` 欠落、または `timeout` が不正 |
| `403` | 認証トークンが無い／不正 |
| `404` | `kernel_id` に対応するカーネルが存在しない |
| `504` | カーネルが時間内に応答しなかった（例: 長時間ブロックするセルが実行中） |

保存成功時のボディ例:

```json
{
  "ok": true,
  "elapsed_seconds": 0.052,
  "path": "/work/.elastic_kernel/<hash>/checkpoint.pickle",
  "vss_to_migrate": 3,
  "vss_to_recompute": 0
}
```

---

## 使用例

```sh
TOK="<jupyter token>"
BASE="http://127.0.0.1:8888"

# 1) kernel_id を調べる（ノートブックとカーネルの対応は /api/sessions が分かりやすい）
curl -s -H "Authorization: token $TOK" "$BASE/api/sessions"

# 2) 保存
curl -s -X POST \
  -H "Authorization: token $TOK" -H "Content-Type: application/json" \
  -d '{"kernel_id":"<ID>"}' \
  "$BASE/elastic_kernel/checkpoint"

# 3) 復元
curl -s -X POST \
  -H "Authorization: token $TOK" -H "Content-Type: application/json" \
  -d '{"kernel_id":"<ID>"}' \
  "$BASE/elastic_kernel/restore"
```

> **注意（復元の破壊性）**: `restore` はカーネルの現在の名前空間を上書きし、必要なセルを
> 再計算する。どのタイミングで誰のカーネルに対して発火するかはオーケストレーター側の責務。

---

## 自動挙動の切り替え

ElasticKernel はデフォルトで、**起動時にチェックポイントを自動復元**し、**停止時に自動保存**する。
ほとんどのユーザーはこのままでよい。

一方、外部オーケストレーターがマイグレーションを制御するカーネル（例: ElasticHub の
クラウドバースティングでコスト削減のためクラウド→オンプレへ状態を移すケース）では、
自動挙動が次のように邪魔になる:

- クラウド側カーネルの停止時に自動保存が走ると、明示保存したチェックポイントを上書きしたり、
  「保存完了の確認 → ファイル転送 → 停止」という順序制御を壊す。
- オンプレ側カーネルの起動時に自動復元が走ると、まだチェックポイントが転送・配置される前に
  復元しようとしたり、オーケストレーターが意図したタイミングと食い違う。

このようなカーネルに対しては、**起動時に環境変数を設定して自動挙動を無効化**し、保存/復元の
タイミングを上記の明示 API（control メッセージ / REST）だけで制御する。

| 環境変数 | 既定 | 説明 |
| --- | --- | --- |
| `ELASTIC_KERNEL_AUTO_CHECKPOINT` | 有効 | `0` / `false` / `no` / `off`（大文字小文字・前後空白は無視）で、起動時の自動復元と停止時の自動保存を**両方**無効化する。未設定または上記以外の値なら従来どおり自動が有効。 |

無効化しても、このページで説明している**明示的な保存/復元（control メッセージ・REST API）は
引き続き機能する**。「自動は切るが、手動でいつでも保存/復元できる」状態になる。

設定はカーネル単位（プロセスの環境変数）なので、オーケストレーターがマイグレーション対象の
カーネルを起動するときにだけ付与すればよい。通常ユーザーのカーネルは環境変数を付けないため
自動挙動のまま影響を受けない。

```python
# 例: kernel_manager 経由でマイグレーション用カーネルを起動するとき
import os

env = dict(os.environ, ELASTIC_KERNEL_AUTO_CHECKPOINT="0")
# kernel_manager.start_kernel(env=env) など、起動 API に env として渡す
```

どちらのモードで起動したかはカーネルのログ（`.elastic_kernel/<hash>/ElasticKernel.log`）の
`Auto checkpoint/restore: enabled|disabled` で確認できる。

---

## サーバー拡張を使わない方法（control チャネル直送）

オーケストレーターがカーネルと**同一ホスト**にあり、カーネルの接続ファイルを読める場合は、
Jupyter Server 拡張を介さず `jupyter_client` で control チャネルへ直接メッセージを送ることも
できる（control チャネルのハンドラはサーバー拡張の有効・無効に関わらず常に登録されている）。

```python
from jupyter_client import BlockingKernelClient

client = BlockingKernelClient()
client.load_connection_file("<jupyter runtime dir>/kernel-<kernel_id>.json")
client.start_channels()

msg = client.session.msg("elastic_checkpoint_request", {})  # 復元は elastic_restore_request
client.control_channel.send(msg)
print(client.get_control_msg(timeout=120)["content"])       # {"ok": True, ...}

client.stop_channels()
```

別ホストから操作する場合はカーネルの ZMQ ポートがネットワークに露出していないため、この方法は
使えない。HTTP（Jupyter Server のポート）経由の REST API を使うこと。
