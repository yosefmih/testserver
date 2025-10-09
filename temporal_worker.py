#!/usr/bin/env python3
"""
Simple Temporal worker for testing KEDA autoscaling.
Demonstrates basic workflow and activity patterns.
"""

import asyncio
import logging
import os
from datetime import timedelta, datetime
from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio import activity
from temporalio.common import RetryPolicy
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
import random

# Load environment variables from .env file (development only)
if os.path.exists('.env'):
    load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Temporal configuration - will be validated when worker starts
ORDER_PROCESSING_TASK_QUEUE = "order-processing-queue-v2"


def get_temporal_config():
    """Get and validate Temporal configuration from environment."""
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
    logger.info(f"Sending notification: {message}")
    await asyncio.sleep(1)
    result = f"Notification sent: {message}"
    logger.info(result)
    return result


@activity.defn
async def validate_inventory_activity(order_id: str, items: list) -> dict:
    logger.info(f"Validating inventory for order {order_id}: {items}")
    await asyncio.sleep(random.uniform(2, 5))
    
    all_available = random.random() > 0.1
    result = {
        "order_id": order_id,
        "all_items_available": all_available,
        "items_checked": len(items)
    }
    logger.info(f"Inventory validation result: {result}")
    return result


@activity.defn
async def authorize_payment_activity(order_id: str, amount: float) -> dict:
    logger.info(f"Authorizing payment for order {order_id}: ${amount}")
    await asyncio.sleep(random.uniform(3, 8))
    
    success = random.random() > 0.05
    result = {
        "order_id": order_id,
        "amount": amount,
        "authorized": success,
        "transaction_id": f"txn-{random.randint(100000, 999999)}"
    }
    logger.info(f"Payment authorization result: {result}")
    return result


@activity.defn
async def reserve_inventory_activity(order_id: str, items: list) -> dict:
    logger.info(f"Reserving inventory for order {order_id}")
    await asyncio.sleep(random.uniform(2, 4))
    
    result = {
        "order_id": order_id,
        "items_reserved": len(items),
        "reservation_id": f"res-{random.randint(100000, 999999)}"
    }
    logger.info(f"Inventory reservation result: {result}")
    return result


@activity.defn
async def capture_payment_activity(order_id: str, transaction_id: str, amount: float) -> dict:
    logger.info(f"Capturing payment for order {order_id}, txn: {transaction_id}")
    await asyncio.sleep(random.uniform(2, 6))
    
    result = {
        "order_id": order_id,
        "transaction_id": transaction_id,
        "amount": amount,
        "captured": True,
        "receipt_id": f"rec-{random.randint(100000, 999999)}"
    }
    logger.info(f"Payment capture result: {result}")
    return result


@activity.defn
async def prepare_shipment_activity(order_id: str, items: list) -> dict:
    logger.info(f"Preparing shipment for order {order_id}")
    await asyncio.sleep(random.uniform(5, 10))
    
    result = {
        "order_id": order_id,
        "items_packed": len(items),
        "tracking_number": f"TRK{random.randint(1000000000, 9999999999)}",
        "estimated_ship_date": "2024-01-15"
    }
    logger.info(f"Shipment preparation result: {result}")
    return result


@activity.defn
async def update_customer_activity(order_id: str, status: str, details: dict) -> dict:
    logger.info(f"Updating customer for order {order_id}, status: {status}")
    await asyncio.sleep(random.uniform(1, 3))
    
    result = {
        "order_id": order_id,
        "status": status,
        "customer_notified": True,
        "notification_channels": ["email", "sms"]
    }
    logger.info(f"Customer update result: {result}")
    return result


@activity.defn
def generate_invoice_activity(order_id: str, items: list, amount: float) -> dict:
    import hashlib
    import time
    
    logger.info(f"Generating invoice for order {order_id}")
    
    start_time = time.time()
    invoice_data = f"{order_id}-{amount}-{len(items)}"
    
    result_hash = invoice_data
    for _ in range(100000):
        result_hash = hashlib.sha256(result_hash.encode()).hexdigest()
    
    computation_time = time.time() - start_time
    
    result = {
        "order_id": order_id,
        "invoice_number": f"INV-{result_hash[:12].upper()}",
        "amount": amount,
        "items_count": len(items),
        "computation_time_ms": int(computation_time * 1000)
    }
    logger.info(f"Invoice generated: {result['invoice_number']} (took {result['computation_time_ms']}ms)")
    return result


