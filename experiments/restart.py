import json
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone

log_file_path = "./.workspace/.elastic_kernel/7902699be42c8a8e/ElasticKernel.log"
JST = timezone(timedelta(hours=9))

restart_start_time = datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+09:00"

# ===================== Dockerイベント取得 =====================
events_output = []


def capture_events():
    proc = subprocess.Popen(
        ["docker", "compose", "events", "--json", "--since", restart_start_time],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
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


events_thread = threading.Thread(target=capture_events, daemon=True)
events_thread.start()

# ===================== コンテナ停止・起動 =====================
subprocess.run(["docker", "compose", "stop"])
print("=" * 50)
print(restart_start_time)
print("=" * 50)
subprocess.run(
    [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.exp.yml",
        "up",
        "-d",
    ]
)

input("セル1を実行できたらEnterキーを押してください: ")

# ===================== Docker LOGS =====================
raw_logs = subprocess.run(
    ["docker", "compose", "logs", "--timestamps"], capture_output=True, text=True
).stdout.splitlines()

print("\n===================== docker compose logs =====================")
for line in raw_logs:
    parts = line.split()
    if len(parts) >= 3:
        ts_str = parts[2]
        try:
            dt_utc = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            dt_jst = dt_utc.astimezone(JST)
            ts_jst = dt_jst.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+09:00"
            if ts_jst >= restart_start_time:
                line_jst = line.replace(ts_str, ts_jst, 1)
                print(line_jst)
        except Exception:
            print(line)

# ===================== LOG FILE =====================
print("\n===================== ElasticKernel.log =====================")
try:
    with open(log_file_path, "r") as f:
        for line in f:
            # フォーマット: [2025-10-23 13:59:51.845196 ...]
            if line.startswith("[") and "]" in line:
                ts_str = line[1:27]
                try:
                    dt_file = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")
                    dt_file = dt_file.replace(tzinfo=JST)
                    ts_jst = dt_file.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+09:00"
                    if ts_jst >= restart_start_time:
                        print(f"{ts_jst} {line.strip()}")
                except Exception:
                    print(line.strip())
except FileNotFoundError:
    print(f"[WARN] ログファイルが見つかりません: {log_file_path}")

# ===================== EVENTS =====================
print("\n===================== docker compose events =====================")
for event in events_output:
    if "time" in event:
        ts = event["time"]
        try:
            dt_event = datetime.fromisoformat(ts)
            dt_event_jst = dt_event.astimezone(JST)
            ts_jst = dt_event_jst.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+09:00"
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
# イベント順序
コンテナ停止命令(SIGTERM): kill
jupyter停止命令: received signal 15, stopping
jupyterカーネル停止命令: Shutting down N kernel
セッション状態保存開始: Saving checkpoint started at
セッション状態保存完了: Saving checkpoint finished at
jupyterカーネル停止: Kernel shutdown
コンテナ停止(Docker Engineレベル): stop
コンテナ停止(OSレベル): die
コンテナ起動開始: start
jupyter起動開始: 一番上の行
jupyter起動完了: Jupyter Server x.x.x is running at
カーネル起動開始: Kernel started
セッション状態復元開始: Loading checkpoint started at
セッション状態復元完了: Loading checkpoint finished at
カーネル起動: Connecting to kernelの一番最新のもの

# 例


# ログ
===================== docker compose logs =====================
jupyter-1  | 2025-10-23T21:33:38.591+09:00 [C 2025-10-23 12:33:38.590 ServerApp] received signal 15, stopping
jupyter-1  | 2025-10-23T21:33:38.592+09:00 [I 2025-10-23 12:33:38.592 ServerApp] Shutting down 5 extensions
jupyter-1  | 2025-10-23T21:33:38.592+09:00 [I 2025-10-23 12:33:38.592 ServerApp] Shutting down 1 kernel
jupyter-1  | 2025-10-23T21:33:38.592+09:00 [I 2025-10-23 12:33:38.592 ServerApp] Kernel shutdown: 1b7e6bb7-b98f-4b65-827b-9bb282dd1839
jupyter-1  | 2025-10-23T21:33:40.859+09:00 [I 2025-10-23 12:33:40.859 ServerApp] jupyter_lsp | extension was successfully linked.
jupyter-1  | 2025-10-23T21:33:40.860+09:00 [I 2025-10-23 12:33:40.860 ServerApp] jupyter_server_terminals | extension was successfully linked.
jupyter-1  | 2025-10-23T21:33:40.860+09:00 [W 2025-10-23 12:33:40.860 LabApp] 'token' has moved from NotebookApp to ServerApp. This config will be passed to ServerApp. Be sure to update your config before our next release.
jupyter-1  | 2025-10-23T21:33:40.860+09:00 [W 2025-10-23 12:33:40.860 LabApp] 'password' has moved from NotebookApp to ServerApp. This config will be passed to ServerApp. Be sure to update your config before our next release.
jupyter-1  | 2025-10-23T21:33:40.861+09:00 [W 2025-10-23 12:33:40.861 ServerApp] ServerApp.token config is deprecated in 2.0. Use IdentityProvider.token.
jupyter-1  | 2025-10-23T21:33:40.861+09:00 [I 2025-10-23 12:33:40.861 ServerApp] jupyterlab | extension was successfully linked.
jupyter-1  | 2025-10-23T21:33:40.863+09:00 [I 2025-10-23 12:33:40.863 ServerApp] notebook | extension was successfully linked.
jupyter-1  | 2025-10-23T21:33:41.004+09:00 [I 2025-10-23 12:33:41.003 ServerApp] notebook_shim | extension was successfully linked.
jupyter-1  | 2025-10-23T21:33:41.009+09:00 [W 2025-10-23 12:33:41.009 ServerApp] All authentication is disabled.  Anyone who can connect to this server will be able to run code.
jupyter-1  | 2025-10-23T21:33:41.010+09:00 [I 2025-10-23 12:33:41.010 ServerApp] notebook_shim | extension was successfully loaded.
jupyter-1  | 2025-10-23T21:33:41.011+09:00 [I 2025-10-23 12:33:41.010 ServerApp] jupyter_lsp | extension was successfully loaded.
jupyter-1  | 2025-10-23T21:33:41.011+09:00 [I 2025-10-23 12:33:41.011 ServerApp] jupyter_server_terminals | extension was successfully loaded.
jupyter-1  | 2025-10-23T21:33:41.012+09:00 [I 2025-10-23 12:33:41.012 LabApp] JupyterLab extension loaded from /usr/local/lib/python3.12/site-packages/jupyterlab
jupyter-1  | 2025-10-23T21:33:41.012+09:00 [I 2025-10-23 12:33:41.012 LabApp] JupyterLab application directory is /usr/local/share/jupyter/lab
jupyter-1  | 2025-10-23T21:33:41.012+09:00 [I 2025-10-23 12:33:41.012 LabApp] Extension Manager is 'pypi'.
jupyter-1  | 2025-10-23T21:33:41.026+09:00 [I 2025-10-23 12:33:41.026 ServerApp] jupyterlab | extension was successfully loaded.
jupyter-1  | 2025-10-23T21:33:41.027+09:00 [I 2025-10-23 12:33:41.027 ServerApp] notebook | extension was successfully loaded.
jupyter-1  | 2025-10-23T21:33:41.028+09:00 [I 2025-10-23 12:33:41.027 ServerApp] Serving notebooks from local directory: /app
jupyter-1  | 2025-10-23T21:33:41.028+09:00 [I 2025-10-23 12:33:41.027 ServerApp] Jupyter Server 2.17.0 is running at:
jupyter-1  | 2025-10-23T21:33:41.028+09:00 [I 2025-10-23 12:33:41.028 ServerApp] http://d6a77f37d434:8888/lab
jupyter-1  | 2025-10-23T21:33:41.028+09:00 [I 2025-10-23 12:33:41.028 ServerApp]     http://127.0.0.1:8888/lab
jupyter-1  | 2025-10-23T21:33:41.028+09:00 [I 2025-10-23 12:33:41.028 ServerApp] Use Control-C to stop this server and shut down all kernels (twice to skip confirmation).
jupyter-1  | 2025-10-23T21:33:41.036+09:00 [I 2025-10-23 12:33:41.035 ServerApp] Skipped non-installed server(s): basedpyright, bash-language-server, dockerfile-language-server-nodejs, javascript-typescript-langserver, jedi-language-server, julia-language-server, pyrefly, pyright, python-language-server, python-lsp-server, r-languageserver, sql-language-server, texlab, typescript-language-server, unified-language-server, vscode-css-languageserver-bin, vscode-html-languageserver-bin, vscode-json-languageserver-bin, yaml-language-server
jupyter-1  | 2025-10-23T21:33:44.163+09:00 [W 2025-10-23 12:33:44.162 LabApp] Could not determine jupyterlab build status without nodejs
jupyter-1  | 2025-10-23T21:33:44.417+09:00 [W 2025-10-23 12:33:44.417 ServerApp] Notebook test_restart.ipynb is not trusted
jupyter-1  | 2025-10-23T21:33:44.481+09:00 [I 2025-10-23 12:33:44.481 ServerApp] Kernel started: 726bc61b-b2d4-4640-8b9c-3a7da781d600
jupyter-1  | 2025-10-23T21:33:45.626+09:00 [I 2025-10-23 12:33:45.626 ServerApp] Connecting to kernel 726bc61b-b2d4-4640-8b9c-3a7da781d600.
jupyter-1  | 2025-10-23T21:33:45.627+09:00 [I 2025-10-23 12:33:45.627 ServerApp] Connecting to kernel 726bc61b-b2d4-4640-8b9c-3a7da781d600.
jupyter-1  | 2025-10-23T21:33:45.628+09:00 [W 2025-10-23 12:33:45.628 ServerApp] The websocket_ping_timeout (90000) cannot be longer than the websocket_ping_interval (30000).
jupyter-1  | 2025-10-23T21:33:45.628+09:00     Setting websocket_ping_timeout=30000
jupyter-1  | 2025-10-23T21:33:45.642+09:00 [I 2025-10-23 12:33:45.641 ServerApp] Connecting to kernel 726bc61b-b2d4-4640-8b9c-3a7da781d600.
jupyter-1  | 2025-10-23T21:33:45.669+09:00 [W 2025-10-23 12:33:45.669 ServerApp] Got events for closed stream <zmq.eventloop.zmqstream.ZMQStream object at 0xffff885d5a00>

===================== ElasticKernel.log =====================
2025-10-23T21:33:38.593+09:00 [2025-10-23 21:33:38.593549 ElasticKernelLogger kernel.py:240 INFO] Saving checkpoint started at: 2025-10-23T21:33:38.593527+0900
2025-10-23T21:33:38.623+09:00 [2025-10-23 21:33:38.623327 ElasticKernelLogger kernel.py:264 ERROR] Error saving checkpoint: unsupported operand type(s) for -: 'str' and 'str'
2025-10-23T21:33:38.623+09:00 [2025-10-23 21:33:38.623833 ElasticKernelLogger kernel.py:265 ERROR] Error details:
2025-10-23T21:33:45.514+09:00 [2025-10-23 21:33:45.514644 ElasticKernelLogger kernel.py:56 INFO] ===============================================
2025-10-23T21:33:45.514+09:00 [2025-10-23 21:33:45.514740 ElasticKernelLogger kernel.py:57 INFO] Initializing ElasticKernel (726bc61b-b2d4-4640-8b9c-3a7da781d600)
2025-10-23T21:33:45.514+09:00 [2025-10-23 21:33:45.514819 ElasticKernelLogger kernel.py:61 INFO] ===============================================
2025-10-23T21:33:45.515+09:00 [2025-10-23 21:33:45.515007 ElasticKernelLogger kernel.py:79 INFO] ElasticNotebook successfully loaded.
2025-10-23T21:33:45.515+09:00 [2025-10-23 21:33:45.515098 ElasticKernelLogger kernel.py:85 INFO] Checkpoint file exists. Loading checkpoint.
2025-10-23T21:33:45.515+09:00 [2025-10-23 21:33:45.515154 ElasticKernelLogger kernel.py:89 INFO] Loading checkpoint started at: 2025-10-23T21:33:45.515133+0900
2025-10-23T21:33:45.516+09:00 [2025-10-23 21:33:45.516524 ElasticKernelLogger kernel.py:105 ERROR] Error loading checkpoint: unsupported operand type(s) for -: 'str' and 'str'
2025-10-23T21:33:45.516+09:00 [2025-10-23 21:33:45.516685 ElasticKernelLogger kernel.py:106 ERROR] Error details:

===================== docker compose events =====================
2025-10-23T21:33:38.591+09:00 [jupyter] kill {'desktop.docker.io/binds/0/Source': '/Users/matsumotoryutaro/programs/ElasticKernel/.workspace', 'desktop.docker.io/binds/0/SourceKind': 'hostFile', 'desktop.docker.io/binds/0/Target': '/app', 'desktop.docker.io/ports.scheme': 'v2', 'desktop.docker.io/ports/8888/tcp': ':8888', 'image': 'elastickernel-jupyter', 'name': 'elastickernel-jupyter-1', 'signal': '15'}
2025-10-23T21:33:39.858+09:00 [jupyter] stop {'desktop.docker.io/binds/0/Source': '/Users/matsumotoryutaro/programs/ElasticKernel/.workspace', 'desktop.docker.io/binds/0/SourceKind': 'hostFile', 'desktop.docker.io/binds/0/Target': '/app', 'desktop.docker.io/ports.scheme': 'v2', 'desktop.docker.io/ports/8888/tcp': ':8888', 'image': 'elastickernel-jupyter', 'name': 'elastickernel-jupyter-1'}
2025-10-23T21:33:39.862+09:00 [jupyter] die {'desktop.docker.io/binds/0/Source': '/Users/matsumotoryutaro/programs/ElasticKernel/.workspace', 'desktop.docker.io/binds/0/SourceKind': 'hostFile', 'desktop.docker.io/binds/0/Target': '/app', 'desktop.docker.io/ports.scheme': 'v2', 'desktop.docker.io/ports/8888/tcp': ':8888', 'execDuration': '20', 'exitCode': '0', 'image': 'elastickernel-jupyter', 'name': 'elastickernel-jupyter-1'}
2025-10-23T21:33:40.060+09:00 [jupyter] start {'desktop.docker.io/binds/0/Source': '/Users/matsumotoryutaro/programs/ElasticKernel/.workspace', 'desktop.docker.io/binds/0/SourceKind': 'hostFile', 'desktop.docker.io/binds/0/Target': '/app', 'desktop.docker.io/ports.scheme': 'v2', 'desktop.docker.io/ports/8888/tcp': ':8888', 'image': 'elastickernel-jupyter', 'name': 'elastickernel-jupyter-1'}
"""
