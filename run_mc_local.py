#!/usr/bin/env python3
"""
Run Monte Carlo workflow locally using Temporal's in-process test server.
This does not require external Temporal credentials.
"""

import asyncio
import logging

from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from concurrent.futures import ThreadPoolExecutor

from temporal_worker import MonteCarloWorkflow, mc_simulate_shard


async def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    params = {
        "num_paths_total": 200_000,
        "steps_per_path": 128,
        "paths_per_shard": 50_000,
        "S0": 100.0,
        "K": 100.0,
        "mu": 0.05,
        "sigma": 0.2,
        "r": 0.01,
        "T": 1.0,
        "payoff": "european_call",
        "discount": True,
        "master_seed": 42,
        "heartbeat_every_paths": 10_000,
        "store_full_paths": False,
    }

    # Start ephemeral Temporal dev environment
    async with await WorkflowEnvironment.start_time_skipping() as env:
        client = env.client
        # Start worker and execute workflow
        async with Worker(
            client,
            task_queue="mc-test",
            workflows=[MonteCarloWorkflow],
            activities=[mc_simulate_shard],
            activity_executor=ThreadPoolExecutor(max_workers=8),
        ):
            result = await client.execute_workflow(
                MonteCarloWorkflow.run,
                params,
                id="mc-test-local",
                task_queue="mc-test",
            )
            logger.info("Monte Carlo result: %s", result)


if __name__ == "__main__":
    asyncio.run(main())


