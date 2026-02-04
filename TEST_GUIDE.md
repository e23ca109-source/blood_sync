# BloodSync - Quick Test & Usage Guide

## 🚀 START THE APPLICATION

```bash
cd c:\Users\HP\Desktop\BloodSync\bloodbridge
python app.py
```

**Application runs at**: http://127.0.0.1:5000/

---

## 👥 SAMPLE USERS (Pre-loaded)

### Donors
| Donor ID | Name | Blood | Phone | Email |
|----------|------|-------|-------|-------|
| DON-A1B2C3D4 | Rahul Sharma | O+ | 9876543210 | rahul@example.com |
| DON-E5F6G7H8 | Priya Patel | A+ | 8765432109 | priya@example.com |
| DON-A2B3C4D5 | Anjali Gupta | A- | 7654321098 | anjali@example.com |
| DON-I9J0K1L2 | Amit Kumar | B- | 6543210987 | amit@example.com |
| DON-M3N4O5P6 | Sneha Gupta | O- | 5432109876 | sneha@example.com |
| DON-Q7R8S9T0 | Vikram Singh | AB+ | 4321098765 | vikram@example.com |

### Requestors
| Requestor ID | Name | Org | Phone | Email |
|---|---|---|---|---|
| REQ-X1Y2Z3A4 | Dr. Meera Reddy | City General Hospital | 3210987654 | meera@hospital.com |

### Blood Request (Sample)
| Request ID | Patient | Blood | Units | Hospital |
|---|---|---|---|---|
| BR-B5C6D7E8 | Ramesh Iyer | A+ | 5 | City General Hospital |

---

## 🔴 TEST FEATURE 1: DONOR DONATES TO INVENTORY

### Steps:
1. Go to home → Search for "Donor" or direct link: http://127.0.0.1:5000/donor/login
2. Login as **DON-A1B2C3D4** (Rahul Sharma) with email **rahul@example.com**
3. Click **"Donate to Inventory"** button (green) in Profile card
4. Select:
   - Blood Group: **O+** (auto-filled)
   - Units: **2**
   - Center: **Main Center** (or custom)
5. Click **"Complete Donation"**
6. ✓ See success: "✓ Donation recorded successfully! 2 unit(s) of O+ added to inventory"
7. Check **Donation History** → shows new entry with timestamp

### Verify:
- Inventory `/blood-inventory` shows O+ increased by 2 units
- Donation history shows new entry
- Last donation date updated

---

## 🔵 TEST FEATURE 2: REQUESTOR TAKES FROM INVENTORY

### Steps:
1. Go to http://127.0.0.1:5000/request/BR-B5C6D7E8
2. Scroll to **"Still Need: 5 unit(s)"** section
3. Enter **2** units in inventory form
4. Click **"Take"** button (red warehouse)
5. ✓ See success: "✓ 2 unit(s) taken from inventory. Remaining needed: 3 unit(s)"
6. Check Fulfilled History → shows "Blood Bank Inventory - 2 units"

### Verify:
- Request status changed from `pending` → `partial`
- Fulfilled units: 0 → 2
- Remaining: 5 → 3
- Inventory decreased by 2
- Fulfilled History shows inventory withdrawal

---

## 🟢 TEST FEATURE 3: DONOR ACCEPT & REQUESTOR CONFIRM

### Steps:

#### A) Donor Accepts Request
1. Login as Donor **DON-E5F6G7H8** (Priya Patel)
2. Go to Donor Dashboard
3. Scroll to **"Available Blood Requests"** table
4. Find request **BR-B5C6D7E8** (A+ blood needed)
5. Click **"Accept"** button
6. Modal appears → Select **1** unit, click **"Accept Request"**
7. ✓ Success: "✓ You have accepted the request!"

#### B) Requestor Confirms Donor
1. Go to http://127.0.0.1:5000/requestor/dashboard/REQ-X1Y2Z3A4
2. Find request **BR-B5C6D7E8** in accordion
3. Under **"Assigned Donors"**, find **Priya Patel**
4. Click **"Confirm Donor"** button
5. ✓ Success: "✓ Confirmed! Awaiting Priya Patel to complete donation of 1 unit(s)."

#### C) Donor Completes Donation
1. Back to Donor Dashboard (Priya)
2. Scroll to **"My Assigned Requests"**
3. Click **"Confirm Donation"** button
4. Modal: Verify units (1), click **"Confirm Donation"**
5. ✓ Success: "✓ Donation confirmed! 1 unit(s) donated. Remaining needed: 2 unit(s)"

### Verify:
- Request status: `pending` → `partial` (now 3/5 fulfilled)
- Assignment status: `pending` → `accepted` → `confirmed_by_requestor` → `completed`
- Fulfilled History shows Priya Patel donation
- Donor history shows request link with patient name

---

## 🟡 TEST FEATURE 4: PARTIAL FULFILLMENT

### Current State After Feature 3:
- Request BR-B5C6D7E8 (A+, 5 units)
- Fulfilled: 3 units (2 from inventory + 1 from Priya)
- Remaining: 2 units
- Status: `partial`

