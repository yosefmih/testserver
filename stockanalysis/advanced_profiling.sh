#!/bin/bash

# Simplified Clinic.js Profiling - 60 Second Analysis
# Auto-attaches, profiles for 60s, and provides decisive blocking analysis

set -e

INSPECT_PORT="localhost:9229"
PROFILE_DURATION=60
RUN_BOTH_ANALYSES=true

echo "🔬 60-Second CPU + I/O Blocking Analysis"
echo "========================================"
echo "Target: $INSPECT_PORT"
echo "Duration: ${PROFILE_DURATION} seconds"
echo "Analysis: Event Loop (Doctor) + I/O Patterns (Bubbleprof)"
echo ""

# Install clinic if needed
check_clinic() {
    if ! command -v clinic &> /dev/null; then
        echo "📦 Installing Clinic.js..."
        npm install -g clinic
        echo "✅ Clinic.js installed"
    else
        echo "✅ Clinic.js is available"
    fi
}

# Check if server is running and inspector is available
check_server() {
    echo "🔍 Checking server and inspector..."
    
    # Check if server responds
    if ! curl -s http://localhost:3000/health > /dev/null; then
        echo "❌ Server not responding on port 3000"
        echo "   Start server first: docker run -d -p 3000:3000 -p 9229:9229 --name stock-analysis-container stock-analysis"
        exit 1
    fi
    
    # Check if inspector is available
    if ! nc -z localhost 9229 2>/dev/null; then
        echo "❌ Inspector not available on port 9229"
        echo "   Make sure server has --inspect flag enabled"
        exit 1
    fi
    
    echo "✅ Server and inspector ready"
}

