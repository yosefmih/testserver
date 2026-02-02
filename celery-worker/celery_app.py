import os
import time
import random
from celery import Celery

BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'amqp://celery:celery123@rabbitmq:5672/')

app = Celery('tasks', broker=BROKER_URL)

app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_prefetch_multiplier=1,
)


@app.task
def simple_task(n):
    time.sleep(0.1)
    return n * 2


@app.task
def memory_hog_task(size_mb=10, hold_seconds=1):
    """Allocates memory and holds it - useful for memory leak testing."""
    data = bytearray(size_mb * 1024 * 1024)
    for i in range(0, len(data), 4096):
        data[i] = random.randint(0, 255)
    time.sleep(hold_seconds)
    return f"allocated {size_mb}MB for {hold_seconds}s"


@app.task
def leaky_task(leak_mb=1):
    """Simulates a memory leak by storing data in a global list."""
    if not hasattr(leaky_task, '_leak_store'):
        leaky_task._leak_store = []
    leaky_task._leak_store.append(bytearray(leak_mb * 1024 * 1024))
    return f"leaked {leak_mb}MB, total leaked: {len(leaky_task._leak_store) * leak_mb}MB"


@app.task
def cpu_bound_task(iterations=1000000):
    """CPU-bound task for testing."""
    total = 0
    for i in range(iterations):
        total += i * i
    return total
