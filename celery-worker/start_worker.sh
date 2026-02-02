#!/bin/bash
set -e

# Defaults for 2 CPU / 2GB RAM config:
# - concurrency=2 (match CPU cores)
# - max-tasks-per-child=1000 (recycle after 1000 tasks)
# - max-memory-per-child=500000 KB (~500MB per worker)
#   With 2 workers: 2×500MB = 1GB, leaves ~1GB for main process + headroom
CONCURRENCY="${CELERY_CONCURRENCY:-2}"
MAX_TASKS="${CELERY_MAX_TASKS_PER_CHILD:-1000}"
MAX_MEMORY="${CELERY_MAX_MEMORY_PER_CHILD:-500000}"
LOGLEVEL="${CELERY_LOGLEVEL:-info}"

ARGS="-A celery_app worker --loglevel=$LOGLEVEL --concurrency=$CONCURRENCY --max-tasks-per-child=$MAX_TASKS --max-memory-per-child=$MAX_MEMORY"

echo "Starting celery with: celery $ARGS"
exec celery $ARGS
