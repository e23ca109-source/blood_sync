# BloodSync Troubleshooting Guide

## Issue: ERR_CONNECTION_TIMED_OUT

### What This Means
The browser cannot reach the Flask application at `http://172.31.6.85:5000`. This could be because:
1. Flask app isn't running
2. Port 5000 isn't open
3. Security group doesn't allow inbound traffic
4. Something else is using port 5000

---

## Step 1: Check if App is Running

### On EC2 (Linux):
```bash
# SSH into your EC2 instance
ssh -i your-key.pem ec2-user@172.31.6.85

# Check if Flask is running
ps aux | grep AWS_app.py

# Check if port 5000 is listening
netstat -tlnp | grep 5000
# or
sudo ss -tlnp | grep 5000
```

### Check recent logs:
```bash
tail -f /tmp/bloodsync.log
```

---

## Step 2: Run Diagnostics

```bash
# Go to app directory
cd /home/ec2-user/blood_sync

# Run diagnostic script
python3 diagnose.py
```

This will show:
- ✓ or ✗ for Python, packages, AWS credentials, DynamoDB, port availability

---

## Step 3: Restart the Application

```bash
# Kill any existing Flask processes
pkill -f AWS_app.py

# Wait 5 seconds
sleep 5

# Start fresh (stay in foreground to see logs)
cd /home/ec2-user/blood_sync
python3 AWS_app.py

# You should see:
# ========== BloodSync Application Starting ==========
# Initializing DynamoDB tables...
# ✓ AWS connection successful
# ✓ All tables ready!
# ✓ Application initialized successfully!
# ✓ Starting Flask server on http://0.0.0.0:5000
```

---

## Step 4: Test the App

### Test locally on EC2:
```bash
curl http://localhost:5000/health
```

Should return: `{"status": "healthy", "message": "Application is running"}`

### Test from your Windows machine:
```powershell
# In PowerShell on your Windows machine:
curl http://172.31.6.85:5000/health
```

---

## Step 5: Check AWS Security Group

If the app is running but you still can't access it:

1. Go to AWS Console → EC2 → Security Groups
2. Find the security group for your instance
3. Check **Inbound Rules**
4. Make sure there's a rule allowing:
   - Protocol: TCP
   - Port: 5000
   - Source: Your IP or 0.0.0.0/0 (less secure)

### Example Inbound Rule:
| Type | Protocol | Port Range | Source |
|------|----------|-----------|--------|
| Custom TCP | TCP | 5000 | 0.0.0.0/0 |

---

## Step 6: Common Issues & Solutions

### Issue: "Connection refused"
```bash
# App isn't running or port isn't listening
# Solution: Start the app
python3 AWS_app.py
```

### Issue: "AWS Connection Error"
```bash
# AWS credentials not configured
# Solution: Configure credentials
aws configure
# Enter your AWS Access Key ID and Secret Access Key
```

### Issue: "Failed to initialize DynamoDB tables"
```bash
# Check if you have DynamoDB permissions
# Check if region is correct (should be ap-south-1)
# Try manually listing tables
aws dynamodb list-tables --region ap-south-1
```

### Issue: "Port already in use"
```bash
# Port 5000 is being used by something else
# Either:
# 1. Kill the existing process
pkill -f AWS_app.py

# 2. Or use a different port (edit AWS_app.py)
# Change: app.run(host="0.0.0.0", port=5001, ...)
```

---

## Step 7: Running in Background

Once you confirm it works, run in background:

```bash
# Using nohup (stays running even if you disconnect)
nohup python3 AWS_app.py > /tmp/bloodsync.log 2>&1 &

# Or using screen (can reconnect later)
screen -S bloodsync
python3 AWS_app.py

# (Press Ctrl+A then D to detach)
# (To reattach: screen -r bloodsync)

# Or using systemd (most professional)
# (See systemd_service.txt in this directory)
```

---

## Step 8: Verify Application is Working

Once running, test these endpoints:

1. **Health Check**
   ```
   http://172.31.6.85:5000/health
   ```
   Should return: `{"status":"healthy"}`

2. **Home Page**
   ```
   http://172.31.6.85:5000/
   ```
   Should load the BloodSync homepage

3. **Donor Registration**
   ```
   http://172.31.6.85:5000/donor/register
   ```

---

## Quick Debug Checklist

- [ ] SSH into EC2 instance
- [ ] Check logs: `tail -f /tmp/bloodsync.log`
- [ ] Run diagnostics: `python3 diagnose.py`
- [ ] Test locally: `curl http://localhost:5000/health`
- [ ] Check security group allows port 5000
- [ ] Test from Windows: `curl http://172.31.6.85:5000/health`
- [ ] Restart if needed: `pkill -f AWS_app.py && python3 AWS_app.py`

---

## Contact Support

If you still can't connect, provide this information:

1. Output of `python3 diagnose.py`
2. Output of `tail -100 /tmp/bloodsync.log`
3. EC2 instance ID
4. Your public/elastic IP
5. Exact error message from browser
