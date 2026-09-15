"""Exercise Modal sandbox filesystem snapshots and time each step.

Modal sandboxes run under gVisor: the app talks to a userspace kernel
(the sentry), which uses the host kernel for time, net, and files.
`time.monotonic()` inside the sandbox is the sentry's clock, usually
backed by the host — so it is a bad freeze detector. This script pings
an in-sandbox HTTP server from the client during snapshot; those gaps
are laptop time, and a reply only happens if the sentry ran the app.

This run measures how the snapshot freeze scales with FILE COUNT, the
axis the 20 GiB run never charged. Modal's fs stall scales with data
(~0.25s/GiB, measured); a tree-serialization term should add a per-file
cost. Two snapshots: A at 1 GiB in one file, B after adding 100,000
tiny files (+25 MB data, +100k inodes). B's stall minus A's stall,
minus the ~6ms the data slope predicts, is the per-file freeze cost.
Probes: HTTP pings (scheduler), disk heartbeat (fs freeze, windowed),
deadline-based CPU probe (no fs ops until dump), causal ping-pong
writer during B (consistency cut). Restore from B verifies the 100k
files and times the restored metadata walk (lazy-load behavior for
small files) plus first-touch read of the 1 GiB.

Run from this directory:

    modal run modal_sandboxes.py
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from time import perf_counter

import modal

app = modal.App("sandbox-snapshot-bench")

PYTHON_IMAGE = "python:3.12-slim"
STATE_DIR = "/tmp/sandbox-state"
MARKER_BEFORE = f"{STATE_DIR}/before-snapshot.txt"
MARKER_AFTER = f"{STATE_DIR}/after-snapshot.txt"
SCRIPT_PATH = f"{STATE_DIR}/hello.py"
HEARTBEAT_PATH = f"{STATE_DIR}/heartbeat.py"
HEARTBEAT_LOG = f"{STATE_DIR}/heartbeat.jsonl"
HEARTBEAT_STOP = f"{STATE_DIR}/heartbeat.stop"
HTTP_SERVER_PATH = f"{STATE_DIR}/http_probe.py"
CPU_PROBE_PATH = f"{STATE_DIR}/cpu_probe.py"
CPU_PROBE_LOG = f"{STATE_DIR}/cpu_probe.json"
CPU_PROBE_STOP = f"{STATE_DIR}/cpu_probe.stop"
CAUSAL_PATH = f"{STATE_DIR}/causal_writer.py"
CAUSAL_A = f"{STATE_DIR}/causal-a.log"
CAUSAL_B = f"{STATE_DIR}/causal-b.log"
CAUSAL_STOP = f"{STATE_DIR}/causal.stop"
READ_TEST_PATH = f"{STATE_DIR}/read_test.py"
HEARTBEAT_INTERVAL_S = 0.02
PING_PORT = 8765
PING_INTERVAL_S = 0.02
PING_TIMEOUT_S = 2.0
RECORD_LEN = 128
PER_FILE_BYTES = 1 << 30
MANY_FILES_DIRS = 100
MANY_FILES_PER_DIR = 1000  # 100 dirs x 1000 files = 100,000 files
MANY_FILES_SIZE = 256
SNAPSHOT_TIMEOUT_S = 60 * 60
SANDBOX_TIMEOUT_S = 2 * 60 * 60
WRITE_TIMEOUT_S = 30 * 60

# Disk heartbeat: sleep, then write+flush. Blocks on a filesystem freeze
# even if the sentry is still running other processes.
HEARTBEAT_SCRIPT = f"""
import json, os, time

log = {HEARTBEAT_LOG!r}
stop = {HEARTBEAT_STOP!r}
interval = {HEARTBEAT_INTERVAL_S}

last_mono = time.monotonic()
last_wall = time.time()
with open(log, "w") as f:
    while not os.path.exists(stop):
        time.sleep(interval)
        now_mono = time.monotonic()
        now_wall = time.time()
        f.write(json.dumps({{
            "wall": now_wall,
            "gap_mono": now_mono - last_mono,
        }}) + "\\n")
        f.flush()
        last_mono, last_wall = now_mono, now_wall
