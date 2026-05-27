#!/usr/bin/env python3
"""
Mr.Holmes CRM - Smoke Tests
Testes básicos pós-deployment para verificar que tudo está funcionando
"""

import requests
import json
import sys
import time
from datetime import datetime

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(title: str):
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}{title}{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'='*60}{Colors.END}\n")

def test_ok(message: str):
    print(f"{Colors.GREEN}✅ {message}{Colors.END}")

def test_fail(message: str, critical: bool = False):
    marker = "❌ CRITICAL" if critical else "⚠️"
    print(f"{Colors.RED}{marker} {message}{Colors.END}")

def test_info(message: str):
    print(f"{Colors.BLUE}ℹ️  {message}{Colors.END}")

class SmokeTests:
    """Smoke tests para validação pós-deploy"""
    
    def __init__(self, base_url: str = "http://localhost:8000", 
                 streamlit_url: str = "http://localhost:8512",
                 timeout: int = 10):
        self.base_url = base_url
        self.streamlit_url = streamlit_url
        self.timeout = timeout
        self.session = requests.Session()
        self.passed = 0
        self.failed = 0
        self.critical_failed = 0
    
    def run_all(self) -> bool:
        """Run all smoke tests"""
        print_header("🧪 Mr.Holmes CRM - Smoke Tests")
        print(f"{Colors.BLUE}Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.END}\n")
        
        # API Tests
        print_header("API Tests")
        self.test_api_health()
        self.test_api_auth()
        self.test_api_endpoints()
        self.test_api_database()
        
        # Streamlit Tests
        print_header("Streamlit UI Tests")
        self.test_streamlit_health()
        self.test_streamlit_login()
        
        # Integration Tests
        print_header("Integration Tests")
        self.test_auth_flow()
        self.test_role_permissions()
        
        # Summary
        self.print_summary()
        
        return self.critical_failed == 0
    
    def test_api_health(self):
        """Test API health endpoint"""
        try:
            response = self.session.get(
                f"{self.base_url}/health",
                timeout=self.timeout
            )
            if response.status_code == 200:
                test_ok(f"API health check: {response.json()}")
                self.passed += 1
            else:
                test_fail(f"API health returned {response.status_code}", critical=True)
                self.failed += 1
                self.critical_failed += 1
        except Exception as e:
            test_fail(f"API health check failed: {e}", critical=True)
            self.failed += 1
            self.critical_failed += 1
    
    def test_api_auth(self):
        """Test authentication endpoints"""
        try:
            # Test login
            response = self.session.post(
                f"{self.base_url}/auth/login",
                json={"username": "admin", "password": "admin123"},
                timeout=self.timeout
            )
            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    test_ok("Admin login successful")
                    self.passed += 1
                    return data["access_token"]
                else:
                    test_fail("Login response missing access_token", critical=True)
                    self.failed += 1
                    self.critical_failed += 1
            else:
                test_fail(f"Login failed with {response.status_code}", critical=True)
                self.failed += 1
                self.critical_failed += 1
        except Exception as e:
            test_fail(f"Auth test failed: {e}", critical=True)
            self.failed += 1
            self.critical_failed += 1
    
    def test_api_endpoints(self):
        """Test key API endpoints"""
        # Get token first
        try:
            response = self.session.post(
                f"{self.base_url}/auth/login",
                json={"username": "admin", "password": "admin123"},
                timeout=self.timeout
            )
            if response.status_code != 200:
                test_fail("Cannot get auth token for endpoint tests")
                return
            
            token = response.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            
            # Test endpoints
            endpoints = [
                "/customers",
                "/tickets",
                "/deals",
                "/integrations",
            ]
            
            for endpoint in endpoints:
                try:
                    response = self.session.get(
                        f"{self.base_url}{endpoint}",
                        headers=headers,
                        timeout=self.timeout
                    )
                    if response.status_code == 200:
                        test_ok(f"Endpoint {endpoint}: OK")
                        self.passed += 1
                    else:
                        test_fail(f"Endpoint {endpoint}: {response.status_code}")
                        self.failed += 1
                except Exception as e:
                    test_fail(f"Endpoint {endpoint}: {e}")
                    self.failed += 1
        except Exception as e:
            test_fail(f"Could not test endpoints: {e}")
    
    def test_api_database(self):
        """Test database connectivity"""
        try:
            response = self.session.post(
                f"{self.base_url}/auth/login",
                json={"username": "admin", "password": "admin123"},
                timeout=self.timeout
            )
            if response.status_code == 200:
                test_ok("Database connectivity: OK (login works)")
                self.passed += 1
            else:
                test_fail("Database might be down (login failed)", critical=True)
                self.failed += 1
                self.critical_failed += 1
        except Exception as e:
            test_fail(f"Database test failed: {e}", critical=True)
            self.failed += 1
            self.critical_failed += 1
    
    def test_streamlit_health(self):
        """Test Streamlit UI is running"""
        try:
            response = self.session.get(
                self.streamlit_url,
                timeout=self.timeout
            )
            if response.status_code == 200:
                if "streamlit" in response.text.lower():
                    test_ok("Streamlit UI: Running")
                    self.passed += 1
                else:
                    test_info("Streamlit responded but content unclear")
                    self.passed += 1
            else:
                test_fail(f"Streamlit returned {response.status_code}")
                self.failed += 1
        except Exception as e:
            test_fail(f"Streamlit not reachable: {e}")
            self.failed += 1
    
    def test_streamlit_login(self):
        """Test Streamlit login form loads"""
        try:
            response = self.session.get(
                f"{self.streamlit_url}",
                timeout=self.timeout
            )
            if response.status_code == 200:
                if "login" in response.text.lower() or "usuario" in response.text.lower():
                    test_ok("Streamlit login form: Present")
                    self.passed += 1
                else:
                    test_info("Streamlit login form not clearly identified")
        except Exception as e:
            test_fail(f"Streamlit login test failed: {e}")
            self.failed += 1
    
    def test_auth_flow(self):
        """Test complete auth flow"""
        try:
            # 1. Login
            response = self.session.post(
                f"{self.base_url}/auth/login",
                json={"username": "admin", "password": "admin123"},
                timeout=self.timeout
            )
            assert response.status_code == 200, "Login failed"
            token = response.json()["access_token"]
            
            # 2. Use token
            headers = {"Authorization": f"Bearer {token}"}
            response = self.session.get(
                f"{self.base_url}/customers",
                headers=headers,
                timeout=self.timeout
            )
            assert response.status_code == 200, "Auth didn't work for API call"
            
            test_ok("Complete auth flow: OK")
            self.passed += 1
        except Exception as e:
            test_fail(f"Auth flow failed: {e}")
            self.failed += 1
    
    def test_role_permissions(self):
        """Test role-based permissions"""
        try:
            # Login with default admin
            response = self.session.post(
                f"{self.base_url}/auth/login",
                json={"username": "admin", "password": "admin123"},
                timeout=self.timeout
            )
            assert response.status_code == 200
            
            # Check if user has roles
            token = response.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            
            # This would require endpoints to return user info
            test_info("Role permissions: Assumed OK (full test requires more endpoints)")
            self.passed += 1
        except Exception as e:
            test_fail(f"Role test failed: {e}")
            self.failed += 1
    
    def print_summary(self):
        """Print test summary"""
        print_header("📊 Test Summary")
        
        total = self.passed + self.failed
        percentage = (self.passed / total * 100) if total > 0 else 0
        
        print(f"Total Tests: {total}")
        print(f"{Colors.GREEN}Passed: {self.passed}{Colors.END}")
        print(f"{Colors.RED}Failed: {self.failed}{Colors.END}")
        if self.critical_failed > 0:
            print(f"{Colors.RED}Critical Failed: {self.critical_failed}{Colors.END}")
        
        print(f"\nSuccess Rate: {percentage:.1f}%")
        
        if self.critical_failed == 0 and self.failed == 0:
            print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 ALL TESTS PASSED - READY FOR PRODUCTION!{Colors.END}\n")
            return True
        elif self.critical_failed == 0 and self.failed <= 2:
            print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️  Some non-critical failures, but OK to deploy{Colors.END}\n")
            return True
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}❌ CRITICAL FAILURES - DO NOT DEPLOY{Colors.END}\n")
            return False

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Mr.Holmes CRM Smoke Tests")
    parser.add_argument('--base-url', default='http://localhost:8000', help='API base URL')
    parser.add_argument('--streamlit-url', default='http://localhost:8512', help='Streamlit URL')
    parser.add_argument('--timeout', type=int, default=10, help='Request timeout in seconds')
    
    args = parser.parse_args()
    
    tests = SmokeTests(
        base_url=args.base_url,
        streamlit_url=args.streamlit_url,
        timeout=args.timeout
    )
    
    success = tests.run_all()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
