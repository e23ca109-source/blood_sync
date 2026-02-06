from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import boto3
import random
from datetime import datetime
from decimal import Decimal
import logging
import sys

# ================= LOGGING SETUP =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/bloodsync.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ================= APP CONFIG =================
logger.info("========== BloodSync Application Starting ==========")
try:
    app = Flask(__name__)
    app.secret_key = "bloodsync_secret_key"
    logger.info("✓ Flask app initialized")
except Exception as e:
    logger.error(f"✗ Failed to initialize Flask app: {e}")
    sys.exit(1)

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
    
    logger.info("\n" + "="*60)
    logger.info("Initializing DynamoDB tables...")
    logger.info("="*60)
    
    try:
        logger.info("Connecting to AWS DynamoDB (ap-south-1)...")
        client = boto3.client('dynamodb', region_name='ap-south-1')
        # Test connection by listing tables
        tables = client.list_tables()
        logger.info(f"✓ AWS connection successful")
        logger.info(f"✓ Found {len(tables.get('TableNames', []))} existing tables")
    except Exception as e:
        logger.error(f"\n✗ AWS Connection Error:")
        logger.error(f"  {type(e).__name__}: {e}")
        logger.error(f"\n  This usually means:")
        logger.error(f"  - AWS credentials are not configured")
        logger.error(f"  - Wrong AWS region specified")
        logger.error(f"  - IAM permissions are insufficient")
        logger.error(f"\n  To fix, run: aws configure")
        return False
    
    try:
        existing_tables = client.list_tables()['TableNames']
    except Exception as e:
        logger.error(f"✗ Error listing existing tables: {e}")
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
    logger.info("\nCreating/verifying tables...")
    for table_name, key_schema in tables_to_create.items():
        if table_name not in existing_tables:
            try:
                logger.info(f"  Creating table: {table_name}")
                client.create_table(
                    TableName=table_name,
                    KeySchema=key_schema,
                    AttributeDefinitions=[
                        {'AttributeName': key_schema[0]['AttributeName'], 'AttributeType': 'S'}
                    ],
                    BillingMode='PAY_PER_REQUEST'
                )
                logger.info(f"  ✓ Table creation initiated: {table_name}")
            except client.exceptions.ResourceInUseException:
                logger.info(f"  ✓ Table already exists: {table_name}")
            except Exception as e:
                logger.error(f"  ✗ Error creating table {table_name}: {e}")
                return False
        else:
            logger.info(f"  ✓ Table exists: {table_name}")
    
    # Wait for all tables to be active
    logger.info("\nWaiting for tables to become active (max 60 seconds)...")
    for table_name in tables_to_create.keys():
        try:
            waiter = client.get_waiter('table_exists')
            waiter.wait(
                TableName=table_name,
                WaiterConfig={'Delay': 1, 'MaxAttempts': 60}
            )
            logger.info(f"  ✓ {table_name} is active")
        except Exception as e:
            logger.error(f"  ✗ Timeout waiting for {table_name}: {e}")
            return False
    
    logger.info("\n✓ All tables ready!")
    # Initialize table references after successful table creation
    init_dynamodb()
    logger.info("✓ Database references initialized")
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

# ================= ERROR HANDLERS =================
@app.errorhandler(404)
def page_not_found(error):
    logger.error(f"404 Error: {request.path} not found")
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(error):
    logger.error(f"500 Server Error: {error}")
    import traceback
    logger.error(traceback.format_exc())
    return render_template('500.html'), 500

@app.before_request
def log_request():
    logger.info(f"incoming request: {request.method} {request.path}")

# ================= HOME =================
@app.route('/health')
def health():
    """Health check endpoint"""
    try:
        ensure_tables_initialized()
        return jsonify({'status': 'healthy', 'message': 'Application is running'}), 200
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

@app.route('/debug')
def debug():
    """Debug endpoint to check app status"""
    import os
    debug_info = {
        'status': 'running',
        'tables_initialized': users_table is not None,
        'templates_path': app.template_folder,
        'templates_exist': os.path.exists(app.template_folder) if app.template_folder else False,
        'static_path': app.static_folder,
        'static_exists': os.path.exists(app.static_folder) if app.static_folder else False,
        'registered_routes': [str(rule) for rule in app.url_map.iter_rules()]
    }
    
    if app.template_folder:
        try:
            templates = os.listdir(app.template_folder)
            debug_info['templates_files'] = templates
        except Exception as e:
            debug_info['templates_error'] = str(e)
    
    return jsonify(debug_info), 200

@app.route('/test')
def test():
    """Simple test endpoint"""
    return jsonify({
        'message': 'Flask is working!',
        'tables_initialized': users_table is not None,
        'version': '1.0.0'
    }), 200

@app.route('/')
def home():
    try:
        logger.info("Loading home page...")
        stats = get_statistics()
        try:
            ensure_tables_initialized()
            recent = requests_table.scan().get('Items', [])[:5]
        except Exception as e:
            logger.warning(f"Could not fetch recent requests: {e}")
            recent = []
        logger.info(f"Home page stats: {stats}")
        logger.info("Rendering index.html")
        result = render_template('index.html', stats=stats, recent_requests=recent)
        logger.info("index.html rendered successfully")
        return result
    except Exception as e:
        logger.error(f"Error on home page: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return f"<h1>Error Loading Home Page</h1><pre>{str(e)}</pre>", 500

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
    logger.info("="*60)
    logger.info("BloodSync Application Starting...")
    logger.info("="*60)
    
    # Initialize tables
    if not initialize_tables():
        logger.error("\n" + "="*60)
        logger.error("✗ FATAL ERROR: Failed to initialize DynamoDB tables!")
        logger.error("✗ The application cannot start without database tables.")
        logger.error("="*60)
        logger.error("\nPlease check:")
        logger.error("1. AWS credentials are configured correctly")
        logger.error("2. You have permissions to create DynamoDB tables")
        logger.error("3. Your AWS account has DynamoDB access in ap-south-1 region")
        logger.error("\nTo configure AWS credentials, run:")
        logger.error("  aws configure")
        logger.error("\nLog file: /tmp/bloodsync.log")
        logger.error("="*60)
        sys.exit(1)
    
    logger.info("="*60)
    logger.info("✓ Application initialized successfully!")
    logger.info("✓ Starting Flask server on http://0.0.0.0:5000")
    logger.info("✓ Health check: http://YOUR_IP:5000/health")
    logger.info("✓ Debug info: http://YOUR_IP:5000/debug")
    logger.info("✓ Simple test: http://YOUR_IP:5000/test")
    logger.info("✓ Logs saved to: /tmp/bloodsync.log")
    logger.info("="*60 + "\n")
    
    # Check templates directory
    import os
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    logger.info(f"Template directory: {template_dir}")
    logger.info(f"Template directory exists: {os.path.exists(template_dir)}")
    if os.path.exists(template_dir):
        try:
            templates = os.listdir(template_dir)
            logger.info(f"Available templates: {templates}")
        except Exception as e:
            logger.error(f"Error listing templates: {e}")
    logger.info("="*60 + "\n")
    
    try:
        logger.info("Flask app is now running...")
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    except Exception as e:
        logger.error(f"\n✗ Error starting Flask app: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)