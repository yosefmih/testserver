#!/usr/bin/env python3
"""
Simple Temporal worker for testing KEDA autoscaling.
Demonstrates basic workflow and activity patterns.
"""

import asyncio
import logging
import os
import math
import random
from datetime import timedelta
from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio import activity
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

# Load environment variables from .env file (development only)
if os.path.exists('.env'):
    load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Temporal configuration - will be validated when worker starts
def get_temporal_config():
    """Get and validate Temporal configuration from environment."""
    host = os.getenv("TEMPORAL_HOST")  # e.g., "your-namespace.tmprl.cloud:7233"
    namespace = os.getenv("TEMPORAL_NAMESPACE")  # e.g., "your-namespace.accounting"
    task_queue = os.getenv("TASK_QUEUE")  # e.g., "order-processing-queue"
    api_key = os.getenv("TEMPORAL_API_KEY")  # Required for Temporal Cloud
    
    # Validate required environment variables
    missing = []
    if not host:
        missing.append("TEMPORAL_HOST")
    if not namespace:
        missing.append("TEMPORAL_NAMESPACE") 
    if not task_queue:
        missing.append("TASK_QUEUE")
    if not api_key:
        missing.append("TEMPORAL_API_KEY")
    
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    
    return host, namespace, task_queue, api_key


