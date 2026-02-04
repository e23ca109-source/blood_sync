from flask import Flask, render_template, request, redirect, url_for, session, flash
import boto3
import uuid
import random
from datetime import datetime

app = Flask(__name__)
app.secret_key = "bloodsync_secret_key"

# ---------- AWS CONFIG ----------
dynamodb = boto3.resource(
    'dynamodb',
    region_name='ap-south-1'  # change if needed
)

users_table = dynamodb.Table('BloodSync_Users')
donors_table = dynamodb.Table('BloodSync_Donors')
requests_table = dynamodb.Table('BloodSync_Requests')
inventory_table = dynamodb.Table('BloodSync_Inventory')

# ---------- HELPERS ----------
def generate_6_digit_id():
    return str(random.randint(100000, 999999))

# ---------- ROUTES ----------
@app.route('/')
def home():
    return render_template('index.html')

# ---------- AUTH ----------
@app.route('/register', methods=['POST'])
def register():
    user_id = generate_6_digit_id()

    users_table.put_item(
        Item={
            'user_id': user_id,
            'name': request.form['name'],
            'email': request.form['email'],
            'password': request.form['password'],
            'role': request.form['role'],  # donor / requestor / admin
            'created_at': str(datetime.now())
        }
    )

    flash("Registration successful")
    return redirect(url_for('home'))

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']

    response = users_table.scan()
    for user in response['Items']:
        if user['email'] == email and user['password'] == password:
            session['user'] = user
            return redirect(url_for(f"{user['role']}_dashboard"))

    flash("Invalid credentials")
    return redirect(url_for('home'))

# ---------- DONOR ----------
@app.route('/donor/dashboard')
def donor_dashboard():
    return render_template('donor_dashboard.html')

@app.route('/donor/register', methods=['POST'])
def donor_register():
    donor_id = generate_6_digit_id()

    donors_table.put_item(
        Item={
            'donor_id': donor_id,
            'user_id': session['user']['user_id'],
            'blood_group': request.form['blood_group'],
            'health_condition': request.form['health_condition'],
            'last_donated': request.form['last_donated']
        }
    )

    flash("Donor registered successfully")
    return redirect(url_for('donor_dashboard'))

# ---------- REQUESTOR ----------
@app.route('/requestor/dashboard')
def requestor_dashboard():
    inventory = inventory_table.scan()['Items']
    return render_template('requestor_dashboard.html', inventory=inventory)

@app.route('/request/blood', methods=['POST'])
def request_blood():
    request_id = generate_6_digit_id()

    requests_table.put_item(
        Item={
            'request_id': request_id,
            'user_id': session['user']['user_id'],
            'blood_group': request.form['blood_group'],
            'units': int(request.form['units']),
            'status': 'Pending',
            'requested_at': str(datetime.now())
        }
    )

    flash("Blood request submitted")
    return redirect(url_for('requestor_dashboard'))

# ---------- ADMIN ----------
@app.route('/admin/dashboard')
def admin_dashboard():
    donors = donors_table.scan()['Items']
    requests_data = requests_table.scan()['Items']
    inventory = inventory_table.scan()['Items']

    return render_template(
        'admin_dashboard.html',
        donors=donors,
        requests=requests_data,
        inventory=inventory
    )

@app.route('/inventory/update', methods=['POST'])
def update_inventory():
    inventory_table.put_item(
        Item={
            'blood_group': request.form['blood_group'],
            'units': int(request.form['units'])
        }
    )
    flash("Inventory updated")
    return redirect(url_for('admin_dashboard'))

# ---------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# ---------- RUN ----------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
