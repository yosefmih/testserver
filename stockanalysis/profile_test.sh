#!/bin/bash

# Node.js Event Loop Profiling Test Script
# This script simulates real-world scenarios that cause health check timeouts

set -e

BASE_URL="http://localhost:3000"
HEALTH_ENDPOINT="$BASE_URL/health"
COMPUTE_ENDPOINT="$BASE_URL/compute"
ANALYZE_ENDPOINT="$BASE_URL/analyze"

echo "🚀 Starting Node.js Event Loop Profiling Tests"
echo "================================================"

# Function to check if server is responding
wait_for_server() {
    echo "⏳ Waiting for server to be ready..."
    until curl -s "$BASE_URL" > /dev/null; do
        echo "   Server not ready, waiting..."
        sleep 2
    done
    echo "✅ Server is ready!"
}

# Function to run health checks in background
run_health_checks() {
    local duration=$1
    local interval=$2
    echo "🏥 Starting continuous health checks for ${duration}s (every ${interval}s)"
    
    timeout $duration bash -c "
        while true; do
            start_time=\$(date +%s%3N)
            if curl -s -m 5 '$HEALTH_ENDPOINT' > /dev/null; then
                end_time=\$(date +%s%3N)
                response_time=\$((end_time - start_time))
                echo \"   Health check OK (\${response_time}ms)\"
            else
                echo \"   ❌ Health check FAILED or TIMEOUT\"
            fi
            sleep $interval
        done
    " &
    
    HEALTH_PID=$!
    echo "   Health checks running in background (PID: $HEALTH_PID)"
}

# Function to stop background health checks
stop_health_checks() {
    if [[ -n "$HEALTH_PID" ]]; then
        kill $HEALTH_PID 2>/dev/null || true
        echo "🛑 Stopped health checks"
    fi
}

# Trap to ensure cleanup
trap stop_health_checks EXIT

wait_for_server

echo ""
echo "📊 Test 1: Baseline Performance (No Event Loop Blocking)"
echo "========================================================="
echo "Running 100 requests to /health endpoint..."

# Use wrk if available, otherwise curl
if command -v wrk &> /dev/null; then
    wrk -t4 -c10 -d10s --latency "$HEALTH_ENDPOINT"
else
    echo "Installing wrk for better load testing..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install wrk 2>/dev/null || echo "Please install wrk: brew install wrk"
    else
        echo "Please install wrk for better load testing"
    fi
    
    # Fallback to curl loop
    echo "Using curl fallback for load testing..."
    for i in {1..50}; do
        start_time=$(date +%s%3N)
        curl -s "$HEALTH_ENDPOINT" > /dev/null
        end_time=$(date +%s%3N)
        response_time=$((end_time - start_time))
        echo "Request $i: ${response_time}ms"
    done
fi

echo ""
echo "📊 Test 2: Event Loop Blocking Scenario"
echo "========================================"
echo "This test simulates CPU-intensive operations that block the event loop"

# Start health checks in background
run_health_checks 30 2

sleep 2

echo "🔥 Triggering CPU-intensive computation (30 second version)..."
start_time=$(date +%s)

# Trigger the computation that will block the event loop
curl -X POST \
     -H "Content-Type: application/json" \
     -d '{"iterations": 100000000, "complexity": "extreme"}' \
     -m 35 \
     "$COMPUTE_ENDPOINT" &

COMPUTE_PID=$!

# Wait for the computation to complete
wait $COMPUTE_PID

end_time=$(date +%s)
duration=$((end_time - start_time))

echo "⏱️  Computation completed in ${duration} seconds"

# Let health checks continue for a bit more
sleep 5

stop_health_checks

echo ""
echo "📊 Test 3: Concurrent Stock Analysis Load"
echo "========================================="
echo "Testing concurrent requests to stock analysis endpoint..."

# Test concurrent stock analysis requests
if command -v wrk &> /dev/null; then
    echo "Running concurrent stock analysis requests..."
    wrk -t2 -c5 -d15s --latency "$ANALYZE_ENDPOINT/AAPL"
else
    # Fallback: concurrent curl requests
    echo "Running concurrent curl requests..."
    for i in {1..10}; do
        curl -s "$ANALYZE_ENDPOINT/STOCK$i" &
    done
    wait
fi

echo ""
echo "📊 Test 4: Health Check During High Load"
echo "========================================"

# Start background load on stock analysis
echo "🔄 Starting background load on stock analysis..."
if command -v wrk &> /dev/null; then
    wrk -t2 -c4 -d20s "$ANALYZE_ENDPOINT/MSFT" &
    LOAD_PID=$!
else
    # Fallback background load
    for i in {1..100}; do
        curl -s "$ANALYZE_ENDPOINT/LOAD$i" > /dev/null &
        sleep 0.2
    done &
    LOAD_PID=$!
fi

sleep 2

# Test health checks during load
echo "🏥 Testing health checks during background load..."
run_health_checks 15 1

# Stop background load
kill $LOAD_PID 2>/dev/null || true

echo ""
echo "🎯 Test Summary & Profiling Instructions"
echo "========================================"
echo "1. Connect Chrome DevTools to chrome://inspect"
echo "2. Click 'inspect' on the Node.js target"
echo "3. Go to Performance tab"
echo "4. Run: curl -X POST -H 'Content-Type: application/json' -d '{\"iterations\": 200000000, \"complexity\": \"extreme\"}' http://localhost:3000/compute"
echo "5. Look for long 'Program' blocks in the timeline"
echo "6. Check Call Tree for CPU-intensive functions"
echo ""
echo "Expected behavior:"
echo "- Health checks should fail/timeout during CPU computation"
echo "- Chrome DevTools should show event loop blocking"
echo "- Response times should spike during computation"
echo ""
echo "✅ Profiling test script completed!"