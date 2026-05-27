#!/usr/bin/env python3
"""
Mr.Holmes CRM - Environment & Configuration Validator
Valida .env, dependências, Docker, segurança antes de deploy
"""

import os
import sys
import json
import subprocess
import re
from pathlib import Path
from typing import List, Tuple, Dict

IS_WINDOWS = os.name == "nt"
LOCAL_MODE = os.getenv("CRM_LOCAL_MODE", "").lower() in {"1", "true", "yes", "on"}

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

def check_ok(message: str):
    print(f"{Colors.GREEN}✅ {message}{Colors.END}")

def check_fail(message: str):
    print(f"{Colors.RED}❌ {message}{Colors.END}")

def check_warn(message: str):
    print(f"{Colors.YELLOW}⚠️  {message}{Colors.END}")

def check_info(message: str):
    print(f"{Colors.BLUE}ℹ️  {message}{Colors.END}")

def run_command(cmd: str) -> Tuple[int, str, str]:
    """Execute command and return exit code, stdout, stderr"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "Command timeout"
    except Exception as e:
        return 1, "", str(e)

class EnvValidator:
    """Validar arquivo .env"""
    
    REQUIRED_VARS = {
        'DATABASE_URL': 'postgresql://user:pass@host:5432/crm',
        'REDIS_URL': 'redis://localhost:6379/0',
        'JWT_SECRET_KEY': 'super-secret-key-min-32-chars',
        'JWT_ALGORITHM': 'HS256',
        'API_PORT': '8000',
        'API_HOST': '0.0.0.0',
    }
    
    OPTIONAL_VARS = {
        'TWILIO_ACCOUNT_SID': 'Twilio integration',
        'TWILIO_AUTH_TOKEN': 'Twilio integration',
        'SENDGRID_API_KEY': 'SendGrid integration',
        'SLACK_WEBHOOK_URL': 'Slack notifications',
        'LOG_LEVEL': 'debug/info/warning',
        'SENTRY_DSN': 'Error tracking',
    }
    
    def __init__(self, env_file: str = ".env"):
        self.env_file = env_file
        self.env_vars = self._load_env()
        self.issues = []
        self.warnings = []
    
    def _load_env(self) -> Dict[str, str]:
        """Parse .env file and merge shell environment overrides"""
        vars = {}
        
        if Path(self.env_file).exists():
            with open(self.env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    if '=' not in line:
                        continue
                    
                    key, value = line.split('=', 1)
                    vars[key.strip()] = value.strip()
        else:
            self.issues.append(f".env file not found at {self.env_file}")
        
        for key in self.REQUIRED_VARS.keys():
            if os.getenv(key):
                vars[key] = os.getenv(key, "")
        
        return vars
    
    def validate(self) -> bool:
        """Run all validations"""
        print_header("🔧 ENVIRONMENT VALIDATION")
        
        # Check file exists
        if not Path(self.env_file).exists():
            check_fail(f".env file not found")
            check_info("Create with: cp .env.example .env")
            return False
        
        check_ok(".env file exists")
        
        # Check required vars
        print(f"\n{Colors.BOLD}Required Variables:{Colors.END}")
        missing_required = []
        for var, example in self.REQUIRED_VARS.items():
            if var in self.env_vars:
                value = self.env_vars[var]
                if len(value) > 0:
                    check_ok(f"{var} = {value[:30]}...")
                else:
                    check_warn(f"{var} is empty")
                    self.warnings.append(f"{var} is empty")
            else:
                check_fail(f"{var} is missing")
                missing_required.append(var)
        
        if missing_required:
            check_fail(f"Missing {len(missing_required)} required variables")
            return False
        
        # Check optional vars
        print(f"\n{Colors.BOLD}Optional Variables:{Colors.END}")
        for var, description in self.OPTIONAL_VARS.items():
            if var in self.env_vars and len(self.env_vars[var]) > 0:
                check_ok(f"{var} configured ({description})")
            else:
                check_warn(f"{var} not configured ({description})")
        
        # Validate JWT secret length
        jwt_secret = self.env_vars.get('JWT_SECRET_KEY', '')
        if len(jwt_secret) < 32:
            check_warn(f"JWT_SECRET_KEY too short ({len(jwt_secret)}/32 chars)")
            self.warnings.append("JWT secret should be >= 32 characters")
        else:
            check_ok(f"JWT_SECRET_KEY strength adequate")
        
        # Validate DATABASE_URL format
        db_url = self.env_vars.get('DATABASE_URL', '')
        if LOCAL_MODE and db_url.startswith("sqlite:///"):
            check_ok("DATABASE_URL format looks good for local SQLite mode")
        elif not re.match(r'postgres(?:ql)?://\S+', db_url):
            check_warn("DATABASE_URL format might be incorrect")
            self.warnings.append("DATABASE_URL should start with postgresql://, postgres://, or sqlite:/// in local mode")
        else:
            check_ok("DATABASE_URL format looks good")
        
        # Validate REDIS_URL format
        redis_url = self.env_vars.get('REDIS_URL', '')
        if not re.match(r'redis://\S+', redis_url):
            check_warn("REDIS_URL format might be incorrect")
            self.warnings.append("REDIS_URL should start with redis://")
        else:
            check_ok("REDIS_URL format looks good")
        
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ Environment validation passed{Colors.END}")
        return len(missing_required) == 0

class DockerValidator:
    """Validar Docker setup"""
    
    def validate(self) -> bool:
        print_header("🐳 DOCKER VALIDATION")
        
        if LOCAL_MODE:
            check_info("CRM_LOCAL_MODE enabled - Docker checks skipped for local Windows execution")
            return True
        
        # Check Docker installed
        code, stdout, stderr = run_command("docker --version")
        if code != 0:
            check_fail("Docker not installed")
            check_info("Install from: https://docs.docker.com/get-docker/")
            return False
        
        check_ok(f"Docker installed: {stdout.strip()}")
        
        # Check Docker running
        code, stdout, stderr = run_command("docker ps")
        if code != 0:
            check_fail("Docker daemon not running")
            check_info("Start Docker Desktop or daemon")
            return False
        
        check_ok("Docker daemon running")
        
        # Check Docker Compose
        code, stdout, stderr = run_command("docker-compose --version")
        if code != 0:
            check_fail("Docker Compose not installed")
            return False
        
        check_ok(f"Docker Compose installed: {stdout.strip()}")
        
        # Check docker-compose.yml
        if not Path("docker-compose.yml").exists():
            check_fail("docker-compose.yml not found")
            return False
        
        check_ok("docker-compose.yml found")
        
        # Try validate compose file
        code, stdout, stderr = run_command("docker-compose config --quiet")
        if code != 0:
            check_fail(f"docker-compose.yml validation failed: {stderr}")
            return False
        
        check_ok("docker-compose.yml is valid")
        
        # Check required images/services
        required_services = ['postgres', 'redis', 'crm-app', 'api']
        code, stdout, stderr = run_command("docker-compose config")
        
        found_services = []
        for line in stdout.split('\n'):
            for service in required_services:
                if f"{service}:" in line:
                    found_services.append(service)
        
        for service in required_services:
            if service in found_services:
                check_ok(f"Service '{service}' defined")
            else:
                check_warn(f"Service '{service}' not defined")
        
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ Docker validation passed{Colors.END}")
        return True

class PortValidator:
    """Validar portas disponíveis"""
    
    REQUIRED_PORTS = {
        '8512': 'Streamlit CRM',
        '8000': 'FastAPI',
        '5432': 'PostgreSQL',
        '6379': 'Redis',
    }
    
    def validate(self) -> bool:
        print_header("🔌 PORT VALIDATION")
        
        all_available = True
        for port, service in self.REQUIRED_PORTS.items():
            # Try to connect to port
            code, _, _ = run_command(f"nc -zv localhost {port} 2>&1 || true")
            
            # Port in use if connection succeeds
            if code == 0:
                check_warn(f"Port {port} ({service}) already in use")
                all_available = False
            else:
                check_ok(f"Port {port} ({service}) available")
        
        if not all_available:
            check_info("Either stop existing services or change docker-compose port mappings")
        
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ Port validation completed{Colors.END}")
        return all_available

class DependencyValidator:
    """Validar Python dependencies"""
    
    REQUIRED_PACKAGES = [
        'streamlit',
        'fastapi',
        'uvicorn',
        'sqlalchemy',
        'psycopg2',
        'redis',
        'pydantic',
        'pyjwt',
    ]
    
    def validate(self) -> bool:
        print_header("📦 DEPENDENCY VALIDATION")
        
        missing = []
        for package in self.REQUIRED_PACKAGES:
            code, stdout, stderr = run_command(f"pip show {package}")
            if code != 0:
                check_warn(f"{package} not installed")
                missing.append(package)
            else:
                # Extract version
                version = "unknown"
                for line in stdout.split('\n'):
                    if line.startswith('Version:'):
                        version = line.split(':')[1].strip()
                
                check_ok(f"{package} {version}")
        
        if missing:
            check_info(f"Install with: pip install {' '.join(missing)}")
            if LOCAL_MODE:
                missing_without_psycopg2 = [pkg for pkg in missing if pkg != "psycopg2"]
                if not missing_without_psycopg2:
                    check_info("LOCAL_MODE: psycopg2 skipped because SQLite is being used")
                    missing = []
        else:
            check_ok("All required packages installed")
        
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ Dependency validation completed{Colors.END}")
        return len(missing) == 0

class SecurityValidator:
    """Validar segurança e exposições"""
    
    def validate(self) -> bool:
        print_header("🔒 SECURITY VALIDATION")
        
        issues = []
        
        # Check .env not in git
        gitignore_path = Path(".gitignore")
        if gitignore_path.exists():
            gitignore_entries = {
                line.strip()
                for line in gitignore_path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            }
            if ".env" in gitignore_entries:
                check_ok(".env is in .gitignore")
            else:
                check_fail(".env not in .gitignore - will expose secrets!")
                issues.append(".env should be in .gitignore")
        else:
            check_warn(".gitignore not found")
            issues.append(".gitignore file missing")
        
        # Check no hardcoded secrets in code
        if IS_WINDOWS:
            code, stdout, stderr = run_command(
                'findstr /S /I /N "password" crm_*.py'
            )
            suspicious_lines = [
                line for line in stdout.splitlines()
                if line and "#" not in line and "PASSWORD" not in line
            ]
            if suspicious_lines:
                if LOCAL_MODE:
                    check_warn("Possible hardcoded passwords found (ignored in LOCAL_MODE)")
                else:
                    check_warn("Possible hardcoded passwords found")
                    issues.append("Review for hardcoded secrets")
            else:
                check_ok("No obvious hardcoded passwords found")
        else:
            code, stdout, stderr = run_command(
                "grep -r 'password' crm_*.py 2>/dev/null | grep -v '#' || true"
            )
            if stdout:
                if LOCAL_MODE:
                    check_warn("Possible hardcoded passwords found (ignored in LOCAL_MODE)")
                else:
                    check_warn("Possible hardcoded passwords found")
                    issues.append("Review for hardcoded secrets")
            else:
                check_ok("No obvious hardcoded passwords found")
        
        # Check API keys in environment
        env_vars = {}
        if Path(".env").exists():
            with open(".env") as f:
                for line in f:
                    if '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()
        
        secret_vars = ['PASSWORD', 'TOKEN', 'KEY', 'SECRET', 'CREDENTIAL']
        found_secrets = 0
        for key, value in env_vars.items():
            if any(secret in key.upper() for secret in secret_vars):
                if len(value) > 0:
                    found_secrets += 1
        
        check_ok(f"Found {found_secrets} configured secrets")
        
        # Check Dockerfile security
        if Path("Dockerfile").exists():
            with open("Dockerfile") as f:
                content = f.read()
                if "USER" in content:
                    check_ok("Dockerfile runs as non-root user")
                else:
                    check_warn("Dockerfile might be running as root")
                    issues.append("Add USER directive to Dockerfile")
        
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ Security validation completed{Colors.END}")
        return len(issues) == 0

def main():
    """Run all validations"""
    print(f"{Colors.BOLD}{Colors.CYAN}")
    if IS_WINDOWS:
        print("============================================================")
        print("       Mr.Holmes CRM - Environment Validator")
        print("          Ready for Production Deployment")
        print("============================================================")
    else:
        print(r"""
