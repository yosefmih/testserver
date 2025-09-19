#!/usr/bin/env python3
"""
Simple Temporal worker for testing KEDA autoscaling.
Demonstrates basic workflow and activity patterns.
"""

import asyncio
import logging
import os
from datetime import timedelta
from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Temporal configuration - all from environment for Temporal Cloud
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST")  # e.g., "your-namespace.tmprl.cloud:7233"
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE")  # e.g., "your-namespace.accounting"
TASK_QUEUE = os.getenv("TASK_QUEUE")  # e.g., "order-processing-queue"
TEMPORAL_API_KEY = os.getenv("TEMPORAL_API_KEY")  # Required for Temporal Cloud

# Validate required environment variables
if not TEMPORAL_HOST:
    raise ValueError("TEMPORAL_HOST environment variable is required")
if not TEMPORAL_NAMESPACE:
    raise ValueError("TEMPORAL_NAMESPACE environment variable is required")
if not TASK_QUEUE:
    raise ValueError("TASK_QUEUE environment variable is required")
if not TEMPORAL_API_KEY:
    raise ValueError("TEMPORAL_API_KEY environment variable is required for Temporal Cloud")


@activity
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


@activity
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


@workflow
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
    logger.info(f"Connecting to Temporal at {TEMPORAL_HOST}")
    logger.info(f"Using namespace: {TEMPORAL_NAMESPACE}")
    logger.info(f"Using task queue: {TASK_QUEUE}")

    # Create client with API key for Temporal Cloud
    client = await Client.connect(
        TEMPORAL_HOST, 
        namespace=TEMPORAL_NAMESPACE,
        api_key=TEMPORAL_API_KEY
    )

    # Create worker with workflows and activities
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
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
        logger.info(f"Worker started and listening on task queue: {TASK_QUEUE}")
        
        # Run the worker
        await worker.run()
        
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())