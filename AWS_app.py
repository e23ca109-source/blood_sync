from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import boto3
import random
from datetime import datetime
from decimal import Decimal

# ================= APP CONFIG =================
app = Flask(__name__)
app.secret_key = "bloodsync_secret_key"

# ================= AWS CONFIG =================
dynamodb = None
dynamodb_client = None

users_table = None
donors_table = None
requestors_table = None
requests_table = None
inventory_table = None
assignments_table = None
donations_table = None

def init_dynamodb():
    """Initialize DynamoDB resources after connection is established"""
    global dynamodb, dynamodb_client, users_table, donors_table, requestors_table, requests_table, inventory_table, assignments_table, donations_table
    
    dynamodb = boto3.resource('dynamodb', region_name='ap-south-1')
    dynamodb_client = boto3.client('dynamodb', region_name='ap-south-1')
    
    users_table = dynamodb.Table('BloodSync_Users')
    donors_table = dynamodb.Table('BloodSync_Donors')
    requestors_table = dynamodb.Table('BloodSync_Requestors')
    requests_table = dynamodb.Table('BloodSync_Requests')
    inventory_table = dynamodb.Table('BloodSync_Inventory')
    assignments_table = dynamodb.Table('BloodSync_Assignments')
    donations_table = dynamodb.Table('BloodSync_Donations')

# ================= TABLE INITIALIZATION =================
def initialize_tables():
    """Create DynamoDB tables if they don't exist and wait for them to be active"""
    import time
    
    try:
        client = boto3.client('dynamodb', region_name='ap-south-1')
    except Exception as e:
        print(f"Error connecting to AWS: {e}")
        print("Make sure your AWS credentials are configured correctly")
        return False
    
    try:
        existing_tables = client.list_tables()['TableNames']
    except Exception as e:
        print(f"Error listing tables: {e}")
        return False
    
    tables_to_create = {
        'BloodSync_Users': [
            {'AttributeName': 'user_id', 'KeyType': 'HASH'},
        ],
        'BloodSync_Donors': [
            {'AttributeName': 'donor_id', 'KeyType': 'HASH'},
        ],
        'BloodSync_Requestors': [
            {'AttributeName': 'requestor_id', 'KeyType': 'HASH'},
        ],
        'BloodSync_Requests': [
            {'AttributeName': 'request_id', 'KeyType': 'HASH'},
        ],
        'BloodSync_Inventory': [
            {'AttributeName': 'blood_group', 'KeyType': 'HASH'},
        ],
        'BloodSync_Assignments': [
            {'AttributeName': 'assignment_id', 'KeyType': 'HASH'},
        ],
        'BloodSync_Donations': [
            {'AttributeName': 'donation_id', 'KeyType': 'HASH'},
        ],
    }
    
    # Create missing tables
    print("Initializing DynamoDB tables...")
    for table_name, key_schema in tables_to_create.items():
        if table_name not in existing_tables:
            try:
                client.create_table(
                    TableName=table_name,
                    KeySchema=key_schema,
                    AttributeDefinitions=[
                        {'AttributeName': key_schema[0]['AttributeName'], 'AttributeType': 'S'}
                    ],
                    BillingMode='PAY_PER_REQUEST'
                )
                print(f"✓ Creating table: {table_name}")
            except client.exceptions.ResourceInUseException:
                print(f"✓ Table already exists: {table_name}")
            except Exception as e:
                print(f"✗ Error creating table {table_name}: {e}")
                return False
        else:
            print(f"✓ Table exists: {table_name}")
    
    # Wait for all tables to be active
    print("\nWaiting for tables to be active...")
    for table_name in tables_to_create.keys():
        try:
            waiter = client.get_waiter('table_exists')
            waiter.wait(
                TableName=table_name,
                WaiterConfig={'Delay': 1, 'MaxAttempts': 60}
            )
            print(f"✓ Table {table_name} is now active")
        except Exception as e:
            print(f"✗ Error waiting for table {table_name}: {e}")
            return False
    
    print("\n✓ All tables initialized successfully!\n")
    # Initialize table references after successful table creation
    init_dynamodb()
    return True

# ================= HELPERS =================
def ensure_tables_initialized():
    """Ensure tables are initialized before use"""
    if users_table is None or donors_table is None:
        raise RuntimeError("Database tables not initialized. Please restart the application.")

def generate_6_digit_id():
    return str(random.randint(100000, 999999))

