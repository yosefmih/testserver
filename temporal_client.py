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
from temporal_worker import OrderProcessingWorkflow
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
        
    else:
        logger.error(f"Unknown mode: {mode}")


if __name__ == "__main__":
    asyncio.run(main())