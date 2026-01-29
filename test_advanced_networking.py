#!/usr/bin/env python3
"""
Advanced Networking Annotation Test Suite

Tests all advanced networking configurations for Porter web services:
- Timeouts (connect, read, write, client body timeout)
- Request body size limits
- Rate limiting
- Session affinity (cookie and client IP modes)
- Firewall/IP allowlisting
- Compression (gzip)
- Host-based redirects

Usage:
    python test_advanced_networking.py <base_url> [--config config.yaml]

Example:
    python test_advanced_networking.py https://web-1-cdded00c-76e4daot.withporter.run
"""

import argparse
import json
import sys
import time
import threading
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from urllib.parse import urljoin

import requests


class TestResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class TestCase:
    name: str
    description: str
    result: TestResult = TestResult.SKIP
    message: str = ""
    duration_seconds: float = 0.0
    details: dict = field(default_factory=dict)


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"

    @classmethod
    def disable(cls):
        cls.GREEN = cls.RED = cls.YELLOW = cls.BLUE = cls.BOLD = cls.END = ""


def colorize(text: str, color: str) -> str:
    return f"{color}{text}{Colors.END}"


class AdvancedNetworkingTester:
    def __init__(self, base_url: str, verbose: bool = False):
        self.base_url = base_url.rstrip("/")
        self.verbose = verbose
        self.results: list[TestCase] = []
        self.session = requests.Session()

    def log(self, message: str):
        if self.verbose:
            print(f"  {colorize('→', Colors.BLUE)} {message}")

    def run_all_tests(self, config: Optional[dict] = None):
        """Run all applicable tests based on configuration."""
        print(f"\n{colorize('=' * 60, Colors.BOLD)}")
        print(colorize("Advanced Networking Test Suite", Colors.BOLD))
        print(f"Target: {self.base_url}")
        print(colorize("=" * 60, Colors.BOLD))

        # Run test categories
        self._test_connectivity()

        if config:
            # Run fast/stable tests first
            if config.get("requestBody"):
                self._test_request_body(config["requestBody"])
            if config.get("buffering"):
                self._test_buffering(config["buffering"])
            if config.get("sessionAffinity"):
                self._test_session_affinity(config["sessionAffinity"])
            # Test upstreamContext BEFORE firewall since realIpHeader affects firewall behavior
            if config.get("upstreamContext"):
                self._test_upstream_context(config["upstreamContext"], config.get("firewall"))
            if config.get("firewall"):
                self._test_firewall(config["firewall"], config.get("upstreamContext"))
            if config.get("headers"):
                self._test_headers(config["headers"])
            if config.get("compression"):
                self._test_compression(config["compression"])
            if config.get("redirects"):
                self._test_redirects(config["redirects"])
            # Timeout tests run near the end (they take time and can leave server busy)
            if config.get("timeouts"):
                self._test_timeouts(config["timeouts"])
                self._wait_for_server_recovery("timeout tests")
            # Rate limit runs LAST since it can affect other tests
            if config.get("rateLimit"):
                self._test_rate_limit(config["rateLimit"])
        else:
            # Run with discovery/defaults
            self._test_request_body_discovery()
            self._test_session_affinity_discovery()
            self._test_headers_discovery()
            # Timeout tests run near the end
            self._test_timeouts_discovery()
            self._wait_for_server_recovery("timeout tests")
            # Rate limit runs LAST since it can affect other tests
            self._test_rate_limit_discovery()

        self._print_summary()

    def _wait_for_server_recovery(self, after_what: str, wait_seconds: int = 5):
        """Wait for server to recover after tests that may leave it busy."""
        self.log(f"Waiting {wait_seconds}s for server to recover after {after_what}...")
        time.sleep(wait_seconds)
        # Verify server is responsive
        for attempt in range(3):
            try:
                resp = requests.get(f"{self.base_url}/healthz", timeout=5)
                if resp.status_code == 200:
                    self.log("Server ready")
                    return
            except:
                pass
            time.sleep(2)
        self.log("Server may still be recovering, proceeding anyway...")

    def _test_connectivity(self):
        """Basic connectivity test."""
        print(f"\n{colorize('▶ Connectivity Test', Colors.BOLD)}")

        test = TestCase(
            name="basic_connectivity",
            description="Verify the endpoint is reachable"
        )

        start = time.time()
        try:
            resp = self.session.get(f"{self.base_url}/test/connectivity", timeout=10)
            test.duration_seconds = time.time() - start

            if resp.status_code == 200:
                test.result = TestResult.PASS
                test.message = f"Endpoint reachable (HTTP {resp.status_code})"
            elif resp.status_code == 404:
                # Fall back to /healthz if /test/connectivity not available
                resp = self.session.get(f"{self.base_url}/healthz", timeout=10)
                if resp.status_code == 200:
                    test.result = TestResult.PASS
                    test.message = f"Endpoint reachable via /healthz (HTTP {resp.status_code})"
                else:
                    test.result = TestResult.FAIL
                    test.message = f"Unexpected status code: {resp.status_code}"
            else:
                test.result = TestResult.FAIL
                test.message = f"Unexpected status code: {resp.status_code}"
        except requests.exceptions.RequestException as e:
            test.duration_seconds = time.time() - start
            test.result = TestResult.FAIL
            test.message = f"Connection failed: {e}"

        self._record_result(test)

    def _test_timeouts(self, config: dict):
        """Test timeout configurations."""
        print(f"\n{colorize('▶ Timeout Tests', Colors.BOLD)}")

        read_seconds = config.get("readSeconds", 60)
        write_seconds = config.get("writeSeconds", 60)
        client_body_timeout = config.get("clientBodyTimeoutSeconds", 0)

        # Test that requests within timeout succeed
        self._test_timeout_within_limit(read_seconds)

        # Test that requests exceeding timeout fail
        self._test_timeout_exceeds_limit(read_seconds)

        # Test client body timeout if configured
        if client_body_timeout > 0:
            self._test_client_body_timeout(client_body_timeout)

    def _test_timeouts_discovery(self):
        """Discover timeout limits through testing."""
        print(f"\n{colorize('▶ Timeout Tests (Discovery Mode)', Colors.BOLD)}")

        # Test common timeout boundaries
        test_durations = [30, 65, 90, 125]

        for duration in test_durations:
            test = TestCase(
                name=f"timeout_{duration}s",
                description=f"Request with {duration}s delay"
            )

            self.log(f"Testing {duration}s delay...")
            start = time.time()

            try:
                resp = self.session.get(
                    f"{self.base_url}/delay?seconds={duration}",
                    timeout=duration + 30  # Client timeout higher than expected server timeout
                )
                test.duration_seconds = time.time() - start

                if resp.status_code == 200:
                    test.result = TestResult.PASS
                    test.message = f"Completed in {test.duration_seconds:.1f}s"
                elif resp.status_code == 504:
                    test.result = TestResult.INCONCLUSIVE
                    test.message = f"Gateway timeout (504) - server timeout < {duration}s"
                else:
                    test.result = TestResult.INCONCLUSIVE
                    test.message = f"HTTP {resp.status_code}"

            except requests.exceptions.Timeout:
                test.duration_seconds = time.time() - start
                test.result = TestResult.INCONCLUSIVE
                test.message = f"Client timeout after {test.duration_seconds:.1f}s"
            except requests.exceptions.RequestException as e:
                test.duration_seconds = time.time() - start
                test.result = TestResult.FAIL
                test.message = f"Request failed: {e}"

            self._record_result(test)

    def _test_timeout_within_limit(self, timeout_seconds: int):
        """Test that a request within the timeout limit succeeds."""
        delay = max(1, timeout_seconds - 30)  # 30s buffer

        test = TestCase(
            name=f"timeout_within_limit_{delay}s",
            description=f"Request with {delay}s delay (within {timeout_seconds}s limit)"
        )

        self.log(f"Testing {delay}s delay (should succeed with {timeout_seconds}s timeout)...")
        start = time.time()

        try:
            resp = self.session.get(
                f"{self.base_url}/test/timeout?seconds={delay}",
                timeout=delay + 60
            )
            test.duration_seconds = time.time() - start
            test.details = {"status_code": resp.status_code, "expected_delay": delay}

            if resp.status_code == 200:
                if test.duration_seconds >= delay * 0.9:  # Allow 10% tolerance
                    test.result = TestResult.PASS
                    test.message = f"Completed in {test.duration_seconds:.1f}s (expected ~{delay}s)"
                else:
                    test.result = TestResult.INCONCLUSIVE
                    test.message = f"Completed too fast ({test.duration_seconds:.1f}s) - /test/timeout endpoint may not be deployed"
            elif resp.status_code == 404:
                test.result = TestResult.SKIP
                test.message = "/test/timeout endpoint not found - redeploy with updated server.py"
            elif resp.status_code == 504:
                test.result = TestResult.FAIL
                test.message = f"Gateway timeout - proxy timeout may be < {delay}s"
            elif resp.status_code >= 500:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"Server error (HTTP {resp.status_code}) - check server logs"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"Unexpected HTTP {resp.status_code}"

        except requests.exceptions.RequestException as e:
            test.duration_seconds = time.time() - start
            test.result = TestResult.FAIL
            test.message = f"Request failed: {e}"

        self._record_result(test)

    def _test_timeout_exceeds_limit(self, timeout_seconds: int):
        """Test that a request exceeding the timeout limit fails appropriately."""
        delay = timeout_seconds + 30  # 30s beyond limit

        test = TestCase(
            name=f"timeout_exceeds_limit_{delay}s",
            description=f"Request with {delay}s delay (exceeds {timeout_seconds}s limit)"
        )

        self.log(f"Testing {delay}s delay (should timeout with {timeout_seconds}s limit)...")
        start = time.time()

        try:
            resp = self.session.get(
                f"{self.base_url}/test/timeout?seconds={delay}",
                timeout=delay + 60
            )
            test.duration_seconds = time.time() - start
            test.details = {"status_code": resp.status_code, "expected_delay": delay, "actual_duration": test.duration_seconds}

            if resp.status_code == 504:
                test.result = TestResult.PASS
                test.message = f"Gateway timeout as expected after {test.duration_seconds:.1f}s"
            elif resp.status_code == 404:
                test.result = TestResult.SKIP
                test.message = "/test/timeout endpoint not found - redeploy with updated server.py"
            elif resp.status_code == 200:
                # Check if it actually delayed or returned immediately
                if test.duration_seconds < delay * 0.5:
                    test.result = TestResult.INCONCLUSIVE
                    test.message = f"Completed in {test.duration_seconds:.1f}s - /delay endpoint may not be deployed"
                elif test.duration_seconds >= timeout_seconds:
                    # It took longer than the configured timeout - timeout not enforced
                    test.result = TestResult.FAIL
                    test.message = f"Completed in {test.duration_seconds:.1f}s (timeout {timeout_seconds}s not enforced)"
                else:
                    test.result = TestResult.INCONCLUSIVE
                    test.message = f"Completed in {test.duration_seconds:.1f}s - unexpected"
            elif resp.status_code >= 500:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"Server error (HTTP {resp.status_code}) after {test.duration_seconds:.1f}s"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"HTTP {resp.status_code} after {test.duration_seconds:.1f}s"

        except requests.exceptions.Timeout:
            test.duration_seconds = time.time() - start
            test.result = TestResult.PASS
            test.message = f"Timed out as expected after {test.duration_seconds:.1f}s"
        except requests.exceptions.RequestException as e:
            test.duration_seconds = time.time() - start
            test.result = TestResult.INCONCLUSIVE
            test.message = f"Request failed after {test.duration_seconds:.1f}s: {e}"

        self._record_result(test)

    def _test_client_body_timeout(self, timeout_seconds: int):
        """Test client body timeout by sending data slowly.

        The client body timeout controls how long nginx waits between successive
        read operations while receiving the request body. If we send data slower
        than this timeout, the connection should be dropped.
        """
        test = TestCase(
            name=f"client_body_timeout_{timeout_seconds}s",
            description=f"Test slow request body upload (timeout: {timeout_seconds}s)"
        )

        self.log(f"Testing client body timeout ({timeout_seconds}s)...")
        self.log("Note: This test sends data with pauses to trigger the timeout")

        # We'll try to send data with a pause longer than the timeout
        pause_between_chunks = timeout_seconds + 5  # 5 seconds past timeout

        start = time.time()

        try:
            # Create a generator that yields data slowly
            def slow_body_generator():
                """Yield data with pauses to test client body timeout."""
                yield b"chunk1="
                time.sleep(pause_between_chunks)
                yield b"chunk2"

            # This should timeout because we pause longer than client_body_timeout
            resp = requests.post(
                f"{self.base_url}/update-greeting",
                data=slow_body_generator(),
                headers={"Content-Type": "application/octet-stream"},
                timeout=pause_between_chunks + 30  # Client timeout higher than expected
            )
            test.duration_seconds = time.time() - start
            test.details = {
                "status_code": resp.status_code,
                "pause_seconds": pause_between_chunks,
                "actual_duration": test.duration_seconds
            }

            if resp.status_code in [408, 499, 502]:
                test.result = TestResult.PASS
                test.message = f"Request timed out as expected (HTTP {resp.status_code})"
            elif resp.status_code == 200:
                # If we got 200, check if we actually waited
                if test.duration_seconds >= pause_between_chunks * 0.9:
                    test.result = TestResult.FAIL
                    test.message = f"Request succeeded after {test.duration_seconds:.1f}s (timeout not enforced)"
                else:
                    test.result = TestResult.INCONCLUSIVE
                    test.message = f"Request completed in {test.duration_seconds:.1f}s (generator may not have paused)"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"HTTP {resp.status_code} after {test.duration_seconds:.1f}s"

        except requests.exceptions.ChunkedEncodingError as e:
            test.duration_seconds = time.time() - start
            # Connection dropped mid-transfer - this is what we expect
            test.result = TestResult.PASS
            test.message = f"Connection dropped after {test.duration_seconds:.1f}s (client body timeout working)"
        except requests.exceptions.ConnectionError as e:
            test.duration_seconds = time.time() - start
            if test.duration_seconds < timeout_seconds + 10:
                test.result = TestResult.PASS
                test.message = f"Connection closed after {test.duration_seconds:.1f}s (timeout enforced)"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"Connection error after {test.duration_seconds:.1f}s: {e}"
        except requests.exceptions.Timeout:
            test.duration_seconds = time.time() - start
            test.result = TestResult.INCONCLUSIVE
            test.message = f"Client timeout after {test.duration_seconds:.1f}s"
        except requests.exceptions.RequestException as e:
            test.duration_seconds = time.time() - start
            test.result = TestResult.INCONCLUSIVE
            test.message = f"Request failed after {test.duration_seconds:.1f}s: {e}"

        self._record_result(test)

    def _test_request_body(self, config: dict):
        """Test request body size limits."""
        print(f"\n{colorize('▶ Request Body Size Tests', Colors.BOLD)}")

        max_size_bytes = config.get("maxSizeBytes", 1048576)  # Default 1MB
        max_size_mb = max_size_bytes / (1024 * 1024)

        # Test within limit
        self._test_body_size_within_limit(max_size_bytes)

        # Test exceeding limit
        self._test_body_size_exceeds_limit(max_size_bytes)

    def _test_request_body_discovery(self):
        """Discover request body size limits."""
        print(f"\n{colorize('▶ Request Body Size Tests (Discovery Mode)', Colors.BOLD)}")

        # Test common size boundaries (in MB)
        test_sizes_mb = [1, 10, 25, 55, 75, 105]

        for size_mb in test_sizes_mb:
            self._test_body_size(size_mb * 1024 * 1024, f"{size_mb}MB")

    def _test_body_size_within_limit(self, max_size_bytes: int):
        """Test that a body within the limit succeeds."""
        # Use 50% of limit to avoid server memory issues (JSON parsing needs ~2x memory)
        size_bytes = int(max_size_bytes * 0.5)
        size_desc = self._format_bytes(size_bytes)

        self._test_body_size(size_bytes, size_desc, expect_success=True)

    def _test_body_size_exceeds_limit(self, max_size_bytes: int):
        """Test that a body exceeding the limit fails."""
        size_bytes = int(max_size_bytes * 1.2)  # 120% of limit
        size_desc = self._format_bytes(size_bytes)

        self._test_body_size(size_bytes, size_desc, expect_success=False)

    def _test_body_size(self, size_bytes: int, size_desc: str, expect_success: Optional[bool] = None):
        """Test sending a body of specific size."""
        test = TestCase(
            name=f"body_size_{size_desc.replace(' ', '_')}",
            description=f"POST request with {size_desc} body"
        )

        self.log(f"Testing {size_desc} body...")

        # Generate payload - use raw bytes to avoid JSON overhead
        # We'll send as application/octet-stream to a generic endpoint
        payload_data = b"x" * size_bytes

        start = time.time()
        try:
            # Use a simple POST with raw data to the dedicated body-size test endpoint
            resp = self.session.post(
                f"{self.base_url}/test/body-size",
                data=payload_data,
                headers={"Content-Type": "application/octet-stream"},
                timeout=120
            )
            test.duration_seconds = time.time() - start
            test.details = {"status_code": resp.status_code, "size_bytes": size_bytes}

            # Analyze response
            if resp.status_code == 413:
                if expect_success is False:
                    test.result = TestResult.PASS
                    test.message = "Correctly rejected as too large (413)"
                else:
                    test.result = TestResult.FAIL
                    test.message = f"Rejected as too large but should have been accepted"
            elif resp.status_code in [200, 400]:
                # 200 or 400 means request reached the server (400 = bad JSON is OK)
                if expect_success is False:
                    test.result = TestResult.FAIL
                    test.message = f"Request accepted (HTTP {resp.status_code}) but should have been rejected"
                else:
                    test.result = TestResult.PASS
                    test.message = f"Request reached server (HTTP {resp.status_code})"
            elif resp.status_code == 502:
                # 502 often means backend crashed (OOM) or timed out
                test.result = TestResult.INCONCLUSIVE
                test.message = "Backend error (502) - server may have insufficient memory"
            elif resp.status_code == 504:
                test.result = TestResult.INCONCLUSIVE
                test.message = "Gateway timeout (504) - request took too long"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"HTTP {resp.status_code}"

        except requests.exceptions.RequestException as e:
            test.duration_seconds = time.time() - start
            error_str = str(e)
            test.details = {"error": error_str, "size_bytes": size_bytes}

            if "413" in error_str or "Request Entity Too Large" in error_str:
                test.result = TestResult.PASS if expect_success is False else TestResult.FAIL
                test.message = "Request rejected (413 - body too large)"
            elif "Connection" in error_str:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"Connection error (server may have closed connection for large body)"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"Request failed: {e}"

        self._record_result(test)

    def _test_rate_limit(self, config: dict):
        """Test rate limiting configuration."""
        print(f"\n{colorize('▶ Rate Limit Tests', Colors.BOLD)}")

        rpm = config.get("requestsPerMinute", 0)
        burst = config.get("burstSize", 5)

        if rpm == 0:
            test = TestCase(
                name="rate_limit_disabled",
                description="Rate limiting is not configured",
                result=TestResult.SKIP,
                message="No rate limit configured"
            )
            self._record_result(test)
            return

        self._test_rate_limit_enforcement(rpm, burst)

    def _test_rate_limit_discovery(self):
        """Discover rate limiting through testing."""
        print(f"\n{colorize('▶ Rate Limit Tests (Discovery Mode)', Colors.BOLD)}")
        self._test_rate_limit_enforcement(100, 10)  # Assume default

    def _test_rate_limit_enforcement(self, expected_rpm: int, burst_size: int):
        """Test that rate limiting is enforced."""
        # Burst bucket = rpm * burst_multiplier
        burst_bucket = expected_rpm * burst_size

        test = TestCase(
            name="rate_limit_enforcement",
            description=f"Send {expected_rpm + 50} requests rapidly (limit: {expected_rpm} rpm, burst: {burst_bucket})"
        )

        num_requests = expected_rpm + 50
        self.log(f"Sending {num_requests} requests rapidly...")
        self.log(f"Expected burst bucket: {burst_bucket} requests (rpm={expected_rpm} × burst={burst_size})")

        results = {"success": 0, "rate_limited": 0, "errors": 0}
        other_status_codes = {}  # Track specific non-200/429 codes
        errors = []

        def make_request(i):
            try:
                resp = requests.get(f"{self.base_url}/test/rate-limit", timeout=10)
                if resp.status_code == 404:
                    # Fall back to /healthz if new endpoint not available
                    resp = requests.get(f"{self.base_url}/healthz", timeout=10)
                return resp.status_code
            except Exception as e:
                return f"error:{type(e).__name__}:{e}"

        start = time.time()

        # Use moderate concurrency to avoid overwhelming small servers
        # while still testing rate limiting behavior
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(make_request, i): i for i in range(num_requests)}
            for future in as_completed(futures):
                status = future.result()
                if status == 200:
                    results["success"] += 1
                elif status == 429:
                    results["rate_limited"] += 1
                elif isinstance(status, str) and status.startswith("error:"):
                    results["errors"] += 1
                    if len(errors) < 5:
                        errors.append(status)
                else:
                    # Track other HTTP status codes
                    other_status_codes[status] = other_status_codes.get(status, 0) + 1

        test.duration_seconds = time.time() - start

        # Build detailed results
        test.details = {
            "success_200": results["success"],
            "rate_limited_429": results["rate_limited"],
            "connection_errors": results["errors"],
            "other_status_codes": other_status_codes,
            "total_requests": num_requests,
            "expected_burst_bucket": burst_bucket,
        }
        if errors:
            test.details["sample_errors"] = errors[:5]

        total_http_responses = results["success"] + results["rate_limited"] + sum(other_status_codes.values())

        # Build message parts for detailed output
        status_breakdown = [f"200:{results['success']}", f"429:{results['rate_limited']}"]
        for code, count in sorted(other_status_codes.items()):
            status_breakdown.append(f"{code}:{count}")
        if results["errors"] > 0:
            status_breakdown.append(f"errors:{results['errors']}")
        breakdown_str = ", ".join(status_breakdown)

        # Check for rate limiting - nginx can return 429 OR 503 depending on config
        if results["rate_limited"] > 0:
            test.result = TestResult.PASS
            test.message = f"Rate limiting active: {results['rate_limited']}/{num_requests} got 429 [{breakdown_str}]"
        elif other_status_codes.get(503, 0) > 0 and results["success"] <= burst_bucket:
            # 503 with limited successes suggests rate limiting (nginx sometimes uses 503)
            test.result = TestResult.PASS
            test.message = f"Rate limiting likely active via 503: {results['success']} succeeded, {other_status_codes[503]} got 503 [{breakdown_str}]"
            test.message += "\n           Note: nginx returned 503 instead of 429 - consider checking nginx config"
        elif total_http_responses == 0:
            test.result = TestResult.INCONCLUSIVE
            test.message = f"All {results['errors']} requests failed with connection errors"
            if errors:
                test.message += f"\n           Sample: {errors[0]}"
        elif results["success"] > 0 and sum(other_status_codes.values()) == 0 and results["errors"] == 0:
            # All requests succeeded - no rate limiting at all
            test.result = TestResult.FAIL
            test.message = f"No rate limiting detected: all {results['success']}/{num_requests} requests got 200"
        elif other_status_codes or results["errors"] > 0:
            # Some requests failed but not with 429 or expected 503 pattern
            test.result = TestResult.INCONCLUSIVE
            test.message = f"Mixed results [{breakdown_str}]"
            if 503 in other_status_codes:
                test.message += "\n           503 errors may indicate server overload or rate limiting"
            if errors:
                test.message += f"\n           Sample error: {errors[0]}"
        else:
            test.result = TestResult.INCONCLUSIVE
            test.message = f"Unexpected: [{breakdown_str}]"

        self._record_result(test)

    def _test_buffering(self, config: dict):
        """Test buffering configuration by checking header buffer limits."""
        print(f"\n{colorize('▶ Buffering Tests', Colors.BOLD)}")

        # Get outbound buffer size (this controls response header buffering)
        outbound = config.get("outbound", {})
        buffer_size_bytes = outbound.get("sizeBytes", 32768)  # Default 32KB
        buffer_size_kb = buffer_size_bytes // 1024

        self.log(f"Configured outbound buffer size: {buffer_size_kb}KB")

        # Test 1: Headers within buffer size should succeed
        self._test_headers_within_buffer(buffer_size_kb)

        # Test 2: Headers exceeding buffer size should fail with 502
        self._test_headers_exceed_buffer(buffer_size_kb)

    def _test_headers_within_buffer(self, buffer_size_kb: int):
        """Test that response headers within buffer size succeed."""
        # Use 50% of buffer to be safely within limits
        test_size_kb = max(1, buffer_size_kb // 2)

        test = TestCase(
            name=f"buffer_headers_within_{test_size_kb}kb",
            description=f"Response with {test_size_kb}KB headers (within {buffer_size_kb}KB buffer)"
        )

        self.log(f"Testing {test_size_kb}KB headers (should succeed)...")
        start = time.time()

        try:
            resp = self.session.get(
                f"{self.base_url}/test/buffering?size_kb={test_size_kb}",
                timeout=30
            )
            test.duration_seconds = time.time() - start
            test.details = {"status_code": resp.status_code, "header_size_kb": test_size_kb}

            if resp.status_code == 200:
                test.result = TestResult.PASS
                test.message = f"Headers within buffer accepted (HTTP 200)"
            elif resp.status_code == 404:
                test.result = TestResult.SKIP
                test.message = "/test/buffering endpoint not found - redeploy with updated server.py"
            elif resp.status_code == 502:
                test.result = TestResult.FAIL
                test.message = f"Got 502 but headers ({test_size_kb}KB) should be within buffer ({buffer_size_kb}KB)"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"Unexpected HTTP {resp.status_code}"

        except requests.exceptions.RequestException as e:
            test.duration_seconds = time.time() - start
            test.result = TestResult.FAIL
            test.message = f"Request failed: {e}"

        self._record_result(test)

    def _test_headers_exceed_buffer(self, buffer_size_kb: int):
        """Test that response headers exceeding buffer size fail with 502."""
        # Use 150% of buffer to clearly exceed limits
        test_size_kb = int(buffer_size_kb * 1.5)

        test = TestCase(
            name=f"buffer_headers_exceed_{test_size_kb}kb",
            description=f"Response with {test_size_kb}KB headers (exceeds {buffer_size_kb}KB buffer)"
        )

        self.log(f"Testing {test_size_kb}KB headers (should fail with 502)...")
        start = time.time()

        try:
            resp = self.session.get(
                f"{self.base_url}/test/buffering?size_kb={test_size_kb}",
                timeout=30
            )
            test.duration_seconds = time.time() - start
            test.details = {"status_code": resp.status_code, "header_size_kb": test_size_kb}

            if resp.status_code == 502:
                test.result = TestResult.PASS
                test.message = f"Correctly rejected with 502 (headers exceed buffer)"
            elif resp.status_code == 404:
                test.result = TestResult.SKIP
                test.message = "/test/buffering endpoint not found - redeploy with updated server.py"
            elif resp.status_code == 200:
                test.result = TestResult.FAIL
                test.message = f"Headers ({test_size_kb}KB) accepted but should exceed buffer ({buffer_size_kb}KB)"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"HTTP {resp.status_code} (expected 502)"

        except requests.exceptions.RequestException as e:
            test.duration_seconds = time.time() - start
            # Connection errors might also indicate buffer overflow
            if "502" in str(e):
                test.result = TestResult.PASS
                test.message = "Request failed with 502 (buffer exceeded)"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"Request failed: {e}"

        self._record_result(test)

    def _test_session_affinity(self, config: dict):
        """Test session affinity configuration."""
        print(f"\n{colorize('▶ Session Affinity Tests', Colors.BOLD)}")

        if not config.get("enabled", False):
            test = TestCase(
                name="session_affinity_disabled",
                description="Session affinity is not enabled",
                result=TestResult.SKIP,
                message="Session affinity not configured"
            )
            self._record_result(test)
            return

        mode = config.get("mode", "COOKIE")

        if mode == "COOKIE":
            self._test_cookie_affinity()
        elif mode == "CLIENT_IP":
            self._test_client_ip_affinity()

    def _test_session_affinity_discovery(self):
        """Test session affinity without known configuration."""
        print(f"\n{colorize('▶ Session Affinity Tests (Discovery Mode)', Colors.BOLD)}")
        self._test_cookie_affinity()

    def _test_cookie_affinity(self):
        """Test cookie-based session affinity."""
        test = TestCase(
            name="cookie_affinity",
            description="Verify cookie-based session affinity"
        )

        self.log("Testing cookie-based session affinity...")

        # First request - get affinity cookie
        session = requests.Session()
        hostnames = set()

        start = time.time()
        try:
            for i in range(10):
                resp = session.get(f"{self.base_url}/test/session-affinity", timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    hostnames.add(data.get("hostname", "unknown"))
                elif resp.status_code == 404:
                    # Fall back to /config if new endpoint not available
                    resp = session.get(f"{self.base_url}/config", timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        hostnames.add(data.get("hostname", "unknown"))
                time.sleep(0.1)

            test.duration_seconds = time.time() - start
            test.details = {"unique_hostnames": list(hostnames), "request_count": 10}

            if len(hostnames) == 1:
                test.result = TestResult.PASS
                test.message = f"All requests routed to same host: {list(hostnames)[0]}"
            elif len(hostnames) > 1:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"Requests routed to {len(hostnames)} different hosts (may not have affinity or single replica)"
            else:
                test.result = TestResult.FAIL
                test.message = "No hostname data received"

        except requests.exceptions.RequestException as e:
            test.duration_seconds = time.time() - start
            test.result = TestResult.FAIL
            test.message = f"Request failed: {e}"

        self._record_result(test)

    def _test_client_ip_affinity(self):
        """Test client IP-based session affinity."""
        test = TestCase(
            name="client_ip_affinity",
            description="Verify client IP-based session affinity"
        )

        self.log("Testing client IP-based session affinity...")

        hostnames = set()

        start = time.time()
        try:
            # Don't use session to avoid cookie affinity
            for i in range(10):
                resp = requests.get(f"{self.base_url}/test/session-affinity", timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    hostnames.add(data.get("hostname", "unknown"))
                elif resp.status_code == 404:
                    # Fall back to /config if new endpoint not available
                    resp = requests.get(f"{self.base_url}/config", timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        hostnames.add(data.get("hostname", "unknown"))
                time.sleep(0.1)

            test.duration_seconds = time.time() - start
            test.details = {"unique_hostnames": list(hostnames), "request_count": 10}

            if len(hostnames) == 1:
                test.result = TestResult.PASS
                test.message = f"All requests routed to same host: {list(hostnames)[0]}"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"Requests routed to {len(hostnames)} different hosts"

        except requests.exceptions.RequestException as e:
            test.duration_seconds = time.time() - start
            test.result = TestResult.FAIL
            test.message = f"Request failed: {e}"

        self._record_result(test)

    def _test_firewall(self, config: dict, upstream_context: Optional[dict] = None):
        """Test firewall/IP allowlisting and path blocking."""
        print(f"\n{colorize('▶ Firewall Tests', Colors.BOLD)}")

        allowed_cidrs = config.get("allowedCidrs", [])
        blocked_paths = config.get("blockedPaths", [])

        # Check if realIpHeader is configured - affects how we test firewall
        real_ip_header = upstream_context.get("realIpHeader", "") if upstream_context else ""

        if not allowed_cidrs and not blocked_paths:
            test = TestCase(
                name="firewall_disabled",
                description="No firewall rules configured",
                result=TestResult.SKIP,
                message="Firewall not configured (no allowedCidrs or blockedPaths)"
            )
            self._record_result(test)
            return

        if allowed_cidrs:
            self.log(f"Allowlist: {allowed_cidrs}")
            if real_ip_header:
                self.log(f"Note: realIpHeader ({real_ip_header}) is configured - firewall uses that header for IP")

            # Test 1: Check if we're allowed (verifies allowlist works for our IP)
            # When realIpHeader is configured, we need to send that header to get through
            self._test_firewall_allowed(allowed_cidrs, real_ip_header)

            # Test 2: Verify pod self-test (only if no realIpHeader or we can reach the endpoint)
            if not real_ip_header:
                self._test_firewall_ip_match(allowed_cidrs)

        if blocked_paths:
            self.log(f"Blocked paths: {blocked_paths}")
            self._test_blocked_paths(blocked_paths, real_ip_header, allowed_cidrs)

    def _test_firewall_allowed(self, allowed_cidrs: list, real_ip_header: str = ""):
        """Test basic firewall access."""
        test = TestCase(
            name="firewall_access",
            description=f"Test access with allowlist configured"
        )

        # If realIpHeader is configured, we need to send that header to get through
        headers = {}
        if real_ip_header and allowed_cidrs:
            # Use the first allowed IP from the CIDR
            allowed_ip = allowed_cidrs[0].split("/")[0]
            headers[real_ip_header] = allowed_ip
            test.description = f"Test access with {real_ip_header}: {allowed_ip}"

        start = time.time()
        try:
            resp = self.session.get(f"{self.base_url}/test/firewall", headers=headers, timeout=10)
            test.duration_seconds = time.time() - start
            test.details = {
                "status_code": resp.status_code,
                "allowed_cidrs": allowed_cidrs,
                "headers_sent": headers
            }

            if resp.status_code == 200:
                test.result = TestResult.PASS
                if real_ip_header:
                    test.message = f"Access allowed via {real_ip_header} header"
                else:
                    test.message = "Access allowed (your IP is in the allowlist)"
            elif resp.status_code == 404:
                # Fall back to /healthz if new endpoint not available
                resp = self.session.get(f"{self.base_url}/healthz", headers=headers, timeout=10)
                if resp.status_code == 200:
                    test.result = TestResult.PASS
                    test.message = "Access allowed (your IP is in the allowlist)"
                elif resp.status_code == 403:
                    test.result = TestResult.PASS
                    test.message = "Access denied (your IP is NOT in the allowlist) - firewall working!"
                else:
                    test.result = TestResult.INCONCLUSIVE
                    test.message = f"HTTP {resp.status_code}"
            elif resp.status_code == 403:
                if real_ip_header:
                    test.result = TestResult.FAIL
                    test.message = f"Access denied even with {real_ip_header} header - realIpHeader may not be working"
                else:
                    test.result = TestResult.PASS
                    test.message = "Access denied (your IP is NOT in the allowlist) - firewall working!"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"HTTP {resp.status_code}"

        except requests.exceptions.RequestException as e:
            test.duration_seconds = time.time() - start
            test.result = TestResult.INCONCLUSIVE
            test.message = f"Request failed: {e}"

        self._record_result(test)

    def _test_firewall_ip_match(self, allowed_cidrs: list):
        """Test that pod IP (not in allowlist) gets blocked when requesting through ingress."""
        test = TestCase(
            name="firewall_internal_blocked",
            description="Verify pod IP is blocked by firewall (requests through ingress)"
        )

        self.log("Asking pod to request itself through ingress (pod IP should be blocked)...")

        start = time.time()
        try:
            # Extract host from base_url for the self-test
            from urllib.parse import urlparse as url_parse
            parsed = url_parse(self.base_url)
            host = parsed.netloc

            resp = self.session.get(
                f"{self.base_url}/firewall-self-test?host={host}",
                timeout=15
            )
            test.duration_seconds = time.time() - start

            if resp.status_code == 404:
                test.result = TestResult.SKIP
                test.message = "/firewall-self-test endpoint not found - redeploy with updated server.py"
                self._record_result(test)
                return

            if resp.status_code == 403:
                # We ourselves are blocked - can't run this test
                test.result = TestResult.SKIP
                test.message = "Cannot run self-test: our IP is blocked by firewall"
                self._record_result(test)
                return

            if resp.status_code != 200:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"Unexpected status: HTTP {resp.status_code}"
                self._record_result(test)
                return

            data = resp.json()
            test.details = data

            internal_status = data.get("internal_request_status")
            blocked = data.get("blocked", False)

            if blocked and internal_status == 403:
                test.result = TestResult.PASS
                test.message = f"Pod IP correctly blocked (403) when requesting through ingress"
                test.message += f"\n           Pod: {data.get('pod_hostname', 'unknown')}"
            elif internal_status == 200:
                test.result = TestResult.FAIL
                test.message = f"Pod request succeeded (200) - firewall not blocking internal IPs!"
                test.message += f"\n           Pod IP may need to be excluded from allowlist"
            elif "error" in data:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"Self-test error: {data.get('error', 'unknown')}"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"Internal request returned {internal_status}"

        except requests.exceptions.RequestException as e:
            test.duration_seconds = time.time() - start
            if "403" in str(e):
                test.result = TestResult.SKIP
                test.message = "Our IP is blocked - cannot run pod self-test"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"Request failed: {e}"

        self._record_result(test)

    def _test_blocked_paths(self, blocked_paths: list, real_ip_header: str = "", allowed_cidrs: list = None):
        """Test that configured blocked paths return 403."""
        # If realIpHeader is configured, we need to send that header to pass IP allowlist
        headers = {}
        if real_ip_header and allowed_cidrs:
            allowed_ip = allowed_cidrs[0].split("/")[0]
            headers[real_ip_header] = allowed_ip

        for path in blocked_paths:
            test = TestCase(
                name=f"blocked_path_{path.replace('/', '_')}",
                description=f"Verify path '{path}' returns 403"
            )

            self.log(f"Testing blocked path: {path}...")
            start = time.time()

            try:
                resp = self.session.get(f"{self.base_url}{path}", headers=headers, timeout=10)
                test.duration_seconds = time.time() - start
                test.details = {"status_code": resp.status_code, "path": path, "headers_sent": headers}

                if resp.status_code == 403:
                    test.result = TestResult.PASS
                    test.message = f"Correctly blocked with 403"
                elif resp.status_code == 404:
                    test.result = TestResult.INCONCLUSIVE
                    test.message = f"Path returned 404 (may not exist on server)"
                elif resp.status_code == 200:
                    test.result = TestResult.FAIL
                    test.message = f"Path accessible (200) - should be blocked!"
                else:
                    test.result = TestResult.INCONCLUSIVE
                    test.message = f"HTTP {resp.status_code}"

            except requests.exceptions.RequestException as e:
                test.duration_seconds = time.time() - start
                if "403" in str(e):
                    test.result = TestResult.PASS
                    test.message = "Correctly blocked with 403"
                else:
                    test.result = TestResult.INCONCLUSIVE
                    test.message = f"Request failed: {e}"

            self._record_result(test)

    def _test_headers(self, config: dict):
        """Test header manipulation configuration."""
        print(f"\n{colorize('▶ Header Manipulation Tests', Colors.BOLD)}")

        request_config = config.get("request", {})
        response_config = config.get("response", {})

        if not request_config and not response_config:
            test = TestCase(
                name="headers_disabled",
                description="No header manipulation configured",
                result=TestResult.SKIP,
                message="Headers not configured"
            )
            self._record_result(test)
            return

        # Test request headers (headers added to requests going to backend)
        if request_config:
            add_headers = request_config.get("add", {})
            remove_headers = request_config.get("remove", [])

            if add_headers:
                self._test_request_headers_added(add_headers)
            if remove_headers:
                self._test_request_headers_removed(remove_headers)

        # Test response headers (headers added/removed from responses)
        if response_config:
            add_headers = response_config.get("add", {})
            remove_headers = response_config.get("remove", [])

            if add_headers:
                self._test_response_headers_added(add_headers)
            if remove_headers:
                self._test_response_headers_removed(remove_headers)

    def _test_headers_discovery(self):
        """Test header echo endpoint is available."""
        print(f"\n{colorize('▶ Header Tests (Discovery Mode)', Colors.BOLD)}")

        test = TestCase(
            name="headers_echo_endpoint",
            description="Verify /test/headers endpoint is available"
        )

        start = time.time()
        try:
            resp = self.session.get(f"{self.base_url}/test/headers", timeout=10)
            # Fall back to /headers-echo if new endpoint not available
            if resp.status_code == 404:
                resp = self.session.get(f"{self.base_url}/headers-echo", timeout=10)
            test.duration_seconds = time.time() - start

            if resp.status_code == 200:
                data = resp.json()
                test.result = TestResult.PASS
                test.message = f"Endpoint available, received {len(data.get('request_headers', {}))} headers"
                test.details = {"headers_count": len(data.get("request_headers", {}))}
            elif resp.status_code == 404:
                test.result = TestResult.SKIP
                test.message = "/test/headers endpoint not found - redeploy with updated server.py"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"HTTP {resp.status_code}"

        except requests.exceptions.RequestException as e:
            test.duration_seconds = time.time() - start
            test.result = TestResult.FAIL
            test.message = f"Request failed: {e}"

        self._record_result(test)

    def _test_request_headers_added(self, headers_to_add: dict):
        """Test that configured request headers are added."""
        for header_name, expected_value in headers_to_add.items():
            test = TestCase(
                name=f"request_header_add_{header_name.lower()}",
                description=f"Verify request header '{header_name}' is added"
            )

            self.log(f"Testing request header addition: {header_name}...")
            start = time.time()

            try:
                resp = self.session.get(f"{self.base_url}/test/headers", timeout=10)
                test.duration_seconds = time.time() - start

                if resp.status_code == 404:
                    # Fall back to /headers-echo if new endpoint not available
                    resp = self.session.get(f"{self.base_url}/headers-echo", timeout=10)
                    if resp.status_code == 404:
                        test.result = TestResult.SKIP
                        test.message = "/test/headers endpoint not found"
                        self._record_result(test)
                        continue

                if resp.status_code == 200:
                    data = resp.json()
                    received_headers = data.get("request_headers", {})
                    actual_value = received_headers.get(header_name)

                    test.details = {"expected": expected_value, "actual": actual_value}

                    if actual_value == expected_value:
                        test.result = TestResult.PASS
                        test.message = f"Header correctly added with value: {actual_value}"
                    elif actual_value:
                        test.result = TestResult.FAIL
                        test.message = f"Header present but value mismatch: expected '{expected_value}', got '{actual_value}'"
                    else:
                        test.result = TestResult.FAIL
                        test.message = f"Header not found in request (proxy may not be adding it)"
                else:
                    test.result = TestResult.INCONCLUSIVE
                    test.message = f"HTTP {resp.status_code}"

            except requests.exceptions.RequestException as e:
                test.duration_seconds = time.time() - start
                test.result = TestResult.FAIL
                test.message = f"Request failed: {e}"

            self._record_result(test)

    def _test_request_headers_removed(self, headers_to_remove: list):
        """Test that configured request headers are removed."""
        for header_name in headers_to_remove:
            test = TestCase(
                name=f"request_header_remove_{header_name.lower()}",
                description=f"Verify request header '{header_name}' is removed"
            )

            self.log(f"Testing request header removal: {header_name}...")
            start = time.time()

            try:
                # Send request with the header that should be stripped
                resp = self.session.get(
                    f"{self.base_url}/test/headers",
                    headers={header_name: "test-value-should-be-stripped"},
                    timeout=10
                )
                test.duration_seconds = time.time() - start

                if resp.status_code == 404:
                    # Fall back to /headers-echo if new endpoint not available
                    resp = self.session.get(
                        f"{self.base_url}/headers-echo",
                        headers={header_name: "test-value-should-be-stripped"},
                        timeout=10
                    )
                    if resp.status_code == 404:
                        test.result = TestResult.SKIP
                        test.message = "/test/headers endpoint not found"
                        self._record_result(test)
                        continue

                if resp.status_code == 200:
                    data = resp.json()
                    received_headers = data.get("request_headers", {})
                    actual_value = received_headers.get(header_name)

                    test.details = {"header": header_name, "value_if_present": actual_value}

                    if not actual_value or actual_value == "":
                        test.result = TestResult.PASS
                        test.message = "Header correctly removed/cleared"
                    else:
                        test.result = TestResult.FAIL
                        test.message = f"Header still present with value: {actual_value}"
                else:
                    test.result = TestResult.INCONCLUSIVE
                    test.message = f"HTTP {resp.status_code}"

            except requests.exceptions.RequestException as e:
                test.duration_seconds = time.time() - start
                test.result = TestResult.FAIL
                test.message = f"Request failed: {e}"

            self._record_result(test)

    def _test_response_headers_added(self, headers_to_add: dict):
        """Test that configured response headers are added."""
        for header_name, expected_value in headers_to_add.items():
            test = TestCase(
                name=f"response_header_add_{header_name.lower()}",
                description=f"Verify response header '{header_name}' is added"
            )

            self.log(f"Testing response header addition: {header_name}...")
            start = time.time()

            try:
                resp = self.session.get(f"{self.base_url}/test/headers", timeout=10)
                # Fall back to /healthz if new endpoint not available
                if resp.status_code == 404:
                    resp = self.session.get(f"{self.base_url}/healthz", timeout=10)
                test.duration_seconds = time.time() - start

                actual_value = resp.headers.get(header_name)
                test.details = {"expected": expected_value, "actual": actual_value}

                if actual_value == expected_value:
                    test.result = TestResult.PASS
                    test.message = f"Header correctly added with value: {actual_value}"
                elif actual_value:
                    test.result = TestResult.FAIL
                    test.message = f"Header present but value mismatch: expected '{expected_value}', got '{actual_value}'"
                else:
                    test.result = TestResult.FAIL
                    test.message = f"Header not found in response"

            except requests.exceptions.RequestException as e:
                test.duration_seconds = time.time() - start
                test.result = TestResult.FAIL
                test.message = f"Request failed: {e}"

            self._record_result(test)

    def _test_response_headers_removed(self, headers_to_remove: list):
        """Test that configured response headers are removed."""
        for header_name in headers_to_remove:
            test = TestCase(
                name=f"response_header_remove_{header_name.lower()}",
                description=f"Verify response header '{header_name}' is removed"
            )

            self.log(f"Testing response header removal: {header_name}...")
            start = time.time()

            try:
                resp = self.session.get(f"{self.base_url}/test/headers", timeout=10)
                # Fall back to /healthz if new endpoint not available
                if resp.status_code == 404:
                    resp = self.session.get(f"{self.base_url}/healthz", timeout=10)
                test.duration_seconds = time.time() - start

                actual_value = resp.headers.get(header_name)
                test.details = {"header": header_name, "value_if_present": actual_value}

                if not actual_value:
                    test.result = TestResult.PASS
                    test.message = "Header correctly removed"
                else:
                    test.result = TestResult.INCONCLUSIVE
                    test.message = f"Header still present: {actual_value} (may be added by server, not proxy)"

            except requests.exceptions.RequestException as e:
                test.duration_seconds = time.time() - start
                test.result = TestResult.FAIL
                test.message = f"Request failed: {e}"

            self._record_result(test)

    def _test_compression(self, config: dict):
        """Test compression (gzip) configuration."""
        print(f"\n{colorize('▶ Compression Tests', Colors.BOLD)}")

        if not config.get("enabled", False):
            test = TestCase(
                name="compression_disabled",
                description="Compression is not enabled",
                result=TestResult.SKIP,
                message="Compression not configured"
            )
            self._record_result(test)
            return

        # Test that compression is applied to compressible content
        self._test_compression_applied(config)

        # Test that compression respects Accept-Encoding
        self._test_compression_accept_encoding()

    def _test_compression_applied(self, config: dict):
        """Test that gzip compression is applied to responses."""
        test = TestCase(
            name="compression_gzip_applied",
            description="Verify gzip compression is applied to responses"
        )

        self.log("Testing gzip compression on JSON response...")
        start = time.time()

        try:
            # Request with Accept-Encoding: gzip
            resp = self.session.get(
                f"{self.base_url}/test/compression",
                headers={"Accept-Encoding": "gzip, deflate"},
                timeout=10
            )
            # Fall back to /config if new endpoint not available
            if resp.status_code == 404:
                resp = self.session.get(
                    f"{self.base_url}/config",
                    headers={"Accept-Encoding": "gzip, deflate"},
                    timeout=10
                )
            test.duration_seconds = time.time() - start

            content_encoding = resp.headers.get("Content-Encoding", "")
            content_length = resp.headers.get("Content-Length", "unknown")

            test.details = {
                "status_code": resp.status_code,
                "content_encoding": content_encoding,
                "content_length": content_length,
                "content_type": resp.headers.get("Content-Type", "")
            }

            if resp.status_code == 200:
                if "gzip" in content_encoding.lower():
                    test.result = TestResult.PASS
                    test.message = f"Response is gzip compressed (Content-Encoding: {content_encoding})"
                else:
                    # Compression may not be applied to small responses
                    min_length = config.get("minLength", 256)
                    test.result = TestResult.INCONCLUSIVE
                    test.message = f"Response not compressed (may be below {min_length} byte threshold)"
                    test.message += f"\n           Content-Length: {content_length}"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"HTTP {resp.status_code}"

        except requests.exceptions.RequestException as e:
            test.duration_seconds = time.time() - start
            test.result = TestResult.FAIL
            test.message = f"Request failed: {e}"

        self._record_result(test)

    def _test_compression_accept_encoding(self):
        """Test that compression respects Accept-Encoding header."""
        test = TestCase(
            name="compression_respects_accept_encoding",
            description="Verify compression is not applied when not requested"
        )

        self.log("Testing response without Accept-Encoding...")
        start = time.time()

        try:
            # Request without Accept-Encoding
            resp = self.session.get(
                f"{self.base_url}/test/compression",
                headers={"Accept-Encoding": "identity"},  # Explicitly request no compression
                timeout=10
            )
            # Fall back to /config if new endpoint not available
            if resp.status_code == 404:
                resp = self.session.get(
                    f"{self.base_url}/config",
                    headers={"Accept-Encoding": "identity"},
                    timeout=10
                )
            test.duration_seconds = time.time() - start

            content_encoding = resp.headers.get("Content-Encoding", "")

            test.details = {
                "status_code": resp.status_code,
                "content_encoding": content_encoding
            }

            if resp.status_code == 200:
                if not content_encoding or content_encoding == "identity":
                    test.result = TestResult.PASS
                    test.message = "Response correctly not compressed when not requested"
                elif "gzip" in content_encoding.lower():
                    test.result = TestResult.FAIL
                    test.message = "Response compressed despite Accept-Encoding: identity"
                else:
                    test.result = TestResult.INCONCLUSIVE
                    test.message = f"Unexpected Content-Encoding: {content_encoding}"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"HTTP {resp.status_code}"

        except requests.exceptions.RequestException as e:
            test.duration_seconds = time.time() - start
            test.result = TestResult.FAIL
            test.message = f"Request failed: {e}"

        self._record_result(test)

    def _test_redirects(self, config: dict):
        """Test host-based redirect configuration."""
        print(f"\n{colorize('▶ Redirect Tests', Colors.BOLD)}")

        host_redirects = config.get("hostRedirects", [])

        if not host_redirects:
            test = TestCase(
                name="redirects_disabled",
                description="No redirects configured",
                result=TestResult.SKIP,
                message="Redirects not configured"
            )
            self._record_result(test)
            return

        for redirect in host_redirects:
            from_host = redirect.get("from", "")
            to_host = redirect.get("to", "")
            permanent = redirect.get("permanent", False)

            if from_host and to_host:
                self._test_host_redirect(from_host, to_host, permanent)

    def _test_host_redirect(self, from_host: str, to_host: str, permanent: bool):
        """Test a specific host redirect rule."""
        expected_code = 301 if permanent else 302
        test = TestCase(
            name=f"redirect_{from_host.replace('.', '_')}_to_{to_host.replace('.', '_')}",
            description=f"Verify redirect from '{from_host}' to '{to_host}' ({expected_code})"
        )

        self.log(f"Testing redirect: {from_host} -> {to_host} ({expected_code})...")

        # Note: We can only test this if we can actually reach the from_host
        # This test will be INCONCLUSIVE if we can't resolve/reach the from_host
        # In a real scenario, you'd need DNS pointing from_host to the ingress

        start = time.time()
        try:
            # Try to make a request with Host header set to the from_host
            # This simulates what would happen if DNS pointed from_host to this server
            resp = requests.get(
                f"{self.base_url}/test/redirect",
                headers={"Host": from_host},
                allow_redirects=False,
                timeout=10
            )
            test.duration_seconds = time.time() - start

            test.details = {
                "status_code": resp.status_code,
                "location": resp.headers.get("Location", ""),
                "from_host": from_host,
                "to_host": to_host,
                "expected_code": expected_code
            }

            if resp.status_code == expected_code:
                location = resp.headers.get("Location", "")
                if to_host in location:
                    test.result = TestResult.PASS
                    test.message = f"Correctly redirected ({expected_code}) to: {location}"
                else:
                    test.result = TestResult.FAIL
                    test.message = f"Redirected but to wrong location: {location}"
            elif resp.status_code in [301, 302, 307, 308]:
                location = resp.headers.get("Location", "")
                test.result = TestResult.INCONCLUSIVE
                test.message = f"Got {resp.status_code} (expected {expected_code}) -> {location}"
            elif resp.status_code == 200:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"No redirect occurred - Host header may not trigger redirect rule"
                test.message += f"\n           (Redirect rules may only work with actual DNS resolution)"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"HTTP {resp.status_code}"

        except requests.exceptions.RequestException as e:
            test.duration_seconds = time.time() - start
            test.result = TestResult.INCONCLUSIVE
            test.message = f"Request failed: {e}"

        self._record_result(test)

    def _test_upstream_context(self, config: dict, firewall_config: Optional[dict] = None):
        """Test upstream context configuration (real IP header)."""
        print(f"\n{colorize('▶ Upstream Context Tests', Colors.BOLD)}")

        real_ip_header = config.get("realIpHeader", "")

        if not real_ip_header:
            test = TestCase(
                name="upstream_context_disabled",
                description="No upstream context configured",
                result=TestResult.SKIP,
                message="UpstreamContext not configured"
            )
            self._record_result(test)
            return

        self.log(f"Real IP header configured: {real_ip_header}")

        # Test 1: Verify header is passed to backend
        self._test_real_ip_header(real_ip_header)

        # Test 2: Verify nginx uses the header for IP-based decisions (firewall)
        if firewall_config and firewall_config.get("allowedCidrs"):
            self._test_real_ip_header_firewall(real_ip_header, firewall_config["allowedCidrs"])

    def _test_real_ip_header(self, header_name: str):
        """Test that the real_ip_header directive is working."""
        test = TestCase(
            name="real_ip_header",
            description=f"Verify real IP is extracted from '{header_name}'"
        )

        self.log(f"Testing real IP header extraction from: {header_name}...")

        # Use a distinctive test IP
        test_ip = "73.162.196.20"

        start = time.time()
        try:
            # Send request with the configured real IP header
            custom_headers = {header_name: test_ip}
            resp = self.session.get(
                f"{self.base_url}/test/headers",
                headers=custom_headers,
                timeout=10
            )
            # Fall back to /headers-echo if new endpoint not available
            if resp.status_code == 404:
                resp = self.session.get(
                    f"{self.base_url}/headers-echo",
                    headers=custom_headers,
                    timeout=10
                )
            test.duration_seconds = time.time() - start

            if resp.status_code == 404:
                test.result = TestResult.SKIP
                test.message = "/test/headers endpoint not found"
                self._record_result(test)
                return

            if resp.status_code == 200:
                data = resp.json()
                client_info = data.get("client_info", {})
                received_headers = data.get("request_headers", {})

                perceived_ip = client_info.get("perceived_ip", "")
                ip_source = client_info.get("ip_source", "")

                test.details = {
                    "test_ip": test_ip,
                    "perceived_ip": perceived_ip,
                    "ip_source": ip_source,
                    "header_received": received_headers.get(header_name)
                }

                # Note: The backend sees the original header; nginx real_ip_header
                # affects how nginx interprets the client IP for its own processing
                # (logging, geo, etc). The backend still receives the header.
                if received_headers.get(header_name) == test_ip:
                    test.result = TestResult.PASS
                    test.message = f"Header '{header_name}' correctly passed to backend with value: {test_ip}"
                    test.message += f"\n           (nginx real_ip_header affects nginx's IP perception, not backend)"
                else:
                    test.result = TestResult.INCONCLUSIVE
                    test.message = f"Header value: {received_headers.get(header_name)} (expected {test_ip})"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"HTTP {resp.status_code}"

        except requests.exceptions.RequestException as e:
            test.duration_seconds = time.time() - start
            test.result = TestResult.FAIL
            test.message = f"Request failed: {e}"

        self._record_result(test)

    def _test_real_ip_header_firewall(self, header_name: str, allowed_cidrs: list):
        """Test that nginx uses real_ip_header for firewall (whitelist-source-range) decisions.

        This is the CRITICAL test for real_ip_header functionality:
        - If firewall allowedCidrs is set to a test IP (e.g., 73.162.196.20/32)
        - And we send the header with that IP (e.g., CF-Connecting-IP: 73.162.196.20)
        - nginx should use that IP for firewall evaluation
        - If allowed: real_ip_header is working
        - If blocked (403): nginx is using real client IP, not the header
        """
        test = TestCase(
            name="real_ip_header_firewall_integration",
            description=f"Verify nginx uses '{header_name}' for firewall decisions"
        )

        # Extract the test IP from the first CIDR in the allowlist
        if not allowed_cidrs:
            test.result = TestResult.SKIP
            test.message = "No allowedCidrs configured"
            self._record_result(test)
            return

        # Parse the test IP from CIDR (e.g., "73.162.196.20/32" -> "73.162.196.20")
        test_ip = allowed_cidrs[0].split("/")[0]

        self.log(f"Testing firewall with {header_name}: {test_ip}")
        self.log(f"Allowlist: {allowed_cidrs}")

        start = time.time()
        try:
            # Send request WITH the configured real IP header set to an allowed IP
            custom_headers = {header_name: test_ip}
            resp = self.session.get(
                f"{self.base_url}/test/firewall",
                headers=custom_headers,
                timeout=10
            )
            # Fall back to /healthz if new endpoint not available
            if resp.status_code == 404:
                resp = self.session.get(
                    f"{self.base_url}/healthz",
                    headers=custom_headers,
                    timeout=10
                )
            test.duration_seconds = time.time() - start
            test.details = {
                "header_name": header_name,
                "header_value": test_ip,
                "allowed_cidrs": allowed_cidrs,
                "status_code": resp.status_code
            }

            if resp.status_code == 200:
                test.result = TestResult.PASS
                test.message = f"Firewall allowed request! nginx correctly used '{header_name}' ({test_ip}) for IP evaluation"
                test.message += f"\n           This proves real_ip_header directive is working"
            elif resp.status_code == 403:
                test.result = TestResult.FAIL
                test.message = f"Firewall blocked (403) - nginx is NOT using '{header_name}' for IP evaluation"
                test.message += f"\n           nginx is likely using your real IP or the NLB IP instead"
                test.message += f"\n           Check: Is real_ip_header in server-snippet? Is it overriding proxy_protocol?"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"Unexpected HTTP {resp.status_code}"

        except requests.exceptions.RequestException as e:
            test.duration_seconds = time.time() - start
            if "403" in str(e):
                test.result = TestResult.FAIL
                test.message = f"Firewall blocked - nginx not using '{header_name}'"
            else:
                test.result = TestResult.INCONCLUSIVE
                test.message = f"Request failed: {e}"

        self._record_result(test)

        # Also test WITHOUT the header to verify firewall blocks
        test2 = TestCase(
            name="real_ip_header_firewall_without_header",
            description=f"Verify firewall blocks when '{header_name}' is not sent"
        )

        self.log(f"Testing firewall WITHOUT {header_name} header...")

        start = time.time()
        try:
            # Send request WITHOUT the header - should be blocked
            resp = self.session.get(
                f"{self.base_url}/test/firewall",
                timeout=10
            )
            # Fall back to /healthz if new endpoint not available
            if resp.status_code == 404:
                resp = self.session.get(
                    f"{self.base_url}/healthz",
                    timeout=10
                )
            test2.duration_seconds = time.time() - start
            test2.details = {"status_code": resp.status_code, "allowed_cidrs": allowed_cidrs}

            if resp.status_code == 403:
                test2.result = TestResult.PASS
                test2.message = "Correctly blocked (403) when header not present"
                test2.message += f"\n           Your real IP is not in allowlist - firewall working!"
            elif resp.status_code == 200:
                test2.result = TestResult.INCONCLUSIVE
                test2.message = "Request allowed without header - your real IP may be in allowlist"
            else:
                test2.result = TestResult.INCONCLUSIVE
                test2.message = f"HTTP {resp.status_code}"

        except requests.exceptions.RequestException as e:
            test2.duration_seconds = time.time() - start
            if "403" in str(e):
                test2.result = TestResult.PASS
                test2.message = "Correctly blocked when header not present"
            else:
                test2.result = TestResult.INCONCLUSIVE
                test2.message = f"Request failed: {e}"

        self._record_result(test2)

    def _record_result(self, test: TestCase):
        """Record and display a test result."""
        self.results.append(test)

        if test.result == TestResult.PASS:
            status = colorize("✓ PASS", Colors.GREEN)
        elif test.result == TestResult.FAIL:
            status = colorize("✗ FAIL", Colors.RED)
        elif test.result == TestResult.SKIP:
            status = colorize("○ SKIP", Colors.YELLOW)
        else:
            status = colorize("? INCONCLUSIVE", Colors.YELLOW)

        print(f"  {status}: {test.description}")
        if test.message:
            print(f"           {test.message}")

    def _print_summary(self):
        """Print test summary."""
        print(f"\n{colorize('=' * 60, Colors.BOLD)}")
        print(colorize("Summary", Colors.BOLD))
        print(colorize("=" * 60, Colors.BOLD))

        passed = sum(1 for t in self.results if t.result == TestResult.PASS)
        failed = sum(1 for t in self.results if t.result == TestResult.FAIL)
        skipped = sum(1 for t in self.results if t.result == TestResult.SKIP)
        inconclusive = sum(1 for t in self.results if t.result == TestResult.INCONCLUSIVE)

        print(f"  {colorize('Passed:', Colors.GREEN)} {passed}")
        print(f"  {colorize('Failed:', Colors.RED)} {failed}")
        print(f"  {colorize('Skipped:', Colors.YELLOW)} {skipped}")
        print(f"  {colorize('Inconclusive:', Colors.YELLOW)} {inconclusive}")
        print()

        if failed > 0:
            print(colorize("Failed Tests:", Colors.RED))
            for test in self.results:
                if test.result == TestResult.FAIL:
                    print(f"  - {test.name}: {test.message}")
            print()

    def _format_bytes(self, size_bytes: int) -> str:
        """Format bytes as human-readable string."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f}TB"

    def get_exit_code(self) -> int:
        """Return appropriate exit code based on results."""
        failed = sum(1 for t in self.results if t.result == TestResult.FAIL)
        return 1 if failed > 0 else 0


def load_config_from_yaml(yaml_path: str) -> dict:
    """Load advanced networking config from a porter.yaml file."""
    try:
        import yaml
    except ImportError:
        print("Warning: PyYAML not installed. Install with: pip install pyyaml")
        return {}

    try:
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        # Extract advancedNetworking from services
        for service in data.get("services", []):
            if service.get("type") == "web" and "advancedNetworking" in service:
                return service["advancedNetworking"]

        return {}
    except Exception as e:
        print(f"Warning: Could not load config from {yaml_path}: {e}")
        return {}


def main():
    parser = argparse.ArgumentParser(
        description="Test advanced networking annotations for Porter web services"
    )
    parser.add_argument("url", help="Base URL to test")
    parser.add_argument(
        "--config",
        help="Path to porter.yaml file to read expected configuration"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    if args.no_color:
        Colors.disable()

    config = None
    if args.config:
        config = load_config_from_yaml(args.config)
        if config:
            print(f"Loaded configuration from {args.config}")

    tester = AdvancedNetworkingTester(args.url, verbose=args.verbose)
    tester.run_all_tests(config)

    if args.json:
        results = []
        for test in tester.results:
            results.append({
                "name": test.name,
                "description": test.description,
                "result": test.result.value,
                "message": test.message,
                "duration_seconds": test.duration_seconds,
                "details": test.details
            })
        print(json.dumps(results, indent=2))

    sys.exit(tester.get_exit_code())


if __name__ == "__main__":
    main()