@workflow.defn
class OrderProcessingWorkflow:

    @workflow.run
    async def run(self, order_data: dict) -> dict:
        order_id = order_data.get("order_id")
        items = order_data.get("items", [])
        amount = order_data.get("amount", 0.0)
        
        workflow.logger.info(f"Starting order processing workflow for order: {order_id}")
        
        inventory_result = await workflow.execute_activity(
            validate_inventory_activity,
            order_id,
            items,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
        )
        
        if not inventory_result["all_items_available"]:
            await workflow.execute_activity(
                update_customer_activity,
                order_id,
                "inventory_unavailable",
                {"reason": "Some items are out of stock"},
                start_to_close_timeout=timedelta(seconds=30)
            )
            return {
                "order_id": order_id,
                "status": "failed",
                "reason": "inventory_unavailable"
            }
        
        payment_auth = await workflow.execute_activity(
            authorize_payment_activity,
            order_id,
            amount,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
        )
        
        if not payment_auth["authorized"]:
            await workflow.execute_activity(
                update_customer_activity,
                order_id,
                "payment_failed",
                {"reason": "Payment authorization failed"},
                start_to_close_timeout=timedelta(seconds=30)
            )
            return {
                "order_id": order_id,
                "status": "failed",
                "reason": "payment_authorization_failed"
            }
        
        reservation = await workflow.execute_activity(
            reserve_inventory_activity,
            order_id,
            items,
            start_to_close_timeout=timedelta(seconds=30)
        )
        
        payment_capture = await workflow.execute_activity(
            capture_payment_activity,
            order_id,
            payment_auth["transaction_id"],
            amount,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=5,
            ),
        )
        
        shipment = await workflow.execute_activity(
            prepare_shipment_activity,
            order_id,
            items,
            start_to_close_timeout=timedelta(seconds=60)
        )
        
        invoice = await workflow.execute_activity(
            generate_invoice_activity,
            order_id,
            items,
            amount,
            start_to_close_timeout=timedelta(seconds=30)
        )
        
        await workflow.execute_activity(
            update_customer_activity,
            order_id,
            "order_confirmed",
            {
                "tracking_number": shipment["tracking_number"],
                "estimated_ship_date": shipment["estimated_ship_date"],
                "invoice_number": invoice["invoice_number"]
            },
            start_to_close_timeout=timedelta(seconds=30)
        )
        
        final_result = {
            "order_id": order_id,
            "status": "completed",
            "payment": payment_capture,
            "shipment": shipment,
            "reservation": reservation,
            "invoice": invoice
        }
        
        workflow.logger.info(f"Order processing completed: {final_result}")
        return final_result


async def create_worker():
    """
    Create and configure the Temporal worker.
    """
    host, namespace, api_key = get_temporal_config()
    
    logger.info(f"Connecting to Temporal at {host}")
    logger.info(f"Using namespace: {namespace}")

    client = await Client.connect(
        host, 
        namespace=namespace,
        api_key=api_key,
        tls=True
    )

    activity_threads = int(os.getenv("ACTIVITY_THREADS", "2"))
    
    order_worker = Worker(
        client,
        task_queue=ORDER_PROCESSING_TASK_QUEUE,
        workflows=[OrderProcessingWorkflow],
        activities=[
            process_order_activity,
            send_notification_activity,
            validate_inventory_activity,
            authorize_payment_activity,
            reserve_inventory_activity,
            capture_payment_activity,
            prepare_shipment_activity,
            update_customer_activity,
            generate_invoice_activity
        ],
        max_concurrent_activites=10,
        activity_executor=ThreadPoolExecutor(max_workers=activity_threads),
    )

    logger.info(f"Order processing worker created on task queue: {ORDER_PROCESSING_TASK_QUEUE}")
    return [order_worker]


async def main():
    logger.info("Starting Temporal worker...")
    
    try:
        workers = await create_worker()
        logger.info("Workers started and listening...")
        
        await asyncio.gather(*[worker.run() for worker in workers])
        
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())