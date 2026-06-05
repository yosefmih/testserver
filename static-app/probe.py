#!/usr/bin/env python3
"""
Uptime + 404 probe for static-app.

What it does on each tick (default 1s):
  - GET /healthz                       - liveness
  - GET /                              - detect new deploys (chunk hashes change in index.html)
  - GET /assets/<pinned-main-hash>.js  - the hashes captured at T0,
  - GET /assets/<pinned-vendor-hash>.js  simulating a browser tab that
                                       loaded the page before any deploys

The pinned hashes start as 200 from every pod. When a new deploy ships and the
old image is gone, those pinned hashes start returning 404 — that is the white
screen mechanism. Healthz and / are tracked separately so we can see if the
service itself is up during rollouts.

Each line of output is TSV: ts  endpoint  status  latency_ms
On SIGINT/SIGTERM, prints a per-(endpoint,status) summary.

Usage:
  ./probe.py
  ./probe.py --base https://web-2-db804f74-i22f5o97.withporter.run --interval 0.5
  ./probe.py 2>&1 | tee probe.log
"""
import argparse
import re
import signal
import sys
import time
from collections import Counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE = 'https://web-2-db804f74-i22f5o97.withporter.run'
HASH_RE = re.compile(r'/assets/((?:main|vendor)-[a-f0-9]+\.js)')


def fetch(url, timeout=5):
    t0 = time.monotonic()
    try:
        req = Request(url, headers={'User-Agent': 'static-app-probe/1.0'})
        with urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, body, (time.monotonic() - t0) * 1000
    except HTTPError as e:
        return e.code, b'', (time.monotonic() - t0) * 1000
    except URLError as e:
        return 'NET-ERR', repr(e).encode(), (time.monotonic() - t0) * 1000
    except Exception as e:
        return 'EXC', repr(e).encode(), (time.monotonic() - t0) * 1000


def parse_hashes(html_bytes):
    return set(HASH_RE.findall(html_bytes.decode('utf-8', errors='replace')))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=DEFAULT_BASE)
    ap.add_argument('--interval', type=float, default=1.0)
    ap.add_argument('--timeout', type=float, default=5.0)
    args = ap.parse_args()
    base = args.base.rstrip('/')

    print(f'[probe] base={base} interval={args.interval}s timeout={args.timeout}s', file=sys.stderr)

    # Capture pinned hashes at startup.
    for attempt in range(5):
        status, body, _ = fetch(base + '/', timeout=args.timeout)
        if status == 200:
            break
        print(f'[probe] startup GET / -> {status}, retry {attempt+1}/5', file=sys.stderr)
        time.sleep(1)
    else:
        print('[probe] could not reach the app, abort', file=sys.stderr)
        sys.exit(1)

    pinned = parse_hashes(body)
    if not pinned:
        print('[probe] no main/vendor hashes found in /, abort', file=sys.stderr)
        sys.exit(1)
    current = set(pinned)
    print(f'[probe] pinned (T0) hashes: {sorted(pinned)}', file=sys.stderr)

    counts = Counter()
    deploys_seen = 0
    started = time.monotonic()

    def summary(*_):
        elapsed = time.monotonic() - started
        total = sum(counts.values())
        non_ok = sum(c for (e, s), c in counts.items() if s != 200)
        print(f'\n[probe] ==== SUMMARY ====', file=sys.stderr)
        print(f'[probe] elapsed={elapsed:.1f}s requests={total} non_200={non_ok} deploys_seen={deploys_seen}', file=sys.stderr)
        for (endpoint, status), c in sorted(counts.items(), key=lambda x: (x[0][0], str(x[0][1]))):
            print(f'  {endpoint:<46} status={str(status):<8} count={c}', file=sys.stderr)
        sys.exit(0)

    signal.signal(signal.SIGINT, summary)
    signal.signal(signal.SIGTERM, summary)

    def probe(endpoint):
        url = base + endpoint
        status, body, ms = fetch(url, timeout=args.timeout)
        counts[(endpoint, status)] += 1
        ts = time.strftime('%H:%M:%S')
        marker = '' if status == 200 else '  <-- NOT 200'
        print(f'{ts}\t{endpoint:<46}\t{status}\t{ms:7.1f}ms{marker}', flush=True)
        return status, body

    while True:
        probe('/healthz')

        status, body = probe('/')
        if status == 200:
            now = parse_hashes(body)
            if now and now != current:
                added = sorted(now - current)
                removed = sorted(current - now)
                deploys_seen += 1
                ts = time.strftime('%H:%M:%S')
                print(f'{ts}\t[DEPLOY DETECTED] added={added} removed={removed}', file=sys.stderr, flush=True)
                current = now

        for h in sorted(pinned):
            probe('/assets/' + h)

        time.sleep(args.interval)


if __name__ == '__main__':
    main()
