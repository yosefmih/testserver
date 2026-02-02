import os
import time
import random
from celery import Celery

BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'amqp://celery:celery123@rabbitmq:5672/')

app = Celery('tasks', broker=BROKER_URL)

app.conf.update(
    task_serializer='pickle',
    accept_content=['pickle', 'json'],
    result_serializer='pickle',
    timezone='UTC',
    enable_utc=True,
    worker_prefetch_multiplier=1,
)


@app.task
def simple_task(n):
    time.sleep(0.1)
    return n * 2


@app.task
def memory_hog_task(size_mb=10, hold_seconds=60):
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


@app.task
def long_running_task(duration_minutes=5, memory_mb=50, work_interval_seconds=10):
    """
    Simulates a long-running production task (up to 12.5+ minutes).
    Holds memory and does periodic work to simulate real workload.
    """
    duration_seconds = duration_minutes * 60
    data = bytearray(memory_mb * 1024 * 1024)

    start_time = time.time()
    iterations = 0

    while time.time() - start_time < duration_seconds:
        for i in range(0, len(data), 4096):
            data[i] = random.randint(0, 255)
        iterations += 1
        time.sleep(work_interval_seconds)

    elapsed = time.time() - start_time
    return f"ran for {elapsed:.1f}s, {iterations} iterations, held {memory_mb}MB"


@app.task
def gradual_leak_task(duration_minutes=5, leak_mb_per_minute=10):
    """
    Simulates gradual memory leak over time - more realistic than instant leak.
    Leaks memory_mb every minute for duration_minutes.
    """
    if not hasattr(gradual_leak_task, '_leak_store'):
        gradual_leak_task._leak_store = []

    duration_seconds = duration_minutes * 60
    leak_interval = 60
    start_time = time.time()
    leaks = 0

    while time.time() - start_time < duration_seconds:
        gradual_leak_task._leak_store.append(bytearray(leak_mb_per_minute * 1024 * 1024))
        leaks += 1
        remaining = duration_seconds - (time.time() - start_time)
        if remaining > leak_interval:
            time.sleep(leak_interval)
        elif remaining > 0:
            time.sleep(remaining)
            break

    total_leaked = len(gradual_leak_task._leak_store) * leak_mb_per_minute
    return f"leaked {leaks * leak_mb_per_minute}MB over {duration_minutes}min, total accumulated: {total_leaked}MB"


class TaskResult:
    """Complex object that requires pickle serialization."""
    def __init__(self, task_id, data_size_mb, duration_seconds):
        self.task_id = task_id
        self.data = bytearray(data_size_mb * 1024 * 1024)
        self.duration = duration_seconds
        self.timestamp = time.time()
        self.metadata = {
            'iterations': 0,
            'checksum': 0,
        }

    def process(self):
        for i in range(0, len(self.data), 4096):
            self.data[i] = random.randint(0, 255)
            self.metadata['checksum'] += self.data[i]
        self.metadata['iterations'] += 1


@app.task
def pickle_task(task_id, data_size_mb=10, duration_minutes=1):
    """
    Task that passes and returns complex Python objects requiring pickle.
    This exercises pickle serialization for both args and results.
    """
    result = TaskResult(task_id, data_size_mb, duration_minutes * 60)

    start_time = time.time()
    while time.time() - start_time < result.duration:
        result.process()
        time.sleep(5)

    return result


@app.task
def pickle_chain_task(previous_result=None, task_id=0, data_size_mb=5):
    """
    Task that receives a pickled object from previous task and returns a new one.
    Use for chaining: pickle_chain_task.s() | pickle_chain_task.s() | ...
    """
    inherited_checksum = 0
    if previous_result and hasattr(previous_result, 'metadata'):
        inherited_checksum = previous_result.metadata.get('checksum', 0)

    result = TaskResult(task_id, data_size_mb, 10)
    result.process()
    result.metadata['inherited_checksum'] = inherited_checksum

    time.sleep(5)
    return result
