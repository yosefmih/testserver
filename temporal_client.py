#!/usr/bin/env python3
"""
Temporal client for KEDA autoscaling stress tests.
Supports burst submissions, concurrent workflow starts, and configurable load patterns.
"""

import asyncio
import argparse
import logging
import os
import uuid
import time
from dataclasses import dataclass
from typing import Optional

from temporalio.client import Client
from dotenv import load_dotenv

from temporal_worker import (
    StressTestWorkflow,
    BurstWorkflow,
    get_temporal_config,
    TASK_QUEUE,
)

if os.path.exists('.env'):
    load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class LoadStats:
    started: int = 0
    completed: int = 0
    failed: int = 0
    start_time: float = 0.0

    def summary(self) -> str:
        elapsed = time.time() - self.start_time if self.start_time else 0
        rate = self.started / elapsed if elapsed > 0 else 0
        return (
            f"Started: {self.started}, Completed: {self.completed}, "
            f"Failed: {self.failed}, Rate: {rate:.1f}/s, Elapsed: {elapsed:.1f}s"
        )


async def create_client() -> Client:
    host, namespace, api_key = get_temporal_config()

    logger.info(f"Connecting to Temporal at {host}")

    client = await Client.connect(
        host,
        namespace=namespace,
        api_key=api_key,
        tls=True
    )
    logger.info(f"Connected to namespace: {namespace}")
    return client


