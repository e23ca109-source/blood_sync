from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime, timedelta
import uuid
import json
import os
import random
from functools import wraps

# AWS imports (optional)
try:
    import boto3
    from decimal import Decimal
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False

app = Flask(__name__)
app.secret_key = 'bloodsync-secret-key-2024-unified'

# ============== CONFIGURATION ==============
# Set to True for AWS DynamoDB, False for local in-memory storage
USE_AWS = os.getenv('USE_AWS', 'False').lower() == 'true'

# ============== AWS DYNAMODB CONFIG (only if AWS is enabled) ==============
if USE_AWS and AWS_AVAILABLE:
    try:
        dynamodb = boto3.resource(
            'dynamodb',
            region_name=os.getenv('AWS_REGION', 'ap-south-1')
        )
        users_table = dynamodb.Table('BloodSync_Users')
        donors_table = dynamodb.Table('BloodSync_Donors')
        requests_table = dynamodb.Table('BloodSync_Requests')
        inventory_table = dynamodb.Table('BloodSync_Inventory')
        AWS_CONFIGURED = True
    except Exception as e:
        print(f"AWS Configuration Error: {e}")
        AWS_CONFIGURED = False
        USE_AWS = False
else:
    AWS_CONFIGURED = False
    if USE_AWS:
        print("AWS requested but boto3 not available or not configured")
        USE_AWS = False

# ============== DATA STORAGE (Local - used when USE_AWS=False) ==============

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
    if USE_AWS:
        return str(random.randint(100000, 999999))
    return f"DON-{uuid.uuid4().hex[:8].upper()}"

def generate_requestor_id():
    """Generate unique requestor ID"""
    return f"REQ-{uuid.uuid4().hex[:8].upper()}"

def generate_request_id():
    """Generate unique blood request ID"""
    if USE_AWS:
        return str(random.randint(100000, 999999))
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

# ============== DATA ACCESS FUNCTIONS ==============

def get_all_donors():
    """Get all donors - works with both local and AWS"""
    if USE_AWS and AWS_CONFIGURED:
        try:
            response = donors_table.scan()
            return response.get('Items', [])
        except Exception as e:
            print(f"AWS Error getting donors: {e}")
            return []
    else:
        return list(donors_db.values())

def get_all_requests():
    """Get all requests - works with both local and AWS"""
    if USE_AWS and AWS_CONFIGURED:
        try:
            response = requests_table.scan()
            return response.get('Items', [])
        except Exception as e:
            print(f"AWS Error getting requests: {e}")
            return []
    else:
        return list(blood_requests_db.values())

def get_inventory():
    """Get inventory - works with both local and AWS"""
    if USE_AWS and AWS_CONFIGURED:
        try:
            response = inventory_table.scan()
            items = response.get('Items', [])
            # Convert to dictionary format for template compatibility
            inventory = {}
            for item in items:
                blood_group = item.get('blood_group')
                units = int(item.get('units', 0))
                if blood_group:
                    inventory[blood_group] = {'units': units, 'donors': []}

            # Ensure all blood groups exist
            all_blood_groups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
            for bg in all_blood_groups:
                if bg not in inventory:
                    inventory[bg] = {'units': 0, 'donors': []}

            return inventory
        except Exception as e:
            print(f"AWS Error getting inventory: {e}")
            return blood_inventory.copy()
    else:
        return blood_inventory.copy()

def save_donor(donor_data):
    """Save donor - works with both local and AWS"""
    if USE_AWS and AWS_CONFIGURED:
        try:
            donors_table.put_item(Item=donor_data)
        except Exception as e:
            print(f"AWS Error saving donor: {e}")
    else:
        donors_db[donor_data['donor_id']] = donor_data

def save_request(request_data):
    """Save request - works with both local and AWS"""
    if USE_AWS and AWS_CONFIGURED:
        try:
            # Convert units to Decimal for DynamoDB
            request_data_copy = request_data.copy()
            if 'units' in request_data_copy:
                request_data_copy['units'] = Decimal(str(request_data_copy['units']))
            requests_table.put_item(Item=request_data_copy)
        except Exception as e:
            print(f"AWS Error saving request: {e}")
    else:
        blood_requests_db[request_data['request_id']] = request_data

def save_inventory_item(inventory_data):
    """Save inventory item - works with both local and AWS"""
    if USE_AWS and AWS_CONFIGURED:
        try:
            # Convert units to Decimal for DynamoDB
            inventory_data_copy = inventory_data.copy()
            if 'units' in inventory_data_copy:
                inventory_data_copy['units'] = Decimal(str(inventory_data_copy['units']))
            inventory_table.put_item(Item=inventory_data_copy)
        except Exception as e:
            print(f"AWS Error saving inventory: {e}")
    else:
        blood_group = inventory_data['blood_group']
        units = inventory_data['units']
        if blood_group in blood_inventory:
            blood_inventory[blood_group]['units'] = units

# ============== STATISTICS FUNCTION ==============

