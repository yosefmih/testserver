#!/usr/bin/env python3
"""
Test script for WebSocket session affinity.

1. Generate a SESSION_ID client-side (critical for consistent hashing!)
2. Connect via WebSocket WITH the SESSION_ID cookie
3. Send HTTP request to /send with same SESSION_ID
4. Verify the message arrives on the WebSocket

Usage: python test_affinity.py [n_sessions]
"""

import argparse
import asyncio
import json
import ssl
import uuid
import aiohttp
import websockets

BASE_URL = "web-2-3439a89a-unm0fax7.withporter.run"
WS_URL = f"wss://{BASE_URL}/ws"
HTTP_URL = f"https://{BASE_URL}/send"


async def test_single_session(session_num: int, verbose: bool = False) -> dict:
    """Run a single session test. Returns result dict."""
    session_id = str(uuid.uuid4())
    ssl_context = ssl.create_default_context()
    prefix = f"[Session {session_num}]"
    result = {
        "session_num": session_num,
        "session_id": session_id[:8],
        "ws_pod": None,
        "http_pod": None,
        "affinity_ok": False,
        "message_received": False,
    }

    def log(msg):
        if verbose:
            print(f"{prefix} {msg}")

    try:
        log(f"Generating SESSION_ID: {session_id[:8]}...")
        log(f"Connecting to WebSocket: {WS_URL}")

        async with websockets.connect(
            WS_URL,
            ssl=ssl_context,
            additional_headers={"Cookie": f"SESSION_ID={session_id}"}
        ) as ws:
            welcome = await ws.recv()
            welcome_data = json.loads(welcome)
            result["ws_pod"] = welcome_data.get("hostname")
            log(f"✓ WebSocket connected to pod: {result['ws_pod']}")

            log(f"Sending HTTP POST to {HTTP_URL}")
            async with aiohttp.ClientSession() as http:
                async with http.post(
                    HTTP_URL,
                    json={"message": f"Test {session_num}"},
                    cookies={"SESSION_ID": session_id}
                ) as resp:
                    http_data = await resp.json()
                    result["http_pod"] = http_data.get("hostname")
                    relayed_to = http_data.get("relayed_to", 0)
                    result["affinity_ok"] = result["ws_pod"] == result["http_pod"]
                    log(f"✓ HTTP response from pod: {result['http_pod']} (relayed_to={relayed_to})")

            if result["affinity_ok"]:
                log(f"✓ AFFINITY OK: Both requests hit {result['ws_pod']}")
            else:
                log(f"✗ AFFINITY BROKEN: WS={result['ws_pod']}, HTTP={result['http_pod']}")

            log("Waiting for relayed message on WebSocket...")
            try:
                relayed = await asyncio.wait_for(ws.recv(), timeout=5.0)
                relayed_data = json.loads(relayed)
                result["message_received"] = relayed_data.get("message") == f"Test {session_num}"
                if result["message_received"]:
                    log(f"✓ Message received: \"{relayed_data.get('message')}\"")
                else:
                    log(f"✗ Message mismatch: expected \"Test {session_num}\", got \"{relayed_data.get('message')}\"")
            except asyncio.TimeoutError:
                log("✗ Timeout waiting for message")
                result["message_received"] = False

    except Exception as e:
        result["error"] = str(e)
        log(f"✗ Error: {e}")

    return result


async def run_tests(n_sessions: int, verbose: bool = False):
    """Run n_sessions tests concurrently and report results."""
    print(f"Running {n_sessions} session test(s) against {BASE_URL}")
    if verbose:
        print("Verbose mode enabled\n")
    else:
        print()

    tasks = [test_single_session(i + 1, verbose=verbose) for i in range(n_sessions)]
    results = await asyncio.gather(*tasks)

    if verbose:
        print("\n" + "=" * 113)

    # Print results table
    print(f"{'#':<3} {'Session ID':<10} {'WS Pod':<35} {'HTTP Pod':<35} {'Affinity':<10} {'Message':<10}")
    print("-" * 113)

    success_count = 0
    for r in results:
        affinity = "✓" if r["affinity_ok"] else "✗"
        message = "✓" if r["message_received"] else "✗"
        ws_pod = r["ws_pod"] or "ERROR"
        http_pod = r["http_pod"] or "ERROR"

        if r["affinity_ok"] and r["message_received"]:
            success_count += 1

        print(f"{r['session_num']:<3} {r['session_id']:<10} {ws_pod:<35} {http_pod:<35} {affinity:<10} {message:<10}")

    print("-" * 113)
    print(f"\nResults: {success_count}/{n_sessions} sessions passed ({100*success_count/n_sessions:.0f}%)")

    if success_count == n_sessions:
        print("✓ All sessions routed correctly - affinity working!")
    else:
        print("✗ Some sessions failed - check configuration")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test WebSocket session affinity")
    parser.add_argument("n", type=int, nargs="?", default=5, help="Number of sessions to test (default: 5)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show detailed logs for each session")
    args = parser.parse_args()

    asyncio.run(run_tests(args.n, verbose=args.verbose))
