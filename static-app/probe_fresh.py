#!/usr/bin/env python3
"""
Routing-race probe for static-app.

Behavior on every tick (default 0.5s):
  - GET /                     (returns index.html, references current chunks)
  - Parse main-/vendor- hashes out of that HTML
  - GET /assets/<that-main>   and  GET /assets/<that-vendor>

Unlike probe.py, this does NOT pin to the hashes seen at T0. Each tick uses
the hashes from the just-fetched HTML. The point is to expose the routing
race during a rollout:

  - browser GET /  -> ingress picks a NEW pod  -> returns new hashes in HTML
  - browser GET /assets/<new-hash>.js  -> ingress *independently* picks an
    upstream  -> may land on an OLD pod that pre-dates those hashes -> 404

Even with N+N-1 retention in place, the old pod cannot have *future*
chunks. So this loop will see 404s during the rolling window that the
pin-to-T0 probe wouldn't.

Each line is TSV: ts  endpoint  status  ms
SIGINT/SIGTERM prints a per-(endpoint,status) summary.

Usage:
  ./probe_fresh.py
  ./probe_fresh.py --base https://web-2-db804f74-i22f5o97.withporter.run --interval 0.25
  ./probe_fresh.py 2>&1 | tee probe_fresh.log
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
        req = Request(url, headers={'User-Agent': 'static-app-probe-fresh/1.0'})
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
    return sorted(set(HASH_RE.findall(html_bytes.decode('utf-8', errors='replace'))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=DEFAULT_BASE)
    ap.add_argument('--interval', type=float, default=0.5)
    ap.add_argument('--timeout', type=float, default=5.0)
    args = ap.parse_args()
    base = args.base.rstrip('/')

    print(f'[probe-fresh] base={base} interval={args.interval}s', file=sys.stderr)

    counts = Counter()
    started = time.monotonic()
    last_hashes = None

    def summary(*_):
        elapsed = time.monotonic() - started
        total = sum(counts.values())
        non_ok = sum(c for (e, s), c in counts.items() if s != 200)
        print(f'\n[probe-fresh] ==== SUMMARY ====', file=sys.stderr)
        print(f'[probe-fresh] elapsed={elapsed:.1f}s requests={total} non_200={non_ok}', file=sys.stderr)
        for (endpoint, status), c in sorted(counts.items(), key=lambda x: (x[0][0], str(x[0][1]))):
            print(f'  {endpoint:<32} status={str(status):<8} count={c}', file=sys.stderr)
        sys.exit(0)

    signal.signal(signal.SIGINT, summary)
    signal.signal(signal.SIGTERM, summary)

    while True:
        status, body, ms = fetch(base + '/', timeout=args.timeout)
        counts[('/', status)] += 1
        ts = time.strftime('%H:%M:%S')
        marker = '' if status == 200 else '  <-- /'
        print(f'{ts}\t/\t\t\t\t{status}\t{ms:7.1f}ms{marker}', flush=True)

        if status != 200:
            time.sleep(args.interval)
            continue

        hashes = parse_hashes(body)
        if hashes and hashes != last_hashes:
            ts = time.strftime('%H:%M:%S')
            print(f'{ts}\t[NEW HASHES IN HTML] {hashes}', file=sys.stderr, flush=True)
            last_hashes = hashes

        for h in hashes:
            url = base + '/assets/' + h
            status, _, ms = fetch(url, timeout=args.timeout)
            counts[('/assets/' + h, status)] += 1
            ts = time.strftime('%H:%M:%S')
            marker = '' if status == 200 else '  <-- ROUTING RACE'
            print(f'{ts}\t/assets/{h:<26}\t{status}\t{ms:7.1f}ms{marker}', flush=True)

        time.sleep(args.interval)


if __name__ == '__main__':
    main()
