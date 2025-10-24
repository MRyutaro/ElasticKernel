import re
import json
import subprocess
import threading
from datetime import datetime, timedelta, timezone

# ===================== 設定 =====================
log_file_path = "./.workspace/.elastic_kernel/7902699be42c8a8e/ElasticKernel.log"
JST = timezone(timedelta(hours=9))

# JSTの基準時刻
restart_start_time = datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+09:00"

# ===================== 収集用（あとで要約を出す） =====================
events_output = []
all_lines_docker = []     # docker compose logs（JST化後）をフルで保持
all_lines_file = []       # アプリログ（ファイル）をフルで保持
all_lines_events = []     # docker compose events をフルで保持（JST化後）
timeline = []             # (timestamp, message) を全部突っ込む
event_times = {}          # {イベント名: timestamp} 後段の“時刻, イベント”用

# イベント名の抽出規則（あなたの要件に合わせて）
# なるべくログの文字列で正確に判定する
PATTERNS = [
    ("コンテナ停止命令(SIGTERM): kill", re.compile(r"\[.*?\]\s*kill\b.*?(?:'signal':\s*'15'|signal=15)?")),
    ("jupyter停止命令", re.compile(r"received signal 15, stopping", re.IGNORECASE)),
    ("jupyterカーネル停止命令", re.compile(r"Shutting down \d+ kernel")),
    ("セッション状態保存開始", re.compile(r"Saving checkpoint started|Saving checkpoint started at", re.IGNORECASE)),
    ("セッション状態保存完了", re.compile(r"Saving checkpoint finished(?: at)?:?", re.IGNORECASE)),
    ("jupyterカーネル停止", re.compile(r"Kernel shutdown", re.IGNORECASE)),
    ("コンテナ停止(Docker Engineレベル): stop", re.compile(r"\[.*?\]\s*stop\b")),
    ("コンテナ停止(OSレベル): die", re.compile(r"\[.*?\]\s*die\b")),
    ("コンテナ起動開始: start", re.compile(r"\[.*?\]\s*start\b")),
    ("jupyter起動開始", re.compile(r"jupyter_lsp | extension was successfully linked.", re.IGNORECASE)),
    ("jupyter起動完了", re.compile(r"Jupyter Server .* is running at", re.IGNORECASE)),
    ("カーネル起動開始", re.compile(r"Kernel started", re.IGNORECASE)),
    ("セッション状態復元開始", re.compile(r"Loading checkpoint started(?: at)?:?", re.IGNORECASE)),
    ("セッション状態復元完了", re.compile(r"Loading checkpoint finished(?: at)?:?", re.IGNORECASE)),
    # カーネル接続は「最後の1件」をあとで選ぶので別処理
]

# ===================== ユーティリティ =====================
def iso_jst(dt: datetime) -> str:
    return dt.astimezone(JST).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+09:00"

def parse_any_timestamp_to_jst(ts: str) -> str:
    """ISO8601のZ/+09:00, 'YYYY-mm-dd HH:MM:SS.ssssss' のどれでも受け入れてJST ISOへ"""
    ts = ts.strip()
    # 1) すでに +09:00 などのISOの場合
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return iso_jst(dt)
    except Exception:
        pass
    # 2) 角括弧付き [YYYY-mm-dd HH:MM:SS.ffffff ...] を想定
    try:
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=JST)
        return iso_jst(dt)
    except Exception:
        pass
    return ""  # 取れなければ空文字

def try_extract_ts_from_docker_line(line: str) -> str:
    # 例: jupyter-1  | 2025-10-23T21:33:41.028+09:00 ...
    m = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+\+\d{2}:\d{2}", line)
    return m.group(0) if m else ""

def try_extract_ts_from_file_line(line: str) -> str:
    # 例: [2025-10-23 21:33:38.593549 ElasticKernelLogger ...]
    m = re.search(r"\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{6})\s", line)
    if m:
        return parse_any_timestamp_to_jst(m.group(1))
    return ""

def record_event_time(ev_name: str, ts: str):
    # 最初に出た時刻を採用（“最後の Connecting to kernel”だけ後で上書き）
    if ts and ts >= restart_start_time and ev_name not in event_times:
        event_times[ev_name] = ts