# ================= BLOOD COMPATIBILITY =================
RECEIVE_COMPATIBILITY = {
    'A+': ['A+', 'A-', 'O+', 'O-'],
    'A-': ['A-', 'O-'],
    'B+': ['B+', 'B-', 'O+', 'O-'],
    'B-': ['B-', 'O-'],
    'AB+': ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'],
    'AB-': ['A-', 'B-', 'AB-', 'O-'],
    'O+': ['O+', 'O-'],
    'O-': ['O-']
}

# ================= INVENTORY =================
def update_inventory(blood_group, units, operation):
    ensure_tables_initialized()
    item = inventory_table.get_item(
        Key={'blood_group': blood_group}
    ).get('Item', {'units': Decimal(0)})

    current = int(item.get('units', 0))
    new_units = current + units if operation == 'add' else max(0, current - units)

    inventory_table.put_item(
        Item={
            'blood_group': blood_group,
            'units': Decimal(new_units)
        }
    )

# ================= DASHBOARD STATS =================
def get_statistics():
    try:
        ensure_tables_initialized()
        donors = donors_table.scan().get('Items', [])
        requests_data = requests_table.scan().get('Items', [])
        inventory = inventory_table.scan().get('Items', [])

        total_units = sum(int(i.get('units', 0)) for i in inventory)
        critical = [i['blood_group'] for i in inventory if int(i.get('units', 0)) < 20]

        return {
            'total_donors': len(donors),
            'total_requests': len(requests_data),
            'active_requests': sum(1 for r in requests_data if r.get('status') in ['pending', 'partial']),
            'fulfilled_requests': sum(1 for r in requests_data if r.get('status') == 'fulfilled'),
            'total_units': total_units,
            'critical_groups': critical,
            'inventory': inventory
        }
    except Exception as e:
        print(f"Error fetching statistics: {e}")
        return {
            'total_donors': 0,
            'total_requests': 0,
            'active_requests': 0,
            'fulfilled_requests': 0,
            'total_units': 0,
            'critical_groups': [],
            'inventory': []
        }

# ================= HOME =================
@app.route('/')
def home():
    stats = get_statistics()
    try:
        ensure_tables_initialized()
        recent = requests_table.scan().get('Items', [])[:5]
    except Exception as e:
        print(f"Error fetching recent requests: {e}")
        recent = []
    return render_template('index.html', stats=stats, recent_requests=recent)

# ================= AUTH =================
@app.route('/register', methods=['POST'])
def register():
    try:
        ensure_tables_initialized()
        users_table.put_item(
            Item={
                'user_id': generate_6_digit_id(),
                'name': request.form['name'],
                'email': request.form['email'],
                'password': request.form['password'],
                'role': request.form['role'],
                'created_at': str(datetime.now())
            }
        )
        flash("Registration successful", "success")
    except Exception as e:
        print(f"Error during registration: {e}")
        flash("Registration failed", "danger")
    return redirect(url_for('home'))

