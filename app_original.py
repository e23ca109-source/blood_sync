"""
BloodSync - Blood Bank Management System
Flask Backend Application
Connects Blood Donors with Requestors
Version 2.0 - Enhanced with Request-Donor Matching Flow
"""

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime, timedelta
import uuid
import json
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = 'bloodsync-secret-key-2024-enhanced'

# ============== DATA STORAGE (Local - Will be replaced with AWS later) ==============

# Donors dictionary: {donor_id: donor_data}
donors_db = {}

# Requestors dictionary: {requestor_id: requestor_data}
requestors_db = {}

# Blood requests dictionary: {request_id: request_data}
blood_requests_db = {}

# Donations dictionary: {donation_id: donation_data}
donations_db = {}

# Donor-Request assignments: {assignment_id: assignment_data}
donor_request_assignments = {}

# Blood inventory by blood group
blood_inventory = {
    'A+': {'units': 50, 'donors': []},
    'A-': {'units': 30, 'donors': []},
    'B+': {'units': 45, 'donors': []},
    'B-': {'units': 25, 'donors': []},
    'AB+': {'units': 20, 'donors': []},
    'AB-': {'units': 15, 'donors': []},
    'O+': {'units': 60, 'donors': []},
    'O-': {'units': 40, 'donors': []}
}

# ============== BLOOD COMPATIBILITY MATRIX ==============
# Who can DONATE TO whom (Donor Blood Group -> Recipient Blood Groups)
BLOOD_COMPATIBILITY = {
    'A+': ['A+', 'AB+'],
    'A-': ['A+', 'A-', 'AB+', 'AB-'],
    'B+': ['B+', 'AB+'],
    'B-': ['B+', 'B-', 'AB+', 'AB-'],
    'AB+': ['AB+'],
    'AB-': ['AB+', 'AB-'],
    'O+': ['O+', 'A+', 'B+', 'AB+'],
    'O-': ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-']  # Universal donor
}

# Who can RECEIVE FROM whom (Recipient Blood Group -> Donor Blood Groups)
RECEIVE_COMPATIBILITY = {
    'A+': ['A+', 'A-', 'O+', 'O-'],
    'A-': ['A-', 'O-'],
    'B+': ['B+', 'B-', 'O+', 'O-'],
    'B-': ['B-', 'O-'],
    'AB+': ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'],  # Universal recipient
    'AB-': ['A-', 'B-', 'AB-', 'O-'],
    'O+': ['O+', 'O-'],
    'O-': ['O-']
}

# ============== HELPER FUNCTIONS ==============

def generate_donor_id():
    """Generate unique donor ID"""
    return f"DON-{uuid.uuid4().hex[:8].upper()}"

def generate_requestor_id():
    """Generate unique requestor ID"""
    return f"REQ-{uuid.uuid4().hex[:8].upper()}"

def generate_request_id():
    """Generate unique blood request ID"""
    return f"BR-{uuid.uuid4().hex[:8].upper()}"

def generate_donation_id():
    """Generate unique donation ID"""
    return f"DN-{uuid.uuid4().hex[:8].upper()}"

def generate_assignment_id():
    """Generate unique assignment ID"""
    return f"ASGN-{uuid.uuid4().hex[:8].upper()}"

def get_compatible_donor_blood_groups(recipient_blood_group):
    """
    Get list of donor blood groups that can donate to recipient
    Example: For A+ recipient, returns ['A+', 'A-', 'O+', 'O-']
    """
    return RECEIVE_COMPATIBILITY.get(recipient_blood_group, [])

def get_compatible_donors(recipient_blood_group, location=None):
    """
    Find compatible donors who can donate to recipient's blood group
    Returns list of compatible donors
    """
    compatible_blood_groups = get_compatible_donor_blood_groups(recipient_blood_group)
    compatible_donors = []
    
    for donor_id, donor in donors_db.items():
        if donor['blood_group'] in compatible_blood_groups:
            if donor['available'] and donor['status'] == 'active':
                # Check location if specified
                if location:
                    if (location.lower() in donor.get('city', '').lower() or 
                        location.lower() in donor.get('state', '').lower()):
                        compatible_donors.append(donor)
                else:
                    compatible_donors.append(donor)
    
    # Sort by last donation date (most recent first)
    # Use a fallback string when value is None to avoid TypeError during comparison
    compatible_donors.sort(key=lambda x: (x.get('last_donation') or '1900-01-01'), reverse=True)
    return compatible_donors

def can_donate(last_donation_date):
    """Check if donor can donate (56 days gap required)"""
    if not last_donation_date:
        return True
    try:
        last = datetime.strptime(last_donation_date, '%Y-%m-%d')
        return (datetime.now() - last).days >= 56
    except:
        return True

