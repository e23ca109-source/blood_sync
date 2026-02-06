#!/bin/bash
# BloodSync Startup Script
# Helps diagnose and run the application

echo "=========================================="
echo "BloodSync Application Launcher"
echo "=========================================="
echo ""

# Check if running diagnostics
if [ "$1" = "diagnose" ]; then
    echo "Running diagnostics..."
    python3 diagnose.py
    exit 0
fi

# Check Python
echo "Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo "✗ Python 3 is not installed"
    exit 1
fi
echo "✓ Python 3 found: $(python3 --version)"
echo ""

# Check dependencies
echo "Checking dependencies..."
python3 -c "import flask; import boto3" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "✗ Missing dependencies. Installing..."
    pip install flask boto3
fi
echo "✓ Dependencies OK"
echo ""

# Run app
echo "=========================================="
echo "Starting BloodSync Application"
echo "=========================================="
echo ""
echo "The app will start on: http://0.0.0.0:5000"
echo "Health check: http://YOUR_IP:5000/health"
echo "Logs: tail -f /tmp/bloodsync.log"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python3 AWS_app.py