"""

# CPU probe: identical sleep-loop cadence but touches NO files until told
# to stop, so it measures pure scheduler stalls; a filesystem freeze is
# invisible to it. The gap log is dumped only after the stop file appears.
CPU_PROBE_SCRIPT = f"""
import json, sys, time

out = {CPU_PROBE_LOG!r}
deadline = time.monotonic() + float(sys.argv[1])

gaps = []
max_gap = 0.0
last = time.monotonic()
while time.monotonic() < deadline:
    time.sleep(0.002)
    now = time.monotonic()
    gap = now - last
    last = now
    if gap > max_gap:
        max_gap = gap
    if gap > 0.05:
        gaps.append([time.time(), round(gap, 4)])
with open(out, "w") as f:
    json.dump({{"max_gap": max_gap, "gaps": gaps[-100:]}}, f)
"""

# HTTP probe: no disk on the request path. A client ping succeeding means
# gVisor scheduled this process and it wrote a response.
HTTP_SERVER_SCRIPT = f"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import time

class Probe(BaseHTTPRequestHandler):
    seq = 0

    def do_GET(self):
        Probe.seq += 1
        body = f"{{Probe.seq}} {{time.monotonic():.6f}}".encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return

HTTPServer(("0.0.0.0", {PING_PORT}), Probe).serve_forever()
"""

# Causal ping-pong writer: A[n] is fully written and fsynced strictly
# before B[n]. Fixed-width checksummed records make torn writes and the
# capture's cut point recoverable from the restored logs.
CAUSAL_WRITER_SCRIPT = f"""
import hashlib, os, time

a_path = {CAUSAL_A!r}
b_path = {CAUSAL_B!r}
stop = {CAUSAL_STOP!r}
record_len = {RECORD_LEN}


def record(seq):
    body = f"{{seq:09d}} {{time.time():.6f}} {{time.monotonic():.6f}}"
    digest = hashlib.sha256(body.encode()).hexdigest()[:8]
    return f"{{body}} {{digest}}".ljust(record_len - 1, "x") + "\\n"


seq = 0
with open(a_path, "w") as fa, open(b_path, "w") as fb:
    while not os.path.exists(stop):
        fa.write(record(seq))
        fa.flush()
        os.fsync(fa.fileno())
        fb.write(record(seq))
        fb.flush()
        os.fsync(fb.fileno())
        seq += 1
        time.sleep(0.005)
"""

# Generate the payload inside the sandbox. Pulling it through the client
# filesystem API would measure upload, not guest writes. urandom so the
# snapshot cannot collapse the payload as sparse zeros or a repeated block.
WRITE_CHANGES_SCRIPT = f"""
import os, sys, time

root = {STATE_DIR!r}
first = int(sys.argv[1])
count = int(sys.argv[2])
per_file = {PER_FILE_BYTES}
chunk = 4 << 20

os.makedirs(root, exist_ok=True)
start = time.monotonic()
for i in range(first, first + count):
    path = os.path.join(root, f"change-{{i:02d}}.bin")
    remaining = per_file
    with open(path, "wb") as f:
        while remaining:
            buf = os.urandom(min(chunk, remaining))
            f.write(buf)
            remaining -= len(buf)
        f.flush()
        os.fsync(f.fileno())
elapsed = time.monotonic() - start
total = per_file * count
print(f"wrote {{total}} in {{elapsed:.2f}}s guest-side "
      f"({{total / elapsed / 1048576:.0f}} MiB/s)")
"""

MANY_FILES_SCRIPT = f"""
import os, time

root = {STATE_DIR!r} + "/manyfiles"
t0 = time.monotonic()
for d in range({MANY_FILES_DIRS}):
    sub = os.path.join(root, f"d{{d:03d}}")
    os.makedirs(sub, exist_ok=True)
    for i in range({MANY_FILES_PER_DIR}):
        with open(os.path.join(sub, f"f{{i:04d}}"), "wb") as f:
            f.write(os.urandom({MANY_FILES_SIZE}))
total = {MANY_FILES_DIRS} * {MANY_FILES_PER_DIR}
print(f"wrote {{total}} files in {{time.monotonic()-t0:.1f}}s")
"""