def calculate_donor_eligibility(donor):
    """Calculate donor eligibility score"""
    score = 100
    
    # Age factor
    age = donor.get('age', 0)
    if 25 <= age <= 45:
        score += 10
    elif age < 18 or age > 65:
        score -= 50
    
    # Availability
    if not donor.get('available', True):
        score -= 100
    
    # Last donation recency
    last_donation = donor.get('last_donation')
    if last_donation:
        try:
            days_since = (datetime.now() - datetime.strptime(last_donation, '%Y-%m-%d')).days
            if days_since > 90:
                score += 5
        except:
            pass
    else:
        score += 10  # New donor bonus
    
    # Donation history
    total_donations = donor.get('total_donations', 0)
    score += min(total_donations * 2, 20)
    
    return max(0, min(score, 150))

def get_donor_assigned_requests(donor_id):
    """Get all requests assigned to a donor"""
    assigned = []
    for assignment in donor_request_assignments.values():
        if assignment['donor_id'] == donor_id and assignment['status'] in ['pending', 'accepted']:
            request_data = blood_requests_db.get(assignment['request_id'])
            if request_data:
                assigned.append({
                    **assignment,
                    'request': request_data
                })
    return assigned

def get_request_assigned_donors(request_id):
    """Get all donors assigned to a request"""
    assigned = []
    for assignment in donor_request_assignments.values():
        if assignment['request_id'] == request_id:
            donor_data = donors_db.get(assignment['donor_id'])
            if donor_data:
                assigned.append({
                    **assignment,
                    'donor': donor_data
                })
    return assigned

def get_available_requests_for_donor(donor_id):
    """Get all requests that this donor can fulfill"""
    donor = donors_db.get(donor_id)
    if not donor:
        return []
    
    donor_blood_group = donor['blood_group']
    # Get blood groups this donor can donate to
    can_donate_to = BLOOD_COMPATIBILITY.get(donor_blood_group, [])
    
    available_requests = []
    for request_id, request_data in blood_requests_db.items():
        # Check if request blood group is in the list this donor can donate to
        if request_data['blood_group'] in can_donate_to:
            # Check if request is still pending or partial
            if request_data['status'] in ['pending', 'partial']:
                # Check if this donor is not already assigned
                already_assigned = any(
                    a['donor_id'] == donor_id and a['request_id'] == request_id 
                    for a in donor_request_assignments.values()
                )
                if not already_assigned:
                    # Calculate remaining units needed
                    remaining = request_data['units_needed'] - request_data.get('fulfilled_units', 0)
                    available_requests.append({
                        **request_data,
                        'remaining_units': remaining
                    })
    
    # Sort by urgency and date (guard against missing/None created_at)
    urgency_order = {'critical': 0, 'high': 1, 'normal': 2}
    available_requests.sort(key=lambda x: (urgency_order.get(x.get('urgency'), 2), x.get('created_at') or '1900-01-01'))
    
    return available_requests

def get_matching_donors_for_request(request_id):
    """Get donors who have accepted this request (for display)"""
    matching = []
    for assignment in donor_request_assignments.values():
        if assignment['request_id'] == request_id and assignment['status'] in ['accepted', 'confirmed_by_requestor', 'completed']:
            donor_data = donors_db.get(assignment['donor_id'])
            if donor_data:
                matching.append({
                    'donor': donor_data,
                    'assignment': assignment
                })
    return matching

def check_matching_donors(blood_group):
    """Check if there are available donors for a blood group"""
    compatible_blood_groups = RECEIVE_COMPATIBILITY.get(blood_group, [])
    for donor_id, donor in donors_db.items():
        if donor['blood_group'] in compatible_blood_groups and donor['available'] and donor['status'] == 'active':
            if can_donate(donor.get('last_donation')):
                return True
    return False

def match_blood_request(request_data):
    """
    Blood matching algorithm
    Finds best matching donors for a blood request
    """
    blood_group = request_data['blood_group']
    units_needed = request_data['units_needed']
    location = request_data.get('location', '')
    urgency = request_data.get('urgency', 'normal')
    
    # Get compatible donors
    compatible_donors = get_compatible_donors(blood_group, location)
    
    # Calculate eligibility scores
    scored_donors = []
    for donor in compatible_donors:
        score = calculate_donor_eligibility(donor)
        scored_donors.append({
            **donor,
            'match_score': score,
            'can_donate_now': can_donate(donor.get('last_donation'))
        })
    
    # Sort by match score
    scored_donors.sort(key=lambda x: x['match_score'], reverse=True)
    
    # Check inventory first for exact match
    inventory_available = blood_inventory.get(blood_group, {}).get('units', 0)
    
    # Calculate remaining units needed
    remaining_units = units_needed - request_data.get('fulfilled_units', 0)
    
    return {
        'exact_match_inventory': inventory_available,
        'compatible_donors': scored_donors[:10],  # Top 10 matches
        'total_compatible': len(scored_donors),
        'fulfillable': inventory_available >= remaining_units or len(scored_donors) > 0,
        'remaining_units': remaining_units
    }

def update_inventory(blood_group, units, operation='add'):
    """Update blood inventory"""
    if blood_group in blood_inventory:
        if operation == 'add':
            blood_inventory[blood_group]['units'] += units
        elif operation == 'remove':
            blood_inventory[blood_group]['units'] = max(0, blood_inventory[blood_group]['units'] - units)

