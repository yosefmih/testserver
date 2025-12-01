#!/usr/bin/env python3
"""
Temporal worker for testing KEDA autoscaling.
Provides CPU and memory intensive workloads to stress test autoscaling.
"""

import asyncio
import logging
import os
import random
import hashlib
import time
import math
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from typing import List

from temporalio import workflow, activity
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.common import RetryPolicy
from dotenv import load_dotenv

if os.path.exists('.env'):
    load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE", "stress-test-queue")


def get_temporal_config():
    host = os.getenv("TEMPORAL_HOST")
    namespace = os.getenv("TEMPORAL_NAMESPACE")
    api_key = os.getenv("TEMPORAL_API_KEY")

    missing = []
    if not host:
        missing.append("TEMPORAL_HOST")
    if not namespace:
        missing.append("TEMPORAL_NAMESPACE")
    if not api_key:
        missing.append("TEMPORAL_API_KEY")

    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    return host, namespace, api_key


@activity.defn
def cpu_intensive_activity(task_id: str, iterations: int) -> dict:
    """
    CPU-bound activity that performs hash computations.
    iterations: controls intensity (1M iterations ≈ 1-2 seconds on typical CPU)
    """
    start = time.time()
    logger.info(f"[{task_id}] Starting CPU work: {iterations:,} iterations")

    data = f"{task_id}-{time.time()}"
    for i in range(iterations):
        data = hashlib.sha256(data.encode()).hexdigest()
        if i % 100000 == 0:
            activity.heartbeat(f"iteration {i}")

    elapsed = time.time() - start
    result = {
        "task_id": task_id,
        "iterations": iterations,
        "duration_ms": int(elapsed * 1000),
        "hash_sample": data[:16]
    }
    logger.info(f"[{task_id}] CPU work completed in {elapsed:.2f}s")
    return result


@activity.defn
def memory_intensive_activity(task_id: str, size_mb: int) -> dict:
    """
    Memory-bound activity that allocates and processes large arrays.
    size_mb: amount of memory to allocate and process
    """
    start = time.time()
    logger.info(f"[{task_id}] Starting memory work: {size_mb}MB allocation")

    chunk_size = 1024 * 1024  # 1MB chunks
    chunks = []

    for i in range(size_mb):
        chunk = bytearray(random.getrandbits(8) for _ in range(chunk_size))
        checksum = sum(chunk) % 256
        chunks.append((len(chunk), checksum))
        activity.heartbeat(f"allocated {i+1}MB")

    total_checksum = sum(c[1] for c in chunks)

    elapsed = time.time() - start
    result = {
        "task_id": task_id,
        "size_mb": size_mb,
        "duration_ms": int(elapsed * 1000),
        "checksum": total_checksum
    }
    logger.info(f"[{task_id}] Memory work completed in {elapsed:.2f}s")
    return result


@activity.defn
def prime_calculation_activity(task_id: str, limit: int) -> dict:
    """
    CPU-bound activity using prime number sieve.
    limit: find all primes up to this number (1M ≈ 1-2 seconds)
    """
    start = time.time()
    logger.info(f"[{task_id}] Finding primes up to {limit:,}")

    sieve = [True] * (limit + 1)
    sieve[0] = sieve[1] = False

    for i in range(2, int(math.sqrt(limit)) + 1):
        if sieve[i]:
            for j in range(i*i, limit + 1, i):
                sieve[j] = False
        if i % 10000 == 0:
            activity.heartbeat(f"sieve at {i}")

    prime_count = sum(sieve)
    largest_prime = max(i for i, is_prime in enumerate(sieve) if is_prime)

    elapsed = time.time() - start
    result = {
        "task_id": task_id,
        "limit": limit,
        "prime_count": prime_count,
        "largest_prime": largest_prime,
        "duration_ms": int(elapsed * 1000)
    }
    logger.info(f"[{task_id}] Found {prime_count:,} primes in {elapsed:.2f}s")
    return result


@activity.defn
def matrix_multiplication_activity(task_id: str, size: int) -> dict:
    """
    CPU-bound activity with matrix operations.
    size: matrix dimension (500 ≈ 2-3 seconds)
    """
    start = time.time()
    logger.info(f"[{task_id}] Matrix multiplication: {size}x{size}")

    A = [[random.random() for _ in range(size)] for _ in range(size)]
    B = [[random.random() for _ in range(size)] for _ in range(size)]
    C = [[0.0] * size for _ in range(size)]

    for i in range(size):
        for j in range(size):
            for k in range(size):
                C[i][j] += A[i][k] * B[k][j]
        if i % 50 == 0:
            activity.heartbeat(f"row {i}")

    trace = sum(C[i][i] for i in range(size))

    elapsed = time.time() - start
    result = {
        "task_id": task_id,
        "matrix_size": size,
        "trace": trace,
        "duration_ms": int(elapsed * 1000)
    }
    logger.info(f"[{task_id}] Matrix multiplication completed in {elapsed:.2f}s")
    return result


