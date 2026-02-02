#!/usr/bin/env python3
"""
Trigger Celery tasks for memory leak investigation.

Usage:
    python trigger_tasks.py simple 100              # 100 simple tasks
    python trigger_tasks.py memory 5 50 60          # 5 memory_hog tasks, 50MB each, hold 60s
    python trigger_tasks.py leaky 100 1             # 100 leaky tasks, 1MB leak each
    python trigger_tasks.py cpu 20                  # 20 CPU-bound tasks
    python trigger_tasks.py mixed 100               # 100 mixed tasks
    python trigger_tasks.py long 2 10 100           # 2 long tasks, 10 min each, 100MB
    python trigger_tasks.py gradual 2 5 20          # 2 gradual leak tasks, 5 min, 20MB/min
    python trigger_tasks.py pickle 5 10 2           # 5 pickle tasks, 10MB objects, 2 min each
"""
import sys
from celery_app import (
    simple_task, memory_hog_task, leaky_task, cpu_bound_task,
    long_running_task, gradual_leak_task, pickle_task
)


def trigger_simple(count):
    print(f"Triggering {count} simple tasks...")
    for i in range(count):
        simple_task.delay(i)
    print(f"Queued {count} simple tasks")


def trigger_memory(count, size_mb=50, hold_seconds=60):
    print(f"Triggering {count} memory_hog tasks ({size_mb}MB each, hold {hold_seconds}s)...")
    for i in range(count):
        memory_hog_task.delay(size_mb=size_mb, hold_seconds=hold_seconds)
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
    print(f"Triggering {count} mixed tasks (all 7 task types)...")
    for i in range(count):
        task_type = i % 7
        if task_type == 0:
            simple_task.delay(i)
        elif task_type == 1:
            memory_hog_task.delay(size_mb=20, hold_seconds=30)
        elif task_type == 2:
            leaky_task.delay(leak_mb=1)
        elif task_type == 3:
            cpu_bound_task.delay(iterations=500000)
        elif task_type == 4:
            long_running_task.delay(duration_minutes=2, memory_mb=20, work_interval_seconds=10)
        elif task_type == 5:
            gradual_leak_task.delay(duration_minutes=2, leak_mb_per_minute=5)
        else:
            pickle_task.delay(task_id=i, data_size_mb=10, duration_minutes=1)
    print(f"Queued {count} mixed tasks")


def trigger_long(count, duration_minutes=5, memory_mb=50):
    print(f"Triggering {count} long-running tasks ({duration_minutes} min, {memory_mb}MB)...")
    for i in range(count):
        long_running_task.delay(
            duration_minutes=duration_minutes,
            memory_mb=memory_mb,
            work_interval_seconds=10
        )
    print(f"Queued {count} long-running tasks (will run for ~{duration_minutes} min each)")


def trigger_gradual(count, duration_minutes=5, leak_mb_per_minute=10):
    print(f"Triggering {count} gradual leak tasks ({duration_minutes} min, {leak_mb_per_minute}MB/min)...")
    for i in range(count):
        gradual_leak_task.delay(
            duration_minutes=duration_minutes,
            leak_mb_per_minute=leak_mb_per_minute
        )
    total_potential = count * duration_minutes * leak_mb_per_minute
    print(f"Queued {count} gradual leak tasks (potential leak: {total_potential}MB)")


def trigger_pickle(count, data_size_mb=10, duration_minutes=2):
    print(f"Triggering {count} pickle tasks ({data_size_mb}MB objects, {duration_minutes} min each)...")
    for i in range(count):
        pickle_task.delay(
            task_id=i,
            data_size_mb=data_size_mb,
            duration_minutes=duration_minutes
        )
    print(f"Queued {count} pickle tasks (complex objects serialized via pickle)")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    task_type = sys.argv[1]
    count = int(sys.argv[2])

    if task_type == 'simple':
        trigger_simple(count)
    elif task_type == 'memory':
        size = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        hold = int(sys.argv[4]) if len(sys.argv) > 4 else 60
        trigger_memory(count, size, hold)
    elif task_type == 'leaky':
        leak = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        trigger_leaky(count, leak)
    elif task_type == 'cpu':
        trigger_cpu(count)
    elif task_type == 'mixed':
        trigger_mixed(count)
    elif task_type == 'long':
        duration = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        mem = int(sys.argv[4]) if len(sys.argv) > 4 else 50
        trigger_long(count, duration, mem)
    elif task_type == 'gradual':
        duration = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        leak_rate = int(sys.argv[4]) if len(sys.argv) > 4 else 10
        trigger_gradual(count, duration, leak_rate)
    elif task_type == 'pickle':
        data_size = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        duration = int(sys.argv[4]) if len(sys.argv) > 4 else 2
        trigger_pickle(count, data_size, duration)
    else:
        print(f"Unknown task type: {task_type}")
        print(__doc__)
        sys.exit(1)