def get_statistics():
    """Get dashboard statistics"""
    total_donors = len(donors_db)
    total_requestors = len(requestors_db)
    total_requests = len(blood_requests_db)
    
    active_requests = sum(1 for r in blood_requests_db.values() if r['status'] in ['pending', 'partial'])
    fulfilled_requests = sum(1 for r in blood_requests_db.values() if r['status'] == 'fulfilled')
    
    total_units_available = sum(inv['units'] for inv in blood_inventory.values())
    
    # Critical blood groups (less than 20 units)
    critical_groups = [bg for bg, inv in blood_inventory.items() if inv['units'] < 20]
    
    return {
        'total_donors': total_donors,
        'total_requestors': total_requestors,
        'total_requests': total_requests,
        'active_requests': active_requests,
        'fulfilled_requests': fulfilled_requests,
        'total_units': total_units_available,
        'critical_groups': critical_groups,
        'inventory': blood_inventory
    }

# ============== ROUTES ==============

@app.route('/')
def home():
    """Home page"""
    stats = get_statistics()
    recent_requests = sorted(
        blood_requests_db.values(), 
        key=lambda x: (x.get('created_at') or ''), 
        reverse=True
    )[:5]
    return render_template('index.html', stats=stats, recent_requests=recent_requests)

@app.route('/about')
def about():
    """About page"""
    return render_template('about.html')

# ============== DONOR ROUTES ==============

@app.route('/donor/register', methods=['GET', 'POST'])
def donor_register():
    """Donor registration"""
    if request.method == 'POST':
        donor_id = generate_donor_id()
        
        donor_data = {
            'donor_id': donor_id,
            'name': request.form['name'],
            'email': request.form['email'],
            'phone': request.form['phone'],
            'age': int(request.form['age']),
            'gender': request.form['gender'],
            'blood_group': request.form['blood_group'],
            'weight': float(request.form['weight']),
            'address': request.form['address'],
            'city': request.form['city'],
            'state': request.form['state'],
            'pincode': request.form['pincode'],
            'medical_history': request.form.get('medical_history', 'None'),
            'available': True,
            'status': 'active',
            'total_donations': 0,
            'last_donation': None,
            'registered_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'emergency_contact': request.form.get('emergency_contact', ''),
            'preferred_contact_time': request.form.get('preferred_contact_time', 'Anytime')
        }
        
        # Validate age
        if donor_data['age'] < 18 or donor_data['age'] > 65:
            flash('Donor age must be between 18 and 65 years!', 'error')
            return redirect(url_for('donor_register'))
        
        # Validate weight
        if donor_data['weight'] < 50:
            flash('Donor weight must be at least 50kg!', 'error')
            return redirect(url_for('donor_register'))
        
        donors_db[donor_id] = donor_data
        
        # Update inventory donor list
        blood_inventory[donor_data['blood_group']]['donors'].append(donor_id)
        
        flash(f'Registration successful! Your Donor ID is: {donor_id}', 'success')
        return redirect(url_for('donor_dashboard', donor_id=donor_id))
    
    return render_template('donor_register.html')

@app.route('/donor/dashboard/<donor_id>')
def donor_dashboard(donor_id):
    """Donor dashboard"""
    donor = donors_db.get(donor_id)
    if not donor:
        flash('Donor not found!', 'error')
        return redirect(url_for('home'))
    
    # Get donation history
    donation_history = [d for d in donations_db.values() if d['donor_id'] == donor_id]
    
    # Check eligibility
    can_donate_now = can_donate(donor.get('last_donation'))
    
    # Get assigned requests
    assigned_requests = get_donor_assigned_requests(donor_id)
    
    # Get available requests for this donor
    available_requests = get_available_requests_for_donor(donor_id)
    
    return render_template('donor_dashboard.html', donor=donor, 
                          donation_history=donation_history, 
                          can_donate_now=can_donate_now,
                          assigned_requests=assigned_requests,
                          available_requests=available_requests)

@app.route('/donor/login', methods=['GET', 'POST'])
def donor_login():
    """Donor login"""
    if request.method == 'POST':
        donor_id = request.form['donor_id']
        email = request.form['email']
        
        donor = donors_db.get(donor_id)
        if donor and donor['email'] == email:
            session['donor_id'] = donor_id
            flash('Login successful!', 'success')
            return redirect(url_for('donor_dashboard', donor_id=donor_id))
        else:
            flash('Invalid Donor ID or Email!', 'error')
    
    return render_template('donor_login.html')

@app.route('/donor/update/<donor_id>', methods=['POST'])
def donor_update(donor_id):
    """Update donor information"""
    donor = donors_db.get(donor_id)
    if not donor:
        flash('Donor not found!', 'error')
        return redirect(url_for('home'))
    
    donor['phone'] = request.form.get('phone', donor['phone'])
    donor['address'] = request.form.get('address', donor['address'])
    donor['available'] = request.form.get('available') == 'on'
    donor['city'] = request.form.get('city', donor['city'])
    donor['state'] = request.form.get('state', donor['state'])
    
    flash('Profile updated successfully!', 'success')
    return redirect(url_for('donor_dashboard', donor_id=donor_id))

