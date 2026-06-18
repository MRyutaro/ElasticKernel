# 任意タイミングのチェックポイント / 復元 API

ElasticKernel は通常、**カーネルの停止時にチェックポイントを保存**し、**起動時に復元**する。
これに加えて、外部のオーケストレーションシステムから **任意のタイミングで保存 / 復元を発火**
できる API を提供する。

> **自動保存 / 自動復元の無効化**: 終了時の自動保存・起動時の自動復元は、環境変数で
> **それぞれ独立に**無効化できる（`ELASTIC_KERNEL_CHECKPOINT_ON_SHUTDOWN` /
> `ELASTIC_KERNEL_RESTORE_ON_STARTUP`）。さらに**終了時の自動保存**は起動後も control / REST
> で実行時に切り替えられる（復元は起動時の一度きりのイベントなので実行時切り替えの対象外）。
> たとえば ElasticHub の zero-reload マイグレーションでは、保存・復元とも明示 API のタイミング
> に寄せる。とくに復元は、**カーネルをあらかじめ起動して待機**させておき**任意のタイミングで
> 明示的に発火**することで、カーネルの再起動時間をクリティカルパスから外す（起動時の自動復元
> には頼らない）。無効化してもこのページの明示 API は引き続き機能する。詳細は
> [自動挙動の切り替え](#自動挙動の切り替え)を参照。

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

Jupyter Server のトークン認証を使うため、`Authorization: token <TOKEN>`
ヘッダを付ける（トークン認証なら XSRF ヘッダは不要）。

| メソッド・パス | 説明 |
| --- | --- |
| `POST /elastic_kernel/checkpoint` | 対象カーネルの現在の状態を保存する |
| `POST /elastic_kernel/restore` | 対象カーネルをチェックポイントから復元する（**破壊的**: `user_ns` を上書きする） |
| `POST /elastic_kernel/checkpoint_on_shutdown` | 走行中カーネルの**終了時の自動保存を実行時に切り替える**（[自動挙動の切り替え](#自動挙動の切り替え)を参照） |
| `GET /elastic_kernel/checkpoint_on_shutdown` | 走行中カーネルの**現在値を照会する**（read-only・何も変更しない）。`kernel_id` はクエリ引数で渡す |

### リクエストボディ（JSON）

`POST` はボディに JSON を渡す。`GET /checkpoint_on_shutdown` はボディを取らず、`kernel_id` を
クエリ引数（`?kernel_id=<id>`）で渡す。

| フィールド | 必須 | 説明 |
| --- | --- | --- |
| `kernel_id` | ○ | 対象カーネルの ID。`GET /api/kernels` や `GET /api/sessions` から取得する |
| `timeout` | – | カーネルからの応答を待つ秒数（デフォルト 120） |
| `enabled` | △ | （`POST /checkpoint_on_shutdown` のみ・bool・必須）終了時の自動保存を ON/OFF する |

`POST /checkpoint_on_shutdown` は `enabled`（bool）が必須（省略すると `400`、bool 以外も `400`）。
`GET /checkpoint_on_shutdown` は `enabled` を取らず現在値だけを返す。いずれの応答も
`{"ok": true, "checkpoint_on_shutdown": ..., "changed": ...}`（`changed` は実際に値を変えたか
の bool。`GET` や同値での更新でなく「書き込みを行ったか」を表すので、`GET` では常に `false`）。

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

# 4) 終了時の自動保存を実行時に OFF（移行対象に決めた瞬間にその pod だけ手動へ倒す）
curl -s -X POST \
  -H "Authorization: token $TOK" -H "Content-Type: application/json" \
  -d '{"kernel_id":"<ID>","enabled":false}' \
  "$BASE/elastic_kernel/checkpoint_on_shutdown"

# 5) 現在値を照会（read-only・何も変更しない）
curl -s -H "Authorization: token $TOK" \
  "$BASE/elastic_kernel/checkpoint_on_shutdown?kernel_id=<ID>"
```

> **注意（復元の破壊性）**: `restore` はカーネルの現在の名前空間を上書きし、必要なセルを
> 再計算する。どのタイミングで誰のカーネルに対して発火するかはオーケストレーター側の責務。

---

## 自動挙動の切り替え

ElasticKernel はデフォルトで、**起動時にチェックポイントを自動復元**し、**停止時に自動保存**する。
ほとんどのユーザーはこのままでよい。

一方、外部オーケストレーターが保存/復元のタイミングを制御するカーネルでは、自動挙動の片方
（または両方）が邪魔になる。**保存と復元は独立に**切り替えられる。

- **起動時の初期モードは環境変数で決める**（保存・復元の両方）。
- **終了時の自動保存はさらに control メッセージ / REST で実行時に上書きできる**。一方、起動時の
  自動復元は**起動時の一度きりのイベント**なので、起動後に切り替えても効果がない。そのため
  実行時の上書き対象は保存側のみ（復元は env と起動時ログでのみ制御/確認する）。

### 1. 起動時の初期モード（環境変数）

| 環境変数 | 既定 | 効果 |
| --- | --- | --- |
| `ELASTIC_KERNEL_CHECKPOINT_ON_SHUTDOWN` | 有効 | `0` / `false` / `no` / `off`（大文字小文字・前後空白は無視）で、**停止時（`do_shutdown`）の自動保存**を無効化する。 |
| `ELASTIC_KERNEL_RESTORE_ON_STARTUP` | 有効 | 同上の値で、**起動時（`__init__`）の自動復元**を無効化する。 |

未設定または上記以外の値なら、それぞれ従来どおり有効。無効化しても、このページで説明している
**明示的な保存/復元（control メッセージ・REST API）は引き続き機能する**。

両フラグは**カーネルの `__init__`（＝起動時）に一度だけ評価**され、`self.checkpoint_on_shutdown`
/ `self.restore_on_startup` の初期値になる。停止時の `do_shutdown` は前者を参照する。

### 2. 実行時の上書き（control メッセージ / REST）— 終了時の自動保存のみ

起動後に判断を変えたい場合は、走行中のカーネルへ control メッセージ
`elastic_set_checkpoint_on_shutdown`（REST なら `POST /elastic_kernel/checkpoint_on_shutdown`）
を送って `self.checkpoint_on_shutdown` を差し替えられる。`enabled`（bool）を送ると更新され、
応答は更新後の現在値を返す（`enabled` を省略すると現在値を返すだけの read-only 照会）。

フラグの読み書きだけで `user_ns` には触れないため、**セル実行中でも割り込んで切り替えられる**
（保存/復元と違ってメインループの空き待ちが不要）。

```python
# control チャネル直送（同一ホスト）
msg = client.session.msg("elastic_set_checkpoint_on_shutdown", {"enabled": False})
client.control_channel.send(msg)
print(client.get_control_msg(timeout=10)["content"])
# {"ok": True, "checkpoint_on_shutdown": False, "changed": True}
```

> **オーケストレーターでの使い方**: 全 pod を auto（既定）のまま起動しておき、**移行対象に
> 決めた瞬間にその pod だけ** `enabled=false` へ倒してから保存→旧 pod 削除、という流れに
> できる。env を起動時に固定する方式と違い、「移行する pod だけ手動」を後から選べるので、
> culling 等の通常停止で保存されなくなる副作用（下記）を移行対象以外には及ぼさずに済む。

### ElasticHub zero-reload マイグレーションでの使い分け

zero-reload 移行では、旧カーネルを**殺さずに**明示 API（`POST /elastic_kernel/checkpoint`）で
保存し、新 pod では**あらかじめカーネルを起動して待機**させておき、切り替えの瞬間に明示 API
（`POST /elastic_kernel/restore`）で状態を戻す。このとき:

- **停止時の自動保存は不要かつ有害** … 明示保存済みなのに旧 pod 削除時の `do_shutdown` が共有
  NFS の同じ checkpoint を二重に上書きし、teardown を遅らせる。→ 停止時の自動保存を切る
- **起動時の自動復元は使わない** … 復元を `__init__`（カーネル起動）と密結合させると、カーネルの
  再起動時間がそのままクリティカルパスに乗る。カーネルを先に起動しておき**任意のタイミングで
  明示復元**することで、再起動時間をクリティカルパスから外す。→ 起動時の自動復元を切る

つまり移行対象のカーネルは**自動保存・自動復元をともに切り、保存も復元も明示 API のタイミングに
寄せる**。起動時のフラグ（env）は両方を `0` にし、起動後に「移行対象に決めた瞬間」へ寄せたい場合は
終了時の自動保存だけ前項の control / REST で OFF にする（復元側は起動時に決まるので env で固定する）。

### 環境変数の渡し方

設定はカーネルプロセスの環境変数なので、**カーネルを起動するときの環境**に載せる。素の
`POST /api/kernels` の body では任意の env を受け取れない点に注意（別途プロビジョナ等が必要）。
実用的には次のいずれか:

- **singleuser pod / サーバープロセスの環境に設定する**（最も手軽・推奨）。KubeSpawner の
  `environment` などで pod に与えれば、その上で起動する全カーネルが継承する。ElasticHub のように
  「全 elastic カーネルで自動保存 OFF」にしたい場合はこれで一括設定できる。
- **カーネル起動 API に env を渡す**。`jupyter_client` の `KernelManager.start_kernel(env=...)`
  や、`elastic_id_shim` の `km.start_kernel(..., env=...)` 経路に environ を載せる。

```python
import os

env = dict(os.environ, ELASTIC_KERNEL_CHECKPOINT_ON_SHUTDOWN="0")
# kernel_manager.start_kernel(env=env) など、起動 API に env として渡す
```

どのモードで起動したかはカーネルのログ（`.elastic_kernel/<hash>/ElasticKernel.log`）の
`Auto checkpoint: on_shutdown=on|off, on_startup=on|off` で確認できる。

> **注意（自動保存 OFF の副作用）**: 自動保存を切ると、マイグレーション以外の通常停止
> （culling・ログアウト等）でも保存されなくなる。その場合は停止前にオーケストレーターが
> 明示保存するか、対象を限定して環境変数を与えること。

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
# 終了時の自動保存の切り替えなら elastic_set_checkpoint_on_shutdown（content に enabled を載せる）
client.control_channel.send(msg)
print(client.get_control_msg(timeout=120)["content"])       # {"ok": True, ...}

client.stop_channels()
```

別ホストから操作する場合はカーネルの ZMQ ポートがネットワークに露出していないため、この方法は
使えない。HTTP（Jupyter Server のポート）経由の REST API を使うこと。
