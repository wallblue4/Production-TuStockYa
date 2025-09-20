#!/usr/bin/env python3
"""
CORS Configuration Test Script
Tests CORS functionality and security for TuStockYa API
"""

import requests
import json
from typing import List, Dict

def test_cors_configuration(base_url: str = "http://localhost:8000") -> Dict:
    """Test CORS configuration with different origins"""
    
    results = {
        "base_url": base_url,
        "tests": [],
        "summary": {}
    }
    
    # Test cases: (origin, should_be_allowed)
    test_origins = [
        ("http://localhost:3000", True),   # Should be allowed
        ("https://tustockya.com", True),   # Should be allowed
        ("https://www.tustockya.com", True),   # Should be allowed
        ("https://app.tustockya.com", False),  # Should be blocked (removed from allowed)
        ("http://localhost:8080", False),  # Should be blocked (removed from allowed)
        ("https://malicious-site.com", False),  # Should be blocked
        ("http://evil.com", False),        # Should be blocked
        (None, True),                      # No origin (direct API call)
    ]
    
    for origin, should_be_allowed in test_origins:
        test_result = perform_cors_test(base_url, origin, should_be_allowed)
        results["tests"].append(test_result)
    
    # Generate summary
    passed = sum(1 for test in results["tests"] if test["status"] == "PASS")
    failed = sum(1 for test in results["tests"] if test["status"] == "FAIL")
    
    results["summary"] = {
        "total_tests": len(results["tests"]),
        "passed": passed,
        "failed": failed,
        "success_rate": f"{(passed / len(results['tests']) * 100):.1f}%"
    }
    
    return results

def perform_cors_test(base_url: str, origin: str, should_be_allowed: bool) -> Dict:
    """Perform a single CORS test"""
    
    test_name = f"Origin: {origin or 'None (Direct)'}"
    
    try:
        # Test preflight request (OPTIONS)
        headers = {}
        if origin:
            headers["Origin"] = origin
            headers["Access-Control-Request-Method"] = "POST"
            headers["Access-Control-Request-Headers"] = "Authorization,Content-Type"
        
        # Test preflight
        preflight_response = requests.options(
            f"{base_url}/api/v1/",
            headers=headers,
            timeout=10
        )
        
        # Test actual request
        actual_headers = {}
        if origin:
            actual_headers["Origin"] = origin
        
        actual_response = requests.get(
            f"{base_url}/api/v1/",
            headers=actual_headers,
            timeout=10
        )
        
        # Analyze results
        cors_headers = {
            "Access-Control-Allow-Origin": actual_response.headers.get("Access-Control-Allow-Origin"),
            "Access-Control-Allow-Credentials": actual_response.headers.get("Access-Control-Allow-Credentials"),
            "Access-Control-Allow-Methods": actual_response.headers.get("Access-Control-Allow-Methods"),
            "Access-Control-Allow-Headers": actual_response.headers.get("Access-Control-Allow-Headers"),
        }
        
        # Check if CORS is working as expected
        origin_allowed = (
            cors_headers["Access-Control-Allow-Origin"] == origin or
            cors_headers["Access-Control-Allow-Origin"] == "*" or
            (origin is None and actual_response.status_code == 200)
        )
        
        # Determine test result
        if should_be_allowed and origin_allowed:
            status = "PASS"
            message = "Origin correctly allowed"
        elif not should_be_allowed and not origin_allowed:
            status = "PASS"
            message = "Origin correctly blocked"
        elif should_be_allowed and not origin_allowed:
            status = "FAIL"
            message = "Origin should be allowed but was blocked"
        else:
            status = "FAIL"
            message = "Origin should be blocked but was allowed"
        
        return {
            "test_name": test_name,
            "status": status,
            "message": message,
            "preflight_status": preflight_response.status_code,
            "actual_status": actual_response.status_code,
            "cors_headers": cors_headers,
            "expected_allowed": should_be_allowed,
            "actually_allowed": origin_allowed
        }
        
    except requests.exceptions.RequestException as e:
        return {
            "test_name": test_name,
            "status": "ERROR",
            "message": f"Request failed: {str(e)}",
            "expected_allowed": should_be_allowed,
            "actually_allowed": None
        }

def print_results(results: Dict):
    """Print test results in a readable format"""
    
    print("🔒 CORS Configuration Test Results")
    print("=" * 50)
    print(f"API Base URL: {results['base_url']}")
    print()
    
    for test in results["tests"]:
        status_emoji = "✅" if test["status"] == "PASS" else "❌" if test["status"] == "FAIL" else "⚠️"
        print(f"{status_emoji} {test['test_name']}")
        print(f"   Status: {test['status']}")
        print(f"   Message: {test['message']}")
        
        if "cors_headers" in test:
            print(f"   CORS Headers:")
            for header, value in test["cors_headers"].items():
                if value:
                    print(f"     {header}: {value}")
        print()
    
    print("📊 Summary")
    print("-" * 20)
    print(f"Total Tests: {results['summary']['total_tests']}")
    print(f"Passed: {results['summary']['passed']}")
    print(f"Failed: {results['summary']['failed']}")
    print(f"Success Rate: {results['summary']['success_rate']}")
    
    if results['summary']['failed'] == 0:
        print("\n🎉 All CORS tests passed! Your configuration is working correctly.")
    else:
        print(f"\n⚠️ {results['summary']['failed']} test(s) failed. Please review your CORS configuration.")

if __name__ == "__main__":
    import sys
    
    # Allow custom base URL as command line argument
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    
    print(f"🧪 Testing CORS configuration for: {base_url}")
    print("Starting tests...\n")
    
    results = test_cors_configuration(base_url)
    print_results(results)
    
    # Exit with error code if tests failed
    if results['summary']['failed'] > 0:
        sys.exit(1)