# リバースプロキシによるシームレスな移行設計

## 1. 問題の定義

### 1.1 現状の課題

ElasticKernelでは、checkpoint/restore時にユーザーがページをリロードしないと新たなJupyter Notebookに再接続できない問題があります。

**技術的な原因:**
- checkpoint/restore時にJupyterカーネルIDが変更される（例: `abc123` → `xyz789`）
- ブラウザは古いカーネルIDをキャッシュしており、新しいカーネルIDを自動取得しない
- ページをリロードすることで、サーバーから最新のカーネルリストを取得し、新しいIDで再接続できる

### 1.2 JupyterLab拡張機能では解決できない理由

当初、JupyterLab拡張機能による自動リロードも検討しましたが、以下の理由により実現不可能です：

- **コンテナごと再起動される**: run.shのrestart処理では、JupyterLabコンテナ全体がCRIUでcheckpoint/restoreされる
- **拡張機能も停止する**: コンテナが停止すると、JupyterLab拡張機能のプロセスも停止するため、restore完了を検知できない
- **ブラウザとの接続が切れる**: コンテナ再起動中、ブラウザからサーバーへの接続が完全に切断される

したがって、**ブラウザとコンテナの間に常駐するリバースプロキシ**が必要です。

---

## 2. 解決策の概要

### 2.1 基本アイデア

**Blue-Green Deployment的アプローチ**を採用します：

```
[ブラウザ] ← 常に同じURL (例: http://localhost:80)
    ↓
[リバースプロキシ] ← 接続先を動的に切り替え
    ↓
  8888 (旧コンテナ) → 8889 (新コンテナ)
    ↓
[JupyterLabコンテナ]
```

### 2.2 移行の流れ（概要）

1. **移行指示が出される** → 新コンテナ(8889)を起動し、JupyterLab起動まで完了
2. **旧コンテナ(8888)でcheckpoint保存** → ElasticKernelが変数を最適化して保存
3. **checkpoint完了** → 新コンテナ(8889)でJupyterカーネルを起動し、変数復元
4. **プロキシの向き先を切り替え** → 8888から8889へ
5. **旧コンテナを停止・削除**

### 2.3 ユーザー体験（目標）

- ユーザーはブラウザでJupyterLabを開いたまま
- checkpoint/restoreが裏で実行される
- プロキシが自動的に新コンテナに接続先を切り替える
- **ページリロード不要（理想）**
  - WebSocket接続は一時的に切断される
  - セッション情報を移行することで、JupyterLabが自動的に新カーネルに再接続
  - **ただし、JupyterLabの自動再接続挙動を検証する必要がある**（セクション8.5参照）
- 最悪の場合でも、ページリロード1回で新カーネルに接続可能（現状より改善）

---

## 3. アーキテクチャ設計

### 3.1 システム構成図

```
┌─────────────┐
│  ブラウザ   │
│             │
└──────┬──────┘
       │ HTTP/WebSocket
       │ localhost:80
       ↓
┌─────────────────────────────┐
│   リバースプロキシ          │
│                             │
│  - 接続先管理               │
│  - WebSocketサポート        │
│  - 動的切り替え             │
└──────┬──────────────┬───────┘
       │              │
   8888 (旧)      8889 (新)
       │              │
       ↓              ↓
┌─────────────┐ ┌─────────────┐
│コンテナ A   │ │コンテナ B   │
│             │ │             │
│ JupyterLab  │ │ JupyterLab  │
│ + Kernel    │ │ + Kernel    │
└─────────────┘ └─────────────┘
```

### 3.2 コンポーネントの責務

#### 3.2.1 リバースプロキシ

**責務:**
- ブラウザからのHTTP/WebSocketリクエストを現在アクティブなコンテナに転送
- 接続先ポート（8888または8889）を管理
- 切り替え指示を受けたら、転送先を変更
- 切り替え中の接続を適切にハンドリング

**必要な機能:**
- WebSocketアップグレードのサポート
- 動的なバックエンド切り替え
- ヘルスチェック（接続先が起動しているか確認）

#### 3.2.2 JupyterLabコンテナ（旧: 8888）

**責務:**
- ユーザーが作業中のJupyterLab環境を提供
- checkpoint指示を受けたら、ElasticKernelを通じて状態を保存
- checkpoint完了後、プロキシから切り離され、停止される

#### 3.2.3 JupyterLabコンテナ（新: 8889）

**責務:**
- 移行指示と同時に起動
- JupyterLabサーバーを起動して待機
- 旧コンテナのcheckpoint完了を待つ
- checkpoint.pickleから変数を復元してカーネルを起動
- プロキシから接続されたら、以降のリクエストを処理

#### 3.2.4 run.sh（オーケストレーター）

**責務:**
- 全体の移行フローを制御
- 新コンテナの起動
- 旧コンテナへのcheckpoint指示
- プロキシへの切り替え指示
- 旧コンテナの削除

---

## 4. 移行フロー（詳細）

### 4.1 初期状態

```
[ブラウザ] → [プロキシ] → [コンテナ A (8888)]
                         JupyterLab起動中
                         ユーザーが作業中
```

### 4.2 Step 1: 移行指示 → 新コンテナ起動

**トリガー:** `./run.sh restart` コマンド実行

**処理:**
1. run.shが新しいコンテナB (8889) を起動
2. コンテナB内でJupyterLabサーバーを起動
3. JupyterLabが`/api/kernels`エンドポイントに応答するまで待機

**状態:**
```
[ブラウザ] → [プロキシ] → [コンテナ A (8888)] ← 接続中
                          [コンテナ B (8889)] ← JupyterLab起動完了、待機中
```

### 4.3 Step 2: 旧コンテナでcheckpoint

**処理:**
1. run.shが旧コンテナA (8888) に対してcheckpoint指示
2. JupyterLabにREST API経由でカーネル停止リクエスト送信
   ```bash
   curl -X DELETE "http://localhost:8888/api/kernels/{kernel_id}"
   ```