# First-touch vs cached read of one restored file, timed on the guest
# clock so client transfer speed is not in the measurement.
READ_TEST_SCRIPT = """
import sys, time

path = sys.argv[1]
t0 = time.monotonic()
n = 0
with open(path, "rb", buffering=0) as f:
    while True:
        buf = f.read(4 << 20)
        if not buf:
            break
        n += len(buf)
elapsed = time.monotonic() - t0
print(f"{n} bytes in {elapsed:.3f}s = {n / elapsed / 1048576:.1f} MiB/s")
"""


class Stopwatch:
    def __init__(self) -> None:
        self.timings: list[tuple[str, float]] = []

    @contextmanager
    def measure(self, name: str):
        print(f"\n→ {name}")
        start = perf_counter()
        try:
            yield
        finally:
            elapsed = perf_counter() - start
            self.timings.append((name, elapsed))
            print(f"  done in {elapsed:.3f}s")

    def named(self, name: str) -> float:
        for timing_name, elapsed in self.timings:
            if timing_name == name:
                return elapsed
        raise KeyError(name)

    def report(self) -> None:
        width = max(len(name) for name, _ in self.timings)
        total = sum(elapsed for _, elapsed in self.timings)
        print("\nTiming summary")
        print("-" * (width + 14))
        for name, elapsed in self.timings:
            print(f"{name:<{width}}  {elapsed:8.3f}s")
        print("-" * (width + 14))
        print(f"{'total':<{width}}  {total:8.3f}s")


def run(sb: modal.Sandbox, *cmd: str, timeout: int = 60) -> str:
    process = sb.exec(*cmd, timeout=timeout)
    stdout = process.stdout.read()
    stderr = process.stderr.read()
    process.wait()
    if process.returncode != 0:
        raise RuntimeError(f"{cmd!r} exited {process.returncode}\n{stderr}")
    return stdout


def ping_once(url: str, timeout: float = PING_TIMEOUT_S) -> None:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        response.read()


