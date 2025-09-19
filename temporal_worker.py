#!/usr/bin/env python3
"""
Simple Temporal worker for testing KEDA autoscaling.
Demonstrates basic workflow and activity patterns.
"""

import asyncio
import logging
import os
from datetime import timedelta
from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio import activity
from dotenv import load_dotenv

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
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[OrderProcessingWorkflow],
        activities=[process_order_activity, send_notification_activity],
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