def get_statistics():
    """Get dashboard statistics"""
    if USE_AWS and AWS_CONFIGURED:
        try:
            # Get total donors
            donors_response = donors_table.scan()
            total_donors = len(donors_response.get('Items', []))

            # Get total requests and fulfilled requests
            requests_response = requests_table.scan()
            requests_items = requests_response.get('Items', [])
            total_requests = len(requests_items)
            fulfilled_requests = sum(1 for r in requests_items if r.get('status') == 'fulfilled')
            active_requests = sum(1 for r in requests_items if r.get('status') in ['Pending', 'partial'])

            # Get inventory data
            inventory = get_inventory()
            total_units = sum(data['units'] for data in inventory.values())

            # Critical blood groups (less than 20 units)
            critical_groups = [bg for bg, data in inventory.items() if data['units'] < 20]

            # For now, assume total_requestors equals total_requests (simplified)
            total_requestors = total_requests

            return {
                'total_donors': total_donors,
                'total_requestors': total_requestors,
                'total_requests': total_requests,
                'active_requests': active_requests,
                'fulfilled_requests': fulfilled_requests,
                'total_units': total_units,
                'critical_groups': critical_groups,
                'inventory': inventory
            }
        except Exception as e:
            print(f"AWS Error in get_statistics: {e}")
            # Fall back to default values
            return {
                'total_donors': 0,
                'total_requestors': 0,
                'total_requests': 0,
                'active_requests': 0,
                'fulfilled_requests': 0,
                'total_units': 0,
                'critical_groups': [],
                'inventory': blood_inventory.copy()
            }
    else:
        # Local statistics
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
            'inventory': blood_inventory.copy()
        }

# ============== ROUTES ==============

@app.route('/')
def home():
    """Home page"""
    stats = get_statistics()
    recent_requests = sorted(
        get_all_requests(),
        key=lambda x: (x.get('created_at') or x.get('requested_at') or '', ''),
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
            'blood_group': request.form['blood_group'],
            'health_condition': request.form['health_condition'],
            'last_donated': request.form['last_donated'],
            'created_at': str(datetime.now())
        }

        save_donor(donor_data)

        flash("Donor registered successfully", "success")
        return redirect(url_for('donor_dashboard'))

    return render_template('donor_register.html')

@app.route('/donor/dashboard')
def donor_dashboard():
    """Donor dashboard"""
    return render_template('donor_dashboard.html')

# ============== REQUESTOR ROUTES ==============

@app.route('/requestor/register')
def requestor_register():
    """Requestor registration"""
    return render_template('requestor_register.html')

@app.route('/requestor/dashboard')
def requestor_dashboard():
    """Requestor dashboard"""
    inventory = get_inventory()
    return render_template('requestor_dashboard.html', inventory=inventory)

@app.route('/request/blood', methods=['GET', 'POST'])
def request_blood():
    """Blood request form"""
    if request.method == 'POST':
        request_id = generate_request_id()

        request_data = {
            'request_id': request_id,
            'name': request.form['name'],
            'blood_group': request.form['blood_group'],
            'units': int(request.form['units']),
            'status': 'Pending',
            'requested_at': str(datetime.now())
        }

        save_request(request_data)

        flash("Blood request submitted", "success")
        return redirect(url_for('requestor_dashboard'))

    return render_template('request_blood.html')

# ============== SEARCH ROUTES ==============

@app.route('/search/donors')
def search_donors():
    """Search donors page"""
    donors = get_all_donors()
    return render_template('search_donors.html', donors=donors)

# ============== INVENTORY ROUTES ==============

@app.route('/blood-inventory')
def blood_inventory_view():
    """View blood inventory"""
    stats = get_statistics()
    return render_template('blood_inventory.html', inventory=stats['inventory'], stats=stats)

# ============== ADMIN ROUTES ==============

@app.route('/dashboard')
def admin_dashboard():
    """Admin dashboard"""
    stats = get_statistics()

    # Get all data for admin view
    all_donors = get_all_donors()
    all_requests = get_all_requests()
    inventory = get_inventory()

    return render_template(
        'admin_dashboard.html',
        donors=all_donors,
        requests=all_requests,
        inventory=inventory,
        stats=stats
    )

@app.route('/inventory/update', methods=['POST'])
def update_inventory():
    """Update inventory"""
    inventory_data = {
        'blood_group': request.form['blood_group'],
        'units': int(request.form['units'])
    }

    save_inventory_item(inventory_data)

    flash("Inventory updated successfully", "success")
    return redirect(url_for('admin_dashboard'))

# ============== API ROUTES ==============

@app.route('/api/statistics')
def api_statistics():
    """API endpoint for statistics"""
    return jsonify(get_statistics())

@app.route('/api/donors')
def api_donors():
    """API endpoint for donors"""
    return jsonify(get_all_donors())

@app.route('/api/requests')
def api_requests():
    """API endpoint for requests"""
    return jsonify(get_all_requests())
@app.route('/about')
def about():
    return render_template('about.html')
# ============== RUN APPLICATION ==============

if __name__ == '__main__':
    print(f"BloodSync starting in {'AWS' if USE_AWS else 'Local'} mode")
    if USE_AWS and not AWS_CONFIGURED:
        print("Warning: AWS mode requested but not configured. Using local mode.")
    app.run(host='0.0.0.0', port=5000, debug=True)