def wait_until_http(url: str, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            ping_once(url)
            return
        except Exception as exc:
            last_err = exc
            time.sleep(0.05)
    raise RuntimeError(f"http probe never became ready: {last_err}")


def run_pings(
    url: str, stop: threading.Event, rows: list[tuple[float, float, bool]]
) -> None:
    while not stop.is_set():
        t0 = perf_counter()
        try:
            ping_once(url)
            rows.append((t0, perf_counter() - t0, True))
        except (urllib.error.URLError, TimeoutError, OSError):
            rows.append((t0, perf_counter() - t0, False))
        leftover = PING_INTERVAL_S - (perf_counter() - t0)
        if leftover > 0:
            stop.wait(leftover)


def max_success_gap(rows: list[tuple[float, float, bool]]) -> float:
    times = [t for t, _, ok in rows if ok]
    if len(times) < 2:
        return 0.0
    return max(b - a for a, b in zip(times, times[1:]))


def report_ping_window(
    rows: list[tuple[float, float, bool]],
    name: str,
    start: float,
    end: float,
    idle_gap: float,
) -> None:
    during = [row for row in rows if start <= row[0] <= end]
    misses = sum(1 for _, _, ok in during if not ok)
    print(
        f"  HTTP during {name}: max gap {max_success_gap(during)*1000:.1f}ms "
        f"(idle {idle_gap*1000:.1f}ms), {misses} misses / {len(during)} pings"
    )


def parse_causal_log(raw: str) -> dict:
    lines = raw.split("\n")
    intact: list[tuple[int, float]] = []
    torn_mid = 0
    last_index = len(lines) - 1
    while last_index >= 0 and not lines[last_index]:
        last_index -= 1
    for index, line in enumerate(lines):
        if not line:
            continue
        parts = line.rstrip("x").split()
        ok = len(line) == RECORD_LEN - 1 and len(parts) == 4
        if ok:
            body = " ".join(parts[:3])
            ok = hashlib.sha256(body.encode()).hexdigest()[:8] == parts[3]
        if ok:
            intact.append((int(parts[0]), float(parts[1])))
        elif index < last_index:
            torn_mid += 1
    return {
        "max_seq": max((seq for seq, _ in intact), default=-1),
        "last_wall": max((wall for _, wall in intact), default=0.0),
        "torn_mid": torn_mid,
        "tail_torn": bool(lines[last_index]) and last_index >= 0 and (
            len(lines[last_index]) != RECORD_LEN - 1
        ),
        "records": len(intact),
    }


def cut_verdict(
    a: dict, b: dict, window_start_wall: float, window_end_wall: float
) -> None:
    span = max(window_end_wall - window_start_wall, 1e-9)
    pos_a = (a["last_wall"] - window_start_wall) / span
    pos_b = (b["last_wall"] - window_start_wall) / span
    print(
        f"  causal writer captured: A max seq {a['max_seq']} "
        f"(cut at {pos_a:+.0%} of snapshot window), "
        f"B max seq {b['max_seq']} (cut at {pos_b:+.0%})"
    )
    print(
        f"  torn mid-file records: A={a['torn_mid']} B={b['torn_mid']}; "
        f"torn tails: A={a['tail_torn']} B={b['tail_torn']}"
    )
    if b["max_seq"] > a["max_seq"]:
        print(
            "  VERDICT: causality violated (B ahead of A) — live per-file "
            "scan, no point-in-time guarantee"
        )
    elif a["torn_mid"] or b["torn_mid"]:
        print(
            "  VERDICT: mid-file torn records — live copy without file "
            "atomicity"
        )
    elif abs(pos_a - pos_b) > 0.2:
        print(
            "  VERDICT: files cut at different instants — per-file live "
            "walk, even though sequences stayed lucky"
        )
    elif pos_a < 0.25:
        print(
            "  VERDICT: consistent cut near window START — COW-style "
            "freeze-then-stream"
        )
    elif pos_a > 0.75:
        print(
            "  VERDICT: consistent cut near window END — pre-copy style "
            "(stream live, freeze for final delta)"
        )
    else:
        print(
            "  VERDICT: consistent cut mid-window — single freeze at an "
            "interior instant (clock skew caveat applies)"
        )


def heartbeat_samples(raw: str) -> list[dict]:
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def heartbeat_gap_in_window(
    samples: list[dict], start_wall: float, end_wall: float, slack: float = 2.0
) -> float:
    inside = [
        s["gap_mono"]
        for s in samples
        if start_wall - slack <= s["wall"] <= end_wall + slack
    ]
    return max(inside, default=0.0)


def terminate(sb: modal.Sandbox | None) -> None:
    if sb is None:
        return
    try:
        sb.terminate()
    except Exception as exc:
        print(f"  warning: failed to terminate {sb.object_id}: {exc}")


@app.local_entrypoint()
def main() -> None:
    clock = Stopwatch()
    image = modal.Image.from_registry(PYTHON_IMAGE)
    sb1: modal.Sandbox | None = None
    sb2: modal.Sandbox | None = None
    total_files = MANY_FILES_DIRS * MANY_FILES_PER_DIR

    with modal.enable_output():
        with clock.measure("create sandbox + ready"):
            sb1 = modal.Sandbox.create(
                app=app,
                image=image,
                timeout=SANDBOX_TIMEOUT_S,
                encrypted_ports=[PING_PORT],
                readiness_probe=modal.Probe.with_exec("true"),
            )
            sb1.wait_until_ready()
        print(f"  sandbox 1 id: {sb1.object_id}")

        with clock.measure("stage scripts + write 1 GiB single file"):
            sb1.filesystem.make_directory(STATE_DIR)
            sb1.filesystem.write_text(
                "this file should survive the snapshot\n", MARKER_BEFORE
            )
            for path, script in (
                (f"{STATE_DIR}/write_changes.py", WRITE_CHANGES_SCRIPT),
                (f"{STATE_DIR}/many_files.py", MANY_FILES_SCRIPT),
                (HTTP_SERVER_PATH, HTTP_SERVER_SCRIPT),
                (HEARTBEAT_PATH, HEARTBEAT_SCRIPT),
                (CPU_PROBE_PATH, CPU_PROBE_SCRIPT),
                (CAUSAL_PATH, CAUSAL_WRITER_SCRIPT),
                (READ_TEST_PATH, READ_TEST_SCRIPT),
            ):
                sb1.filesystem.write_text(script, path)
            print(
                run(
                    sb1,
                    "python",
                    f"{STATE_DIR}/write_changes.py",
                    "0",
                    "1",
                    timeout=WRITE_TIMEOUT_S,
                ).rstrip()
            )

        cpu_probe_duration = 240.0
        run(
            sb1,
            "bash",
            "-c",
            f"python {HTTP_SERVER_PATH} >/dev/null 2>&1 & "
            f"python {HEARTBEAT_PATH} >/dev/null 2>&1 & "
            f"python {CPU_PROBE_PATH} {cpu_probe_duration} >/dev/null 2>&1 & echo ok",
        )
        probe_url = sb1.tunnels()[PING_PORT].url
        print(f"  http probe: {probe_url}")
        wait_until_http(probe_url)
        probes_started = time.time()

        ping_rows: list[tuple[float, float, bool]] = []
        stop_pings = threading.Event()
        ping_thread = threading.Thread(
            target=run_pings, args=(probe_url, stop_pings, ping_rows), daemon=True
        )
        ping_thread.start()
        time.sleep(1.0)

        windows: dict[str, tuple[float, float, float, float]] = {}

        def snapshot(name: str) -> modal.Image:
            with clock.measure(name):
                start, start_wall = perf_counter(), time.time()
                snap = sb1.snapshot_filesystem(timeout=SNAPSHOT_TIMEOUT_S)
                end, end_wall = perf_counter(), time.time()
            windows[name] = (start, end, start_wall, end_wall)
            print(f"  image id: {snap.object_id}")
            return snap

        name_a = "snapshot A: 1 GiB, 1 file"
        name_b = f"snapshot B: 1 GiB + {total_files} files"

        snapshot(name_a)

        with clock.measure(f"write {total_files} small files"):
            print("  " + run(
                sb1,
                "python",
                f"{STATE_DIR}/many_files.py",
                timeout=WRITE_TIMEOUT_S,
            ).strip())

        with clock.measure("md5 baseline"):
            baseline_md5 = run(
                sb1, "md5sum", f"{STATE_DIR}/change-00.bin", timeout=300
            ).split()[0]
            print(f"  change-00: {baseline_md5}")

        run(sb1, "bash", "-c", f"python {CAUSAL_PATH} >/dev/null 2>&1 & echo ok")
        time.sleep(1.0)

        snap_b = snapshot(name_b)

        sb1.filesystem.write_text("", CAUSAL_STOP)
        time.sleep(0.3)
        raw_a = sb1.filesystem.read_text(CAUSAL_A)
        walls = [
            float(line.rstrip("x").split()[1])
            for line in raw_a.splitlines()
            if len(line.rstrip("x").split()) == 4
        ]
        writer_stall = max(
            (b - a for a, b in zip(walls, walls[1:])), default=0.0
        )
        print(
            f"  causal writer: {len(walls)} records, "
            f"max inter-record gap {writer_stall:.2f}s"
        )

        stop_pings.set()
        ping_thread.join(timeout=5.0)
        sb1.filesystem.write_text("", HEARTBEAT_STOP)
        time.sleep(0.5)

        idle_gap = max_success_gap(
            [r for r in ping_rows if r[0] < windows[name_a][0]]
        )
        for name, (start, end, _, _) in windows.items():
            report_ping_window(ping_rows, name, start, end, idle_gap)

        samples = heartbeat_samples(sb1.filesystem.read_text(HEARTBEAT_LOG))
        stall = {}
        for name, (_, _, w0, w1) in windows.items():
            stall[name] = heartbeat_gap_in_window(samples, w0, w1)
            print(f"  fs stall during {name}: {stall[name]*1000:.1f}ms")

        cpu_deadline = probes_started + cpu_probe_duration + 15
        cpu_report = "cpu probe: no data"
        while time.time() < cpu_deadline:
            try:
                cpu = json.loads(sb1.filesystem.read_text(CPU_PROBE_LOG))
                cpu_report = (
                    f"cpu probe (no fs ops): max scheduler gap "
                    f"{cpu['max_gap']*1000:.1f}ms, "
                    f"{len(cpu['gaps'])} gaps > 50ms at "
                    + ", ".join(f"{w:.2f}" for w, _ in cpu["gaps"][:5])
                )
                break
            except Exception:
                time.sleep(5.0)
        print(f"  {cpu_report}")
        print("  snapshot windows (wall): " + "; ".join(
            f"{n}: {w0:.2f}..{w1:.2f}" for n, (_, _, w0, w1) in windows.items()
        ))

        sb1.filesystem.write_text(
            "this file was written after the snapshot\n", MARKER_AFTER
        )

        with clock.measure("create sandbox 2 from snapshot B + ready"):
            sb2 = modal.Sandbox.create(
                app=app,
                image=snap_b,
                timeout=SANDBOX_TIMEOUT_S,
                readiness_probe=modal.Probe.with_exec("true"),
            )
            sb2.wait_until_ready()
        print(f"  sandbox 2 id: {sb2.object_id}")

        with clock.measure("restored metadata walk (find 100k files, guest)"):
            count = run(
                sb2,
                "bash",
                "-c",
                f"cd {STATE_DIR}/manyfiles && find . -type f | wc -l",
                timeout=1800,
            ).strip()
            print(f"  files found: {count}")
        with clock.measure("restored metadata walk again (cached)"):
            run(
                sb2,
                "bash",
                "-c",
                f"cd {STATE_DIR}/manyfiles && find . -type f | wc -l",
                timeout=1800,
            )
        with clock.measure("first-touch read of restored 1 GiB (guest clock)"):
            print("  " + run(
                sb2,
                "python",
                READ_TEST_PATH,
                f"{STATE_DIR}/change-00.bin",
                timeout=1800,
            ).strip())

        with clock.measure("verify restored filesystem"):
            restored_md5 = run(
                sb2, "md5sum", f"{STATE_DIR}/change-00.bin", timeout=1800
            ).split()[0]
            after_missing = run(
                sb2,
                "python",
                "-c",
                f"import os; print(os.path.exists('{MARKER_AFTER}'))",
            ).strip()
            print(f"  md5 match: {restored_md5 == baseline_md5}, "
                  f"after-file leaked: {after_missing}")
            captured_a = parse_causal_log(sb2.filesystem.read_text(CAUSAL_A))
            captured_b = parse_causal_log(sb2.filesystem.read_text(CAUSAL_B))
            _, _, w0, w1 = windows[name_b]
            cut_verdict(captured_a, captured_b, w0, w1)
            if restored_md5 != baseline_md5:
                raise RuntimeError("restored payload md5 mismatch")
            if int(count) != total_files:
                raise RuntimeError(f"restored {count} files, expected {total_files}")
            if after_missing != "False":
                raise RuntimeError("post-snapshot file leaked into the restore")

    clock.report()

    a, b = stall[name_a], stall[name_b]
    extra_data_s = (MANY_FILES_DIRS * MANY_FILES_PER_DIR * MANY_FILES_SIZE) / (1 << 30) / 4.0
    print("\nDerived numbers")
    print(f"  fs stall A (1 GiB, 1 file):        {a*1000:.1f}ms")
    print(f"  fs stall B (1 GiB + {total_files} files): {b*1000:.1f}ms")
    print(f"  data-slope prediction for B - A:   ~{extra_data_s*1000:.0f}ms "
          f"(25 MB extra at the measured ~0.25s/GiB)")
    if b > a:
        print(f"  implied per-file freeze cost:      {(b-a)/total_files*1e6:.1f}us/file")
    print(f"  snapshot wall time A vs B: {clock.named(name_a):.1f}s vs {clock.named(name_b):.1f}s")

    terminate(sb1)
    terminate(sb2)
