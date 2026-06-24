"""Launch N Porter sandboxes concurrently against the in-cluster sandbox API.

The sandbox API is reachable only from inside the cluster, so run this from a
pod that already has the porter-sandbox SDK and PORTER_SANDBOX_* env set — e.g.
exec into the linear-autopilot web pod:

    kubectl exec -it deploy/linear-autopilot-web -- python scripts/sandbox_loadtest.py --count 10

Each sandbox runs to completion (its command is the workload); the script fans
them out concurrently, polls each to a terminal phase, prints a summary, and
terminates them unless --keep is passed.
"""
import argparse
import asyncio
import time

from porter_sandbox import AsyncPorter

TERMINAL_PHASES = {"succeeded", "failed", "terminated"}


async def run_one(porter, index, image, command, tag, ready_timeout):
    started = time.monotonic()
    cmd = command or ["sh", "-c", f"echo hello from sandbox {index}; uname -m"]
    sandbox = await porter.sandboxes.create(
        image=image,
        command=cmd,
        tags={"test": tag, "idx": str(index)},
    )

    phase, exit_code = "creating", None
    while time.monotonic() - started < ready_timeout:
        status = await porter.sandboxes.raw.get_sandbox(id=sandbox.id)
        phase, exit_code = status.phase.value, status.exit_code
        if phase in TERMINAL_PHASES:
            break
        await asyncio.sleep(1)

    try:
        logs = await porter.sandboxes.raw.get_sandbox_logs(id=sandbox.id, limit=20)
        lines = [line.line for line in logs.logs if line.line.strip()]
        last_line = lines[-1] if lines else ""
    except Exception as e:
        last_line = f"<logs error: {e}>"

    return {
        "idx": index,
        "id": sandbox.id,
        "phase": phase,
        "exit_code": exit_code,
        "secs": round(time.monotonic() - started, 1),
        "last_line": last_line,
        "sandbox": sandbox,
    }


async def main():
    parser = argparse.ArgumentParser(description="Launch N Porter sandboxes concurrently.")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--image", default="python:3.12-slim", help="Must be publicly pullable (no private-registry auth in sandboxes).")
    parser.add_argument("--tag", default="loadtest", help="Value for the 'test' tag on every sandbox.")
    parser.add_argument("--concurrency", type=int, default=0, help="Max creates in flight (0 = all at once).")
    parser.add_argument("--ready-timeout", type=int, default=120)
    parser.add_argument("--keep", action="store_true", help="Leave sandboxes running instead of terminating them.")
    parser.add_argument("--command", nargs=argparse.REMAINDER, help="Command run in every sandbox (default: echo + uname -m).")
    args = parser.parse_args()

    limit = args.concurrency or args.count
    semaphore = asyncio.Semaphore(limit)

    async with AsyncPorter() as porter:
        async def guarded(i):
            async with semaphore:
                return await run_one(porter, i, args.image, args.command, args.tag, args.ready_timeout)

        print(f"launching {args.count} sandboxes image={args.image} tag={args.tag} concurrency={limit}")
        wall_start = time.monotonic()
        results = await asyncio.gather(*[guarded(i) for i in range(args.count)], return_exceptions=True)
        wall = round(time.monotonic() - wall_start, 1)

        succeeded = 0
        print(f"\n{'idx':>3}  {'sandbox id':<40} {'phase':<10} {'exit':>4} {'secs':>5}  last_line")
        for result in results:
            if isinstance(result, Exception):
                print(f"  -  <error> {result}")
                continue
            if result["phase"] == "succeeded" and result["exit_code"] == 0:
                succeeded += 1
            print(f"{result['idx']:>3}  {result['id']:<40} {result['phase']:<10} "
                  f"{str(result['exit_code']):>4} {result['secs']:>5}  {result['last_line'][:60]}")
        print(f"\n{succeeded}/{args.count} succeeded · {wall}s wall-clock")

        if args.keep:
            print(f"left sandboxes running (tag test={args.tag})")
            return
        sandboxes = [r["sandbox"] for r in results if not isinstance(r, Exception)]
        await asyncio.gather(*[sb.terminate() for sb in sandboxes], return_exceptions=True)
        print(f"terminated {len(sandboxes)} sandboxes (pass --keep to leave them running)")


if __name__ == "__main__":
    asyncio.run(main())