3. ElasticKernelの`do_shutdown()`が呼ばれ、checkpoint処理実行
4. ElasticNotebookが変数を最適化してシリアライズ
5. checkpoint.pickleを共有ディレクトリに保存

**状態:**
```
[ブラウザ] → [プロキシ] → [コンテナ A (8888)] ← checkpoint実行中
                          [コンテナ B (8889)] ← 待機中

                          [checkpoint.pickle] ← 保存完了
```

### 4.4 Step 3: 新コンテナでrestore + セッション情報移行

**処理:**
1. run.shが旧コンテナA (8888) からセッション情報を取得
   ```bash
   OLD_SESSIONS=$(curl -s "http://localhost:8888/api/sessions")
   ```

2. run.shが新コンテナB (8889) に対してカーネル起動リクエスト送信
   ```bash
   NEW_KERNEL_ID=$(curl -X POST "http://localhost:8889/api/kernels" \
        -H "Content-Type: application/json" \
        -d '{"name":"elastic_kernel"}' | jq -r '.id')
   ```

3. ElasticKernelの`__init__()`が実行され、checkpoint.pickleをロード

4. ElasticNotebookが変数を復元し、必要なセルを再計算

5. カーネルが`idle`状態になるまで待機

6. 旧コンテナのセッション情報をもとに、新コンテナで**旧session_idを使って**セッションを作成
   ```bash
   # 各セッションについて繰り返し
   curl -X POST "http://localhost:8889/api/sessions" \
        -H "Content-Type: application/json" \
        -d '{
            "id": "'"$OLD_SESSION_ID"'",
            "path": "'"$NOTEBOOK_PATH"'",
            "type": "notebook",
            "kernel": {"id": "'"$NEW_KERNEL_ID"'", "name": "elastic_kernel"}
        }'
   ```
   **注意:** Jupyter Server APIが`id`パラメータをサポートしているか要検証（セクション8.5.1）

**状態:**
```
[ブラウザ] → [プロキシ] → [コンテナ A (8888)] ← checkpoint完了
                          [コンテナ B (8889)] ← カーネル起動、変数復元完了
                                                  セッション情報移行完了
```

### 4.5 Step 4: プロキシの向き先を切り替え

**処理:**
1. run.shがプロキシに切り替え指示を送信
   ```bash
   curl -X POST "http://localhost:80/admin/switch" \
        -H "Content-Type: application/json" \
        -d '{"target_port": 8889}'
   ```
2. プロキシが接続先を8888から8889に変更
3. 新しいリクエストは全てコンテナBに転送される
4. 既存のWebSocket接続は切断され、ブラウザが自動再接続

**状態:**
```
[ブラウザ] → [プロキシ] ─┐
                        ├→ [コンテナ A (8888)] ← 接続なし
                        └→ [コンテナ B (8889)] ← 接続中
```

### 4.6 Step 5: 旧コンテナ削除

**処理:**
1. run.shが旧コンテナA (8888) を停止
   ```bash
   sudo podman stop elastickernel-jupyter-8888
   ```
2. コンテナを削除
   ```bash
   sudo podman rm elastickernel-jupyter-8888
   ```
3. 次回のrestartでは、コンテナBが旧コンテナとなり、新たにコンテナC (8888) が起動される（ポート番号を交互に使用）

**最終状態:**
```
[ブラウザ] → [プロキシ] → [コンテナ B (8889)] ← 接続中
```

### 4.7 タイミング図

```
時刻 →

ブラウザ:    [作業中] ── [一瞬切断] ── [自動再接続] ── [作業継続]
                                ↑
                            プロキシ切り替え

プロキシ:    [8888に転送] ────────────→ [8889に転送]
                                     ↑

コンテナA:   [起動中] ── [checkpoint] ── [停止]
            (8888)

コンテナB:        [起動] ── [待機] ── [restore] ── [起動中]
                 (8889)           ↑
                              checkpoint完了後
```

---

## 5. プロキシ実装の比較

### 5.1 オプション1: カスタム実装（Python/FastAPI）

**概要:**
FastAPIやStarletteを使って、WebSocketプロキシを実装

**メリット:**
- 既存コードベースと同じPython
- 切り替えロジックを完全にコントロール可能
- run.shとの統合が容易
- デバッグ・拡張が容易

**デメリット:**
- ゼロから実装する必要がある
- 本番運用レベルの性能・安定性を確保するのに手間

**実装イメージ:**
```python
from fastapi import FastAPI, WebSocket
from starlette.responses import StreamingResponse
import httpx

app = FastAPI()
current_target = {"port": 8888}

@app.websocket("/api/kernels/{path:path}")
async def websocket_proxy(websocket: WebSocket, path: str):
    await websocket.accept()
    target = f"ws://localhost:{current_target['port']}/api/kernels/{path}"
    # WebSocketプロキシ処理

@app.post("/admin/switch")
async def switch_target(target_port: int):
    current_target["port"] = target_port
    return {"status": "switched", "target_port": target_port}
```

### 5.2 オプション2: Nginx

**概要:**
Nginxの動的なアップストリーム切り替え機能を使用

**メリット:**
- 本番運用で実績豊富、高性能
- WebSocketサポートが標準
- 設定ファイルベースでシンプル

**デメリット:**
- 動的な切り替えには、追加モジュール（Lua、ngx_http_dyups_module）が必要
- 設定が複雑になる可能性
- run.shとの統合にAPI経由の制御が必要

