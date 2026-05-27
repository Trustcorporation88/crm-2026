#!/usr/bin/env python3
"""
Mr.Holmes CRM - Health Check & Monitoring
Monitora saúde de todos os serviços em tempo real
"""

import os
import sys
import json
import time
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    END = '\033[0m'
    BOLD = '\033[1m'

class HealthChecker:
    """Monitor saúde de serviços"""
    
    SERVICES = {
        'Streamlit': {
            'url': 'http://localhost:8512',
            'timeout': 5,
            'expected_status': 200,
        },
        'FastAPI': {
            'url': 'http://localhost:8000/health',
            'timeout': 5,
            'expected_status': 200,
        },
        'PostgreSQL': {
            'url': 'http://localhost:5432',  # Using socket check
            'timeout': 3,
            'check_type': 'socket',
        },
        'Redis': {
            'url': 'http://localhost:6379',  # Using socket check
            'timeout': 3,
            'check_type': 'socket',
        },
    }
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results = {}
    
    def check_http(self, name: str, url: str, timeout: int = 5) -> Tuple[bool, str]:
        """Check HTTP endpoint"""
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                return True, f"HTTP {response.status_code}"
            else:
                return False, f"HTTP {response.status_code}"
        except requests.ConnectionError:
            return False, "Connection refused"
        except requests.Timeout:
            return False, "Timeout"
        except Exception as e:
            return False, str(e)
    
    def check_socket(self, name: str, host: str, port: int, timeout: int = 3) -> Tuple[bool, str]:
        """Check socket connectivity"""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                return True, "Socket open"
            else:
                return False, "Connection refused"
        except Exception as e:
            return False, str(e)
    
    def check_service(self, name: str, config: Dict) -> Tuple[bool, str]:
        """Check individual service"""
        check_type = config.get('check_type', 'http')
        
        if check_type == 'http':
            url = config['url']
            timeout = config.get('timeout', 5)
            return self.check_http(name, url, timeout)
        
        elif check_type == 'socket':
            # Parse URL to host and port
            url = config['url']
            if '://' in url:
                url = url.split('://', 1)[1]
            
            if ':' in url:
                host, port = url.rsplit(':', 1)
                port = int(port)
            else:
                host = url
                port = 5432 if 'postgres' in name.lower() else 6379
            
            timeout = config.get('timeout', 3)
            return self.check_socket(name, host, port, timeout)
        
        return False, "Unknown check type"
    
    def check_all(self) -> bool:
        """Check all services"""
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*60}{Colors.END}")
        print(f"{Colors.CYAN}{Colors.BOLD}Mr.Holmes CRM - Health Check{Colors.END}")
        print(f"{Colors.CYAN}{Colors.BOLD}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.END}")
        print(f"{Colors.CYAN}{Colors.BOLD}{'='*60}{Colors.END}\n")
        
        all_healthy = True
        
        for name, config in self.SERVICES.items():
            healthy, message = self.check_service(name, config)
            self.results[name] = (healthy, message)
            
            if healthy:
                print(f"{Colors.GREEN}✅ {name:15} {message}{Colors.END}")
            else:
                print(f"{Colors.RED}❌ {name:15} {message}{Colors.END}")
                all_healthy = False
        
        # Summary
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*60}{Colors.END}")
        healthy_count = sum(1 for h, _ in self.results.values() if h)
        total_count = len(self.results)
        
        if all_healthy:
            print(f"{Colors.GREEN}{Colors.BOLD}✅ All {total_count} services healthy!{Colors.END}")
        else:
            print(f"{Colors.YELLOW}{Colors.BOLD}⚠️  {healthy_count}/{total_count} services healthy{Colors.END}")
        
        print(f"{Colors.CYAN}{Colors.BOLD}{'='*60}{Colors.END}\n")
        
        # Recommendations
        if not all_healthy:
            print(f"{Colors.BOLD}Troubleshooting:{Colors.END}\n")
            
            for name, (healthy, message) in self.results.items():
                if not healthy:
                    if "Connection refused" in message:
                        print(f"  {Colors.YELLOW}→ {name} not running{Colors.END}")
                        if name == "Streamlit":
                            print(f"    Try: streamlit run crm_app.py --server.port=8512")
                        elif name == "FastAPI":
                            print(f"    Try: uvicorn crm_api:app --host 0.0.0.0 --port 8000")
                        elif name == "PostgreSQL":
                            print(f"    Try: docker-compose up -d postgres")
                        elif name == "Redis":
                            print(f"    Try: docker-compose up -d redis")
                    
                    elif "Timeout" in message:
                        print(f"  {Colors.YELLOW}→ {name} timeout (too slow or unresponsive){Colors.END}")
                    
                    else:
                        print(f"  {Colors.YELLOW}→ {name}: {message}{Colors.END}")
            
            print()
        
        return all_healthy
    
    def continuous_monitor(self, interval: int = 10, duration: int = 300):
        """Monitor continuously"""
        print(f"{Colors.BOLD}Starting continuous monitoring (interval={interval}s, duration={duration}s)...")
        print("Press Ctrl+C to stop\n{Colors.END}")
        
        start_time = time.time()
        check_count = 0
        
        try:
            while True:
                elapsed = time.time() - start_time
                if elapsed > duration:
                    print(f"\n{Colors.YELLOW}Monitoring duration exceeded ({duration}s){Colors.END}")
                    break
                
                # Clear screen (Unix-like)
                os.system('clear' if os.name != 'nt' else 'cls')
                
                check_count += 1
                self.check_all()
                
                # Show next check time
                if elapsed < duration:
                    remaining = int(duration - elapsed)
                    print(f"{Colors.BLUE}Check #{check_count} | Elapsed: {int(elapsed)}s | Remaining: {remaining}s | Next in {interval}s...{Colors.END}\n")
                    time.sleep(interval)
        
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Monitoring stopped by user{Colors.END}")
            print(f"Total checks: {check_count}")

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Mr.Holmes CRM Health Check")
    parser.add_argument('--monitor', action='store_true', help='Continuous monitoring mode')
    parser.add_argument('--interval', type=int, default=10, help='Monitor interval (seconds)')
    parser.add_argument('--duration', type=int, default=300, help='Monitor duration (seconds)')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    checker = HealthChecker(verbose=args.verbose)
    
    if args.monitor:
        checker.continuous_monitor(interval=args.interval, duration=args.duration)
    else:
        all_healthy = checker.check_all()
        sys.exit(0 if all_healthy else 1)

if __name__ == "__main__":
    main()