@app.route('/donor/donate/<donor_id>', methods=['POST'])
def record_donation(donor_id):
    """Record a new donation to inventory"""
    donor = donors_db.get(donor_id)
    if not donor:
        flash('✗ Donor not found!', 'error')
        return redirect(url_for('home'))
    
    if not can_donate(donor.get('last_donation')):
        last_donation = donor.get('last_donation', '1900-01-01')
        try:
            days_passed = (datetime.now() - datetime.strptime(last_donation, '%Y-%m-%d')).days
            days_remaining = max(0, 56 - days_passed)
            flash(f'✗ You must wait {days_remaining} more days before donating again!', 'error')
        except:
            flash('✗ You must wait 56 days between donations!', 'error')
        return redirect(url_for('donor_dashboard', donor_id=donor_id))
    
    try:
        units = int(request.form.get('units', 1))
        if units <= 0 or units > 5:
            flash('✗ Invalid units! Must be between 1 and 5 units per donation.', 'error')
            return redirect(url_for('donor_dashboard', donor_id=donor_id))
    except ValueError:
        flash('✗ Units must be a valid number!', 'error')
        return redirect(url_for('donor_dashboard', donor_id=donor_id))
    
    donation_id = generate_donation_id()
    
    donation_data = {
        'donation_id': donation_id,
        'donor_id': donor_id,
        'donor_name': donor['name'],
        'blood_group': donor['blood_group'],
        'units': units,
        'donation_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'donation_center': request.form.get('donation_center', 'Main Center'),
        'donation_type': 'direct_inventory',
        'request_id': None,
        'patient_name': None,
        'notes': request.form.get('notes', ''),
        'status': 'completed'
    }
    
    donations_db[donation_id] = donation_data
    
    # Update donor record
    donor['last_donation'] = datetime.now().strftime('%Y-%m-%d')
    donor['total_donations'] += 1
    
    # Update inventory
    update_inventory(donor['blood_group'], units, 'add')
    
    flash(f'✓ Donation recorded successfully! {units} unit(s) of {donor["blood_group"]} added to inventory. ID: {donation_id}', 'success')
    return redirect(url_for('donor_dashboard', donor_id=donor_id))

# ============== NEW: DONOR ACCEPT REQUEST FLOW ==============

@app.route('/donor/accept-request/<donor_id>/<request_id>', methods=['POST'])
def donor_accept_request(donor_id, request_id):
    """Donor accepts a blood request"""
    donor = donors_db.get(donor_id)
    request_data = blood_requests_db.get(request_id)
    
    if not donor or not request_data:
        flash('Invalid donor or request!', 'error')
        return redirect(url_for('home'))
    
    # Create assignment
    assignment_id = generate_assignment_id()
    units_offered = int(request.form.get('units_offered', 1))
    
    assignment_data = {
        'assignment_id': assignment_id,
        'donor_id': donor_id,
        'request_id': request_id,
        'units_offered': units_offered,
        'status': 'accepted',
        'accepted_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'donated_at': None,
        'notes': request.form.get('notes', '')
    }
    
    donor_request_assignments[assignment_id] = assignment_data
    
    flash(f'You have accepted the request! Assignment ID: {assignment_id}', 'success')
    return redirect(url_for('donor_dashboard', donor_id=donor_id))

