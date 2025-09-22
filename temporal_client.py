#!/usr/bin/env python3
"""
Temporal client for starting workflows and managing tasks.
This script demonstrates how to submit workflows to create task queue backlog for KEDA testing.
"""

import asyncio
import logging
import os
import uuid
from temporalio.client import Client
from temporal_worker import OrderProcessingWorkflow, MonteCarloWorkflow
from dotenv import load_dotenv

# Load environment variables from .env file (development only)
if os.path.exists('.env'):
    load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import configuration function from worker
from temporal_worker import get_temporal_config


async def create_client():
    """Create and return a Temporal client."""
    # Get and validate configuration
    host, namespace, task_queue, api_key = get_temporal_config()
    
    logger.info(f"Connecting to Temporal at {host}")
    
    # Create client with API key for Temporal Cloud
    client = await Client.connect(
        host, 
        namespace=namespace,
        api_key=api_key,
        tls=True  # Enable TLS for Temporal Cloud
    )
    logger.info(f"Connected to Temporal namespace: {namespace}")
    return client, task_queue


async def start_mc_workflow(client: Client, task_queue: str, params: dict, workflow_id_suffix: str = ""):
    """Start a Monte Carlo workflow with given params."""
    wf_id = f"mc-workflow-{uuid.uuid4().hex[:8]}"
    if workflow_id_suffix:
        wf_id = f"{wf_id}-{workflow_id_suffix}"
    logger.info(f"Starting Monte Carlo workflow id={wf_id} params={{'num_paths_total': {params.get('num_paths_total')}, 'steps_per_path': {params.get('steps_per_path')}, 'paths_per_shard': {params.get('paths_per_shard')}}}")
    handle = await client.start_workflow(
        MonteCarloWorkflow.run,
        params,
        id=wf_id,
        task_queue=task_queue,
    )
    return handle


def mc_default_params() -> dict:
    return {
        "num_paths_total": int(os.getenv("MC_NUM_PATHS", "2000000")),
        "steps_per_path": int(os.getenv("MC_STEPS", "252")),
        "paths_per_shard": int(os.getenv("MC_PATHS_PER_SHARD", "200000")),
        "max_concurrency": int(os.getenv("MC_MAX_CONCURRENCY", "0")),
        "heartbeat_every_paths": int(os.getenv("MC_HEARTBEAT_EVERY", "10000")),
        "S0": float(os.getenv("MC_S0", "100.0")),
        "K": float(os.getenv("MC_K", "100.0")),
        "mu": float(os.getenv("MC_MU", "0.05")),
        "sigma": float(os.getenv("MC_SIGMA", "0.2")),
        "r": float(os.getenv("MC_R", "0.01")),
        "T": float(os.getenv("MC_T", "1.0")),
        "payoff": os.getenv("MC_PAYOFF", "european_call"),
        "discount": True,
        "master_seed": int(os.getenv("MC_SEED", "42")),
        "store_full_paths": os.getenv("MC_STORE_FULL_PATHS", "false").lower() in ("1", "true", "yes"),
    }


async def start_single_workflow(client: Client, task_queue: str, order_id: str = None):
    """Start a single order processing workflow."""
    if not order_id:
        order_id = f"order-{uuid.uuid4().hex[:8]}"
    
    logger.info(f"Starting workflow for order: {order_id}")
    
    handle = await client.start_workflow(
        OrderProcessingWorkflow.run,
        order_id,
        id=f"order-workflow-{order_id}",
        task_queue=task_queue,
    )
    
    logger.info(f"Workflow started with ID: {handle.id}")
    return handle


async def start_multiple_workflows(client: Client, task_queue: str, count: int = 10):
    """Start multiple workflows to create backlog for KEDA testing."""
    logger.info(f"Starting {count} workflows to create task queue backlog...")
    
    handles = []
    for i in range(count):
        order_id = f"bulk-order-{i:03d}-{uuid.uuid4().hex[:6]}"
        handle = await start_single_workflow(client, task_queue, order_id)
        handles.append(handle)
    
    logger.info(f"Started {len(handles)} workflows")
    return handles


async def wait_for_workflows(handles):
    """Wait for all workflows to complete and log results."""
    logger.info(f"Waiting for {len(handles)} workflows to complete...")
    
    results = []
    for i, handle in enumerate(handles):
        try:
            result = await handle.result()
            logger.info(f"Workflow {i+1}/{len(handles)} completed: {result}")
            results.append(result)
        except Exception as e:
            logger.error(f"Workflow {i+1}/{len(handles)} failed: {e}")
            results.append(f"Failed: {e}")
    
    logger.info(f"All {len(handles)} workflows completed")
    return results