async def start_stress_workflow(
    client: Client,
    task_id: str,
    intensity: str = "medium",
    workflow_type: str = "mixed"
) -> str:
    """Start a StressTestWorkflow and return its ID."""
    workflow_id = f"stress-{task_id}"

    await client.start_workflow(
        StressTestWorkflow.run,
        {
            "task_id": task_id,
            "intensity": intensity,
            "type": workflow_type,
        },
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    return workflow_id


async def start_burst_workflow(
    client: Client,
    task_id: str,
    activity: str = "cpu",
    intensity: str = "medium"
) -> str:
    """Start a BurstWorkflow and return its ID."""
    workflow_id = f"burst-{task_id}"

    await client.start_workflow(
        BurstWorkflow.run,
        {
            "task_id": task_id,
            "activity": activity,
            "intensity": intensity,
        },
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )
    return workflow_id


async def cmd_single(client: Client, args: argparse.Namespace):
    """Run a single stress test workflow and wait for result."""
    task_id = f"single-{uuid.uuid4().hex[:8]}"
    logger.info(f"Starting single workflow: {task_id}")
    logger.info(f"  Intensity: {args.intensity}")
    logger.info(f"  Type: {args.type}")

    workflow_id = await start_stress_workflow(
        client, task_id, args.intensity, args.type
    )

    logger.info(f"Workflow started: {workflow_id}")
    logger.info("Waiting for completion...")

    handle = client.get_workflow_handle(workflow_id)
    result = await handle.result()

    logger.info(f"Workflow completed: {result}")


async def cmd_burst(client: Client, args: argparse.Namespace):
    """
    Fire off many workflows as fast as possible to create queue backlog.
    Uses asyncio.gather for concurrent submissions.
    """
    count = args.count
    concurrency = args.concurrency
    intensity = args.intensity
    activity = args.activity

    logger.info(f"Starting burst: {count} workflows")
    logger.info(f"  Concurrency: {concurrency}")
    logger.info(f"  Intensity: {intensity}")
    logger.info(f"  Activity: {activity}")

    stats = LoadStats(start_time=time.time())
    semaphore = asyncio.Semaphore(concurrency)

    async def submit_one(index: int):
        async with semaphore:
            task_id = f"burst-{index:05d}-{uuid.uuid4().hex[:6]}"
            try:
                await start_burst_workflow(client, task_id, activity, intensity)
                stats.started += 1
                if stats.started % 100 == 0:
                    logger.info(f"Progress: {stats.summary()}")
            except Exception as e:
                stats.failed += 1
                logger.error(f"Failed to start workflow {index}: {e}")

    tasks = [submit_one(i) for i in range(count)]
    await asyncio.gather(*tasks)

    logger.info(f"Burst complete: {stats.summary()}")


async def cmd_sustained(client: Client, args: argparse.Namespace):
    """
    Sustained load: submit workflows at a steady rate.
    Good for testing KEDA's ability to maintain scale.
    """
    rate = args.rate
    duration = args.duration
    intensity = args.intensity
    workflow_type = args.type

    logger.info(f"Starting sustained load")
    logger.info(f"  Rate: {rate} workflows/sec")
    logger.info(f"  Duration: {duration} seconds")
    logger.info(f"  Intensity: {intensity}")
    logger.info(f"  Type: {workflow_type}")

    stats = LoadStats(start_time=time.time())
    interval = 1.0 / rate
    end_time = time.time() + duration

    index = 0
    while time.time() < end_time:
        task_id = f"sustained-{index:06d}-{uuid.uuid4().hex[:6]}"
        try:
            await start_stress_workflow(client, task_id, intensity, workflow_type)
            stats.started += 1
            index += 1

            if stats.started % 10 == 0:
                logger.info(f"Progress: {stats.summary()}")

        except Exception as e:
            stats.failed += 1
            logger.error(f"Failed to start workflow: {e}")

        await asyncio.sleep(interval)

    logger.info(f"Sustained load complete: {stats.summary()}")


async def cmd_ramp(client: Client, args: argparse.Namespace):
    """
    Ramp up load gradually, then hold, then ramp down.
    Good for testing KEDA scale-up and scale-down behavior.
    """
    max_rate = args.max_rate
    ramp_duration = args.ramp_duration
    hold_duration = args.hold_duration
    intensity = args.intensity

    logger.info(f"Starting ramp test")
    logger.info(f"  Max rate: {max_rate} workflows/sec")
    logger.info(f"  Ramp duration: {ramp_duration}s")
    logger.info(f"  Hold duration: {hold_duration}s")
    logger.info(f"  Intensity: {intensity}")

    stats = LoadStats(start_time=time.time())
    index = 0

    async def submit_at_rate(target_rate: float, duration: float, phase: str):
        nonlocal index
        if target_rate <= 0:
            await asyncio.sleep(duration)
            return

        interval = 1.0 / target_rate
        end_time = time.time() + duration

        while time.time() < end_time:
            task_id = f"ramp-{phase}-{index:06d}-{uuid.uuid4().hex[:6]}"
            try:
                await start_burst_workflow(client, task_id, "cpu", intensity)
                stats.started += 1
                index += 1
            except Exception as e:
                stats.failed += 1
                logger.error(f"Failed: {e}")

            await asyncio.sleep(interval)

    logger.info("Phase 1: Ramping up...")
    steps = 10
    step_duration = ramp_duration / steps
    for i in range(1, steps + 1):
        current_rate = (i / steps) * max_rate
        logger.info(f"  Ramp step {i}/{steps}: {current_rate:.1f}/sec")
        await submit_at_rate(current_rate, step_duration, f"up{i}")
        logger.info(f"  Stats: {stats.summary()}")

    logger.info(f"Phase 2: Holding at {max_rate}/sec for {hold_duration}s...")
    await submit_at_rate(max_rate, hold_duration, "hold")
    logger.info(f"  Stats: {stats.summary()}")

    logger.info("Phase 3: Ramping down...")
    for i in range(steps - 1, -1, -1):
        current_rate = (i / steps) * max_rate
        logger.info(f"  Ramp step: {current_rate:.1f}/sec")
        await submit_at_rate(current_rate, step_duration, f"down{i}")
        logger.info(f"  Stats: {stats.summary()}")

    logger.info(f"Ramp test complete: {stats.summary()}")


async def cmd_stress(client: Client, args: argparse.Namespace):
    """
    Maximum stress test: submit as many workflows as possible.
    Warning: This can overwhelm your Temporal cluster!
    """
    duration = args.duration
    concurrency = args.concurrency
    intensity = args.intensity

    logger.info(f"Starting MAXIMUM STRESS test")
    logger.info(f"  Duration: {duration}s")
    logger.info(f"  Concurrency: {concurrency}")
    logger.info(f"  Intensity: {intensity}")
    logger.info("  WARNING: This may overwhelm your cluster!")

    stats = LoadStats(start_time=time.time())
    end_time = time.time() + duration
    semaphore = asyncio.Semaphore(concurrency)
    index = 0
    running = True

    async def submit_continuous():
        nonlocal index
        while running and time.time() < end_time:
            async with semaphore:
                if not running:
                    break
                task_id = f"stress-{index:08d}-{uuid.uuid4().hex[:4]}"
                index += 1
                try:
                    await start_burst_workflow(client, task_id, "cpu", intensity)
                    stats.started += 1
                except Exception as e:
                    stats.failed += 1
                    if "resource exhausted" in str(e).lower():
                        logger.warning("Resource exhausted, backing off...")
                        await asyncio.sleep(1)

    tasks = [asyncio.create_task(submit_continuous()) for _ in range(concurrency)]

    report_interval = 5
    while time.time() < end_time:
        await asyncio.sleep(report_interval)
        logger.info(f"Progress: {stats.summary()}")

    running = False
    await asyncio.gather(*tasks, return_exceptions=True)

    logger.info(f"Stress test complete: {stats.summary()}")


async def cmd_status(client: Client, args: argparse.Namespace):
    """Check the status of workflows."""
    query = f'TaskQueue="{TASK_QUEUE}"'

    if args.running:
        query += ' AND ExecutionStatus="Running"'

    logger.info(f"Querying workflows: {query}")

    count = 0
    async for workflow in client.list_workflows(query=query):
        count += 1
        if count <= 20:
            logger.info(f"  {workflow.id}: {workflow.status.name}")

    if count > 20:
        logger.info(f"  ... and {count - 20} more")

    logger.info(f"Total: {count} workflows")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Temporal KEDA Stress Test Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single workflow test
  python temporal_client.py single --intensity heavy --type sequential

  # Burst 1000 workflows as fast as possible
  python temporal_client.py burst --count 1000 --concurrency 50

  # Sustained load at 10 workflows/sec for 5 minutes
  python temporal_client.py sustained --rate 10 --duration 300

  # Ramp test for KEDA scale-up/down
  python temporal_client.py ramp --max-rate 20 --ramp-duration 60 --hold-duration 120

  # Maximum stress test (careful!)
  python temporal_client.py stress --duration 60 --concurrency 100
        """
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    single = subparsers.add_parser("single", help="Run single workflow")
    single.add_argument("--intensity", choices=["light", "medium", "heavy", "extreme"], default="medium")
    single.add_argument("--type", choices=["cpu", "memory", "mixed", "sequential"], default="mixed")

    burst = subparsers.add_parser("burst", help="Burst submit many workflows")
    burst.add_argument("--count", type=int, default=100, help="Number of workflows")
    burst.add_argument("--concurrency", type=int, default=20, help="Concurrent submissions")
    burst.add_argument("--intensity", choices=["light", "medium", "heavy"], default="medium")
    burst.add_argument("--activity", choices=["cpu", "matrix", "io"], default="cpu")

    sustained = subparsers.add_parser("sustained", help="Sustained load at fixed rate")
    sustained.add_argument("--rate", type=float, default=5.0, help="Workflows per second")
    sustained.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    sustained.add_argument("--intensity", choices=["light", "medium", "heavy", "extreme"], default="medium")
    sustained.add_argument("--type", choices=["cpu", "memory", "mixed", "sequential"], default="mixed")

    ramp = subparsers.add_parser("ramp", help="Ramp up/down load test")
    ramp.add_argument("--max-rate", type=float, default=10.0, help="Max workflows per second")
    ramp.add_argument("--ramp-duration", type=int, default=60, help="Ramp up/down duration")
    ramp.add_argument("--hold-duration", type=int, default=120, help="Hold at max rate duration")
    ramp.add_argument("--intensity", choices=["light", "medium", "heavy"], default="medium")

    stress = subparsers.add_parser("stress", help="Maximum stress test")
    stress.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    stress.add_argument("--concurrency", type=int, default=50, help="Concurrent submissions")
    stress.add_argument("--intensity", choices=["light", "medium", "heavy"], default="light")

    status = subparsers.add_parser("status", help="Check workflow status")
    status.add_argument("--running", action="store_true", help="Only show running workflows")

    return parser.parse_args()


async def main():
    args = parse_args()
    client = await create_client()

    commands = {
        "single": cmd_single,
        "burst": cmd_burst,
        "sustained": cmd_sustained,
        "ramp": cmd_ramp,
        "stress": cmd_stress,
        "status": cmd_status,
    }

    handler = commands.get(args.command)
    if handler:
        await handler(client, args)
    else:
        logger.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    asyncio.run(main())