@activity.defn
def fibonacci_activity(task_id: str, n: int) -> dict:
    """
    CPU-bound recursive fibonacci (intentionally inefficient for load testing).
    n: fibonacci number to calculate (35-40 range is good for testing)
    """
    start = time.time()
    logger.info(f"[{task_id}] Calculating fibonacci({n})")

    def fib(x):
        if x <= 1:
            return x
        return fib(x-1) + fib(x-2)

    result_value = fib(n)

    elapsed = time.time() - start
    result = {
        "task_id": task_id,
        "n": n,
        "result": result_value,
        "duration_ms": int(elapsed * 1000)
    }
    logger.info(f"[{task_id}] fibonacci({n}) = {result_value} in {elapsed:.2f}s")
    return result


@activity.defn
async def io_simulation_activity(task_id: str, duration_seconds: float) -> dict:
    """
    I/O-bound activity simulating external API calls or database operations.
    """
    start = time.time()
    logger.info(f"[{task_id}] Simulating I/O for {duration_seconds}s")

    await asyncio.sleep(duration_seconds)

    elapsed = time.time() - start
    return {
        "task_id": task_id,
        "simulated_duration": duration_seconds,
        "actual_duration_ms": int(elapsed * 1000)
    }


@workflow.defn
class StressTestWorkflow:
    """
    Configurable stress test workflow that chains multiple intensive activities.
    """

    @workflow.run
    async def run(self, params: dict) -> dict:
        task_id = params.get("task_id", "unknown")
        intensity = params.get("intensity", "medium")
        workflow_type = params.get("type", "mixed")

        workflow.logger.info(f"Starting stress test: {task_id}, intensity={intensity}, type={workflow_type}")

        config = self._get_intensity_config(intensity)
        results = []

        if workflow_type == "cpu":
            results = await self._run_cpu_intensive(task_id, config)
        elif workflow_type == "memory":
            results = await self._run_memory_intensive(task_id, config)
        elif workflow_type == "mixed":
            results = await self._run_mixed(task_id, config)
        elif workflow_type == "sequential":
            results = await self._run_sequential(task_id, config)
        else:
            results = await self._run_mixed(task_id, config)

        return {
            "task_id": task_id,
            "intensity": intensity,
            "type": workflow_type,
            "activity_results": results
        }

    def _get_intensity_config(self, intensity: str) -> dict:
        configs = {
            "light": {
                "hash_iterations": 100_000,
                "memory_mb": 10,
                "prime_limit": 100_000,
                "matrix_size": 100,
                "fib_n": 30,
                "io_duration": 1.0
            },
            "medium": {
                "hash_iterations": 500_000,
                "memory_mb": 50,
                "prime_limit": 500_000,
                "matrix_size": 300,
                "fib_n": 35,
                "io_duration": 3.0
            },
            "heavy": {
                "hash_iterations": 2_000_000,
                "memory_mb": 100,
                "prime_limit": 2_000_000,
                "matrix_size": 500,
                "fib_n": 38,
                "io_duration": 5.0
            },
            "extreme": {
                "hash_iterations": 5_000_000,
                "memory_mb": 200,
                "prime_limit": 5_000_000,
                "matrix_size": 700,
                "fib_n": 40,
                "io_duration": 10.0
            }
        }
        return configs.get(intensity, configs["medium"])

    async def _run_cpu_intensive(self, task_id: str, config: dict) -> list:
        results = []

        hash_result = await workflow.execute_activity(
            cpu_intensive_activity,
            args=[f"{task_id}-hash", config["hash_iterations"]],
            start_to_close_timeout=timedelta(minutes=10),
            heartbeat_timeout=timedelta(seconds=60),
        )
        results.append({"activity": "cpu_hash", "result": hash_result})

        prime_result = await workflow.execute_activity(
            prime_calculation_activity,
            args=[f"{task_id}-prime", config["prime_limit"]],
            start_to_close_timeout=timedelta(minutes=10),
            heartbeat_timeout=timedelta(seconds=60),
        )
        results.append({"activity": "prime", "result": prime_result})

        fib_result = await workflow.execute_activity(
            fibonacci_activity,
            args=[f"{task_id}-fib", config["fib_n"]],
            start_to_close_timeout=timedelta(minutes=10),
            heartbeat_timeout=timedelta(seconds=60),
        )
        results.append({"activity": "fibonacci", "result": fib_result})

        return results

    async def _run_memory_intensive(self, task_id: str, config: dict) -> list:
        mem_result = await workflow.execute_activity(
            memory_intensive_activity,
            args=[f"{task_id}-mem", config["memory_mb"]],
            start_to_close_timeout=timedelta(minutes=10),
            heartbeat_timeout=timedelta(seconds=60),
        )
        return [{"activity": "memory", "result": mem_result}]

    async def _run_mixed(self, task_id: str, config: dict) -> list:
        results = []

        hash_result = await workflow.execute_activity(
            cpu_intensive_activity,
            args=[f"{task_id}-hash", config["hash_iterations"]],
            start_to_close_timeout=timedelta(minutes=10),
            heartbeat_timeout=timedelta(seconds=60),
        )
        results.append({"activity": "cpu_hash", "result": hash_result})

        matrix_result = await workflow.execute_activity(
            matrix_multiplication_activity,
            args=[f"{task_id}-matrix", config["matrix_size"]],
            start_to_close_timeout=timedelta(minutes=10),
            heartbeat_timeout=timedelta(seconds=60),
        )
        results.append({"activity": "matrix", "result": matrix_result})

        io_result = await workflow.execute_activity(
            io_simulation_activity,
            args=[f"{task_id}-io", config["io_duration"]],
            start_to_close_timeout=timedelta(minutes=10),
        )
        results.append({"activity": "io", "result": io_result})

        return results

    async def _run_sequential(self, task_id: str, config: dict) -> list:
        """Run all activity types sequentially for maximum single-workflow duration."""
        results = []

        activities = [
            (cpu_intensive_activity, [f"{task_id}-hash", config["hash_iterations"]]),
            (prime_calculation_activity, [f"{task_id}-prime", config["prime_limit"]]),
            (matrix_multiplication_activity, [f"{task_id}-matrix", config["matrix_size"]]),
            (memory_intensive_activity, [f"{task_id}-mem", config["memory_mb"]]),
            (fibonacci_activity, [f"{task_id}-fib", config["fib_n"]]),
            (io_simulation_activity, [f"{task_id}-io", config["io_duration"]]),
        ]

        for activity_fn, args in activities:
            result = await workflow.execute_activity(
                activity_fn,
                args=args,
                start_to_close_timeout=timedelta(minutes=10),
                heartbeat_timeout=timedelta(seconds=60),
            )
            results.append({"activity": activity_fn.__name__, "result": result})

        return results