@app.route('/donor/confirm-donation/<assignment_id>', methods=['POST'])
def donor_confirm_donation(assignment_id):
    """Donor confirms they have donated for an assigned request"""
    assignment = donor_request_assignments.get(assignment_id)
    if not assignment:
        flash('✗ Assignment not found!', 'error')
        return redirect(url_for('home'))
    
    if assignment['status'] not in ['accepted', 'confirmed_by_requestor']:
        flash(f'✗ Cannot confirm donation in {assignment["status"]} status!', 'error')
        return redirect(url_for('donor_dashboard', donor_id=assignment['donor_id']))
    
    donor_id = assignment['donor_id']
    request_id = assignment['request_id']
    
    donor = donors_db.get(donor_id)
    request_data = blood_requests_db.get(request_id)
    
    if not donor or not request_data:
        flash('✗ Invalid data!', 'error')
        return redirect(url_for('donor_dashboard', donor_id=donor_id))
    
    try:
        units_donated = int(request.form.get('units_donated', assignment['units_offered']))
        if units_donated <= 0 or units_donated > assignment['units_offered']:
            flash(f'✗ Invalid units! Must be between 1 and {assignment["units_offered"]}', 'error')
            return redirect(url_for('donor_dashboard', donor_id=donor_id))
    except ValueError:
        flash('✗ Units must be a valid number!', 'error')
        return redirect(url_for('donor_dashboard', donor_id=donor_id))
    
    # Update assignment
    assignment['status'] = 'completed'
    assignment['units_donated'] = units_donated
    assignment['donated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Update request fulfilled units
    request_data['fulfilled_units'] = request_data.get('fulfilled_units', 0) + units_donated
    
    # Update request status
    remaining = request_data['units_needed'] - request_data['fulfilled_units']
    if remaining <= 0:
        request_data['status'] = 'fulfilled'
    else:
        request_data['status'] = 'partial'
    
    # Update donor stats
    donor['last_donation'] = datetime.now().strftime('%Y-%m-%d')
    donor['total_donations'] = donor.get('total_donations', 0) + 1
    
    # Create donation record
    donation_id = generate_donation_id()
    donation_data = {
        'donation_id': donation_id,
        'donor_id': donor_id,
        'donor_name': donor['name'],
        'request_id': request_id,
        'patient_name': request_data['patient_name'],
        'blood_group': donor['blood_group'],
        'units': units_donated,
        'donation_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'donation_center': request.form.get('donation_center', request_data['hospital_name']),
        'donation_type': 'request_fulfillment',
        'notes': f'Fulfilled request {request_id}',
        'assignment_id': assignment_id,
        'status': 'completed'
    }
    donations_db[donation_id] = donation_data
    
    msg = f'✓ Donation confirmed! {units_donated} unit(s) donated to {request_data["patient_name"]}.'
    if remaining > 0:
        msg += f' Remaining needed: {remaining} unit(s)'
    else:
        msg += ' Request fully fulfilled!'
    flash(msg, 'success')
    return redirect(url_for('donor_dashboard', donor_id=donor_id))

# ============== REQUESTOR ROUTES ==============

@app.route('/requestor/register', methods=['GET', 'POST'])
def requestor_register():
    """Requestor registration"""
    if request.method == 'POST':
        requestor_id = generate_requestor_id()
        
        requestor_data = {
            'requestor_id': requestor_id,
            'name': request.form['name'],
            'email': request.form['email'],
            'phone': request.form['phone'],
            'organization': request.form.get('organization', 'Individual'),
            'address': request.form['address'],
            'city': request.form['city'],
            'state': request.form['state'],
            'pincode': request.form['pincode'],
            'registered_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_requests': 0
        }
        
        requestors_db[requestor_id] = requestor_data
        
        flash(f'Registration successful! Your Requestor ID is: {requestor_id}', 'success')
        return redirect(url_for('requestor_dashboard', requestor_id=requestor_id))
    
    return render_template('requestor_register.html')

@app.route('/requestor/dashboard/<requestor_id>')
def requestor_dashboard(requestor_id):
    """Requestor dashboard"""
    requestor = requestors_db.get(requestor_id)
    if not requestor:
        flash('Requestor not found!', 'error')
        return redirect(url_for('home'))
    
    # Get request history with assigned donors
    request_history = []
    for req in blood_requests_db.values():
        if req['requestor_id'] == requestor_id:
            assigned_donors = get_request_assigned_donors(req['request_id'])
            # Donation history for this request
            donation_history = [d for d in donations_db.values() if d.get('request_id') == req['request_id']]

            # Suggested compatible donors (exclude already assigned)
            match_results = match_blood_request(req)
            suggested = []
            assigned_ids = {a['donor_id'] for a in assigned_donors}
            for d in match_results.get('compatible_donors', [])[:10]:
                if d['donor_id'] not in assigned_ids:
                    suggested.append(d)

            request_history.append({
                **req,
                'assigned_donors': assigned_donors,
                'donation_history': donation_history,
                'suggested_donors': suggested,
                'remaining_units': req['units_needed'] - req.get('fulfilled_units', 0),
                'inventory_available': blood_inventory.get(req['blood_group'], {}).get('units', 0)
            })
    
    # Sort by date (guard against missing/None created_at)
    request_history.sort(key=lambda x: (x.get('created_at') or ''), reverse=True)
    
    return render_template('requestor_dashboard.html', requestor=requestor, 
                          request_history=request_history)

@app.route('/requestor/login', methods=['GET', 'POST'])
def requestor_login():
    """Requestor login"""
    if request.method == 'POST':
        requestor_id = request.form['requestor_id']
        email = request.form['email']
        
        requestor = requestors_db.get(requestor_id)
        if requestor and requestor['email'] == email:
            session['requestor_id'] = requestor_id
            flash('Login successful!', 'success')
            return redirect(url_for('requestor_dashboard', requestor_id=requestor_id))
        else:
            flash('Invalid Requestor ID or Email!', 'error')
    
    return render_template('requestor_login.html')

# ============== BLOOD REQUEST ROUTES ==============

@app.route('/request-blood', methods=['GET', 'POST'])
def request_blood():
    """Create blood request"""
    if request.method == 'POST':
        request_id = generate_request_id()
        
        request_data = {
            'request_id': request_id,
            'requestor_id': request.form.get('requestor_id', 'GUEST'),
            'patient_name': request.form['patient_name'],
            'patient_age': int(request.form['patient_age']),
            'patient_gender': request.form['patient_gender'],
            'blood_group': request.form['blood_group'],
            'units_needed': int(request.form['units_needed']),
            'hospital_name': request.form['hospital_name'],
            'hospital_address': request.form['hospital_address'],
            'location': request.form.get('city', ''),
            'city': request.form.get('city', ''),
            'state': request.form.get('state', ''),
            'contact_name': request.form['contact_name'],
            'contact_phone': request.form['contact_phone'],
            'contact_email': request.form.get('contact_email', ''),
            'urgency': request.form.get('urgency', 'normal'),
            'required_date': request.form['required_date'],
            'reason': request.form.get('reason', ''),
            'status': 'pending',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'matched_donors': [],
            'fulfilled_units': 0,
            'inventory_used': 0
        }
        
        blood_requests_db[request_id] = request_data
        
        # Update requestor stats if registered
        requestor_id = request_data['requestor_id']
        if requestor_id in requestors_db:
            requestors_db[requestor_id]['total_requests'] += 1
        
        # Run matching algorithm to find compatible donors
        match_results = match_blood_request(request_data)
        blood_requests_db[request_id]['matched_donors'] = [d['donor_id'] for d in match_results['compatible_donors']]
        
        flash(f'Blood request created! Request ID: {request_id}', 'success')
        return redirect(url_for('request_details', request_id=request_id))
    
    return render_template('request_blood.html')

@app.route('/request/<request_id>')
def request_details(request_id):
    """View request details with matched donors"""
    request_data = blood_requests_db.get(request_id)
    if not request_data:
        flash('Request not found!', 'error')
        return redirect(url_for('home'))
    
    # Get fresh match results
    match_results = match_blood_request(request_data)
    
    # Get assigned donors
    assigned_donors = get_request_assigned_donors(request_id)

    # Donation history for this request
    donation_history = [d for d in donations_db.values() if d.get('request_id') == request_id]
    
    # Calculate remaining units
    remaining_units = request_data['units_needed'] - request_data.get('fulfilled_units', 0)
    
    # Check for matching donors
    has_matching_donors = check_matching_donors(request_data['blood_group'])
    inventory_available = blood_inventory.get(request_data['blood_group'], {}).get('units', 0)
    
    return render_template('request_details.html', request=request_data, 
                          match_results=match_results,
                          assigned_donors=assigned_donors,
                          remaining_units=remaining_units,
                          donation_history=donation_history,
                          has_matching_donors=has_matching_donors,
                          inventory_available=inventory_available)

@app.route('/search-donors', methods=['GET', 'POST'])
def search_donors():
    """Search for donors"""
    results = []
    search_performed = False
    
    if request.method == 'POST':
        blood_group = request.form.get('blood_group', '')
        location = request.form.get('location', '')
        
        search_performed = True
        
        for donor in donors_db.values():
            match = True
            
            if blood_group and donor['blood_group'] != blood_group:
                match = False
            
            if location:
                loc_match = (location.lower() in donor.get('city', '').lower() or 
                           location.lower() in donor.get('state', '').lower() or
                           location.lower() in donor.get('pincode', ''))
                if not loc_match:
                    match = False
            
            if match and donor['available'] and donor['status'] == 'active':
                results.append(donor)
    
    return render_template('search_donors.html', results=results, 
                          search_performed=search_performed)

@app.route('/blood-inventory')
def blood_inventory_view():
    """View blood inventory"""
    stats = get_statistics()
    return render_template('blood_inventory.html', inventory=blood_inventory, stats=stats)

# ============== NEW: INVENTORY DONATION ROUTE ==============

@app.route('/request/<request_id>/use-inventory', methods=['POST'])
def use_inventory_for_request(request_id):
    """Use blood inventory to fulfill a request"""
    request_data = blood_requests_db.get(request_id)
    if not request_data:
        flash('✗ Request not found!', 'error')
        return redirect(url_for('home'))
    
    blood_group = request_data['blood_group']
    try:
        units_from_inventory = int(request.form.get('units_from_inventory', 0))
        if units_from_inventory <= 0:
            flash('✗ Units must be greater than 0!', 'error')
            return redirect(url_for('request_details', request_id=request_id))
    except ValueError:
        flash('✗ Invalid units input!', 'error')
        return redirect(url_for('request_details', request_id=request_id))
    
    # Check if inventory has enough
    available = blood_inventory.get(blood_group, {}).get('units', 0)
    
    if units_from_inventory > available:
        flash(f'✗ Not enough inventory! Available: {available} units, Requested: {units_from_inventory}', 'error')
        return redirect(url_for('request_details', request_id=request_id))
    
    remaining_needed = request_data['units_needed'] - request_data.get('fulfilled_units', 0)
    if units_from_inventory > remaining_needed:
        flash(f'✗ Units exceed remaining need! Only {remaining_needed} more unit(s) needed.', 'error')
        return redirect(url_for('request_details', request_id=request_id))
    
    # Update inventory
    update_inventory(blood_group, units_from_inventory, 'remove')
    
    # Create inventory transaction record
    transaction_id = generate_donation_id()
    transaction_data = {
        'donation_id': transaction_id,
        'blood_group': blood_group,
        'units': units_from_inventory,
        'donation_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'donation_type': 'inventory_withdrawal',
        'request_id': request_id,
        'donor_name': 'Blood Bank Inventory',
        'donor_id': 'INVENTORY',
        'status': 'completed'
    }
    donations_db[transaction_id] = transaction_data
    
    # Update request
    request_data['fulfilled_units'] = request_data.get('fulfilled_units', 0) + units_from_inventory
    request_data['inventory_used'] = request_data.get('inventory_used', 0) + units_from_inventory
    
    # Update status
    remaining = request_data['units_needed'] - request_data['fulfilled_units']
    if remaining <= 0:
        request_data['status'] = 'fulfilled'
        flash(f'✓ Request fully fulfilled! {units_from_inventory} unit(s) taken from inventory.', 'success')
    else:
        request_data['status'] = 'partial'
        flash(f'✓ {units_from_inventory} unit(s) taken from inventory. Remaining needed: {remaining} unit(s)', 'info')
    
    return redirect(url_for('request_details', request_id=request_id))

# ============== NEW: REQUESTOR CONFIRM DONOR ROUTE ==============

@app.route('/request/<request_id>/confirm-donor/<assignment_id>', methods=['POST'])
def requestor_confirm_donor(request_id, assignment_id):
    """Requestor confirms a donor's offer"""
    request_data = blood_requests_db.get(request_id)
    assignment = donor_request_assignments.get(assignment_id)
    
    if not request_data or not assignment:
        flash('✗ Invalid request or assignment!', 'error')
        return redirect(url_for('home'))
    
    if assignment['status'] not in ['accepted', 'pending']:
        flash(f'✗ Cannot confirm assignment in {assignment["status"]} status!', 'error')
        return redirect(url_for('request_details', request_id=request_id))
    
    # Update assignment status
    assignment['status'] = 'confirmed_by_requestor'
    assignment['confirmed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    donor = donors_db.get(assignment['donor_id'])
    flash(f'✓ Confirmed! Awaiting {donor["name"]} to complete donation of {assignment["units_offered"]} unit(s).', 'success')
    return redirect(url_for('request_details', request_id=request_id))

# ============== ADMIN/UTILITY ROUTES ==============

@app.route('/dashboard')
def admin_dashboard():
    """Admin dashboard"""
    stats = get_statistics()
    
    # Get all data for admin view
    all_donors = list(donors_db.values())
    all_requests = sorted(blood_requests_db.values(), 
                         key=lambda x: (x.get('created_at') or ''), reverse=True)
    all_donations = sorted(donations_db.values(),
                          key=lambda x: (x.get('donation_date') or ''), reverse=True)
    all_assignments = list(donor_request_assignments.values())
    
    return render_template('admin_dashboard.html', stats=stats, 
                          donors=all_donors, requests=all_requests,
                          donations=all_donations, assignments=all_assignments)

@app.route('/api/statistics')
def api_statistics():
    """API endpoint for statistics"""
    return jsonify(get_statistics())

@app.route('/api/donors')
def api_donors():
    """API endpoint for donors"""
    return jsonify(list(donors_db.values()))

@app.route('/api/requests')
def api_requests():
    """API endpoint for blood requests"""
    return jsonify(list(blood_requests_db.values()))

@app.route('/request/<request_id>/fulfill', methods=['POST'])
def fulfill_request(request_id):
    """Mark request as fulfilled (legacy route)"""
    request_data = blood_requests_db.get(request_id)
    if not request_data:
        flash('Request not found!', 'error')
        return redirect(url_for('home'))
    
    units_fulfilled = int(request.form.get('units_fulfilled', 0))
    
    request_data['fulfilled_units'] = request_data.get('fulfilled_units', 0) + units_fulfilled
    
    if request_data['fulfilled_units'] >= request_data['units_needed']:
        request_data['status'] = 'fulfilled'
        flash('Request fully fulfilled!', 'success')
    else:
        request_data['status'] = 'partial'
        remaining = request_data['units_needed'] - request_data['fulfilled_units']
        flash(f'Partially fulfilled! {remaining} units still needed.', 'info')
    
    # Update inventory
    update_inventory(request_data['blood_group'], units_fulfilled, 'remove')
    
    return redirect(url_for('request_details', request_id=request_id))

@app.route('/logout')
def logout():
    """Logout"""
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('home'))

# ============== ERROR HANDLERS ==============

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

# ============== INITIALIZE SAMPLE DATA ==============

def init_sample_data():
    """Initialize sample data for testing"""
    # Sample donors with various blood groups
    sample_donors = [
        {
            'donor_id': 'DON-A1B2C3D4',
            'name': 'Rahul Sharma',
            'email': 'rahul@example.com',
            'phone': '9876543210',
            'age': 28,
            'gender': 'Male',
            'blood_group': 'O+',
            'weight': 70,
            'address': '123 Main Street',
            'city': 'Mumbai',
            'state': 'Maharashtra',
            'pincode': '400001',
            'medical_history': 'None',
            'available': True,
            'status': 'active',
            'total_donations': 5,
            'last_donation': '2024-12-01',
            'registered_at': '2024-01-15 10:30:00',
            'emergency_contact': '9876543211',
            'preferred_contact_time': 'Evening'
        },
        {
            'donor_id': 'DON-E5F6G7H8',
            'name': 'Priya Patel',
            'email': 'priya@example.com',
            'phone': '8765432109',
            'age': 32,
            'gender': 'Female',
            'blood_group': 'A+',
            'weight': 58,
            'address': '456 Park Avenue',
            'city': 'Delhi',
            'state': 'Delhi',
            'pincode': '110001',
            'medical_history': 'None',
            'available': True,
            'status': 'active',
            'total_donations': 3,
            'last_donation': '2025-01-10',
            'registered_at': '2024-03-20 14:15:00',
            'emergency_contact': '8765432110',
            'preferred_contact_time': 'Morning'
        },
        {
            'donor_id': 'DON-A2B3C4D5',
            'name': 'Anjali Gupta',
            'email': 'anjali@example.com',
            'phone': '7654321098',
            'age': 26,
            'gender': 'Female',
            'blood_group': 'A-',
            'weight': 55,
            'address': '789 Gandhi Road',
            'city': 'Mumbai',
            'state': 'Maharashtra',
            'pincode': '400002',
            'medical_history': 'None',
            'available': True,
            'status': 'active',
            'total_donations': 2,
            'last_donation': None,
            'registered_at': '2024-06-10 09:00:00',
            'emergency_contact': '7654321099',
            'preferred_contact_time': 'Anytime'
        },
        {
            'donor_id': 'DON-I9J0K1L2',
            'name': 'Amit Kumar',
            'email': 'amit@example.com',
            'phone': '6543210987',
            'age': 25,
            'gender': 'Male',
            'blood_group': 'B-',
            'weight': 72,
            'address': '321 Lake View',
            'city': 'Bangalore',
            'state': 'Karnataka',
            'pincode': '560001',
            'medical_history': 'None',
            'available': True,
            'status': 'active',
            'total_donations': 2,
            'last_donation': None,
            'registered_at': '2024-06-10 09:00:00',
            'emergency_contact': '6543210988',
            'preferred_contact_time': 'Anytime'
        },
        {
            'donor_id': 'DON-M3N4O5P6',
            'name': 'Sneha Gupta',
            'email': 'sneha@example.com',
            'phone': '5432109876',
            'age': 29,
            'gender': 'Female',
            'blood_group': 'O-',
            'weight': 55,
            'address': '654 Hillside',
            'city': 'Chennai',
            'state': 'Tamil Nadu',
            'pincode': '600001',
            'medical_history': 'None',
            'available': True,
            'status': 'active',
            'total_donations': 8,
            'last_donation': '2025-01-15',
            'registered_at': '2023-08-05 16:45:00',
            'emergency_contact': '5432109877',
            'preferred_contact_time': 'Afternoon'
        },
        {
            'donor_id': 'DON-Q7R8S9T0',
            'name': 'Vikram Singh',
            'email': 'vikram@example.com',
            'phone': '4321098765',
            'age': 35,
            'gender': 'Male',
            'blood_group': 'AB+',
            'weight': 80,
            'address': '987 River Road',
            'city': 'Pune',
            'state': 'Maharashtra',
            'pincode': '411001',
            'medical_history': 'None',
            'available': True,
            'status': 'active',
            'total_donations': 4,
            'last_donation': '2024-11-20',
            'registered_at': '2024-02-28 11:20:00',
            'emergency_contact': '4321098766',
            'preferred_contact_time': 'Evening'
        }
    ]
    
    for donor in sample_donors:
        donors_db[donor['donor_id']] = donor
        blood_inventory[donor['blood_group']]['donors'].append(donor['donor_id'])
    
    # Sample requestors
    sample_requestors = [
        {
            'requestor_id': 'REQ-X1Y2Z3A4',
            'name': 'Dr. Meera Reddy',
            'email': 'meera@hospital.com',
            'phone': '3210987654',
            'organization': 'City General Hospital',
            'address': 'Hospital Road',
            'city': 'Hyderabad',
            'state': 'Telangana',
            'pincode': '500001',
            'registered_at': '2024-04-10 08:30:00',
            'total_requests': 2
        }
    ]
    
    for requestor in sample_requestors:
        requestors_db[requestor['requestor_id']] = requestor
    
    # Sample blood requests - A+ request that can be fulfilled by A+, A-, O+, O- donors
    sample_requests = [
        {
            'request_id': 'BR-B5C6D7E8',
            'requestor_id': 'REQ-X1Y2Z3A4',
            'patient_name': 'Ramesh Iyer',
            'patient_age': 45,
            'patient_gender': 'Male',
            'blood_group': 'A+',
            'units_needed': 5,
            'hospital_name': 'City General Hospital',
            'hospital_address': 'Hospital Road, Hyderabad',
            'location': 'Hyderabad',
            'city': 'Hyderabad',
            'state': 'Telangana',
            'contact_name': 'Dr. Meera Reddy',
            'contact_phone': '3210987654',
            'contact_email': 'meera@hospital.com',
            'urgency': 'high',
            'required_date': '2025-02-05',
            'reason': 'Surgery',
            'status': 'pending',
            'created_at': '2025-02-01 09:00:00',
            'matched_donors': ['DON-E5F6G7H8', 'DON-A2B3C4D5', 'DON-A1B2C3D4', 'DON-M3N4O5P6'],
            'fulfilled_units': 0,
            'inventory_used': 0
        }
    ]
    
    for req in sample_requests:
        blood_requests_db[req['request_id']] = req

# Initialize sample data
init_sample_data()

# ============== MAIN ==============

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