**実装イメージ:**
```nginx
upstream jupyter {
    server localhost:8888;  # 動的に8889に切り替える
}

server {
    listen 80;

    location / {
        proxy_pass http://jupyter;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### 5.3 オプション3: Traefik

**概要:**
Traefikのコンテナネイティブな動的設定機能を使用

**メリット:**
- コンテナラベルベースで自動設定
- WebSocketサポートが標準
- ダッシュボードで監視可能

**デメリット:**
- ElasticKernelの要件にはオーバースペック
- 動的切り替えの制御がやや複雑
- 追加の学習コストが必要

### 5.4 推奨技術

**推奨: カスタム実装（Python/FastAPI）**

**理由:**
1. **シンプルさ**: ElasticKernelの要件は「2つのポート間の切り替え」のみで、シンプル
2. **統合の容易さ**: run.shからHTTP APIで制御でき、既存のcurlベースの実装と統一感がある
3. **保守性**: Python開発者が中心なので、保守・拡張が容易
4. **柔軟性**: 将来的な機能追加（ログ、モニタリング、エラーハンドリング）が容易

**実装規模:**
- 約100-200行のPythonコード
- FastAPIとhttpxライブラリを使用
- WebSocketプロキシの実装例は豊富

---

## 6. run.shへの統合

### 6.1 現在の処理フロー

```bash
# 現在のrestart処理（簡略化）
./run.sh restart:
  1. checkpoint実行 → CRIUでコンテナを保存
  2. コンテナ停止
  3. restore実行 → CRIUでコンテナを復元
  4. 新しいカーネルを起動
```

### 6.2 新しい処理フロー

```bash
# 新しいrestart処理
./run.sh restart:
  1. プロキシが起動していることを確認（未起動なら起動）
  2. 現在のコンテナポート番号を取得（8888 or 8889）
  3. 新しいポート番号を決定（8888 ⇔ 8889を交互に）
  4. 新コンテナを起動（新ポート番号で）
  5. JupyterLabの起動を待機
  6. 旧コンテナにcheckpoint指示（カーネル停止 + 変数保存）
  7. 旧コンテナからセッション情報を取得
  8. 新コンテナでrestore（カーネル起動 + 変数復元）
  9. 新コンテナでセッション情報を再作成
  10. プロキシに切り替え指示（新ポート番号へ）
  11. 旧コンテナを停止・削除
```

### 6.3 実装例（擬似コード）

```bash
#!/bin/bash

PROXY_PORT=80
CONTAINER_NAME="elastickernel-jupyter"

restart() {
    # 1. プロキシ起動確認
    if ! curl -s "http://localhost:$PROXY_PORT/health" > /dev/null; then
        echo "Starting proxy..."
        python proxy.py &
        sleep 2
    fi

    # 2. 現在のポート番号を取得
    CURRENT_PORT=$(curl -s "http://localhost:$PROXY_PORT/admin/status" | jq -r '.target_port')

    # 3. 新しいポート番号を決定
    if [ "$CURRENT_PORT" = "8888" ]; then
        NEW_PORT=8889
    else
        NEW_PORT=8888
    fi

    echo "Migrating from $CURRENT_PORT to $NEW_PORT..."

    # 4. 新コンテナを起動
    sudo podman run -d \
        --name "$CONTAINER_NAME-$NEW_PORT" \
        -p "$NEW_PORT:8888" \
        -v "$WORKSPACE_DIR:/app" \
        localhost/elastickernel:latest

    # 5. JupyterLab起動待機
    wait_for_jupyter "localhost:$NEW_PORT"

    # 6. 旧コンテナでcheckpoint
    checkpoint_container "localhost:$CURRENT_PORT"

    # 7. 旧コンテナからセッション情報を取得
    OLD_SESSIONS=$(curl -s "http://localhost:$CURRENT_PORT/api/sessions")

    # 8. 新コンテナでrestore
    NEW_KERNEL_ID=$(restore_container "localhost:$NEW_PORT")

    # 9. 新コンテナでセッション情報を再作成（旧session_idを使用）
    echo "$OLD_SESSIONS" | jq -c '.[]' | while read session; do
        OLD_SESSION_ID=$(echo "$session" | jq -r '.id')
        NOTEBOOK_PATH=$(echo "$session" | jq -r '.path')
        curl -X POST "http://localhost:$NEW_PORT/api/sessions" \
            -H "Content-Type: application/json" \
            -d "{
                \"id\": \"$OLD_SESSION_ID\",
                \"path\": \"$NOTEBOOK_PATH\",
                \"type\": \"notebook\",
                \"kernel\": {\"id\": \"$NEW_KERNEL_ID\", \"name\": \"elastic_kernel\"}
            }"
    done
    # 注意: Jupyter Server APIがidパラメータをサポートしているか要検証（セクション8.5.1）

    # 10. プロキシ切り替え
    curl -X POST "http://localhost:$PROXY_PORT/admin/switch" \
        -H "Content-Type: application/json" \
        -d "{\"target_port\": $NEW_PORT}"

    echo "Switched to port $NEW_PORT"

    # 11. 旧コンテナ削除
    sudo podman stop "$CONTAINER_NAME-$CURRENT_PORT"
    sudo podman rm "$CONTAINER_NAME-$CURRENT_PORT"

    echo "Migration complete!"
}