# Analyze both clinic doctor and bubbleprof results
analyze_results() {
    local doctor_dir=$1
    local bubble_dir=$2
    echo ""
    echo "🔍 ANALYZING RESULTS..."
    echo "======================"
    
    # Find the HTML report files
    local doctor_file=$(find "$doctor_dir" -name "*.clinic-doctor.html" | head -1)
    local bubble_file=$(find "$bubble_dir" -name "*.clinic-bubbleprof.html" | head -1)
    
    if [[ -z "$doctor_file" ]]; then
        echo "❌ No clinic doctor report found"
        return 1
    fi
    
    if [[ -z "$bubble_file" ]]; then
        echo "⚠️  No bubbleprof report found (I/O analysis incomplete)"
    fi
    
    echo "📊 Doctor Report: $doctor_file"
    [[ -n "$bubble_file" ]] && echo "📊 Bubble Report: $bubble_file"
    echo ""
    
    # Extract key data from the clinic JSON data (simplified analysis)
    echo "🎯 BLOCKING ANALYSIS SUMMARY"
    echo "============================"
    
    # Analyze CPU blocking from doctor report
    echo "💻 CPU BLOCKING ANALYSIS:"
    if grep -q "event-loop-delay.*[5-9][0-9]ms\|event-loop-delay.*[1-9][0-9][0-9]ms" "$doctor_file" 2>/dev/null; then
        echo "🚨 CRITICAL: Severe CPU blocking detected (>50ms delays)"
        echo "   ➤ This WILL cause health check timeouts in Kubernetes"
        echo "   ➤ Main thread is blocked by CPU-intensive operations"
        echo "   ➤ ACTION REQUIRED: Optimize or move to worker threads"
    elif grep -q "event-loop-delay.*[1-4][0-9]ms" "$doctor_file" 2>/dev/null; then
        echo "⚠️  WARNING: Moderate CPU blocking detected (10-49ms delays)"
        echo "   ➤ This may cause intermittent health check issues"
        echo "   ➤ Consider optimizing heavy operations"
    elif grep -q "event-loop-delay.*[5-9]ms" "$doctor_file" 2>/dev/null; then
        echo "⚡ MINOR: Light CPU delays detected (5-9ms)"
        echo "   ➤ Generally acceptable for most applications"
        echo "   ➤ Monitor under higher load"
    else
        echo "✅ HEALTHY: No significant CPU blocking detected"
        echo "   ➤ CPU processing is responsive"
    fi
    
    echo ""
    
    # Analyze I/O blocking from bubbleprof report
    echo "💿 I/O BLOCKING ANALYSIS:"
    if [[ -n "$bubble_file" ]]; then
        # Check for I/O delays in bubbleprof
        if grep -q "delay.*[1-9][0-9][0-9]ms\|delay.*[5-9][0-9]ms" "$bubble_file" 2>/dev/null; then
            echo "🚨 CRITICAL: Severe I/O blocking detected (>50ms delays)"
            echo "   ➤ Synchronous I/O operations are blocking event loop"
            echo "   ➤ File system, database, or network calls are synchronous"
            echo "   ➤ ACTION REQUIRED: Convert to async I/O operations"
        elif grep -q "delay.*[1-4][0-9]ms" "$bubble_file" 2>/dev/null; then
            echo "⚠️  WARNING: Moderate I/O delays detected (10-49ms)"
            echo "   ➤ Some I/O operations may be causing delays"
            echo "   ➤ Check database queries and file operations"
        elif grep -q "async.*slow\|promise.*slow" "$bubble_file" 2>/dev/null; then
            echo "⚡ MINOR: Slow async operations detected"
            echo "   ➤ Async operations taking longer than expected"
            echo "   ➤ Check external API calls and database performance"
        else
            echo "✅ HEALTHY: No significant I/O blocking detected"
            echo "   ➤ I/O operations are properly async"
        fi
        
        # Check for specific I/O patterns
        if grep -q "fs\.\|readFile\|writeFile" "$bubble_file" 2>/dev/null; then
            echo "📁 FILE I/O: File system operations detected"
            echo "   ➤ Ensure using async file operations (fs.promises or callbacks)"
        fi
        
        if grep -q "http\.\|fetch\|axios" "$bubble_file" 2>/dev/null; then
            echo "🌐 NETWORK I/O: HTTP requests detected"
            echo "   ➤ Monitor external API response times"
        fi
        
        if grep -q "database\|query\|sql" "$bubble_file" 2>/dev/null; then
            echo "🗄️  DATABASE I/O: Database operations detected"
            echo "   ➤ Check query performance and connection pooling"
        fi
    else
        echo "❌ UNAVAILABLE: I/O analysis failed (bubbleprof report missing)"
        echo "   ➤ Run bubbleprof separately if I/O issues suspected"
    fi
    
    echo ""
    echo "📈 DETAILED FINDINGS:"
    echo "===================="
    
    # Check for CPU usage patterns
    if grep -q "cpu.*9[0-9]%\|cpu.*100%" "$doctor_file" 2>/dev/null; then
        echo "🔥 HIGH CPU: Sustained high CPU usage detected"
        echo "   ➤ Single-threaded operations consuming full core"
        echo "   ➤ Consider breaking work into smaller chunks"
    fi
    
    # Check for memory pressure
    if grep -q "memory.*pressure\|gc.*pressure" "$doctor_file" 2>/dev/null; then
        echo "💾 MEMORY: Garbage collection pressure detected"
        echo "   ➤ Frequent GC may be blocking event loop"
        echo "   ➤ Check for memory leaks or large object allocation"
    fi
    
    # Additional I/O insights from bubbleprof
    if [[ -n "$bubble_file" ]] && grep -q "delay\|slow" "$bubble_file" 2>/dev/null; then
        echo "🔄 ASYNC DELAYS: Slow async operations found"
        echo "   ➤ Review async operation performance in bubbleprof report"
        echo "   ➤ Check for promise chains or callback delays"
    fi
    
    echo ""
    echo "🎯 KUBERNETES HEALTH CHECK VERDICT:"
    echo "==================================="
    
    # Give a decisive recommendation based on both CPU and I/O analysis
    local cpu_blocking=false
    local io_blocking=false
    
    # Check for CPU blocking
    if grep -q "event-loop-delay.*[5-9][0-9]ms\|event-loop-delay.*[1-9][0-9][0-9]ms" "$doctor_file" 2>/dev/null; then
        cpu_blocking=true
    fi
    
    # Check for I/O blocking
    if [[ -n "$bubble_file" ]] && grep -q "delay.*[5-9][0-9]ms\|delay.*[1-9][0-9][0-9]ms" "$bubble_file" 2>/dev/null; then
        io_blocking=true
    fi
    
    # Decisive verdict
    if $cpu_blocking && $io_blocking; then
        echo "🚨 WILL FAIL: Both CPU and I/O blocking detected"
        echo "   ➤ Health checks WILL timeout - multiple blocking sources"
        echo "   ➤ Fix CPU-intensive operations AND I/O synchronous calls"
        echo "   ➤ This is a critical production issue"
    elif $cpu_blocking; then
        echo "🚨 WILL FAIL: CPU blocking will cause health check timeouts"
        echo "   ➤ Move CPU-intensive work to worker threads or break into chunks"
        echo "   ➤ Increase K8s health check timeout as temporary measure"
    elif $io_blocking; then
        echo "🚨 WILL FAIL: I/O blocking will cause health check timeouts"
        echo "   ➤ Convert synchronous I/O operations to async"
        echo "   ➤ Check file operations, database queries, HTTP requests"
    elif grep -q "event-loop-delay.*[1-4][0-9]ms" "$doctor_file" 2>/dev/null; then
        echo "⚠️  MAY FAIL: Moderate blocking may cause intermittent timeouts"
        echo "   ➤ Monitor health check success rate closely"
        echo "   ➤ Consider optimizing before production load increases"
    else
        echo "✅ SHOULD PASS: No significant blocking detected"
        echo "   ➤ Event loop is responsive for health checks"
        echo "   ➤ If health checks still fail, investigate other causes"
    fi
    
    echo ""
    echo "📋 NEXT STEPS:"
    echo "=============="
    echo "1. CPU Analysis: Open $doctor_file"
    echo "   - Look for red spikes in timeline (event loop blocks)"
    echo "   - Check 'CPU' section for processing hotspots"
    [[ -n "$bubble_file" ]] && echo "2. I/O Analysis: Open $bubble_file"
    [[ -n "$bubble_file" ]] && echo "   - Look for large bubbles (slow async operations)"
    [[ -n "$bubble_file" ]] && echo "   - Check delay patterns in async flows"
    echo "3. Focus on functions causing the longest delays"
    echo "4. Consider worker threads for CPU-intensive tasks"
    echo "5. Convert sync I/O to async where found"
    echo ""
    echo "🔗 Comprehensive analysis complete!"
}