╔═══════════════════════════════════════════════════════════╗
║       Mr.Holmes CRM - Environment Validator               ║
║          Ready for Production Deployment                  ║
╚═══════════════════════════════════════════════════════════╝
    """)
    print(Colors.END)
    
    results = []
    
    # Run validators
    validators = [
        ("Environment", EnvValidator()),
        ("Docker", DockerValidator()),
        ("Ports", PortValidator()),
        ("Dependencies", DependencyValidator()),
        ("Security", SecurityValidator()),
    ]
    
    for name, validator in validators:
        try:
            result = validator.validate()
            results.append((name, result))
        except Exception as e:
            check_fail(f"{name} validation crashed: {e}")
            results.append((name, False))
    
    # Summary
    print_header("📊 VALIDATION SUMMARY")
    
    total = len(results)
    passed = sum(1 for _, result in results if result)
    failed = total - passed
    
    for name, result in results:
        status = f"{Colors.GREEN}✅ PASS{Colors.END}" if result else f"{Colors.RED}❌ FAIL{Colors.END}"
        print(f"  {name:20} {status}")
    
    print(f"\n{Colors.BOLD}Total: {passed}/{total} passed{Colors.END}\n")
    
    if failed == 0:
        print(f"{Colors.GREEN}{Colors.BOLD}")
        print("🎉 All validations passed! Ready to deploy!")
        print(f"{Colors.END}\n")
        print("Next steps:")
        if LOCAL_MODE:
            print("  1. Start the local Windows launcher")
            print("  2. Open http://localhost:8512 (Streamlit)")
            print("  3. Open http://localhost:8000/docs (API)")
        else:
            print(f"  1. docker-compose up -d")
            print(f"  2. Wait for services to start")
            print(f"  3. Open http://localhost:8512 (Streamlit)")
            print(f"  4. Open http://localhost:8000/docs (API)")
        sys.exit(0)
    else:
        print(f"{Colors.RED}{Colors.BOLD}")
        print(f"⚠️  {failed} validation(s) failed - fix before deploying")
        print(f"{Colors.END}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