@app.route('/login', methods=['POST'])
def login():
    try:
        ensure_tables_initialized()
        users = users_table.scan().get('Items', [])
        for u in users:
            if u['email'] == request.form['email'] and u['password'] == request.form['password']:
                session['user'] = u
                return redirect(url_for(f"{u['role']}_dashboard"))
    except Exception as e:
        print(f"Error during login: {e}")
        flash("Login error", "danger")
        return redirect(url_for('home'))
    flash("Invalid login", "danger")
    return redirect(url_for('home'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# ================= DONOR =================
@app.route('/donor/register', methods=['GET', 'POST'])
def donor_register():
    if request.method == 'POST':
        try:
            ensure_tables_initialized()
            donor_id = generate_6_digit_id()
            donors_table.put_item(
                Item={
                    'donor_id': donor_id,
                    'name': request.form['name'],
                    'blood_group': request.form['blood_group'],
                    'health_condition': request.form['health_condition'],
                    'city': request.form['city'],
                    'available': True,
                    'status': 'active',
                    'last_donation': None,
                    'total_donations': 0,
                    'created_at': str(datetime.now())
                }
            )
            flash(f"Registered successfully. Donor ID: {donor_id}", "success")
            return redirect(url_for('donor_dashboard'))
        except Exception as e:
            print(f"Error registering donor: {e}")
            flash("Registration failed", "danger")
    return render_template('donor_register.html')

@app.route('/donor/dashboard')
def donor_dashboard():
    donors = []
    try:
        ensure_tables_initialized()
        donors = donors_table.scan().get('Items', [])
    except Exception as e:
        print(f"Error fetching donors: {e}")
    return render_template('donor_dashboard.html', donors=donors)

# ================= REQUESTOR =================
@app.route('/requestor/register', methods=['GET', 'POST'])
def requestor_register():
    if request.method == 'POST':
        try:
            ensure_tables_initialized()
            requestor_id = generate_6_digit_id()
            requestors_table.put_item(
                Item={
                    'requestor_id': requestor_id,
                    'name': request.form['name'],
                    'email': request.form['email'],
                    'created_at': str(datetime.now())
                }
            )
            flash(f"Requestor ID: {requestor_id}", "success")
            return redirect(url_for('requestor_dashboard'))
        except Exception as e:
            print(f"Error registering requestor: {e}")
            flash("Registration failed", "danger")
    return render_template('requestor_register.html')

@app.route('/requestor/dashboard')
def requestor_dashboard():
    inventory = []
    try:
        ensure_tables_initialized()
        inventory = inventory_table.scan().get('Items', [])
    except Exception as e:
        print(f"Error fetching inventory: {e}")
    return render_template('requestor_dashboard.html', inventory=inventory)

# ================= BLOOD REQUEST =================
@app.route('/request/blood', methods=['POST'])
def request_blood():
    try:
        ensure_tables_initialized()
        request_id = generate_6_digit_id()
        requests_table.put_item(
            Item={
                'request_id': request_id,
                'patient_name': request.form['patient_name'],
                'blood_group': request.form['blood_group'],
                'units_needed': int(request.form['units']),
                'fulfilled_units': 0,
                'status': 'pending',
                'requested_at': str(datetime.now())
            }
        )
        flash("Blood request submitted", "success")
    except Exception as e:
        print(f"Error submitting blood request: {e}")
        flash("Request failed", "danger")
    return redirect(url_for('requestor_dashboard'))

# ================= DONOR ACCEPT REQUEST =================
@app.route('/donor/accept/<donor_id>/<request_id>', methods=['POST'])
def donor_accept_request(donor_id, request_id):
    try:
        ensure_tables_initialized()
        assignments_table.put_item(
            Item={
                'assignment_id': generate_6_digit_id(),
                'donor_id': donor_id,
                'request_id': request_id,
                'units_offered': int(request.form['units']),
                'status': 'accepted',
                'accepted_at': str(datetime.now())
            }
        )
        flash("Request accepted", "success")
    except Exception as e:
        print(f"Error accepting request: {e}")
        flash("Accept failed", "danger")
    return redirect(url_for('donor_dashboard'))

# ================= CONFIRM DONATION =================
@app.route('/donor/confirm/<assignment_id>', methods=['POST'])
def donor_confirm(assignment_id):
    try:
        ensure_tables_initialized()
        assignment = assignments_table.get_item(
            Key={'assignment_id': assignment_id}
        ).get('Item')

        request_data = requests_table.get_item(
            Key={'request_id': assignment['request_id']}
        )['Item']

        units = assignment['units_offered']
        fulfilled = request_data['fulfilled_units'] + units
        status = 'fulfilled' if fulfilled >= request_data['units_needed'] else 'partial'

        requests_table.update_item(
            Key={'request_id': request_data['request_id']},
            UpdateExpression="SET fulfilled_units=:f, #s=:s",
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':f': fulfilled,
                ':s': status
            }
        )

        donations_table.put_item(
            Item={
                'donation_id': generate_6_digit_id(),
                'donor_id': assignment['donor_id'],
                'request_id': assignment['request_id'],
                'units': units,
                'created_at': str(datetime.now())
            }
        )

        flash("Donation confirmed", "success")
    except Exception as e:
        print(f"Error confirming donation: {e}")
        flash("Confirmation failed", "danger")
    return redirect(url_for('donor_dashboard'))

# ================= ADMIN =================
@app.route('/admin/dashboard')
def admin_dashboard():
    donors = []
    requests_data = []
    inventory = []
    try:
        ensure_tables_initialized()
        donors = donors_table.scan().get('Items', [])
        requests_data = requests_table.scan().get('Items', [])
        inventory = inventory_table.scan().get('Items', [])
    except Exception as e:
        print(f"Error fetching admin data: {e}")
    
    return render_template(
        'admin_dashboard.html',
        stats=get_statistics(),
        donors=donors,
        requests=requests_data,
        inventory=inventory
    )

@app.route('/inventory/update', methods=['POST'])
def inventory_update():
    try:
        ensure_tables_initialized()
        update_inventory(
            request.form['blood_group'],
            int(request.form['units']),
            'add'
        )
        flash("Inventory updated", "success")
    except Exception as e:
        print(f"Error updating inventory: {e}")
        flash("Update failed", "danger")
    return redirect(url_for('admin_dashboard'))

# ================= RUN =================
if __name__ == "__main__":
    initialize_tables()
    app.run(host="0.0.0.0", port=5000, debug=True)