# restore_container関数は新しいkernel_idを返す
restore_container() {
    local jupyter_url=$1
    local kernel_id=$(curl -X POST "$jupyter_url/api/kernels" \
        -H "Content-Type: application/json" \
        -d '{"name":"elastic_kernel"}' | jq -r '.id')

    # カーネルがidleになるまで待機
    wait_for_kernel_idle "$jupyter_url" "$kernel_id"

    echo "$kernel_id"
}
```

---

## 7. 技術的考慮事項

### 7.1 WebSocket接続の処理

**課題:**
プロキシ切り替え時、既存のWebSocket接続が切断される

**対策:**
1. **JupyterLabの自動再接続機能を活用**
   - JupyterLabは標準でWebSocket切断時に自動再接続を試みる
   - プロキシ切り替え後、新しいコンテナに自動的に再接続される

2. **グレースフルな切り替え**
   - 新コンテナの準備完了を確認してから切り替える
   - 切り替え直後、プロキシは新コンテナへの接続を即座に確立できる

3. **タイムアウト設定**
   - WebSocketのタイムアウトを適切に設定し、再接続までの時間を短縮

### 7.2 ポート管理

**方式: ピンポン方式**

```
restart 1回目: 8888 → 8889
restart 2回目: 8889 → 8888
restart 3回目: 8888 → 8889
...
```

**メリット:**
- ポート番号が予測可能
- リソースリークを防ぐ（常に2つのポートのみ使用）

**実装:**
- プロキシが現在接続中のポート番号を記憶
- run.shはプロキシに問い合わせて、次のポート番号を決定

### 7.3 エラーハンドリング

**想定されるエラーケース:**

1. **新コンテナの起動失敗**
   - 対策: 旧コンテナを維持し、ロールバック
   - プロキシは旧コンテナへの接続を継続

2. **checkpoint失敗**
   - 対策: エラーログを出力し、新コンテナを削除
   - 旧コンテナで作業を継続

3. **restore失敗**
   - 対策: 新コンテナを削除し、旧コンテナを維持
   - ユーザーに警告を表示

4. **プロキシの切り替え失敗**
   - 対策: 切り替えをリトライ（最大3回）
   - 失敗時は旧コンテナを維持

**実装方針:**
```bash
set -e  # エラー時に即座に停止
trap cleanup ERR  # エラー時のクリーンアップ関数を定義

cleanup() {
    echo "Error occurred. Rolling back..."
    # 新コンテナを削除
    # 旧コンテナは維持
}
```

### 7.4 リソースクリーンアップ

**タイミング:**
プロキシ切り替え後、旧コンテナを即座に削除

**理由:**
- メモリ使用量を最小限に保つ
- ポート競合を避ける
- 次回のrestartでスムーズに起動

**実装:**
```bash
# 旧コンテナ削除（graceful shutdown）
sudo podman stop -t 10 "$CONTAINER_NAME-$OLD_PORT"
sudo podman rm "$CONTAINER_NAME-$OLD_PORT"
```

### 7.5 セキュリティ考慮事項

**現状:**
- JupyterLabは認証なし（`--NotebookApp.token=''`）
- XSRF保護も無効（開発環境向け）

**プロキシ導入後:**
- 開発環境では現状維持
- 本番環境で使用する場合は、プロキシレイヤーで認証を追加することを検討

**推奨:**
開発環境では現状のまま、セキュリティ機能は追加しない

### 7.6 パフォーマンス

**懸念:**
プロキシを経由することで、レイテンシが増加する可能性

**対策:**
1. **ローカル接続**: プロキシとコンテナは同一ホスト上で動作し、ネットワークオーバーヘッドは最小限
2. **非同期処理**: FastAPIの非同期処理により、複数の接続を効率的に処理
3. **最小限の処理**: プロキシはリクエストを転送するだけで、追加の処理は行わない

**期待される影響:**
- レイテンシ: +1〜5ms程度（ほぼ無視できる）
- スループット: 直接接続と同等

---

## 8. カーネルID管理の詳細

### 8.1 Jupyter WebSocket APIの仕組み

**発見事項（実験による確認）:**

#### 実験1: 任意のsession_idでカーネルに接続できる

JupyterのWebSocket APIでは、任意の`session_id`を使って既存のカーネルに接続できることが確認されました。

**WebSocket接続のURL構造:**
```
ws://localhost:8888/api/kernels/{kernel_id}/channels?session_id={session_id}
```

**実験コード:**
```python
import asyncio
import json
import uuid
import websockets

JUPYTER_URL = "ws://localhost:8888/api/kernels/{kernel_id}/channels?session_id={session_id}"
KERNEL_ID = "e4a45c3d-68b8-426a-9cbf-fb47d770a13a"  # 既存のカーネルID

async def main():
    session_id = str(uuid.uuid4())  # 任意のUUID
    url = JUPYTER_URL.format(kernel_id=KERNEL_ID, session_id=session_id)

    async with websockets.connect(url) as ws:
        # kernel_info_requestメッセージを送信
        msg = {
            "header": {
                "msg_id": str(uuid.uuid4()),
                "username": "api-client",
                "session": session_id,
                "msg_type": "kernel_info_request",
                "version": "5.3"
            },
            "parent_header": {},
            "metadata": {},
            "content": {},
            "channel": "shell"
        }
        await ws.send(json.dumps(msg))
        print("Sent kernel_info_request")

        # レスポンスを受信
        while True:
            raw = await ws.recv()
            msg = json.loads(raw)
            print(f"← {msg['header'].get('msg_type')}")
            if msg["header"].get("msg_type") == "kernel_info_reply":
                print("✅ Kernel is alive and connected!")
                break

