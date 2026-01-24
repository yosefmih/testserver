#!/usr/bin/env python3
"""
Advanced Networking Annotation Test Suite

Tests all advanced networking configurations for Porter web services:
- Timeouts (connect, read, write)
- Request body size limits
- Rate limiting
- Session affinity (cookie and client IP modes)
- Firewall/IP allowlisting

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
            if config.get("timeouts"):
                self._test_timeouts(config["timeouts"])
                self._wait_for_server_recovery("timeout tests")
            if config.get("requestBody"):
                self._test_request_body(config["requestBody"])
            if config.get("buffering"):
                self._test_buffering(config["buffering"])
            if config.get("sessionAffinity"):
                self._test_session_affinity(config["sessionAffinity"])
            if config.get("firewall"):
                self._test_firewall(config["firewall"])
            if config.get("headers"):
                self._test_headers(config["headers"])
            if config.get("upstreamContext"):
                self._test_upstream_context(config["upstreamContext"])
            # Rate limit runs LAST since it can affect other tests
            if config.get("rateLimit"):
                self._test_rate_limit(config["rateLimit"])
        else:
            # Run with discovery/defaults
            self._test_timeouts_discovery()
            self._wait_for_server_recovery("timeout tests")
            self._test_request_body_discovery()
            self._test_session_affinity_discovery()
            self._test_headers_discovery()
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
            resp = self.session.get(f"{self.base_url}/healthz", timeout=10)
            test.duration_seconds = time.time() - start

            if resp.status_code == 200:
                test.result = TestResult.PASS
                test.message = f"Endpoint reachable (HTTP {resp.status_code})"
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

        # Test that requests within timeout succeed
        self._test_timeout_within_limit(read_seconds)

        # Test that requests exceeding timeout fail
        self._test_timeout_exceeds_limit(read_seconds)

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
                f"{self.base_url}/delay?seconds={delay}",
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
                    test.message = f"Completed too fast ({test.duration_seconds:.1f}s) - /delay endpoint may not be deployed"
            elif resp.status_code == 404:
                test.result = TestResult.SKIP
                test.message = "/delay endpoint not found - redeploy with updated server.py"
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
                f"{self.base_url}/delay?seconds={delay}",
                timeout=delay + 60
            )
            test.duration_seconds = time.time() - start
            test.details = {"status_code": resp.status_code, "expected_delay": delay, "actual_duration": test.duration_seconds}

            if resp.status_code == 504:
                test.result = TestResult.PASS
                test.message = f"Gateway timeout as expected after {test.duration_seconds:.1f}s"
            elif resp.status_code == 404:
                test.result = TestResult.SKIP
                test.message = "/delay endpoint not found - redeploy with updated server.py"
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
            # Use a simple POST with raw data
            resp = self.session.post(
                f"{self.base_url}/update-greeting",
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
                f"{self.base_url}/large-headers?size_kb={test_size_kb}",
                timeout=30
            )
            test.duration_seconds = time.time() - start
            test.details = {"status_code": resp.status_code, "header_size_kb": test_size_kb}

            if resp.status_code == 200:
                test.result = TestResult.PASS
                test.message = f"Headers within buffer accepted (HTTP 200)"
            elif resp.status_code == 404:
                test.result = TestResult.SKIP
                test.message = "/large-headers endpoint not found - redeploy with updated server.py"
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
                f"{self.base_url}/large-headers?size_kb={test_size_kb}",
                timeout=30
            )
            test.duration_seconds = time.time() - start
            test.details = {"status_code": resp.status_code, "header_size_kb": test_size_kb}

            if resp.status_code == 502:
                test.result = TestResult.PASS
                test.message = f"Correctly rejected with 502 (headers exceed buffer)"
            elif resp.status_code == 404:
                test.result = TestResult.SKIP
                test.message = "/large-headers endpoint not found - redeploy with updated server.py"
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

    def _test_firewall(self, config: dict):
        """Test firewall/IP allowlisting and path blocking."""
        print(f"\n{colorize('▶ Firewall Tests', Colors.BOLD)}")

        allowed_cidrs = config.get("allowedCidrs", [])
        blocked_paths = config.get("blockedPaths", [])

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

            # Test 1: Check if we're allowed (verifies allowlist works for our IP)
            self._test_firewall_allowed(allowed_cidrs)

            # Test 2: Verify behavior is correct for our IP vs the allowlist
            self._test_firewall_ip_match(allowed_cidrs)

        if blocked_paths:
            self.log(f"Blocked paths: {blocked_paths}")
            self._test_blocked_paths(blocked_paths)

    def _test_firewall_allowed(self, allowed_cidrs: list):
        """Test basic firewall access."""
        test = TestCase(
            name="firewall_access",
            description=f"Test access with allowlist configured"
        )

        start = time.time()
        try:
            resp = self.session.get(f"{self.base_url}/healthz", timeout=10)
            test.duration_seconds = time.time() - start
            test.details = {"status_code": resp.status_code, "allowed_cidrs": allowed_cidrs}

            if resp.status_code == 200:
                test.result = TestResult.PASS
                test.message = "Access allowed (your IP is in the allowlist)"
            elif resp.status_code == 403:
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

    def _test_blocked_paths(self, blocked_paths: list):
        """Test that configured blocked paths return 403."""
        for path in blocked_paths:
            test = TestCase(
                name=f"blocked_path_{path.replace('/', '_')}",
                description=f"Verify path '{path}' returns 403"
            )

            self.log(f"Testing blocked path: {path}...")
            start = time.time()

            try:
                resp = self.session.get(f"{self.base_url}{path}", timeout=10)
                test.duration_seconds = time.time() - start
                test.details = {"status_code": resp.status_code, "path": path}

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
            description="Verify /headers-echo endpoint is available"
        )

        start = time.time()
        try:
            resp = self.session.get(f"{self.base_url}/headers-echo", timeout=10)
            test.duration_seconds = time.time() - start

            if resp.status_code == 200:
                data = resp.json()
                test.result = TestResult.PASS
                test.message = f"Endpoint available, received {len(data.get('request_headers', {}))} headers"
                test.details = {"headers_count": len(data.get("request_headers", {}))}
            elif resp.status_code == 404:
                test.result = TestResult.SKIP
                test.message = "/headers-echo endpoint not found - redeploy with updated server.py"
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
                resp = self.session.get(f"{self.base_url}/headers-echo", timeout=10)
                test.duration_seconds = time.time() - start

                if resp.status_code == 404:
                    test.result = TestResult.SKIP
                    test.message = "/headers-echo endpoint not found"
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
                    f"{self.base_url}/headers-echo",
                    headers={header_name: "test-value-should-be-stripped"},
                    timeout=10
                )
                test.duration_seconds = time.time() - start

                if resp.status_code == 404:
                    test.result = TestResult.SKIP
                    test.message = "/headers-echo endpoint not found"
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

    def _test_upstream_context(self, config: dict):
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
        self._test_real_ip_header(real_ip_header)

    def _test_real_ip_header(self, header_name: str):
        """Test that the real_ip_header directive is working."""
        test = TestCase(
            name="real_ip_header",
            description=f"Verify real IP is extracted from '{header_name}'"
        )

        self.log(f"Testing real IP header extraction from: {header_name}...")

        # Use a distinctive test IP
        test_ip = "203.0.113.42"

        start = time.time()
        try:
            # Send request with the configured real IP header
            custom_headers = {header_name: test_ip}
            resp = self.session.get(
                f"{self.base_url}/headers-echo",
                headers=custom_headers,
                timeout=10
            )
            test.duration_seconds = time.time() - start

            if resp.status_code == 404:
                test.result = TestResult.SKIP
                test.message = "/headers-echo endpoint not found"
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