# ===================== イベント（compose events）取得 =====================
def capture_events():
    proc = subprocess.Popen(
        ["docker", "compose", "events", "--json", "--since", restart_start_time],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            events_output.append(event)
        except json.JSONDecodeError:
            events_output.append({"raw": line})

events_thread = threading.Thread(target=capture_events, daemon=True)
events_thread.start()

# ===================== コンテナ停止・起動 =====================
subprocess.run(["docker", "compose", "stop"])
print("=" * 50)
print(restart_start_time)
print("=" * 50)
subprocess.run([
    "docker", "compose",
    "-f", "docker-compose.yml",
    "-f", "docker-compose.exp.yml",
    "up", "-d",
])

input("セル1を実行できたらEnterキーを押してください: ")

# ===================== docker compose logs（フル出力） =====================
raw_logs = subprocess.run(
    ["docker", "compose", "logs", "--timestamps"], capture_output=True, text=True
).stdout.splitlines()

# ===================== docker compose events =====================
for ev in events_output:
    if "time" in ev:  # JSON
        ts_raw = ev["time"]
        try:
            dt = datetime.fromisoformat(ts_raw)
            ts = iso_jst(dt)
        except Exception:
            ts = ts_raw  # そのまま
        service = ev.get("service", "unknown")
        action = ev.get("action", "unknown")
        msg = f"{ts} [{service}] {action}"

        if ts and ts >= restart_start_time:
            all_lines_events.append(msg)
            timeline.append((ts, msg))

            # kill/stop/die/start を拾う
            for ev_name, pat in PATTERNS:
                if pat.search(f"[{service}] {action}"):
                    record_event_time(ev_name, ts)
    else:
        raw = ev.get("raw", "")
        ts = try_extract_ts_from_docker_line(raw) or parse_any_timestamp_to_jst(raw)
        if ts and ts >= restart_start_time:
            all_lines_events.append(raw)
            timeline.append((ts, raw))

# ===================== docker compose logs =====================
connecting_to_kernel_ts_list = []  # 最後の1件を採るために保存
for line in raw_logs:
    ts = try_extract_ts_from_docker_line(line)
    if not ts:
        # UTC(Z)のケースにも対応
        m_utc = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z", line)
        if m_utc:
            ts = parse_any_timestamp_to_jst(m_utc.group(0))
    if ts and ts >= restart_start_time:
        all_lines_docker.append(line)
        timeline.append((ts, line))

        # イベント名を判定
        for ev_name, pat in PATTERNS:
            if pat.search(line):
                record_event_time(ev_name, ts)

        # Connecting to kernel（最後のやつ）専用
        if re.search(r"Connecting to kernel", line, re.IGNORECASE):
            connecting_to_kernel_ts_list.append(ts)

# ===================== ElasticKernel.log =====================
try:
    with open(log_file_path, "r") as f:
        for line in f:
            ts = try_extract_ts_from_file_line(line)
            if ts and ts >= restart_start_time:
                all_lines_file.append(line.rstrip("\n"))
                timeline.append((ts, line.rstrip("\n")))

                # イベント名を判定（保存/復元など）
                for ev_name, pat in PATTERNS:
                    if pat.search(line):
                        record_event_time(ev_name, ts)
except FileNotFoundError:
    print(f"[WARN] ログファイルが見つかりません: {log_file_path}")

# ===================== “最後の Connecting to kernel” を設定 =====================
if connecting_to_kernel_ts_list:
    last_ctk = max(connecting_to_kernel_ts_list)
    event_times["カーネル起動"] = last_ctk  # 「カーネル起動: Connecting to kernelの一番最新のもの」

# ===================== まとめ（時刻, イベント） =====================
# 表示順の定義（好きな順に並べてOK）
summary_order = [
    "コンテナ停止命令(SIGTERM): kill",
    "jupyter停止命令",
    "jupyterカーネル停止命令",
    "セッション状態保存開始",
    "セッション状態保存完了",
    "jupyterカーネル停止",
    "コンテナ停止(Docker Engineレベル): stop",
    "コンテナ停止(OSレベル): die",
    "コンテナ起動開始: start",
    "jupyter起動開始",
    "jupyter起動完了",
    "カーネル起動開始",
    "セッション状態復元開始",
    "セッション状態復元完了",
    "カーネル起動",
]

# 参考：全部の行を時刻順に俯瞰したい場合（必要なら）
timeline.sort(key=lambda x: x[0])
print("\n===================== FULL TIMELINE (時刻, 行) =====================")
for ts, line in timeline:
    print(f"{ts}, {line}")

print("\n===================== TIMELINE (時刻, イベント) =====================")
# 取得できたものだけ時刻順に出す
pairs = []
for name, ts in event_times.items():
    pairs.append((ts, name))
pairs.sort(key=lambda x: x[0])
for ts, name in pairs:
    print(f"{ts}, {name}")
