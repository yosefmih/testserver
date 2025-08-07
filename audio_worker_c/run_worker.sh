#!/bin/bash
# Script to run the C audio worker continuously in background

echo "Starting C audio worker in background..."
/Users/yosefmihretie/projects/testserver/audio_worker_c/build/audio_worker --verbose --duration 0 --timeout 5 &
WORKER_PID=$!

echo "Audio worker started with PID: $WORKER_PID"
echo "To stop: kill $WORKER_PID"
echo $WORKER_PID > /tmp/audio_worker.pid