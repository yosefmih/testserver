#!/usr/bin/env python3
"""
Discovers live SeatWatch data (showtimes, seat maps) and generates wrk Lua
scripts for the dynamic endpoints, so a load test always exercises real,
currently-valid showtime IDs and seat names instead of stale hardcoded ones.

Prints a JSON manifest to stdout: [{"name", "kind": "url"|"lua", "value"}].
Progress/diagnostics go to stderr so stdout stays parseable.
"""
import argparse
import json
import random
import ssl
import sys
import time
import urllib.request


def log(msg):
    print(msg, file=sys.stderr)


def fetch_json(url, insecure=False):
    ctx = ssl._create_unverified_context() if insecure else None
    with urllib.request.urlopen(url, timeout=15, context=ctx) as resp:
        return json.load(resp)


def lua_string(s):
    """Render a Go/JSON string as a Lua long-bracket literal (safe: JSON
    bodies never contain the `]]` delimiter, so no escaping needed)."""
    return "[[" + s + "]]"


def build_seatmap_script(ids):
    body = f"""
local ids = {{ {", ".join(str(i) for i in ids)} }}
local headers = {{ ["X-Load-Test"] = "1" }}

request = function()
  local id = ids[math.random(#ids)]
  return wrk.format("GET", "/api/seatmap/" .. id, headers)
end
"""
    return body


def build_evaluate_script(payloads):
    lines = ", ".join(lua_string(json.dumps(p)) for p in payloads)
    body = f"""
local payloads = {{ {lines} }}
local headers = {{ ["Content-Type"] = "application/json", ["X-Load-Test"] = "1" }}

request = function()
  local body = payloads[math.random(#payloads)]
  return wrk.format("POST", "/api/evaluate", headers, body)
end
"""
    return body


def build_mixed_script(ids, payloads, weights):
    # weights: {showtimes, config, seatmap, evaluate} summing conceptually
    # to 100; cumulative thresholds drive a weighted random pick per request.
    cum = []
    total = 0
    for name, w in weights.items():
        total += w
        cum.append((name, total))
    ids_lua = ", ".join(str(i) for i in ids)
    payloads_lua = ", ".join(lua_string(json.dumps(p)) for p in payloads)
    cum_lua = ", ".join(f'{{"{n}", {t}}}' for n, t in cum)
    body = f"""
local ids = {{ {ids_lua} }}
local payloads = {{ {payloads_lua} }}
local cum = {{ {cum_lua} }}
local total = {total}
local get_headers = {{ ["X-Load-Test"] = "1" }}
local post_headers = {{ ["Content-Type"] = "application/json", ["X-Load-Test"] = "1" }}

local function pick()
  local r = math.random() * total
  for _, entry in ipairs(cum) do
    if r <= entry[2] then return entry[1] end
  end
  return cum[#cum][1]
end

request = function()
  local kind = pick()
  if kind == "showtimes" then
    return wrk.format("GET", "/api/showtimes", get_headers)
  elseif kind == "config" then
    return wrk.format("GET", "/api/config", get_headers)
  elseif kind == "seatmap" then
    local id = ids[math.random(#ids)]
    return wrk.format("GET", "/api/seatmap/" .. id, get_headers)
  else
    local body = payloads[math.random(#payloads)]
    return wrk.format("POST", "/api/evaluate", post_headers, body)
  end
end
"""
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_url")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--sample-seatmaps", type=int, default=30)
    ap.add_argument("--movies", type=int, default=5)
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--mixed", action="store_true")
    ap.add_argument(
        "--mix-weights",
        default="showtimes=10,config=5,seatmap=40,evaluate=45",
        help="comma list of name=weight for --mixed mode",
    )
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    log(f"discovering live data from {base} ...")

    try:
        showtimes = fetch_json(f"{base}/api/showtimes", args.insecure)
    except Exception as e:
        log(f"ERROR: couldn't reach {base}/api/showtimes: {e}")
        log("Is the server running and BASE_URL correct? (503 during warmup is normal for a few minutes after a fresh deploy — retry shortly.)")
        sys.exit(1)
    now = time.time()

    def show_at_epoch(st):
        # Go RFC3339 e.g. 2026-08-07T02:00:00Z
        return time.mktime(time.strptime(st["showAt"], "%Y-%m-%dT%H:%M:%SZ")) - time.timezone

    upcoming = [st for st in showtimes if show_at_epoch(st) > now]
    if not upcoming:
        log("WARNING: no upcoming showtimes found; falling back to full cached list")
        upcoming = showtimes
    log(f"{len(showtimes)} showtimes cached, {len(upcoming)} upcoming")

    # Sample showtime IDs for the seatmap scenario.
    n_ids = min(args.sample_seatmaps, len(upcoming))
    sampled = random.sample(upcoming, n_ids)
    seatmap_ids = [st["id"] for st in sampled]
    log(f"seatmap scenario: sampled {len(seatmap_ids)} showtime IDs")

    # Pick distinct (movieSlug, format) combos for the evaluate scenario,
    # favoring ones with more upcoming screenings (more realistic + more
    # interesting seat-matching workload).
    combos = {}
    for st in upcoming:
        key = (st["movieSlug"], st["format"])
        combos.setdefault(key, []).append(st)
    ranked = sorted(combos.items(), key=lambda kv: -len(kv[1]))
    chosen = ranked[: args.movies]

    payloads = []
    for (slug, fmt), sts in chosen:
        rep = sts[0]
        try:
            layout = fetch_json(f"{base}/api/seatmap/{rep['id']}", args.insecure)
        except Exception as e:
            log(f"  skipping {slug}/{fmt}: seatmap fetch failed: {e}")
            continue
        seats = [s["name"] for s in layout["seats"] if s.get("shouldDisplay") and s.get("name")]
        if not seats:
            continue
        payloads.append({
            "movieSlug": slug,
            "format": fmt,
            "numSeats": 2,
            "seats": seats,
            "dateFrom": "",
            "dateTo": "",
        })
        log(f"  {slug} / {fmt}: {len(seats)} seats, {len(sts)} upcoming screenings")

    if not payloads:
        log("ERROR: could not build any evaluate payloads (no seat maps available)")
        sys.exit(1)

    manifest = []
    if args.mixed:
        weights = {}
        for part in args.mix_weights.split(","):
            k, v = part.split("=")
            weights[k.strip()] = float(v)
        script = build_mixed_script(seatmap_ids, payloads, weights)
        path = f"{args.outdir}/mixed.lua"
        with open(path, "w") as f:
            f.write(script)
        manifest.append({"name": "mixed", "kind": "lua", "value": path})
    else:
        manifest.append({"name": "showtimes", "kind": "url", "value": f"{base}/api/showtimes"})
        manifest.append({"name": "config", "kind": "url", "value": f"{base}/api/config"})

        seatmap_path = f"{args.outdir}/seatmap.lua"
        with open(seatmap_path, "w") as f:
            f.write(build_seatmap_script(seatmap_ids))
        manifest.append({"name": "seatmap", "kind": "lua", "value": seatmap_path})

        evaluate_path = f"{args.outdir}/evaluate.lua"
        with open(evaluate_path, "w") as f:
            f.write(build_evaluate_script(payloads))
        manifest.append({"name": "evaluate", "kind": "lua", "value": evaluate_path})

    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
