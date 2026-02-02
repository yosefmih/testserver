#!/usr/bin/env python3
"""
Trigger Celery tasks for memory leak investigation.

Usage:
    python trigger_tasks.py simple 100        # 100 simple tasks
    python trigger_tasks.py memory 50 10      # 50 memory_hog tasks, 10MB each
    python trigger_tasks.py leaky 100 1       # 100 leaky tasks, 1MB leak each
    python trigger_tasks.py cpu 20            # 20 CPU-bound tasks
    python trigger_tasks.py mixed 100         # 100 mixed tasks
"""
import sys
import time
from celery_app import simple_task, memory_hog_task, leaky_task, cpu_bound_task


def trigger_simple(count):
    print(f"Triggering {count} simple tasks...")
    for i in range(count):
        simple_task.delay(i)
    print(f"Queued {count} simple tasks")


def trigger_memory(count, size_mb=10):
    print(f"Triggering {count} memory_hog tasks ({size_mb}MB each)...")
    for i in range(count):
        memory_hog_task.delay(size_mb=size_mb, hold_seconds=1)
    print(f"Queued {count} memory_hog tasks")


def trigger_leaky(count, leak_mb=1):
    print(f"Triggering {count} leaky tasks ({leak_mb}MB leak each)...")
    for i in range(count):
        leaky_task.delay(leak_mb=leak_mb)
    print(f"Queued {count} leaky tasks")


def trigger_cpu(count):
    print(f"Triggering {count} CPU-bound tasks...")
    for i in range(count):
        cpu_bound_task.delay(iterations=1000000)
    print(f"Queued {count} CPU tasks")


def trigger_mixed(count):
    print(f"Triggering {count} mixed tasks...")
    for i in range(count):
        if i % 4 == 0:
            simple_task.delay(i)
        elif i % 4 == 1:
            memory_hog_task.delay(size_mb=5, hold_seconds=0.5)
        elif i % 4 == 2:
            leaky_task.delay(leak_mb=1)
        else:
            cpu_bound_task.delay(iterations=500000)
    print(f"Queued {count} mixed tasks")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    task_type = sys.argv[1]
    count = int(sys.argv[2])

    if task_type == 'simple':
        trigger_simple(count)
    elif task_type == 'memory':
        size = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        trigger_memory(count, size)
    elif task_type == 'leaky':
        leak = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        trigger_leaky(count, leak)
    elif task_type == 'cpu':
        trigger_cpu(count)
    elif task_type == 'mixed':
        trigger_mixed(count)
    else:
        print(f"Unknown task type: {task_type}")
        print(__doc__)
        sys.exit(1)