@activity.defn
def mc_simulate_shard(params: dict) -> dict:
    """
    Monte Carlo shard simulation activity.
    Computes option payoffs over a batch of paths using GBM.
    Heavy CPU/memory lives here (sync def to run off the event loop).
    """
    # Required params
    shard_index: int = params["shard_index"]
    paths_in_shard: int = params["paths_in_shard"]
    steps_per_path: int = params["steps_per_path"]
    s0: float = float(params.get("S0", 100.0))
    k: float = float(params.get("K", 100.0))
    mu: float = float(params.get("mu", 0.05))
    sigma: float = float(params.get("sigma", 0.2))
    r: float = float(params.get("r", 0.01))
    t: float = float(params.get("T", 1.0))
    payoff_type: str = params.get("payoff", "european_call")
    discount: bool = bool(params.get("discount", True))
    master_seed: int = int(params.get("master_seed", 42))
    heartbeat_every: int = int(params.get("heartbeat_every_paths", 10_000))
    store_full_paths: bool = bool(params.get("store_full_paths", False))

    # Time step
    dt: float = t / float(steps_per_path)
    drift_dt: float = (mu - 0.5 * sigma * sigma) * dt
    vol_sqrt_dt: float = sigma * math.sqrt(dt)

    # RNG per-shard for determinism
    seed = (master_seed * 1_000_003) ^ (shard_index * 97_019)
    rng = random.Random(seed)

    # Aggregates
    count = 0
    sum_payoff = 0.0
    sumsq_payoff = 0.0

    # Optional memory-heavy storage (for testing memory footprint)
    # Allocate a dense list for full paths if requested
    # Size: paths_in_shard * steps_per_path floats
    full_paths = None
    if store_full_paths:
        try:
            full_paths = [0.0] * (paths_in_shard * steps_per_path)
        except MemoryError as e:
            # Surface a clear error with sizing info
            raise RuntimeError(
                f"OOM allocating full_paths: paths={paths_in_shard}, steps={steps_per_path}, bytes~={(paths_in_shard*steps_per_path*8)}"
            ) from e

    # Simulation loop
    for p in range(paths_in_shard):
        s = s0
        running_sum = 0.0
        base_index = p * steps_per_path if store_full_paths else 0

        for step in range(steps_per_path):
            z = rng.gauss(0.0, 1.0)
            s = s * math.exp(drift_dt + vol_sqrt_dt * z)
            running_sum += s
            if store_full_paths:
                full_paths[base_index + step] = s

        if payoff_type == "european_call":
            payoff = max(s - k, 0.0)
        elif payoff_type == "european_put":
            payoff = max(k - s, 0.0)
        elif payoff_type == "asian_call":
            avg_price = running_sum / float(steps_per_path)
            payoff = max(avg_price - k, 0.0)
        elif payoff_type == "asian_put":
            avg_price = running_sum / float(steps_per_path)
            payoff = max(k - avg_price, 0.0)
        else:
            raise ValueError(f"Unsupported payoff type: {payoff_type}")

        if discount:
            payoff *= math.exp(-r * t)

        count += 1
        sum_payoff += payoff
        sumsq_payoff += payoff * payoff

        if heartbeat_every > 0 and (count % heartbeat_every == 0):
            try:
                activity.heartbeat({"shard_index": shard_index, "processed_paths": count})
            except Exception:
                # Heartbeat best-effort; ignore heartbeat failures
                pass

    return {
        "shard_index": shard_index,
        "count": count,
        "sum_payoff": sum_payoff,
        "sumsq_payoff": sumsq_payoff,
    }


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _black_scholes_call_price(s0: float, k: float, r: float, sigma: float, t: float) -> float:
    if t <= 0.0 or sigma <= 0.0:
        return max(s0 - k, 0.0)
    d1 = (math.log(s0 / k) + (r + 0.5 * sigma * sigma) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    return s0 * _norm_cdf(d1) - k * math.exp(-r * t) * _norm_cdf(d2)


@workflow.defn
class MonteCarloWorkflow:
    """
    Orchestrates Monte Carlo shard activities and aggregates results.
    """

    @workflow.run
    async def run(self, params: dict) -> dict:
        # Extract and default parameters
        num_paths_total: int = int(params.get("num_paths_total", 2_000_000))
        steps_per_path: int = int(params.get("steps_per_path", 252))
        paths_per_shard: int = int(params.get("paths_per_shard", 200_000))
        max_concurrency: int = int(params.get("max_concurrency", 0))  # 0 = submit all
        heartbeat_every: int = int(params.get("heartbeat_every_paths", 10_000))

        # Financial params
        s0: float = float(params.get("S0", 100.0))
        k: float = float(params.get("K", 100.0))
        mu: float = float(params.get("mu", 0.05))
        sigma: float = float(params.get("sigma", 0.2))
        r: float = float(params.get("r", 0.01))
        t: float = float(params.get("T", 1.0))
        payoff_type: str = params.get("payoff", "european_call")
        discount: bool = bool(params.get("discount", True))
        master_seed: int = int(params.get("master_seed", 42))
        store_full_paths: bool = bool(params.get("store_full_paths", False))

        if num_paths_total <= 0 or steps_per_path <= 0 or paths_per_shard <= 0:
            raise ValueError("num_paths_total, steps_per_path, and paths_per_shard must be > 0")

        # Build shard specs
        num_shards = (num_paths_total + paths_per_shard - 1) // paths_per_shard
        shard_futures = []
        submitted = 0

        for shard_index in range(num_shards):
            remaining = num_paths_total - submitted
            take = paths_per_shard if remaining > paths_per_shard else remaining
            submitted += take

            shard_params = {
                "shard_index": shard_index,
                "paths_in_shard": take,
                "steps_per_path": steps_per_path,
                "S0": s0,
                "K": k,
                "mu": mu,
                "sigma": sigma,
                "r": r,
                "T": t,
                "payoff": payoff_type,
                "discount": discount,
                "master_seed": master_seed,
                "heartbeat_every_paths": heartbeat_every,
                "store_full_paths": store_full_paths,
            }

            # Timeout heuristic: scale with work size
            seconds = max(60, int(steps_per_path * take / 50_000))

            fut = workflow.execute_activity(
                mc_simulate_shard,
                shard_params,
                start_to_close_timeout=timedelta(seconds=seconds),
                heartbeat_timeout=timedelta(seconds=max(30, heartbeat_every // 1000 + 30)),
                retry_policy={
                    "initial_interval": timedelta(seconds=5),
                    "backoff_coefficient": 2.0,
                    "maximum_interval": timedelta(minutes=2),
                    "maximum_attempts": 5,
                },
            )
            shard_futures.append(fut)

        # Await all
        results = await asyncio.gather(*shard_futures)

        # Aggregate
        total_count = 0
        total_sum = 0.0
        total_sumsq = 0.0
        for part in results:
            total_count += int(part["count"])
            total_sum += float(part["sum_payoff"])
            total_sumsq += float(part["sumsq_payoff"])

        mean = total_sum / total_count if total_count else 0.0
        variance = (total_sumsq / total_count - mean * mean) if total_count else 0.0
        stddev = math.sqrt(max(variance, 0.0))
        stderr = stddev / math.sqrt(total_count) if total_count else 0.0

        out = {
            "num_paths_total": total_count,
            "steps_per_path": steps_per_path,
            "payoff": payoff_type,
            "estimate": mean,
            "stddev": stddev,
            "stderr": stderr,
            "confidence_95": [mean - 1.96 * stderr, mean + 1.96 * stderr],
            "shards": len(results),
        }

        # Optional analytic check: Black-Scholes for european call only, risk-neutral drift
        if payoff_type == "european_call":
            out["black_scholes_call"] = _black_scholes_call_price(s0, k, r, sigma, t)
            out["abs_error_vs_bs"] = abs(out["estimate"] - out["black_scholes_call"])  # type: ignore

        return out


@activity.defn
async def process_order_activity(order_id: str) -> str:
    """
    Simple activity that simulates order processing.
    """
    logger.info(f"Processing order: {order_id}")
    
    # Simulate some work
    await asyncio.sleep(2)
    
    result = f"Order {order_id} processed successfully"
    logger.info(result)
    return result


@activity.defn
async def send_notification_activity(message: str) -> str:
    """
    Simple activity that simulates sending a notification.
    """
    logger.info(f"Sending notification: {message}")
    
    # Simulate notification sending
    await asyncio.sleep(1)
    
    result = f"Notification sent: {message}"
    logger.info(result)
    return result


@workflow.defn
class OrderProcessingWorkflow:
    """
    Simple workflow that processes orders and sends notifications.
    """

    @workflow.run
    async def run(self, order_id: str) -> str:
        logger.info(f"Starting order processing workflow for order: {order_id}")

        # Process the order
        order_result = await workflow.execute_activity(
            process_order_activity,
            order_id,
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Send notification
        notification_result = await workflow.execute_activity(
            send_notification_activity,
            f"Order {order_id} has been processed",
            start_to_close_timeout=timedelta(seconds=30),
        )

        final_result = f"Workflow completed: {order_result}, {notification_result}"
        logger.info(final_result)
        return final_result


async def create_worker():
    """
    Create and configure the Temporal worker.
    """
    # Get and validate configuration
    host, namespace, task_queue, api_key = get_temporal_config()
    
    logger.info(f"Connecting to Temporal at {host}")
    logger.info(f"Using namespace: {namespace}")
    logger.info(f"Using task queue: {task_queue}")

    # Create client with API key for Temporal Cloud
    client = await Client.connect(
        host, 
        namespace=namespace,
        api_key=api_key,
        tls=True  # Enable TLS for Temporal Cloud
    )

    # Create worker with workflows and activities
    activity_threads = int(os.getenv("ACTIVITY_THREADS", "8"))
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[OrderProcessingWorkflow, MonteCarloWorkflow],
        activities=[process_order_activity, send_notification_activity, mc_simulate_shard],
        activity_executor=ThreadPoolExecutor(max_workers=activity_threads),
    )

    logger.info("Temporal worker created successfully")
    return worker


async def main():
    """
    Main function to start the Temporal worker.
    """
    logger.info("Starting Temporal worker...")
    
    try:
        worker = await create_worker()
        # Get task queue name from config
        _, _, task_queue, _ = get_temporal_config()
        logger.info(f"Worker started and listening on task queue: {task_queue}")
        
        # Run the worker
        await worker.run()
        
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())