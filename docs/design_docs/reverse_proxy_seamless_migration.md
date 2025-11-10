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

### 2.3 ユーザー体験

- ユーザーはブラウザでJupyterLabを開いたまま
- checkpoint/restoreが裏で実行される
- プロキシが自動的に新コンテナに接続先を切り替える
- **ページリロード不要**
- WebSocket接続は一時的に切断されるが、JupyterLabの再接続機能で自動復帰

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

### 4.4 Step 3: 新コンテナでrestore

**処理:**
1. run.shが新コンテナB (8889) に対してカーネル起動リクエスト送信
   ```bash
   curl -X POST "http://localhost:8889/api/kernels" \
        -H "Content-Type: application/json" \
        -d '{"name":"elastic_kernel"}'
   ```
2. ElasticKernelの`__init__()`が実行され、checkpoint.pickleをロード
3. ElasticNotebookが変数を復元し、必要なセルを再計算
4. カーネルが`idle`状態になるまで待機

**状態:**
```
[ブラウザ] → [プロキシ] → [コンテナ A (8888)] ← checkpoint完了
                          [コンテナ B (8889)] ← カーネル起動、変数復元完了
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
  7. 新コンテナでrestore（カーネル起動 + 変数復元）
  8. プロキシに切り替え指示（新ポート番号へ）
  9. 旧コンテナを停止・削除
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

    # 7. 新コンテナでrestore
    restore_container "localhost:$NEW_PORT"

    # 8. プロキシ切り替え
    curl -X POST "http://localhost:$PROXY_PORT/admin/switch" \
        -H "Content-Type: application/json" \
        -d "{\"target_port\": $NEW_PORT}"

    echo "Switched to port $NEW_PORT"

    # 9. 旧コンテナ削除
    sudo podman stop "$CONTAINER_NAME-$CURRENT_PORT"
    sudo podman rm "$CONTAINER_NAME-$CURRENT_PORT"

    echo "Migration complete!"
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

## 8. 今後の拡張可能性

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

## 9. まとめ

### 9.1 解決される問題

- **ページリロードが不要に**: プロキシが自動的に新コンテナに接続先を切り替え
- **ユーザー体験の向上**: checkpoint/restoreが裏で実行され、ユーザーは作業を継続可能
- **シームレスな移行**: WebSocket接続は一時的に切断されるが、自動再接続により透過的

### 9.2 実装の優先順位

1. **Phase 1**: カスタムプロキシの実装（Python/FastAPI）
2. **Phase 2**: run.shへの統合（新しいrestartフロー）
3. **Phase 3**: エラーハンドリングの強化
4. **Phase 4**: モニタリング・ログ機能の追加

### 9.3 次のステップ

1. カスタムプロキシのプロトタイプ実装
2. run.shの新しいrestartフローの実装
3. 統合テスト
4. ドキュメント更新

---

## 参考資料

- JupyterLab WebSocket再接続: https://github.com/jupyterlab/jupyterlab/pull/8432
- FastAPI WebSocketプロキシ例: https://fastapi.tiangolo.com/advanced/websockets/
- Blue-Green Deployment: https://martinfowler.com/bliki/BlueGreenDeployment.html
