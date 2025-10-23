import subprocess
import threading
import json
from datetime import datetime, timezone, timedelta

# JSTタイムゾーン
JST = timezone(timedelta(hours=9))

# === JSTで基準時刻を取得 ===
restart_start_time = datetime.now(JST).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + "+09:00"

# === Dockerイベント取得をバックグラウンドで実行 ===
events_output = []

def capture_events():
    proc = subprocess.Popen(
        ["docker", "compose", "events", "--json", "--since", restart_start_time],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    try:
        for line in proc.stdout:
            line = line.strip()
            if line:
                try:
                    event = json.loads(line)
                    events_output.append(event)
                except json.JSONDecodeError:
                    events_output.append({"raw": line})
    except Exception as e:
        print(f"[Event capture error] {e}")

# イベント取得スレッド開始
events_thread = threading.Thread(target=capture_events, daemon=True)
events_thread.start()

# === コンテナ停止 ===
subprocess.run(["docker", "compose", "stop"])

print("=" * 50)
print(restart_start_time)
print("=" * 50)

# === コンテナ起動 ===
subprocess.run(["docker", "compose", "up", "-d"])

input("セル1を実行できたらEnterキーを押してください: ")

# === ログ取得 ===
raw_logs = subprocess.run(
    ["docker", "compose", "logs", "--timestamps"],
    capture_output=True,
    text=True
).stdout.splitlines()

print("\n===================== LOGS (JST) =====================")
for line in raw_logs:
    parts = line.split()
    if len(parts) >= 3:
        ts_str = parts[2]
        try:
            # UTCのZをJSTに変換
            dt_utc = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            dt_jst = dt_utc.astimezone(JST)
            ts_jst = dt_jst.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + "+09:00"
            if ts_jst >= restart_start_time:
                # 文字列置換でJSTタイムスタンプに差し替え
                line_jst = line.replace(ts_str, ts_jst, 1)
                print(line_jst)
        except Exception:
            print(line)  # 変換できなければそのまま出す

# === イベント出力 ===
print("\n===================== EVENTS (JST) =====================")
for event in events_output:
    if "time" in event:
        ts = event["time"]
        # events はすでに +09:00 の場合が多いのでそのまま
        try:
            dt_event = datetime.fromisoformat(ts)
            dt_event_jst = dt_event.astimezone(JST)
            ts_jst = dt_event_jst.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + "+09:00"
        except Exception:
            ts_jst = ts

        if ts_jst >= restart_start_time:
            service = event.get("service", "unknown")
            action = event.get("action", "unknown")
            attributes = event.get("attributes", {})
            print(f"{ts_jst} [{service}] {action} {attributes}")
    else:
        print(event.get("raw", ""))



"""
コンテナ停止命令: EVENTSの[jupyter] kill
jupyter停止命令: LOGSのreceived signal 15, stopping
jupyterカーネル停止命令: LOGSの

===================== LOGS (JST) =====================
jupyter-1  | 2025-10-23T17:32:41.648+09:00 [C 2025-10-23 08:32:41.647 ServerApp] received signal 15, stopping
jupyter-1  | 2025-10-23T17:32:41.649+09:00 [I 2025-10-23 08:32:41.649 ServerApp] Shutting down 5 extensions
jupyter-1  | 2025-10-23T17:32:41.649+09:00 [I 2025-10-23 08:32:41.649 ServerApp] Shutting down 1 kernel
jupyter-1  | 2025-10-23T17:32:41.650+09:00 [I 2025-10-23 08:32:41.650 ServerApp] Kernel shutdown: fbee4911-8dee-4d48-a95e-925c0aa1bf53
jupyter-1  | 2025-10-23T17:32:43.417+09:00 [I 2025-10-23 08:32:43.417 ServerApp] jupyter_lsp | extension was successfully linked.
jupyter-1  | 2025-10-23T17:32:43.418+09:00 [I 2025-10-23 08:32:43.418 ServerApp] jupyter_server_terminals | extension was successfully linked.
jupyter-1  | 2025-10-23T17:32:43.419+09:00 [W 2025-10-23 08:32:43.419 LabApp] 'token' has moved from NotebookApp to ServerApp. This config will be passed to ServerApp. Be sure to update your config before our next release.
jupyter-1  | 2025-10-23T17:32:43.419+09:00 [W 2025-10-23 08:32:43.419 LabApp] 'password' has moved from NotebookApp to ServerApp. This config will be passed to ServerApp. Be sure to update your config before our next release.
jupyter-1  | 2025-10-23T17:32:43.420+09:00 [W 2025-10-23 08:32:43.420 ServerApp] ServerApp.token config is deprecated in 2.0. Use IdentityProvider.token.
jupyter-1  | 2025-10-23T17:32:43.420+09:00 [I 2025-10-23 08:32:43.420 ServerApp] jupyterlab | extension was successfully linked.
jupyter-1  | 2025-10-23T17:32:43.421+09:00 [I 2025-10-23 08:32:43.421 ServerApp] notebook | extension was successfully linked.
jupyter-1  | 2025-10-23T17:32:43.532+09:00 [I 2025-10-23 08:32:43.532 ServerApp] notebook_shim | extension was successfully linked.
jupyter-1  | 2025-10-23T17:32:43.537+09:00 [W 2025-10-23 08:32:43.537 ServerApp] All authentication is disabled.  Anyone who can connect to this server will be able to run code.
jupyter-1  | 2025-10-23T17:32:43.538+09:00 [I 2025-10-23 08:32:43.537 ServerApp] notebook_shim | extension was successfully loaded.
jupyter-1  | 2025-10-23T17:32:43.538+09:00 [I 2025-10-23 08:32:43.538 ServerApp] jupyter_lsp | extension was successfully loaded.
jupyter-1  | 2025-10-23T17:32:43.539+09:00 [I 2025-10-23 08:32:43.539 ServerApp] jupyter_server_terminals | extension was successfully loaded.
jupyter-1  | 2025-10-23T17:32:43.540+09:00 [I 2025-10-23 08:32:43.540 LabApp] JupyterLab extension loaded from /usr/local/lib/python3.12/site-packages/jupyterlab
jupyter-1  | 2025-10-23T17:32:43.540+09:00 [I 2025-10-23 08:32:43.540 LabApp] JupyterLab application directory is /usr/local/share/jupyter/lab
jupyter-1  | 2025-10-23T17:32:43.540+09:00 [I 2025-10-23 08:32:43.540 LabApp] Extension Manager is 'pypi'.
jupyter-1  | 2025-10-23T17:32:43.553+09:00 [I 2025-10-23 08:32:43.553 ServerApp] jupyterlab | extension was successfully loaded.
jupyter-1  | 2025-10-23T17:32:43.554+09:00 [I 2025-10-23 08:32:43.554 ServerApp] notebook | extension was successfully loaded.
jupyter-1  | 2025-10-23T17:32:43.554+09:00 [I 2025-10-23 08:32:43.554 ServerApp] Serving notebooks from local directory: /app
jupyter-1  | 2025-10-23T17:32:43.554+09:00 [I 2025-10-23 08:32:43.554 ServerApp] Jupyter Server 2.17.0 is running at:
jupyter-1  | 2025-10-23T17:32:43.554+09:00 [I 2025-10-23 08:32:43.554 ServerApp] http://d19ec3cdba9a:8888/lab
jupyter-1  | 2025-10-23T17:32:43.554+09:00 [I 2025-10-23 08:32:43.554 ServerApp]     http://127.0.0.1:8888/lab
jupyter-1  | 2025-10-23T17:32:43.554+09:00 [I 2025-10-23 08:32:43.554 ServerApp] Use Control-C to stop this server and shut down all kernels (twice to skip confirmation).
jupyter-1  | 2025-10-23T17:32:43.561+09:00 [I 2025-10-23 08:32:43.561 ServerApp] Skipped non-installed server(s): basedpyright, bash-language-server, dockerfile-language-server-nodejs, javascript-typescript-langserver, jedi-language-server, julia-language-server, pyrefly, pyright, python-language-server, python-lsp-server, r-languageserver, sql-language-server, texlab, typescript-language-server, unified-language-server, vscode-css-languageserver-bin, vscode-html-languageserver-bin, vscode-json-languageserver-bin, yaml-language-server
jupyter-1  | 2025-10-23T17:32:44.807+09:00 [W 2025-10-23 08:32:44.807 LabApp] Could not determine jupyterlab build status without nodejs
jupyter-1  | 2025-10-23T17:32:45.088+09:00 [I 2025-10-23 08:32:45.088 ServerApp] Kernel started: c86d02a8-5b7e-40cf-972c-31d3883c5e94
jupyter-1  | 2025-10-23T17:32:46.057+09:00 [I 2025-10-23 08:32:46.056 ServerApp] Connecting to kernel c86d02a8-5b7e-40cf-972c-31d3883c5e94.
jupyter-1  | 2025-10-23T17:32:46.057+09:00 [I 2025-10-23 08:32:46.057 ServerApp] Connecting to kernel c86d02a8-5b7e-40cf-972c-31d3883c5e94.
jupyter-1  | 2025-10-23T17:32:46.058+09:00 [W 2025-10-23 08:32:46.058 ServerApp] The websocket_ping_timeout (90000) cannot be longer than the websocket_ping_interval (30000).
jupyter-1  | 2025-10-23T17:32:46.058+09:00     Setting websocket_ping_timeout=30000
jupyter-1  | 2025-10-23T17:32:46.071+09:00 [I 2025-10-23 08:32:46.070 ServerApp] Connecting to kernel c86d02a8-5b7e-40cf-972c-31d3883c5e94.

===================== EVENTS (JST) =====================
2025-10-23T17:32:41.648+09:00 [jupyter] kill {'desktop.docker.io/binds/0/Source': '/Users/matsumotoryutaro/programs/ElasticKernel/.workspace', 'desktop.docker.io/binds/0/SourceKind': 'hostFile', 'desktop.docker.io/binds/0/Target': '/app', 'desktop.docker.io/ports.scheme': 'v2', 'desktop.docker.io/ports/8888/tcp': ':8888', 'image': 'elastickernel-jupyter', 'name': 'elastickernel-jupyter-1', 'signal': '15'}
2025-10-23T17:32:42.422+09:00 [jupyter] stop {'desktop.docker.io/binds/0/Source': '/Users/matsumotoryutaro/programs/ElasticKernel/.workspace', 'desktop.docker.io/binds/0/SourceKind': 'hostFile', 'desktop.docker.io/binds/0/Target': '/app', 'desktop.docker.io/ports.scheme': 'v2', 'desktop.docker.io/ports/8888/tcp': ':8888', 'image': 'elastickernel-jupyter', 'name': 'elastickernel-jupyter-1'}
2025-10-23T17:32:42.426+09:00 [jupyter] die {'desktop.docker.io/binds/0/Source': '/Users/matsumotoryutaro/programs/ElasticKernel/.workspace', 'desktop.docker.io/binds/0/SourceKind': 'hostFile', 'desktop.docker.io/binds/0/Target': '/app', 'desktop.docker.io/ports.scheme': 'v2', 'desktop.docker.io/ports/8888/tcp': ':8888', 'execDuration': '104', 'exitCode': '0', 'image': 'elastickernel-jupyter', 'name': 'elastickernel-jupyter-1'}
2025-10-23T17:32:42.603+09:00 [jupyter] start {'desktop.docker.io/binds/0/Source': '/Users/matsumotoryutaro/programs/ElasticKernel/.workspace', 'desktop.docker.io/binds/0/SourceKind': 'hostFile', 'desktop.docker.io/binds/0/Target': '/app', 'desktop.docker.io/ports.scheme': 'v2', 'desktop.docker.io/ports/8888/tcp': ':8888', 'image': 'elastickernel-jupyter', 'name': 'elastickernel-jupyter-1'}

"""