@workflow.defn
class BurstWorkflow:
    """
    Simple workflow that runs a single configurable activity.
    Use this for high-volume burst testing.
    """

    @workflow.run
    async def run(self, params: dict) -> dict:
        task_id = params.get("task_id", "burst")
        activity_type = params.get("activity", "cpu")
        intensity = params.get("intensity", "medium")

        config = {
            "light": {"iterations": 100_000, "size": 100, "duration": 1.0},
            "medium": {"iterations": 500_000, "size": 300, "duration": 3.0},
            "heavy": {"iterations": 2_000_000, "size": 500, "duration": 5.0},
        }.get(intensity, {"iterations": 500_000, "size": 300, "duration": 3.0})

        if activity_type == "cpu":
            result = await workflow.execute_activity(
                cpu_intensive_activity,
                args=[task_id, config["iterations"]],
                start_to_close_timeout=timedelta(minutes=5),
                heartbeat_timeout=timedelta(seconds=30),
            )
        elif activity_type == "matrix":
            result = await workflow.execute_activity(
                matrix_multiplication_activity,
                args=[task_id, config["size"]],
                start_to_close_timeout=timedelta(minutes=5),
                heartbeat_timeout=timedelta(seconds=30),
            )
        elif activity_type == "io":
            result = await workflow.execute_activity(
                io_simulation_activity,
                args=[task_id, config["duration"]],
                start_to_close_timeout=timedelta(minutes=5),
            )
        else:
            result = await workflow.execute_activity(
                cpu_intensive_activity,
                args=[task_id, config["iterations"]],
                start_to_close_timeout=timedelta(minutes=5),
                heartbeat_timeout=timedelta(seconds=30),
            )

        return {"task_id": task_id, "activity": activity_type, "result": result}


async def create_worker():
    host, namespace, api_key = get_temporal_config()

    logger.info(f"Connecting to Temporal at {host}")
    logger.info(f"Namespace: {namespace}")
    logger.info(f"Task queue: {TASK_QUEUE}")

    client = await Client.connect(
        host,
        namespace=namespace,
        api_key=api_key,
        tls=True
    )

    max_concurrent = int(os.getenv("MAX_CONCURRENT_ACTIVITIES", "10"))
    thread_pool_size = int(os.getenv("THREAD_POOL_SIZE", "4"))

    logger.info(f"Max concurrent activities: {max_concurrent}")
    logger.info(f"Thread pool size: {thread_pool_size}")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[StressTestWorkflow, BurstWorkflow],
        activities=[
            cpu_intensive_activity,
            memory_intensive_activity,
            prime_calculation_activity,
            matrix_multiplication_activity,
            fibonacci_activity,
            io_simulation_activity,
        ],
        max_concurrent_activities=max_concurrent,
        activity_executor=ThreadPoolExecutor(max_workers=thread_pool_size),
    )

    logger.info(f"Worker created for task queue: {TASK_QUEUE}")
    return worker


async def main():
    logger.info("Starting Temporal stress test worker...")

    try:
        worker = await create_worker()
        logger.info("Worker running. Press Ctrl+C to stop.")
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