### Continue with Feature 4:

#### A) Another Donor Accepts Remaining
1. Login as **DON-A2B3C4D5** (Anjali Gupta, A-)
2. Go to Donor Dashboard
3. Find **BR-B5C6D7E8** in available requests
4. Accept **2** units
5. Requestor confirms
6. Donor completes donation

#### B) Verify Fulfillment
1. Check Request Details: **BR-B5C6D7E8**
2. **Fulfilled History** shows:
   - Blood Bank Inventory: 2 units
   - Priya Patel: 1 unit
   - Anjali Gupta: 2 units
3. Status changed: `partial` → `fulfilled`
4. Message: "✓ Request fully fulfilled!"

### Verify Data:
- Fulfilled units: 5/5
- Remaining units: 0
- Status: **fulfilled**
- Fulfilled History shows all 3 sources with dates
- All donations tracked separately

---

## 🟣 TEST FEATURE 5: MATCHING DONOR DISPLAY

### Case 1: Matching Donor Exists

1. Go to http://127.0.0.1:5000/request-blood
2. Create NEW request:
   - Patient Name: **Test Patient**
   - Patient Age: **30**
   - Blood Group: **O+** (universal donor - many available)
   - Units: **3**
   - Hospital: **Test Hospital**
   - City: **Mumbai**
   - Required Date: **2025-02-20**
3. Click **"Submit"** → See new request created
4. Check **Matching Results** card:
   - ✓ Shows: **"✓ Good News! There are compatible donors available for O+ blood group."**
   - Compatible donors count > 0
5. Verified: **Matching donor indicator working!**

### Case 2: No Matching Donor (Simulate)

1. Create request for **AB-** (rare blood group)
2. Only few donors have this
3. If none available:
   - ✓ Shows: **"✗ No matching donors currently available for AB- blood group."**
   - Shows inventory availability
   - Suggests using inventory

---

## 📊 ADMIN DASHBOARD - VIEW ALL DATA

**URL**: http://127.0.0.1:5000/dashboard

Shows:
- Total donors, requestors, requests
- Active vs fulfilled requests
- All assignments
- All donations with types
- Inventory status

---

## 🧪 STRESS TEST SCENARIOS

### Scenario A: Multiple Donors for One Request

1. Create request for 10 units O+
2. Have Donor A accept 3 units
3. Have Donor B accept 4 units
4. Have Donor C accept 3 units
5. All confirm and complete
6. ✓ Fulfilled History shows all 3 donors
7. ✓ Request shows 10/10 fulfilled

### Scenario B: Mixed Source Fulfillment

1. Create request for 6 units B+
2. Use inventory: 2 units
3. Donor accepts: 2 units
4. Use inventory again: 2 units
5. ✓ Fulfilled History shows:
   - Blood Bank (2 units)
   - Donor (2 units)
   - Blood Bank (2 units)

### Scenario C: Edge Cases

1. Try donating 0 units → ✗ "Invalid units"
2. Try donating 6 units → ✗ "Must be between 1 and 5"
3. Try withdrawing more than inventory → ✗ "Not enough inventory"
4. Try withdrawing more than needed → ✗ "Exceed remaining need"
5. ✓ All error messages clear and specific

---

## 🔍 KEY THINGS TO CHECK

- [ ] Inventory increases when donor donates
- [ ] Inventory decreases when withdrawn for request
- [ ] Request status updates: pending → partial → fulfilled
- [ ] Fulfilled units tracker is accurate
- [ ] Remaining units correctly calculated
- [ ] Assignment status properly tracked
- [ ] Donation history shows correct donor/patient info
- [ ] Timestamps are accurate (YYYY-MM-DD HH:MM:SS)
- [ ] Matching donor indicator shows/hides correctly
- [ ] All validation errors display clearly
- [ ] All success messages show with ✓ icon

---

## 🐛 TROUBLESHOOTING

### App won't start
```bash
python -c "import app; print('OK')"  # Check syntax
```

### Inventory not updating
- Check if route `/request/<id>/use-inventory` is POST
- Verify form submission
- Check dev console for errors

### Donation history not showing
- Ensure donation_date is formatted correctly
- Check donations_db dictionary

### Matching indicator not working
- Check if `check_matching_donors()` is called
- Verify RECEIVE_COMPATIBILITY matrix
- Check donor availability status

---

## 📋 QUICK LINKS

| Task | URL |
|------|-----|
| Home | http://127.0.0.1:5000/ |
| Admin Dashboard | http://127.0.0.1:5000/dashboard |
| Blood Inventory | http://127.0.0.1:5000/blood-inventory |
| Donor Login | http://127.0.0.1:5000/donor/login |
| Requestor Login | http://127.0.0.1:5000/requestor/login |
| Create Request | http://127.0.0.1:5000/request-blood |
| Search Donors | http://127.0.0.1:5000/search-donors |

---

**Status**: ✅ All 5 features implemented and ready to test!

For detailed implementation info, see **FEATURES_IMPLEMENTED.md**