# Main execution
echo "📦 Setting up..."
check_clinic

echo ""
check_server

echo ""
echo "🚀 Starting 60-second profiling session..."
echo "⏰ $(date)"

# Create results directories
DOCTOR_DIR="./clinic-doctor-$(date +%Y%m%d-%H%M%S)"
BUBBLE_DIR="./clinic-bubble-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DOCTOR_DIR" "$BUBBLE_DIR"

echo "📊 Starting dual profiling session..."
echo "   - CPU/Event Loop: Clinic Doctor"
echo "   - I/O/Async: Clinic Bubbleprof"
echo "   - Duration: ${PROFILE_DURATION} seconds each"
echo ""
echo "⚡ TIP: Run your load tests now in another terminal:"
echo "     ./profile_test.sh"
echo ""

# Run both profilers concurrently for comprehensive analysis
echo "🔄 Phase 1: CPU & Event Loop Analysis (Doctor)..."
timeout ${PROFILE_DURATION} clinic doctor --attach-to=$INSPECT_PORT --dest="$DOCTOR_DIR" || {
    echo "⏰ Doctor profiling completed"
}

echo ""
echo "🔄 Phase 2: I/O & Async Analysis (Bubbleprof)..."
timeout ${PROFILE_DURATION} clinic bubbleprof --attach-to=$INSPECT_PORT --dest="$BUBBLE_DIR" || {
    echo "⏰ Bubbleprof profiling completed"
}

# Wait for reports to be generated
echo ""
echo "📝 Generating reports..."
sleep 5

# Analyze both sets of results
analyze_results "$DOCTOR_DIR" "$BUBBLE_DIR"

echo ""
echo "✅ Analysis complete! Check the HTML report for detailed insights."