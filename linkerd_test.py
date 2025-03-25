#!/usr/bin/env python3
import argparse
import subprocess
import time
import json
import sys
import logging
import os
import re
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
TEST_DURATION = 10  # Duration for each test in seconds
LATENCY_MS = 200    # Latency to inject for testing
ERROR_RATE = 30     # Error rate to use for retry testing
REQUESTS = 50       # Number of requests for load test
CONCURRENCY = 5     # Concurrency level for load test

class LinkerdTest:
    def __init__(self, server_url, output_dir=None, verbose=False):
        self.server_url = server_url
        self.verbose = verbose
        
        # Setup output directory
        if output_dir:
            self.output_dir = output_dir
        else:
            self.output_dir = f"linkerd_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            
        # Configure logging to file
        file_handler = logging.FileHandler(f"{self.output_dir}/test_results.log")
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
        
        # Results storage
        self.results = {
            "server_info": {"url": server_url},
            "tests": []
        }
    
    def run_client_command(self, args, capture_output=True, timeout=None):
        """Run client.py with the specified arguments"""
        cmd = ["python", "client.py", "--server", self.server_url]
        cmd.extend(args)
        
        if self.verbose:
            cmd.append("--verbose")
            
        logger.debug(f"Running command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd, 
                capture_output=capture_output, 
                text=True,
                timeout=timeout
            )
            return result
        except subprocess.TimeoutExpired:
            logger.warning(f"Command timed out after {timeout} seconds")
            return None
    
    def get_server_config(self):
        """Get the server configuration"""
        logger.info("Getting server configuration")
        
        # Add timeout to prevent hanging
        result = self.run_client_command(["--get-config"], timeout=15)
        
        # If timeout or failure, provide option to continue anyway
        if not result or result.returncode != 0:
            logger.warning("Failed to get server configuration, proceeding with tests anyway")
            if result:
                logger.warning(f"Error output: {result.stderr}")
            
            # Create default configuration
            default_config = {
                "greeting_word": "DEFAULT",
                "error_rate_percent": 0,
                "latency_injection_ms": 0,
                "trace_propagation": True,
                "hostname": "unknown"
            }
            
            logger.info(f"Using default configuration: {json.dumps(default_config)}")
            self.results["server_info"]["config"] = default_config
            self.results["server_info"]["config_status"] = "default_used"
            return default_config
        
        # Extract config from logs
        # Try to parse the config from output
        config_line = None
        for line in result.stdout.splitlines():
            if "Server configuration:" in line:
                config_line = line.split("Server configuration:", 1)[1].strip()
                break
        
        if config_line:
            try:
                config = json.loads(config_line)
                logger.info(f"Server config: {json.dumps(config, indent=2)}")
                self.results["server_info"]["config"] = config
                self.results["server_info"]["config_status"] = "success"
                return config
            except json.JSONDecodeError:
                logger.error("Failed to parse server configuration")
        
        logger.warning("Failed to extract configuration from response, proceeding with tests anyway")
        self.results["server_info"]["config_status"] = "failed"
        return None
    
    def configure_server(self, config_type, config_value):
        """Configure the server with the specified setting"""
        logger.info(f"Configuring server: {config_type}={config_value}")
        result = self.run_client_command([
            "--mode", "config",
            "--config-type", config_type,
            "--config-value", str(config_value)
        ])
        
        if result and result.returncode == 0:
            logger.info(f"Server configured successfully: {config_type}={config_value}")
            return True
        else:
            logger.error(f"Failed to configure server: {config_type}={config_value}")
            if result:
                logger.error(f"Error: {result.stderr}")
            return False
    
    def reset_server_config(self):
        """Reset server to default configuration"""
        logger.info("Resetting server configuration")
        self.configure_server("error-rate", "0")
        self.configure_server("latency", "0")
        self.configure_server("tracing", "true")
    
    def test_basic_connectivity(self):
        """Test basic connectivity to the server"""
        logger.info("=== Testing Basic Connectivity ===")
        test_data = {
            "name": "basic_connectivity",
            "description": "Tests basic connectivity to server",
            "start_time": datetime.now().isoformat()
        }
        
        # Reset the word with a known value
        word = "CONNECTIVITY-TEST"
        result = self.run_client_command(["--word", word, "--interval", "5"])
        
        # Check if request was successful
        if result and result.returncode == 0:
            success = any("Success! Server's greeting updated" in line for line in result.stdout.splitlines())
            
            if success:
                test_data["status"] = "PASS"
                logger.info("✅ Basic connectivity test passed")
            else:
                test_data["status"] = "FAIL"
                logger.error("❌ Basic connectivity test failed")
        else:
            test_data["status"] = "FAIL"
            logger.error("❌ Basic connectivity test failed - client error")
            
        test_data["end_time"] = datetime.now().isoformat()
        self.results["tests"].append(test_data)
        return test_data["status"] == "PASS"
        
    def test_tracing_headers(self):
        """Test tracing headers propagation"""
        logger.info("=== Testing Tracing Headers Propagation ===")
        test_data = {
            "name": "tracing_headers",
            "description": "Tests if tracing headers are propagated",
            "start_time": datetime.now().isoformat()
        }
        
        # Ensure tracing is enabled
        self.configure_server("tracing", "true")
        
        # Send several requests with same trace ID
        result = self.run_client_command([
            "--mode", "load-test", 
            "--requests", "10", 
            "--concurrency", "1", 
            "--trace", "false"
        ])
        
        trace_id_detected = False
        server_propagation_detected = False
        
        if result and result.returncode == 0:
            # Look for evidence of trace propagation in the output
            output = result.stdout
            
            # Check if trace ID is present in requests
            trace_id_match = re.search(r"Base trace ID: ([a-f0-9]+)", output)
            if trace_id_match:
                trace_id = trace_id_match.group(1)
                trace_id_detected = True
                test_data["trace_id"] = trace_id
                logger.info(f"Found trace ID: {trace_id}")
                
                # Look for evidence that server returned the same trace ID
                if "X-B3-TraceId" in output and "X-Server-Host" in output:
                    server_propagation_detected = True
                    logger.info("Server appears to propagate tracing headers")
        
        if trace_id_detected:
            if server_propagation_detected:
                test_data["status"] = "PASS"
                test_data["propagation"] = True
                logger.info("✅ Tracing headers test passed - headers are propagated")
            else:
                test_data["status"] = "PARTIAL"
                test_data["propagation"] = False
                logger.warning("⚠️ Tracing headers test partial - client sends but server doesn't propagate")
        else:
            test_data["status"] = "FAIL"
            test_data["propagation"] = False
            logger.error("❌ Tracing headers test failed - no trace ID detected")
            
        test_data["end_time"] = datetime.now().isoformat()
        self.results["tests"].append(test_data)
        return test_data
    
    def test_retries(self):
        """Test retry behavior with injected failures"""
        logger.info("=== Testing Retry Behavior ===")
        test_data = {
            "name": "retry_behavior",
            "description": "Tests retry behavior with injected failures",
            "start_time": datetime.now().isoformat()
        }
        
        # Configure server to return errors
        self.configure_server("error-rate", str(ERROR_RATE))
        
        # Send requests with retries
        result = self.run_client_command([
            "--mode", "load-test", 
            "--requests", "20", 
            "--concurrency", "1",
            "--retries", "3",
            "--retry-delay", "0.5"
        ])
        
        if result:
            output = result.stdout
            
            # Extract success and failure counts
            success_match = re.search(r"Load test completed in .* - (\d+) succeeded, (\d+) failed", output)
            if success_match:
                successes = int(success_match.group(1))
                failures = int(success_match.group(2))
                
                test_data["successes"] = successes
                test_data["failures"] = failures
                test_data["error_rate"] = ERROR_RATE
                
                retry_attempts = len(re.findall(r"will retry \((\d+)/(\d+)\)", output))
                test_data["retry_attempts"] = retry_attempts
                
                # With 30% error rate and 3 retries, we expect a high success rate
                if successes > 0 and retry_attempts > 0:
                    test_data["status"] = "PASS"
                    logger.info(f"✅ Retry test passed - {successes} succeeded, {failures} failed, {retry_attempts} retries")
                else:
                    test_data["status"] = "FAIL"
                    logger.error(f"❌ Retry test failed - retries don't seem effective")
            else:
                test_data["status"] = "FAIL"
                logger.error("❌ Retry test failed - couldn't parse results")
        else:
            test_data["status"] = "FAIL"
            logger.error("❌ Retry test failed - client error")
        
        # Reset error rate
        self.configure_server("error-rate", "0")
            
        test_data["end_time"] = datetime.now().isoformat()
        self.results["tests"].append(test_data)
        return test_data
    
    def test_latency(self):
        """Test latency handling"""
        logger.info("=== Testing Latency Handling ===")
        test_data = {
            "name": "latency_handling",
            "description": "Tests behavior with injected latency",
            "start_time": datetime.now().isoformat()
        }
        
        # First measure baseline latency
        baseline_result = self.run_client_command([
            "--mode", "load-test", 
            "--requests", "10", 
            "--concurrency", "1"
        ])
        
        baseline_duration = None
        if baseline_result and baseline_result.returncode == 0:
            duration_match = re.search(r"Load test completed in (\d+\.\d+)s", baseline_result.stdout)
            if duration_match:
                baseline_duration = float(duration_match.group(1))
                test_data["baseline_duration"] = baseline_duration
        
        # Now inject latency
        self.configure_server("latency", str(LATENCY_MS))
        
        # Run test with injected latency
        latency_result = self.run_client_command([
            "--mode", "load-test", 
            "--requests", "10", 
            "--concurrency", "1"
        ])
        
        injected_duration = None
        if latency_result and latency_result.returncode == 0:
            duration_match = re.search(r"Load test completed in (\d+\.\d+)s", latency_result.stdout)
            if duration_match:
                injected_duration = float(duration_match.group(1))
                test_data["injected_duration"] = injected_duration
        
        # Reset latency
        self.configure_server("latency", "0")
        
        if baseline_duration is not None and injected_duration is not None:
            # We expect injected duration to be significantly higher
            expected_minimum = baseline_duration + (LATENCY_MS * 10 / 1000)  # 10 requests with LATENCY_MS each
            
            if injected_duration >= expected_minimum * 0.7:  # Allow some variance
                test_data["status"] = "PASS"
                logger.info(f"✅ Latency test passed - baseline: {baseline_duration:.2f}s, injected: {injected_duration:.2f}s")
            else:
                test_data["status"] = "FAIL"
                logger.error(f"❌ Latency test failed - baseline: {baseline_duration:.2f}s, injected: {injected_duration:.2f}s")
                logger.error(f"   Expected injected duration to be at least {expected_minimum:.2f}s")
        else:
            test_data["status"] = "FAIL"
            logger.error("❌ Latency test failed - couldn't measure latency")
            
        test_data["end_time"] = datetime.now().isoformat()
        self.results["tests"].append(test_data)
        return test_data
    
    def test_load(self):
        """Test behavior under load"""
        logger.info("=== Testing Load Handling ===")
        test_data = {
            "name": "load_test",
            "description": "Tests behavior under load with concurrent requests",
            "start_time": datetime.now().isoformat()
        }
        
        # Run load test
        result = self.run_client_command([
            "--mode", "load-test", 
            "--requests", str(REQUESTS), 
            "--concurrency", str(CONCURRENCY),
            "--retries", "2"
        ])
        
        if result and result.returncode == 0:
            throughput_match = re.search(r"Average throughput: (\d+\.\d+) requests/second", result.stdout)
            success_match = re.search(r"Load test completed in .* - (\d+) succeeded, (\d+) failed", result.stdout)
            
            if throughput_match and success_match:
                throughput = float(throughput_match.group(1))
                successes = int(success_match.group(1))
                failures = int(success_match.group(2))
                
                test_data["throughput"] = throughput
                test_data["successes"] = successes
                test_data["failures"] = failures
                
                success_rate = successes / (successes + failures) if (successes + failures) > 0 else 0
                test_data["success_rate"] = success_rate
                
                if success_rate > 0.9:  # More than 90% success
                    test_data["status"] = "PASS"
                    logger.info(f"✅ Load test passed - {throughput:.2f} req/s, {success_rate*100:.1f}% success")
                else:
                    test_data["status"] = "FAIL"
                    logger.error(f"❌ Load test failed - too many failures ({failures}/{successes+failures})")
            else:
                test_data["status"] = "FAIL"
                logger.error("❌ Load test failed - couldn't parse results")
        else:
            test_data["status"] = "FAIL"
            logger.error("❌ Load test failed - client error")
            
        test_data["end_time"] = datetime.now().isoformat()
        self.results["tests"].append(test_data)
        return test_data
    
    def analyze_results(self):
        """Analyze test results to determine Linkerd configuration"""
        logger.info("=== Analyzing Results ===")
        
        # Extract key indicators
        tracing_test = next((t for t in self.results["tests"] if t["name"] == "tracing_headers"), None)
        retry_test = next((t for t in self.results["tests"] if t["name"] == "retry_behavior"), None)
        latency_test = next((t for t in self.results["tests"] if t["name"] == "latency_handling"), None)
        load_test = next((t for t in self.results["tests"] if t["name"] == "load_test"), None)
        
        # Indicators for Linkerd on client side
        client_in_mesh = False
        if retry_test and retry_test.get("status") == "PASS":
            # If we see successful retries despite server errors, Linkerd might be handling retries
            client_retry_efficiency = retry_test.get("successes", 0) / (retry_test.get("successes", 0) + retry_test.get("failures", 0)) if retry_test.get("successes", 0) + retry_test.get("failures", 0) > 0 else 0
            if client_retry_efficiency > 0.75:  # Higher success than expected with just client retries
                client_in_mesh = True
        
        # Indicators for Linkerd on server side
        server_in_mesh = False
        if tracing_test and tracing_test.get("propagation", False):
            # If server propagates headers correctly, it's likely in the mesh
            server_in_mesh = True
            
        # Determine configuration
        configuration = "unknown"
        if client_in_mesh and server_in_mesh:
            configuration = "both_in_mesh"
        elif client_in_mesh:
            configuration = "client_in_mesh"
        elif server_in_mesh:
            configuration = "server_in_mesh"
        else:
            configuration = "none_in_mesh"
            
        self.results["analysis"] = {
            "client_in_mesh": client_in_mesh,
            "server_in_mesh": server_in_mesh,
            "configuration": configuration
        }
        
        # Print assessment
        logger.info(f"📊 Analysis complete")
        logger.info(f"🔍 Detected configuration: {configuration.replace('_', ' ')}")
        logger.info(f"   - Client in mesh: {'Yes' if client_in_mesh else 'No'}")
        logger.info(f"   - Server in mesh: {'Yes' if server_in_mesh else 'No'}")
        
        return self.results["analysis"]
            
    def run_all_tests(self):
        """Run all tests in sequence"""
        logger.info(f"Starting Linkerd test suite against {self.server_url}")
        
        try:
            # Get server config first (with timeout)
            config_result = self.get_server_config()
            
            # Basic connectivity is essential - if it fails, we can't continue
            logger.info("Checking basic connectivity before proceeding with tests")
            connectivity_test = self.test_basic_connectivity()
            
            if not connectivity_test:
                logger.error("Cannot establish basic connectivity to server, aborting tests")
                self.results["status"] = "failed"
                self.save_results()
                return False
            
            # Attempt to reset server config but continue if it fails
            try:
                self.reset_server_config()
            except Exception as e:
                logger.warning(f"Failed to reset server configuration: {str(e)}")
            
            # Run the test suite with appropriate error handling for each test
            test_functions = [
                self.test_tracing_headers,
                self.test_retries,
                self.test_latency,
                self.test_load
            ]
            
            # Run tests with individual error handling
            for test_func in test_functions:
                try:
                    logger.info(f"Running test: {test_func.__name__}")
                    test_func()
                except Exception as e:
                    logger.error(f"Test {test_func.__name__} failed with error: {str(e)}")
                    import traceback
                    logger.debug(traceback.format_exc())
            
            # Analyze results even if some tests failed
            self.analyze_results()
            
            # Save results to file
            self.save_results()
            
            logger.info(f"Tests completed. Results saved to {self.output_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Test suite execution failed: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            self.results["status"] = "error"
            self.save_results()
            return False
        
    def save_results(self):
        """Save test results to file"""
        results_file = f"{self.output_dir}/test_results.json"
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        logger.info(f"Results saved to {results_file}")

def main():
    parser = argparse.ArgumentParser(description='Run comprehensive Linkerd mesh tests')
    parser.add_argument('--server', required=True, help='Server URL (e.g., http://myapp.default:3000)')
    parser.add_argument('--output-dir', help='Directory to save test results')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Run the test suite
    test = LinkerdTest(args.server, args.output_dir, args.verbose)
    test.run_all_tests()

if __name__ == '__main__':
    main() 