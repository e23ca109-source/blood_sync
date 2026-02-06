# BloodSync Quick Start Guide

## Your Situation
You're trying to reach: `http://172.31.6.85:5000`
Error: `ERR_CONNECTION_TIMED_OUT`

---

## Immediate Fix (9 Steps)

### Step 1: SSH into your EC2 instance
```bash
ssh -i your-key.pem ec2-user@172.31.6.85
```

### Step 2: Navigate to the app directory
```bash
cd /home/ec2-user/blood_sync
```

### Step 3: Check if app is running
```bash
ps aux | grep AWS_app.py
```
Look for a line with `AWS_app.py` (if it exists, the app is running)

### Step 4: Run the diagnostic
```bash
python3 diagnose.py
```
This will tell you exactly what's wrong

### Step 5: Ensure AWS is configured
```bash
aws sts get-caller-identity
```
If you see your AWS account info, credentials are good.
If you see an error, run: `aws configure`

### Step 6: Kill any old processes
```bash
pkill -f AWS_app.py
sleep 2
```

### Step 7: Start the app with full output
```bash
python3 AWS_app.py
```

Look for these lines in the output:
```
========== BloodSync Application Starting ==========
✓ Flask app initialized
Initializing DynamoDB tables...
✓ AWS connection successful
✓ All tables ready!
✓ Application initialized successfully!
✓ Starting Flask server on http://0.0.0.0:5000
```

### Step 8: In another terminal window, test it
```bash
# From EC2
curl http://localhost:5000/health

# Should return: {"status":"healthy","message":"Application is running"}
```

### Step 9: Check AWS Security Group
In AWS Console:
1. Go to EC2 → Your Instance
2. Check Security Groups
3. Make sure Inbound Rules include:
   - Protocol: TCP
   - Port: 5000
   - Source: 0.0.0.0/0 or your IP

---

## If App Doesn't Start

### Check 1: Python/packages
```bash
python3 --version
python3 -c "import flask; import boto3; print('OK')"
```

### Check 2: AWS credentials
```bash
cat ~/.aws/credentials
cat ~/.aws/config
# Should show your access key and secret
```

### Check 3: Logs
```bash
tail -100 /tmp/bloodsync.log
```
Look for errors starting with `✗`

### Check 4: Port conflict
```bash
sudo ss -tlnp | grep 5000
```
If something is already using 5000, kill it:
```bash
sudo pkill -f AWS_app.py
```

---

## If App Starts But Can't Connect

### Test locally first
```bash
# On EC2 itself
curl http://localhost:5000/health
```

### Test from Windows
```powershell
# In PowerShell on your Windows machine
curl http://172.31.6.85:5000/health
```

### If local works but remote doesn't:
Security Group issue!
- Add inbound rule for port 5000
- Or change source to your IP instead of 0.0.0.0/0

---

## Common Error Messages & Fixes

### "Connection refused"
```
→ App isn't running or port isn't open
→ Run: python3 AWS_app.py
```

### "NoCredentialsError"
```
→ AWS credentials not configured
→ Run: aws configure
```

### "ResourceNotFoundException: Requested resource not found"
```
→ DynamoDB tables don't exist
→ The app should create them automatically
→ Wait 1-2 minutes for table creation to complete
```

### "Address already in use"
```
→ Port 5000 is being used by something else
→ Run: sudo lsof -i :5000
→ Kill it: sudo kill -9 <PID>
```

---

## When It Works

Once the app is running successfully:

1. **Browser access** (from Windows)
   ```
   http://172.31.6.85:5000/
   ```

2. **Health check**
   ```
   http://172.31.6.85:5000/health
   ```

3. **Keep it running**
   
   Option A (Simple): Keep SSH window open with app running
   
   Option B (Better): Run in background
   ```bash
   nohup python3 AWS_app.py > /tmp/bloodsync.log 2>&1 &
   ```
   
   Option C (Best): Use systemd service
   ```bash
   sudo cp bloodsync.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable bloodsync
   sudo systemctl start bloodsync
   ```

---

## Verify Everything Works

```bash
# 1. Check app is running
ps aux | grep AWS_app.py

# 2. Check port is listening  
sudo ss -tlnp | grep 5000

# 3. Test locally
curl http://localhost:5000/health

# 4. Check logs for errors
tail /tmp/bloodsync.log

# 5. View app logs in real-time
tail -f /tmp/bloodsync.log
```

---

## Need Help?

Run this and save the output:
```bash
python3 diagnose.py > diagnosis.txt 2>&1
```

Then share:
1. The diagnosis.txt file
2. Output of: `tail -50 /tmp/bloodsync.log`
3. Your EC2 security group inbound rules
4. The exact error message from the browser
