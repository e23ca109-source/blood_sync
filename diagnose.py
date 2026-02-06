#!/usr/bin/env python3
"""
BloodSync Diagnostic Script
Helps debug connection and startup issues
"""

import sys
import socket
import subprocess
from datetime import datetime

print("=" * 70)
print("BloodSync Diagnostic Report")
print("=" * 70)
print(f"Generated: {datetime.now()}\n")

# 1. Check Python version
print("1. Python Setup")
print("-" * 70)
print(f"✓ Python Version: {sys.version}")
print(f"✓ Python Executable: {sys.executable}\n")

# 2. Check required packages
print("2. Required Packages")
print("-" * 70)
packages = ['flask', 'boto3', 'decimal', 'logging']
for package in packages:
    try:
        __import__(package)
        print(f"✓ {package} is installed")
    except ImportError:
        print(f"✗ {package} is NOT installed")
print()

# 3. Check AWS CLI and credentials
print("3. AWS Configuration")
print("-" * 70)
try:
    result = subprocess.run(['aws', '--version'], capture_output=True, text=True)
    print(f"✓ AWS CLI: {result.stdout.strip()}")
except FileNotFoundError:
    print("✗ AWS CLI is not installed or not in PATH")

try:
    result = subprocess.run(['aws', 'sts', 'get-caller-identity'], capture_output=True, text=True)
    if result.returncode == 0:
        import json
        identity = json.loads(result.stdout)
        print(f"✓ AWS Credentials Valid")
        print(f"  Account ID: {identity.get('Account')}")
        print(f"  ARN: {identity.get('Arn')}")
    else:
        print(f"✗ AWS Credentials Error: {result.stderr}")
except Exception as e:
    print(f"✗ Unable to check AWS credentials: {e}")
print()

# 4. Check DynamoDB access
print("4. DynamoDB Access")
print("-" * 70)
try:
    import boto3
    client = boto3.client('dynamodb', region_name='ap-south-1')
    response = client.list_tables()
    tables = response.get('TableNames', [])
    print(f"✓ DynamoDB Connection Successful")
    print(f"✓ Region: ap-south-1")
    print(f"✓ Existing Tables: {len(tables)}")
    if tables:
        for table in tables:
            if 'BloodSync' in table:
                print(f"  - {table}")
except Exception as e:
    print(f"✗ DynamoDB Connection Error: {e}")
print()

# 5. Check network connectivity
print("5. Network Setup")
print("-" * 70)
try:
    hostname = socket.gethostname()
    ip_address = socket.gethostbyname(hostname)
    print(f"✓ Hostname: {hostname}")
    print(f"✓ Local IP: {ip_address}")
except Exception as e:
    print(f"✗ Network Error: {e}")
print()

# 6. Check port availability
print("6. Port Availability")
print("-" * 70)
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex(('127.0.0.1', 5000))
    sock.close()
    if result == 0:
        print("✗ Port 5000 is already in use")
        print("  (This is OK if you're starting fresh)")
    else:
        print("✓ Port 5000 is available")
except Exception as e:
    print(f"✗ Port check error: {e}")
print()

# 7. File structure check
print("7. File Structure")
print("-" * 70)
import os
files_to_check = [
    'AWS_app.py',
    'requirements.txt',
    'templates/index.html',
    'templates/donor_register.html',
    'templates/requestor_register.html',
    'templates/donor_dashboard.html',
    'templates/requestor_dashboard.html'
]

for file in files_to_check:
    path = os.path.join(os.path.dirname(__file__), file)
    if os.path.exists(path):
        print(f"✓ {file}")
    else:
        print(f"✗ {file} - MISSING")
print()

print("=" * 70)
print("Next Steps:")
print("=" * 70)
print("1. If AWS Credentials show error:")
print("   Run: aws configure")
print()
print("2. If DynamoDB Connection fails:")
print("   - Check your IAM permissions")
print("   - Ensure ap-south-1 region is accessible")
print()
print("3. To start the application:")
print("   python AWS_app.py")
print()
print("4. To check logs:")
print("   tail -f /tmp/bloodsync.log")
print()
print("5. To test the app is running:")
print("   curl http://localhost:5000/health")
print("=" * 70)