asyncio.run(main())
```

**実験1の結論:**
- `session_id`は単なるクライアント識別子で、サーバー側で厳密に管理されていない
- 任意の`session_id`で既存の`kernel_id`に接続できる
- カーネルは`idle`状態になり、正常に通信できる

#### 実験2: セッションのカーネルIDを切り替えられる ✅

**同一コンテナ内でのセッションのカーネル切り替えに成功しました。**

**実験手順:**

1. **初期状態のカーネル一覧を確認**
   ```bash
   curl -s "http://localhost:8888/api/kernels" | jq
   ```
   出力:
   ```json
   [
     {
       "id": "12360f24-16bd-4dd5-96e5-f624eb3a5e74",
       "name": "elastic_kernel",
       "last_activity": "2025-11-11T04:54:34.287808Z",
       "execution_state": "idle",
       "connections": 1
     },
     {
       "id": "64b4f1f6-2834-404f-bb37-b3c08bd60099",
       "name": "elastic_kernel",
       "last_activity": "2025-11-11T04:54:11.422423Z",
       "execution_state": "idle",
       "connections": 0
     }
   ]
   ```

2. **セッションのカーネルを切り替え**
   ```bash
   curl -X PATCH "http://localhost:8888/api/sessions/8cb97e97-5c9c-44b7-ab4a-73395c18b0d2" \
     -H "Content-Type: application/json" \
     -d '{"kernel": {"id": "64b4f1f6-2834-404f-bb37-b3c08bd60099"}}'
   ```

3. **カーネル一覧を再確認**
   ```bash
   curl -s "http://localhost:8888/api/kernels" | jq
   ```
   出力:
   ```json
   [
     {
       "id": "64b4f1f6-2834-404f-bb37-b3c08bd60099",
       "name": "elastic_kernel",
       "last_activity": "2025-11-11T04:54:11.422423Z",
       "execution_state": "idle",
       "connections": 0
     }
   ]
   ```
   → 旧カーネル（12360f24...）が削除され、新カーネル（64b4f1f6...）のみ残った

**実験2の結論:**
- ✅ `PATCH /api/sessions/{session_id}` でセッションのカーネルを切り替え可能
- ✅ **ブラウザ上でページリロード不要で新カーネルに接続できた**
- ✅ ブラウザのカーネルステータスは`idle`のまま表示された
- ✅ セルを実行すると`connections`が1になり、正常に動作
- ⚠️ **ただし、この実験では新カーネルがチェックポイントから復元されていない**
  - 新カーネル（64b4f1f6...）は手動で起動したもので、ElasticKernelのcheckpoint復元機能が使われていない

### 8.2 ブラウザのカーネル接続メカニズム

**JupyterLabがカーネルに接続する流れ:**

1. **ノートブックを開く**
   - ブラウザがノートブックファイル（例: `notebook.ipynb`）を開く
   - JupyterLabフロントエンドが`/api/sessions`をリクエスト

2. **セッション情報の取得**
   ```bash
   GET /api/sessions
   ```
   レスポンス例:
   ```json
   [
     {
       "id": "session-abc123",
       "path": "notebook.ipynb",
       "name": "notebook.ipynb",
       "type": "notebook",
       "kernel": {
         "id": "kernel-xyz789",
         "name": "python3",
         "last_activity": "2025-11-11T10:00:00Z",
         "execution_state": "idle",
         "connections": 1
       }
     }
   ]
   ```

3. **WebSocket接続の確立**
   - フロントエンドが`kernel_id`（例: `kernel-xyz789`）を取得
   - クライアント側で`session_id`を生成（UUID）
   - WebSocket接続を確立:
     ```
     ws://localhost:8888/api/kernels/kernel-xyz789/channels?session_id=client-generated-uuid
     ```

**重要なポイント:**
- ブラウザは`kernel_id`を`/api/sessions`から取得する
- `session_id`はクライアント側で生成され、サーバーには保存されない
- プロキシ切り替え後、ブラウザが旧`kernel_id`で接続を試みる問題が発生する

### 8.3 プロキシ切り替え時の課題分析

**実験2の成果:**
- ✅ 同一コンテナ内では`PATCH /api/sessions/{session_id}`でカーネル切り替え成功
- ✅ ブラウザ上でページリロード不要で新カーネルに接続できた

**プロキシ切り替え時の課題:**

しかし、**異なるコンテナ間**でのプロキシ切り替え時には、追加の問題があります：

```
[旧コンテナ (8888)]                      [新コンテナ (8889)]
session_id: session-abc123               session_id: (存在しない)
kernel_id:  kernel-123                   kernel_id:  kernel-789
      ↑                                        ↑
ブラウザは session-abc123 でWebSocket接続
      ↓
プロキシを8889に切り替え
      ↓
ブラウザは session-abc123 に再接続を試みる
      ↓
新コンテナには session-abc123 が存在しない
      ↓
404 Not Found または接続エラー
```

**問題の核心:**

1. **session_idの不一致**
   - ブラウザがキャッシュしている旧`session_id`（session-abc123）
   - 新コンテナには旧`session_id`が存在しない
   - → WebSocket再接続時に404エラー

2. **kernel_idの不一致**（副次的な問題）
   - ブラウザがキャッシュしている旧`kernel_id`（kernel-123）
   - 新コンテナには旧`kernel_id`が存在しない
   - → `/api/sessions`を再取得しても、新しいセッション情報が見つからない可能性

**ブラウザの挙動予測:**

プロキシ切り替え時にWebSocket接続が切断されると、JupyterLabは以下のいずれかの挙動を取る可能性があります（**要検証**）：

1. **既知のsession_idでWebSocket再接続を試みる**
   - ブラウザがキャッシュしている旧`session_id`（session-abc123）でWebSocket接続
   - → 新コンテナに存在しないため、404エラー
   - → `/api/sessions`を再取得する可能性（これが起きれば成功）

2. **`/api/sessions`を再取得する**
   - WebSocket切断時に`/api/sessions`を再度リクエスト
   - **ただし、新コンテナには旧notebook_pathに対応するセッションが存在しない**
   - → 空の配列が返され、カーネルとの接続が失われる

3. **エラーを表示してユーザーにリロードを促す**
   - 再接続に失敗し、「カーネルとの接続が切れました」と表示
   - → ユーザーがF5リロードすることで新セッションに接続（最悪のケース）

### 8.4 実装オプションの比較

実験2の結果を踏まえ、以下の実装オプションを検討します。

#### Option A: プロキシでsession_idとkernel_idをリライトする

**アイデア:**
- プロキシがリクエストを転送する際、URLの`session_id`と`kernel_id`を書き換える
- 旧`session_id`（session-abc123） → 新`session_id`（session-xyz789）にマッピング
- 旧`kernel_id`（kernel-123） → 新`kernel_id`（kernel-789）にマッピング
- レスポンスも逆変換して、ブラウザには旧IDが維持されているように見せる

**実装イメージ:**
```python
# プロキシのマッピングテーブル
session_id_mapping = {
    "session-abc123": "session-xyz789"  # 旧 → 新
}
kernel_id_mapping = {
    "kernel-123": "kernel-789"  # 旧 → 新
}

