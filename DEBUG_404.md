# BloodSync 404 Error Troubleshooting

## Your Situation
You're seeing a 404 Page Not Found error, which means:
- ✓ Flask app IS running (you got a response)
- ✓ The error handler IS working (showing 404.html)
- ✗ But the home route (/) is not being reached

---

## Immediate Debugging Steps

### Step 1: Test Simple Routes
On your EC2, test these endpoints:

```bash
# Test 1: Simple JSON endpoint (no templates needed)
curl http://localhost:5000/test

# Should return:
# {"message":"Flask is working!","tables_initialized":true,"version":"1.0.0"}
```

If this works: Flask is fine
If this fails: Flask isn't running

```bash
# Test 2: Health check
curl http://localhost:5000/health

# Should return:
# {"status":"healthy","message":"Application is running"}
```

```bash
# Test 3: Debug info (shows templates and routes)
curl http://localhost:5000/debug

# Should show:
# {
#   "status": "running",
#   "tables_initialized": true,
#   "templates_exist": true,
#   "templates_files": ["index.html", "donor_register.html", ...],
#   "registered_routes": [...]
# }
```

### Step 2: Check Application Logs

```bash
# Watch live logs (on EC2)
tail -f /tmp/bloodsync.log

# Look for lines like:
# INFO - incoming request: GET /
# INFO - Loading home page...
# INFO - Available templates:... 

# Or error lines like:
# ERROR - Error on home page
# ERROR - jinja2.exceptions.TemplateNotFound
```

### Step 3: Check Templates Directory

```bash
# On EC2, verify templates exist
ls -la /home/ec2-user/blood_sync/templates/

# Should show:
# index.html
# 404.html
# 500.html
# donor_register.html
# donor_dashboard.html
# ... etc
```

If files are missing, download them from your workspace.

### Step 4: Check Template Syntax

```bash
# On EC2, check if templates have syntax errors
python3 -m py_compile /home/ec2-user/blood_sync/templates/*.html

# Or try rendering one
python3 << 'EOF'
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('/home/ec2-user/blood_sync/templates'))
template = env.get_template('index.html')
print("✓ Template loaded successfully")
EOF
```

---

## Common 404 Causes & Fixes

### Issue 1: Templates Directory Missing
```bash
# Check if templates directory exists
ls /home/ec2-user/blood_sync/templates/

# If NOT:
mkdir -p /home/ec2-user/blood_sync/templates

# Then copy all template files from your local workspace
scp -i your-key.pem -r ./templates/* ec2-user@YOUR_IP:/home/ec2-user/blood_sync/templates/
```

### Issue 2: Templates Have Errors
```bash
# Check for Jinja2 syntax errors in templates
# Look in logs for: jinja2.exceptions.TemplateSyntaxError

# Fix: Edit the template file and fix the syntax
nano /home/ec2-user/blood_sync/templates/index.html
```

### Issue 3: Render Template Function Failing
```bash
# If you see "TemplateNotFound" in logs:
# 1. Make sure Flask knows where templates are
# 2. Check app initialization

python3 << 'EOF'
from flask import Flask
app = Flask(__name__)
print(f"Template folder: {app.template_folder}")
# Should show: /home/ec2-user/blood_sync/templates
EOF
```

### Issue 4: Route Not Registered
```bash
# Check if routes are registered
curl http://localhost:5000/debug

# Look for "/" in "registered_routes" list
# Should see: "/"
# If missing: there's an error in route registration
```

---

## Testing from Your Windows Machine

### Test 1: Simple/Test Routes
```powershell
# In PowerShell, test if Flask is responding
curl http://172.31.6.85:5000/test

# Should show:
# {"message":"Flask is working!","tables_initialized":true,"version":"1.0.0"}
```

### Test 2: Home Page
```powershell
# Try to access home page
curl http://172.31.6.85:5000/

# If you get HTML with 404: templates are loading
# If you get JSON error: check /tmp/bloodsync.log on EC2
```

### Test 3: Full Debug Info
```powershell
# Get full debug information
$response = curl http://172.31.6.85:5000/debug -UseBasicParsing
Write-Host $response.Content | ConvertFrom-Json | Format-List
```

---

## Step-by-Step Fix

### Step A: Verify App is Running
```bash
# On EC2
ps aux | grep AWS_app.py

# Should show the app running
# If not, start it: python3 AWS_app.py
```

### Step B: Check Templates Exist
```bash
# On EC2
ls /home/ec2-user/blood_sync/templates/

# If empty, copy templates from your Windows machine
```

### Step C: Restart App with Fresh Logs
```bash
# On EC2
pkill -f AWS_app.py
rm /tmp/bloodsync.log
python3 AWS_app.py

# Watch the output for errors
```

### Step D: Test Step-by-Step
```bash
# On EC2
curl http://localhost:5000/test
curl http://localhost:5000/health  
curl http://localhost:5000/debug
curl http://localhost:5000/
```

### Step E: Check From Windows
```powershell
# Test each endpoint
curl http://172.31.6.85:5000/test
curl http://172.31.6.85:5000/health
curl http://172.31.6.85:5000/debug
```

---

## If Still Getting 404

Run this diagnostic on EC2 and share the output:

```bash
#!/bin/bash
echo "=== Flask Templates Check ==="
python3 << 'EOF'
from flask import Flask
from jinja2 import Environment, FileSystemLoader
import os

app = Flask(__name__, template_folder='templates')

print(f"Template folder: {app.template_folder}")
print(f"Full path: {os.path.abspath(app.template_folder)}")
print(f"Exists: {os.path.exists(app.template_folder)}")

if os.path.exists(app.template_folder):
    files = os.listdir(app.template_folder)
    print(f"Files: {files}")
    
    try:
        env = Environment(loader=FileSystemLoader(app.template_folder))
        template = env.get_template('index.html')
        print("✓ index.html can be loaded")
    except Exception as e:
        print(f"✗ Error loading index.html: {e}")
EOF

echo ""
echo "=== App Routes ==="
python3 AWS_app.py --help 2>&1 | head -20

echo ""
echo "=== Recent Logs ==="
tail -50 /tmp/bloodsync.log
```

Save output to a file and share it:
```bash
bash debug.sh > debug_output.txt 2>&1
```

---

## Quick Checklist

- [ ] App is running: `ps aux | grep AWS_app.py`
- [ ] Port 5000 is listening: `sudo ss -tlnp | grep 5000`
- [ ] Templates directory exists: `ls /home/ec2-user/blood_sync/templates/`
- [ ] Templates have files: `ls templates/ | wc -l` (should be > 0)
- [ ] Test endpoint works: `curl localhost:5000/test`
- [ ] Health endpoint works: `curl localhost:5000/health`
- [ ] Debug endpoint works: `curl localhost:5000/debug`
- [ ] Logs show template loading: `grep "template" /tmp/bloodsync.log`
- [ ] Can reach from Windows: `curl http://172.31.6.85:5000/test`
- [ ] Home page works from Windows: `curl http://172.31.6.85:5000/`
