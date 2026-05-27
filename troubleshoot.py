#!/usr/bin/env python3
"""
Mr.Holmes CRM - Troubleshooting Assistant
Diagnóstico automático de problemas comuns
"""

import os
import subprocess
import json
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

def print_header(title: str):
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}{title}{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'='*60}{Colors.END}\n")

def run_cmd(cmd: str) -> Tuple[int, str]:
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        return result.returncode, result.stdout + result.stderr
    except:
        return 1, ""

class Troubleshooter:
    """Diagnóstico de problemas comuns"""
    
    PROBLEMS = {
        "Port already in use": {
            "symptoms": ["Address already in use", "Errno 48", "Errno 98"],
            "solutions": [
                "Kill process using port: lsof -ti:8512 | xargs kill -9",
                "Or change DOCKER_STREAMLIT_PORT in .env",
                "Or stop existing containers: docker-compose down",
            ]
        },
        "Docker daemon not running": {
            "symptoms": ["Cannot connect to Docker", "docker.sock not found"],
            "solutions": [
                "Windows: Open Docker Desktop application",
                "Mac: Open Docker Desktop application",
                "Linux: Run 'sudo systemctl start docker'",
            ]
        },
        "PostgreSQL connection failed": {
            "symptoms": ["could not connect to server", "psycopg2.OperationalError"],
            "solutions": [
                "Check DATABASE_URL in .env",
                "Run: docker-compose logs postgres",
                "Ensure postgres service is running: docker-compose up -d postgres",
                "Wait for postgres to be ready: docker-compose logs postgres | grep 'ready to accept'",
            ]
        },
        "Redis connection failed": {
            "symptoms": ["Cannot connect to Redis", "Connection refused on 6379"],
            "solutions": [
                "Ensure redis service is running: docker-compose up -d redis",
                "Check REDIS_URL in .env",
                "Run: docker-compose exec redis redis-cli ping",
            ]
        },
        "Streamlit not responding": {
            "symptoms": ["refused to connect", "localhost:8512 not accessible"],
            "solutions": [
                "Check if Streamlit is running: docker-compose logs crm-app",
                "Restart Streamlit: docker-compose restart crm-app",
                "Check port is available: lsof -i :8512 (Mac/Linux) or netstat -ano (Windows)",
                "Check logs for errors: make logs-crm",
            ]
        },
        "FastAPI not responding": {
            "symptoms": ["API health check failed", "localhost:8000 not accessible"],
            "solutions": [
                "Check if API is running: docker-compose logs api",
                "Restart API: docker-compose restart api",
                "Check logs: make logs-api",
                "Verify PostgreSQL is up: docker-compose logs postgres",
            ]
        },
        ".env not found": {
            "symptoms": ["missing .env file"],
            "solutions": [
                "Create from example: cp .env.example .env",
                "Edit with your configuration: nano .env",
                "Ensure all required variables are set",
            ]
        },
        "Out of disk space": {
            "symptoms": ["no space left on device", "disk full"],
            "solutions": [
                "Clean Docker: docker system prune -a",
                "Remove old images: docker image prune -a",
                "Remove dangling volumes: docker volume prune",
                "Check disk usage: df -h",
            ]
        },
        "Database migration failed": {
            "symptoms": ["Alembic migration error", "database schema mismatch"],
            "solutions": [
                "Check database connection first",
                "Run migrations: docker-compose exec api alembic upgrade head",
                "Check migration files in alembic/versions/",
                "Review latest migration: git log --oneline alembic/",
            ]
        },
        "Memory issues": {
            "symptoms": ["OOMKilled", "out of memory"],
            "solutions": [
                "Increase Docker memory limit in Docker Desktop settings",
                "Stop unnecessary containers",
                "Monitor memory: docker stats",
                "Reduce number of Streamlit workers",
            ]
        },
    }
    
    def diagnose(self) -> None:
        """Run complete diagnosis"""
        print_header("🔧 Mr.Holmes CRM - Troubleshooting Assistant")
        
        issues = []
        
        # Check Docker
        code, output = run_cmd("docker --version")
        if code != 0:
            issues.append("Docker not installed")
        
        # Check Docker daemon
        code, output = run_cmd("docker ps")
        if code != 0:
            issues.append("Docker daemon not running")
        
        # Check docker-compose
        code, output = run_cmd("docker-compose --version")
        if code != 0:
            issues.append("Docker Compose not installed")
        
        # Check .env
        if not Path(".env").exists():
            issues.append(".env not found")
        
        # Check ports
        for port in [8512, 8000, 5432, 6379]:
            code, output = run_cmd(f"nc -zv localhost {port} 2>&1 || true")
            if "succeeded" in output or code == 0:
                # Port in use, might be problematic
                pass
        
        # Check docker-compose config
        code, output = run_cmd("docker-compose config > /dev/null 2>&1")
        if code != 0:
            issues.append("docker-compose.yml validation failed")
        
        # Check logs for errors
        code, output = run_cmd("docker-compose logs --tail=50")
        error_keywords = ["error", "failed", "exception", "crashed"]
        for keyword in error_keywords:
            if keyword.lower() in output.lower():
                issues.append(f"Found '{keyword}' in recent logs")
        
        if not issues:
            print(f"{Colors.GREEN}{Colors.BOLD}✅ No obvious issues detected!{Colors.END}\n")
            self.show_system_info()
            return
        
        # Show detected issues
        print(f"{Colors.RED}{Colors.BOLD}Issues detected:{Colors.END}\n")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        
        # Find matching problems and solutions
        print_header("🔍 Suggested Solutions")
        
        shown = set()
        for problem, details in self.PROBLEMS.items():
            for symptom in details['symptoms']:
                for issue in issues:
                    if symptom.lower() in issue.lower() or issue.lower() in symptom.lower():
                        if problem not in shown:
                            print(f"{Colors.BOLD}{problem}{Colors.END}")
                            for solution in details['solutions']:
                                print(f"  → {solution}")
                            print()
                            shown.add(problem)
    
    def show_system_info(self) -> None:
        """Show system information"""
        print_header("ℹ️  System Information")
        
        # Docker info
        code, output = run_cmd("docker --version")
        if code == 0:
            print(f"{Colors.CYAN}Docker:{Colors.END} {output.strip()}")
        
        code, output = run_cmd("docker-compose --version")
        if code == 0:
            print(f"{Colors.CYAN}Docker Compose:{Colors.END} {output.strip()}")
        
        # Python info
        code, output = run_cmd("python3 --version")
        if code == 0:
            print(f"{Colors.CYAN}Python:{Colors.END} {output.strip()}")
        
        # Docker services
        print(f"\n{Colors.CYAN}Running Services:{Colors.END}")
        code, output = run_cmd("docker-compose ps")
        if code == 0:
            for line in output.split('\n')[2:]:  # Skip header
                if line.strip():
                    print(f"  {line}")
        
        # Disk usage
        print(f"\n{Colors.CYAN}Docker Disk Usage:{Colors.END}")
        code, output = run_cmd("docker system df")
        if code == 0:
            for line in output.split('\n'):
                if 'TYPE' in line or 'Images' in line or 'Containers' in line or 'Volumes' in line:
                    print(f"  {line}")
    
    def quick_fix(self) -> None:
        """Apply quick fixes"""
        print_header("🚀 Applying Quick Fixes")
        
        # Clean dangling images
        print("Cleaning dangling Docker images...")
        run_cmd("docker image prune -f")
        print("✅ Done")
        
        # Restart services
        print("Restarting services...")
        run_cmd("docker-compose restart")
        print("✅ Done")
        
        # Verify
        print("\nVerifying services...")
        code, output = run_cmd("docker-compose ps")
        print(output)

def main():
    import sys
    
    troubleshooter = Troubleshooter()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--fix":
            troubleshooter.quick_fix()
        elif sys.argv[1] == "--info":
            troubleshooter.show_system_info()
        else:
            print("Usage: python troubleshoot.py [--fix|--info]")
    else:
        troubleshooter.diagnose()

if __name__ == "__main__":
    main()