@app.websocket("/api/kernels/{kernel_id}/channels")
async def websocket_proxy(websocket: WebSocket, kernel_id: str, session_id: str):
    # IDをリライト
    actual_kernel_id = kernel_id_mapping.get(kernel_id, kernel_id)
    actual_session_id = session_id_mapping.get(session_id, session_id)

    # 新コンテナに転送
    target = f"ws://localhost:{new_port}/api/kernels/{actual_kernel_id}/channels?session_id={actual_session_id}"
    # WebSocketプロキシ処理...

@app.get("/api/sessions")
async def sessions_proxy(request: Request):
    # 新コンテナから取得
    sessions = await fetch_sessions(new_port)
    # session_idとkernel_idを旧IDに逆変換
    for session in sessions:
        session["id"] = reverse_session_id_mapping.get(session["id"], session["id"])
        session["kernel"]["id"] = reverse_kernel_id_mapping.get(session["kernel"]["id"], session["kernel"]["id"])
    return sessions
```

**メリット:**
- ✅ ブラウザからは完全に透過的（ページリロード不要）
- ✅ 既存のJupyterLabフロントエンドに変更不要
- ✅ ユーザー体験が最も良い

**デメリット:**
- ❌ プロキシの実装が非常に複雑
- ❌ WebSocketメッセージ内のIDも書き換える必要がある可能性
- ❌ すべてのREST APIエンドポイントでID変換が必要
- ❌ バグが混入しやすく、デバッグが困難

**実現可能性:** 中（実装コストが高い）

#### Option B: セッション情報を移行する（旧session_idを使用）

**アイデア:**
- 旧コンテナから`/api/sessions`でセッション情報（`session_id`, `path`, `kernel_id`）を取得
- 新コンテナでカーネルを起動（ElasticKernelがcheckpointから自動復元）
- **新コンテナで旧`session_id`を使ってセッションを作成**
- ブラウザがWebSocket再接続時に、同じ`session_id`で接続できる

**実装イメージ:**
```bash
# 1. 旧コンテナからセッション情報を取得
OLD_SESSIONS=$(curl -s "http://localhost:8888/api/sessions")
# → [{"id": "session-abc123", "path": "notebook.ipynb", "kernel": {"id": "kernel-123", ...}}]

# 各セッションについて:
OLD_SESSION_ID=$(echo "$OLD_SESSIONS" | jq -r '.[0].id')  # "session-abc123"
NOTEBOOK_PATH=$(echo "$OLD_SESSIONS" | jq -r '.[0].path')  # "notebook.ipynb"

# 2. 新コンテナでカーネルを起動（checkpointから自動復元）
NEW_KERNEL_ID=$(curl -X POST "http://localhost:8889/api/kernels" \
    -H "Content-Type: application/json" \
    -d '{"name": "elastic_kernel"}' | jq -r '.id')
# → "kernel-789"（ElasticKernelが自動的にcheckpoint.pickleから復元）

# 3. 新コンテナで旧session_idを使ってセッションを作成（要検証！）
curl -X POST "http://localhost:8889/api/sessions" \
    -H "Content-Type: application/json" \
    -d '{
        "id": "'$OLD_SESSION_ID'",
        "path": "'$NOTEBOOK_PATH'",
        "type": "notebook",
        "kernel": {"id": "'$NEW_KERNEL_ID'", "name": "elastic_kernel"}
    }'
```

**重要な検証ポイント:**
- ⚠️ Jupyter Server APIで`id`パラメータを指定してセッションを作成できるか？
- ⚠️ できない場合は、新しい`session_id`が生成され、ブラウザとの接続が失われる

**メリット:**
- ✅ Jupyter標準APIのみを使用（プロキシの実装がシンプル）
- ✅ セッション情報が正しく維持される
- ✅ **旧session_idを保持できれば、ブラウザがWebSocket再接続時に成功する**

**デメリット:**
- ❌ Jupyter Server APIが`id`パラメータをサポートしているか不明（**要検証**）
- ❌ サポートしていない場合、新`session_id`が生成され、ブラウザとの接続が失われる

**実現可能性:** 高（ただしAPIの検証が必要）

#### Option C: プロキシが/api/sessionsをインターセプトする

**アイデア:**
- プロキシが`/api/sessions`リクエストをインターセプト
- 新コンテナから取得したセッション情報を、**旧session_idに書き換えて**ブラウザに返す
- WebSocket接続時も、旧session_idを新session_idに変換して転送

**実装イメージ:**
```python
# プロキシのマッピングテーブル（切り替え時に生成）
session_mapping = {
    "old-session-abc123": "new-session-xyz789"
}

@app.get("/api/sessions")
async def sessions_proxy():
    # 新コンテナから取得
    sessions = await fetch_sessions(new_port)
    # session_idを旧IDに変換してブラウザに返す
    for session in sessions:
        new_session_id = session["id"]
        old_session_id = find_old_session_id_by_path(session["path"])
        session["id"] = old_session_id
        session_mapping[old_session_id] = new_session_id
    return sessions

@app.websocket("/api/kernels/{kernel_id}/channels")
async def websocket_proxy(websocket: WebSocket, kernel_id: str, session_id: str):
    # session_idを新IDに変換
    actual_session_id = session_mapping.get(session_id, session_id)
    # 新コンテナに転送
    target = f"ws://localhost:{new_port}/api/kernels/{kernel_id}/channels?session_id={actual_session_id}"
    # WebSocketプロキシ処理...
