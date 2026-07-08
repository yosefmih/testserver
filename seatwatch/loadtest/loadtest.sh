#!/usr/bin/env bash
# Load test SeatWatch's API with wrk, using live data for the dynamic
# endpoints (seat maps by real showtime ID, evaluate with real seat names)
# instead of hardcoded values that would go stale within minutes.
#
# Usage:
#   ./loadtest.sh [BASE_URL] [options]
#
# Options:
#   -c, --connections N   concurrent connections per scenario (default 20)
#   -t, --threads N       wrk threads (default 4)
#   -d, --duration DUR    per-scenario duration, e.g. 20s, 1m (default 20s)
#   --sample-seatmaps N   distinct showtime IDs to cycle through for the
#                         seatmap scenario (default 30)
#   --movies N            distinct movie/format combos to build evaluate
#                         payloads for (default 5)
#   --only LIST           comma list of scenarios to run: showtimes,config,
#                         seatmap,evaluate,mixed (default: all but mixed)
#   --mixed               run one combined weighted-random scenario instead
#                         of separate per-endpoint runs (see --mix-weights)
#   --mix-weights LIST    name=weight,... for --mixed (default
#                         "showtimes=10,config=5,seatmap=40,evaluate=45")
#   --insecure            skip TLS verification during discovery (curl-side)
#   --keep                keep the generated Lua scripts + wrk logs
#
# Examples:
#   ./loadtest.sh                                   # local dev, defaults
#   ./loadtest.sh http://localhost:8095 -c 50 -d 30s
#   ./loadtest.sh https://seatwatcher.jemy.withporter.run --mixed -c 30
#
# Safety notes:
#   - /api/watches (create/list/delete) is intentionally never load tested:
#     creating watches sends real alert emails when ALERTS_ENABLED=true.
#   - /api/seatmap/{id} for an ID not yet in the server's cache triggers a
#     real on-demand fetch from AMC. Keep --sample-seatmaps modest (the
#     default is) so this can't turn into an AMC-hammering burst.
#   - Point this at localhost or a port-forward by default. Only aim it at
#     a public URL deliberately.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BASE_URL="http://localhost:8095"
CONNECTIONS=20
THREADS=4
DURATION=20s
SAMPLE_SEATMAPS=30
MOVIES=5
ONLY=""
MIXED=false
MIX_WEIGHTS="showtimes=10,config=5,seatmap=40,evaluate=45"
INSECURE=false
KEEP=false

if [[ $# -gt 0 && "$1" != -* ]]; then
	BASE_URL="$1"
	shift
fi

while [[ $# -gt 0 ]]; do
	case "$1" in
	-c | --connections)
		CONNECTIONS="$2"
		shift 2
		;;
	-t | --threads)
		THREADS="$2"
		shift 2
		;;
	-d | --duration)
		DURATION="$2"
		shift 2
		;;
	--sample-seatmaps)
		SAMPLE_SEATMAPS="$2"
		shift 2
		;;
	--movies)
		MOVIES="$2"
		shift 2
		;;
	--only)
		ONLY="$2"
		shift 2
		;;
	--mixed)
		MIXED=true
		shift
		;;
	--mix-weights)
		MIX_WEIGHTS="$2"
		shift 2
		;;
	--insecure)
		INSECURE=true
		shift
		;;
	--keep)
		KEEP=true
		shift
		;;
	-h | --help)
		sed -n '2,40p' "$0"
		exit 0
		;;
	*)
		echo "unknown option: $1" >&2
		exit 1
		;;
	esac
done

if ! command -v wrk >/dev/null; then
	echo "wrk not found. Install it first (e.g. 'brew install wrk')." >&2
	exit 1
fi

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/seatwatch-loadtest.XXXXXX")"
cleanup() {
	if [[ "$KEEP" == false ]]; then
		rm -rf "$WORKDIR"
	else
		echo "kept scripts + logs at: $WORKDIR"
	fi
}
trap cleanup EXIT

echo "== discovering live data from $BASE_URL =="
GEN_ARGS=("$BASE_URL" --outdir "$WORKDIR" --sample-seatmaps "$SAMPLE_SEATMAPS" --movies "$MOVIES")
[[ "$INSECURE" == true ]] && GEN_ARGS+=(--insecure)
if [[ "$MIXED" == true ]]; then
	GEN_ARGS+=(--mixed --mix-weights "$MIX_WEIGHTS")
fi

MANIFEST_JSON="$(python3 "$SCRIPT_DIR/gen_scenarios.py" "${GEN_ARGS[@]}")"
echo

# Emit "name<TAB>kind<TAB>value" lines from the JSON manifest, honoring --only.
SCENARIOS="$(python3 - "$MANIFEST_JSON" "$ONLY" <<'EOF'
import json, sys
manifest = json.loads(sys.argv[1])
only = sys.argv[2]
allowed = set(only.split(",")) if only else None
for s in manifest:
    if allowed is not None and s["name"] not in allowed:
        continue
    print(f"{s['name']}\t{s['kind']}\t{s['value']}")
EOF
)"

if [[ -z "$SCENARIOS" ]]; then
	echo "no scenarios to run (check --only against the available names)" >&2
	exit 1
fi

RESULTS_DIR="$WORKDIR/results"
mkdir -p "$RESULTS_DIR"

echo "== running: connections=$CONNECTIONS threads=$THREADS duration=$DURATION =="
echo

while IFS=$'\t' read -r NAME KIND VALUE; do
	echo "---- $NAME ----"
	LOG="$RESULTS_DIR/$NAME.log"
	if [[ "$KIND" == "url" ]]; then
		wrk -c "$CONNECTIONS" -t "$THREADS" -d "$DURATION" --latency "$VALUE" | tee "$LOG"
	else
		wrk -c "$CONNECTIONS" -t "$THREADS" -d "$DURATION" --latency -s "$VALUE" "$BASE_URL" | tee "$LOG"
	fi
	echo
done <<<"$SCENARIOS"

echo "== summary =="
printf "%-12s %10s %12s %12s %10s\n" "scenario" "req/s" "avg latency" "p99 latency" "errors"
for LOG in "$RESULTS_DIR"/*.log; do
	NAME="$(basename "$LOG" .log)"
	python3 - "$NAME" "$LOG" <<'EOF'
import re, sys
name, path = sys.argv[1], sys.argv[2]
text = open(path).read()
def find(pat, default="-"):
    m = re.search(pat, text)
    return m.group(1) if m else default
rps = find(r"Requests/sec:\s+([\d.]+)")
avg = find(r"Latency\s+([\d.]+\w+)")
p99 = find(r"99%\s+([\d.]+\w+)")
errors = 0
for kind in ("connect", "read", "write", "timeout"):
    m = re.search(rf"{kind} (\d+)", text)
    if m:
        errors += int(m.group(1))
non2xx = find(r"Non-2xx or 3xx responses: (\d+)", "0")
print(f"{name:<12} {rps:>10} {avg:>12} {p99:>12} {int(errors)+int(non2xx):>10}")
EOF
done