async def create_continuous_load(client: Client, task_queue: str, interval_seconds: int = 5):
    """Create continuous workflow submissions for sustained load testing."""
    logger.info(f"Starting continuous load generation (interval: {interval_seconds}s)")
    logger.info("Press Ctrl+C to stop...")
    
    try:
        counter = 0
        while True:
            counter += 1
            order_id = f"continuous-order-{counter:04d}-{uuid.uuid4().hex[:6]}"
            await start_single_workflow(client, task_queue, order_id)
            
            if counter % 10 == 0:
                logger.info(f"Submitted {counter} workflows so far...")
            
            await asyncio.sleep(interval_seconds)
            
    except KeyboardInterrupt:
        logger.info(f"Stopped continuous load generation after {counter} workflows")


async def main():
    """Main function with different workflow submission modes."""
    import sys
    
    client, task_queue = await create_client()
    
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python temporal_client.py single [order_id]")
        print("  python temporal_client.py bulk [count]")
        print("  python temporal_client.py continuous [interval_seconds]")
        print("  python temporal_client.py wait")
        print("  python temporal_client.py mc single [num_paths steps paths_per_shard]")
        print("  python temporal_client.py mc bulk [count]")
        print("  python temporal_client.py mc continuous [interval_seconds]")
        print("  python temporal_client.py mc validate")
        return
    
    mode = sys.argv[1]
    
    if mode == "single":
        order_id = sys.argv[2] if len(sys.argv) > 2 else None
        handle = await start_single_workflow(client, task_queue, order_id)
        result = await handle.result()
        logger.info(f"Final result: {result}")
        
    elif mode == "bulk":
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        handles = await start_multiple_workflows(client, task_queue, count)
        await wait_for_workflows(handles)
        
    elif mode == "continuous":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        await create_continuous_load(client, task_queue, interval)
        
    elif mode == "wait":
        # Just demonstrate the client connection
        logger.info("Client connected successfully. Use other modes to submit workflows.")
    elif mode == "mc":
        if len(sys.argv) < 3:
            logger.error("mc requires a subcommand: single|bulk|continuous|validate")
            return
        sub = sys.argv[2]
        if sub == "single":
            params = mc_default_params()
            # Optional positional overrides
            if len(sys.argv) > 3:
                params["num_paths_total"] = int(sys.argv[3])
            if len(sys.argv) > 4:
                params["steps_per_path"] = int(sys.argv[4])
            if len(sys.argv) > 5:
                params["paths_per_shard"] = int(sys.argv[5])
            handle = await start_mc_workflow(client, task_queue, params)
            result = await handle.result()
            logger.info(f"Monte Carlo result: estimate={result.get('estimate')} stddev={result.get('stddev')} stderr={result.get('stderr')} shards={result.get('shards')}")
            if "black_scholes_call" in result:
                logger.info(f"BS={result['black_scholes_call']} abs_err={result.get('abs_error_vs_bs')}")
        elif sub == "bulk":
            count = int(sys.argv[3]) if len(sys.argv) > 3 else 10
            params = mc_default_params()
            handles = []
            for i in range(count):
                handle = await start_mc_workflow(client, task_queue, params, workflow_id_suffix=f"{i:03d}")
                handles.append(handle)
            await wait_for_workflows(handles)
        elif sub == "continuous":
            interval = int(sys.argv[3]) if len(sys.argv) > 3 else 5
            logger.info(f"Starting continuous Monte Carlo submissions every {interval}s. Ctrl+C to stop.")
            try:
                idx = 0
                params = mc_default_params()
                while True:
                    idx += 1
                    await start_mc_workflow(client, task_queue, params, workflow_id_suffix=f"loop-{idx:06d}")
                    if idx % 10 == 0:
                        logger.info(f"Submitted {idx} Monte Carlo workflows so far...")
                    await asyncio.sleep(interval)
            except KeyboardInterrupt:
                logger.info(f"Stopped after submitting {idx} Monte Carlo workflows")
        elif sub == "validate":
            params = mc_default_params()
            params["num_paths_total"] = max(200_000, int(params["num_paths_total"]))
            params["payoff"] = "european_call"
            handle = await start_mc_workflow(client, task_queue, params, workflow_id_suffix="validate")
            result = await handle.result()
            logger.info(f"Validate: MC={result.get('estimate')} BS={result.get('black_scholes_call')} abs_err={result.get('abs_error_vs_bs')} stderr={result.get('stderr')}")
        else:
            logger.error(f"Unknown mc subcommand: {sub}")
        
    else:
        logger.error(f"Unknown mode: {mode}")


if __name__ == "__main__":
    asyncio.run(main())