```

**メリット:**
- ✅ ブラウザからは旧session_idがそのまま使える（透過的）
- ✅ kernel_idの変換は不要（セッション情報に含まれる）
- ✅ Option Aより実装がシンプル

**デメリット:**
- ❌ プロキシが`/api/sessions`と`/api/kernels/.../channels`の両方を処理する必要がある
- ❌ notebook pathからsession_idのマッピングを維持する必要がある
- ❌ 複数ノートブックがある場合、pathによる識別が必要

**実現可能性:** 高（Option Aより実装コストが低い）

#### Option D: JupyterLabの自動再接続に依存（最悪ページリロード）

**アイデア:**
- プロキシ切り替え時にWebSocket接続を切断
- JupyterLabの標準機能による自動再接続を期待
- 最悪の場合、ユーザーにページリロード（F5）を促す（現状より改善）

**実装:**
- 新コンテナで新session_idと新kernel_idでセッションを作成
- プロキシを切り替え
- JupyterLabが自動的に`/api/sessions`を再取得して新カーネルに接続することを期待
- 失敗した場合、ユーザーがF5でリロード

**メリット:**
- ✅ 実装が最もシンプル
- ✅ JupyterLabの標準機能を最大限活用
- ✅ プロキシはシンプルな転送のみ

**デメリット:**
- ❌ 自動再接続が機能しない場合、ページリロードが必要
- ❌ ユーザー体験が挙動に依存する（不確実性）
- ❌ 現状と同じくページリロードが必要になる可能性

**実現可能性:** 高（ただしUX改善効果は不確実）

### 8.5 検証が必要な項目

**既に確認済み（実験2）:**
- ✅ 同一コンテナ内で`PATCH /api/sessions/{session_id}`によるカーネル切り替えが成功
- ✅ ブラウザ上でページリロード不要で新カーネルに接続できた

**追加で検証が必要な項目:**

#### 8.5.1 旧session_idを指定してセッションを作成できるか（Option B検証）

**実験方法:**
1. 旧コンテナ（8888）でセッション情報を取得
   ```bash
   OLD_SESSIONS=$(curl -s "http://localhost:8888/api/sessions")
   OLD_SESSION_ID=$(echo "$OLD_SESSIONS" | jq -r '.[0].id')
   ```

2. 新コンテナ（8889）でカーネルを起動

3. 新コンテナで**旧session_idを指定**してセッションを作成
   ```bash
   curl -X POST "http://localhost:8889/api/sessions" \
     -H "Content-Type: application/json" \
     -d '{
         "id": "'$OLD_SESSION_ID'",
         "path": "notebook.ipynb",
         "type": "notebook",
         "kernel": {"id": "'$NEW_KERNEL_ID'", "name": "elastic_kernel"}
     }'
   ```

**確認事項:**
- [ ] Jupyter Server APIが`id`パラメータをサポートしているか？
- [ ] 指定した`id`でセッションが作成されるか？
- [ ] それとも、新しいUUIDが自動生成されるか？

**期待される結果:**
- ✅ 指定した`id`でセッションが作成される → Option Bが実現可能
- ❌ 新しいUUIDが生成される → Option C（プロキシでインターセプト）またはOption Dが必要

#### 8.5.2 プロキシ切り替え時のJupyterLabの挙動

**実験方法:**
1. 簡易プロキシを実装（ポート8888と8889を単純転送）
2. JupyterLabを起動してノートブックを開く（プロキシ経由）
3. 新コンテナ（8889）でセッションを作成（旧session_idを使用、または新session_id）
4. プロキシを8888から8889に切り替え
5. ブラウザの開発者ツールでネットワークトラフィックを監視

**確認事項:**
- [ ] WebSocket接続が切断されるか？
- [ ] JupyterLabが`/api/sessions`を再取得するか？
- [ ] それとも、既知の`session_id`でWebSocket再接続を試みるか？
- [ ] 再接続に失敗した場合、エラーメッセージが表示されるか？
- [ ] ページリロード（F5）で正常に新カーネルに接続できるか？

**期待される結果:**
- ✅ JupyterLabが`/api/sessions`を再取得し、新セッションに自動接続
- ⚠️ 既知の`session_id`で再接続を試み、失敗してエラー表示
- ❌ 完全にハングして、ページリロードが必要

#### 8.5.3 WebSocketメッセージ内のsession_idとkernel_id

**実験方法:**
1. ブラウザの開発者ツールでWebSocketトラフィックをキャプチャ
2. JupyterLabでセルを実行
3. WebSocketメッセージのペイロードを解析

**確認事項:**
- [ ] WebSocketメッセージ内に`session_id`が含まれているか？
- [ ] WebSocketメッセージ内に`kernel_id`が含まれているか？
- [ ] 含まれている場合、すべてのメッセージで書き換えが必要か？
- [ ] レスポンスのJSON構造はどうなっているか？

**期待される結果:**
- `session_id`はURLクエリパラメータのみで、メッセージ本体には含まれない → プロキシでのリライトが容易
- メッセージ本体にも含まれる → Option Aの実装が複雑化

### 8.6 推奨アプローチ

**実験2の成果により、実装方針が明確になりました:**

- ✅ 同一コンテナ内では`PATCH /api/sessions/{session_id}`でカーネル切り替え成功
- ⚠️ 異なるコンテナ間では、session_idの移行方法が未確認

**段階的な実装戦略:**

#### Phase 1: セクション8.5.1の実験を最優先で実施

**目的:** Option Bの実現可能性を確認

**実験内容:**
- 新コンテナで旧`session_id`を指定してセッションを作成できるかを確認
- Jupyter Server APIが`id`パラメータをサポートしているかを検証

**期待される結果:**
- ✅ **成功した場合** → Option Bを採用（最もシンプル）
  - 新コンテナで旧session_idを使ってセッションを作成
  - ブラウザがWebSocket再接続時に同じsession_idで接続成功
  - ページリロード不要で移行完了 🎉

- ❌ **失敗した場合** → Phase 2へ進む

#### Phase 2: Option Cまたはセクション8.5.2の実験を実施

**Option Cを試す場合:**
- プロキシで`/api/sessions`をインターセプトしてsession_idを書き換え
- WebSocket接続時もsession_idを変換
- 実装コスト: 中

**セクション8.5.2の実験を試す場合:**
- 簡易プロキシでポート切り替えを実装
- JupyterLabの自動再接続挙動を観察
- `/api/sessions`を再取得して新セッションに自動接続するかを確認

**期待される結果:**
- ✅ JupyterLabが自動的に`/api/sessions`を再取得 → Option D（最もシンプル）を採用
- ❌ 自動再接続が機能しない → Phase 3へ進む

#### Phase 3: Option Cの実装（プロキシでインターセプト）

**実装内容:**
- プロキシが`/api/sessions`と`/api/kernels/.../channels`をインターセプト
- session_idをマッピングテーブルで変換
- kernel_idは変換不要（セッション情報に含まれる）

**メリット:**
- ページリロード不要で移行完了
- Option Aよりシンプル

#### Phase 4: 完全な透過性の実現（オプション）

**Option Aの実装（最も複雑）:**
- プロキシですべてのREST APIとWebSocketメッセージを処理
- session_idとkernel_idを完全にリライト
- 完全に透過的な移行を実現

**採用判断:**
- Phase 3でも問題が残る場合のみ検討
- 実装コストが高いため、最後の手段

---

**次のステップ（優先順位順）:**

1. **🔥 最優先: セクション8.5.1の実験を実施**
   - 新コンテナで旧session_idを使ってセッション作成できるかを確認
   - これが成功すれば、最もシンプルな実装で完了

2. セクション8.5.2の実験を実施
   - プロキシ切り替え時のJupyterLabの挙動を観察
   - 自動再接続の有無を確認

3. セクション8.5.3の実験を実施（オプション）
   - WebSocketメッセージ内のID構造を解析
   - プロキシ実装の詳細設計に活用

4. 実験結果をドキュメントに記録

5. 最適な実装オプションを選択してプロトタイプを開始

---

## 9. 今後の拡張可能性

この設計は、将来的に以下の機能を追加できる柔軟性を持ちます：

1. **複数ノートブックの同時マイグレーション**
   - 複数のJupyterLabインスタンスを管理
   - セッションごとに独立したcheckpoint/restore

2. **ロードバランシング**
   - 複数のコンテナに負荷を分散
   - ユーザーセッションごとに最適なコンテナを割り当て

3. **モニタリング・ログ**
   - プロキシで全リクエストをログ記録
   - パフォーマンスメトリクスの収集

4. **A/Bテスト**
   - 異なるバージョンのElasticKernelを同時に稼働
   - ユーザーごとに異なるバージョンを割り当て

---

## 10. まとめ

### 10.1 実験で確認されたこと

**実験2の成果:**
- ✅ `PATCH /api/sessions/{session_id}`でセッションのカーネルを切り替え可能
- ✅ **ブラウザ上でページリロード不要で新カーネルに接続できた**
- ✅ セルを実行すると正常に動作（connections=1になる）
- ⚠️ ただし、新カーネルがcheckpointから復元されていない問題が残る

**この発見の意義:**
- 同一コンテナ内ではシームレスなカーネル切り替えが可能と確認
- 異なるコンテナ間でも、session_idを適切に管理すれば実現可能性が高い

### 10.2 解決される問題（目標）

- **ページリロード不要（理想）**: プロキシが自動的に新コンテナに接続先を切り替え
  - Option Bが成功すれば実現可能
  - Option C/Dでも一定の改善が期待できる
- **ユーザー体験の向上**: checkpoint/restoreが裏で実行され、ユーザーは作業を継続可能
- **シームレスな移行**: WebSocket接続は一時的に切断されるが、適切に再接続

### 10.3 実装の優先順位

**最優先（Phase 1）:**
1. 🔥 **セクション8.5.1の実験を実施**（最重要）
   - 新コンテナで旧session_idを使ってセッション作成できるかを確認
   - これが成功すれば、最もシンプルな実装で完了

**Phase 2以降:**
2. セクション8.5.2の実験を実施（JupyterLabの自動再接続挙動を確認）
3. 実験結果に基づいて実装オプション（A/B/C/D）を選択
4. カスタムプロキシの実装（Python/FastAPI）
5. run.shへの統合（新しいrestartフロー）
6. エラーハンドリングの強化
7. モニタリング・ログ機能の追加

### 10.4 次のステップ（具体的なアクション）

**1. セクション8.5.1の実験（最優先）**
   ```bash
   # 旧コンテナからセッション情報を取得
   OLD_SESSION_ID=$(curl -s "http://localhost:8888/api/sessions" | jq -r '.[0].id')

   # 新コンテナでカーネルを起動
   NEW_KERNEL_ID=$(curl -X POST "http://localhost:8889/api/kernels" \
       -d '{"name":"elastic_kernel"}' | jq -r '.id')

   # 新コンテナで旧session_idを指定してセッション作成
   curl -X POST "http://localhost:8889/api/sessions" \
       -H "Content-Type: application/json" \
       -d '{
           "id": "'$OLD_SESSION_ID'",
           "path": "notebook.ipynb",
           "type": "notebook",
           "kernel": {"id": "'$NEW_KERNEL_ID'", "name": "elastic_kernel"}
       }'
   ```

**2. 実験結果をドキュメントに記録**
   - 成功した場合: Option Bの実装を開始
   - 失敗した場合: セクション8.5.2の実験へ進む

**3. プロトタイプの実装**
   - 選択したオプションでプロキシを実装
   - run.shへの統合

---

## 参考資料

- JupyterLab WebSocket再接続: https://github.com/jupyterlab/jupyterlab/pull/8432
- FastAPI WebSocketプロキシ例: https://fastapi.tiangolo.com/advanced/websockets/
- Blue-Green Deployment: https://martinfowler.com/bliki/BlueGreenDeployment.html
- Jupyter Server API: https://jupyter-server.readthedocs.io/en/latest/developers/rest-api.html
