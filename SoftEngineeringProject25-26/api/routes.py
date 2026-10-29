from flask import Blueprint, jsonify, request, Response, render_template
import os 
from backend.schemas import PointSchema, SessionSchema, StatusHistorySchema
from backend.services import (
    get_health_stats, reset_all_points, add_points_from_csv, fetch_all_points, 
    fetch_point_by_id, update_point_data, update_point_reservation, create_new_session, 
    fetch_session_history, fetch_status_history, delete_point_from_db, validate_and_normalize_status,
    create_payment_intent, check_user_subscription, process_cancel_reservation, authenticate_or_register,
    start_upgrade_process, update_subscription, process_start_charging, process_stop_charging,
    check_for_expired_sessions, check_for_expired_reservations, activate_session_after_payment
)
from backend.utils import support_csv_export, make_error_response
from datetime import datetime

# Initialize Blueprint
api_bp = Blueprint("api", __name__, template_folder = '../frontend')

# Initialize Schemas
point_schema = PointSchema()
points_schema = PointSchema(many=True)
session_schema = SessionSchema()
sessions_schema = SessionSchema(many=True)
history_schema = StatusHistorySchema(many=True)

@api_bp.route('/')
def home(): return render_template('index.html', maps_api_key=os.getenv('GOOGLE_MAPS_API_KEY', ''))

@api_bp.route('/login')
def login_page(): return render_template('login.html')

# --- AUTH --- 

@api_bp.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Missing username or password"}), 400

    success, user_data, error_msg = authenticate_or_register(username, password)

    if success:
        return jsonify({
            "status": "success", 
            "username": user_data['username'], 
            "role": user_data['role']
        }), 200
    
    return jsonify({"error": error_msg}), 401

@api_bp.route('/api/upgrade', methods=['POST'])
def api_upgrade():
    username = request.json.get('username')
    
    if not username:
        return jsonify({"error": "Username is required"}), 400
    
    success, client_secret, error_msg = start_upgrade_process(username)
    if success: 
        return jsonify({"status": "success", 
                        "stripe_client_secret": client_secret
        })

    return jsonify({"error": error_msg}), 500

@api_bp.route('/api/confirm-upgrade', methods=['POST'])
def confirm_upgrade():
    # frontend will call this only if stripe succeeds 
    username = request.json.get('username')

    success, error_msg = update_subscription(username) 
    if success:
        return jsonify({"status": "success"})
    return make_error_response(error_msg, 500)

# ---------------- Admin endpoints ---------------- 

@api_bp.route('/api/admin/healthcheck', methods=['GET'])
@support_csv_export
def healthcheck():
    stats, error = get_health_stats()
    if error:
        # decorator constructs an error log that contains this error string
        return make_error_response("Refused - Database connection failed", 400)  
    
    return {
        "status": "OK", 
        "dbconnection": "Connected", 
        "n_charge_points": stats['total'],
        "n_charge_points_online": stats['online'],
        "n_charge_points_offline": stats['offline']
    }, 200

# needs to load json file data
@api_bp.route('/api/admin/resetpoints', methods=['POST'])
@support_csv_export
def reset_points():
    success, error = reset_all_points()
    if success:
        return {"status": "OK"}, 200

    return {"error": f"Reset failed: {error}"}, 400

@api_bp.route('/api/admin/addpoints', methods=['POST'])
def add_points():
    if 'file' not in request.files:
        return make_error_response("No file part", 400)
    
    file = request.files['file']
    if file.filename == '':
        return make_error_response("No selected file", 400)

    success, error, count = add_points_from_csv(file)
    
    if success:
        return {"status": "OK", "points_added": count}, 200
    
    return make_error_response(f"Add points failed: {error}", 400)

# ---------------- User/Data endpoints ----------------

@api_bp.route('/api/points', methods=['GET'])
@support_csv_export
def get_points():
    # Check for points that should have reservations or sessions finished
    check_for_expired_reservations()
    check_for_expired_sessions()

    status_query = request.args.get('status')
 
    if status_query:
        normalized = validate_and_normalize_status(status_query)
        # return error log if user's status request not in enumeration
        if normalized is None:
            return make_error_response("Invalid status: '{status_query}", 401)
        status_query = normalized

    raw_points = fetch_all_points(status_query)
    
    limited_schema = PointSchema(many=True, only=(
        "providerName", "pointid", "lon", "lat", "status", "cap"
    ))
    
    result = points_schema.dump(raw_points)        
    return result, 200

@api_bp.route('/api/point/<int:point_id>', methods=['GET'])
def get_point_details(point_id):
    point = fetch_point_by_id(point_id)
    if not point:
        return make_error_response(f"Point with ID {point_id} not found", 404)
    
    detailed_schema = PointSchema(only=(
        "pointid", 
        "lon", 
        "lat", 
        "status", 
        "cap", 
        "reservationendtime", 
        "kwhprice",
        "holder",
        "providerName"
    ))
    
    return jsonify(detailed_schema.dump(point)), 200

@api_bp.route('/api/reserve/<int:point_id>', defaults={'minutes': 30}, methods=['POST'])
@api_bp.route('/api/reserve/<int:point_id>/<int:minutes>', methods=['POST'])
def reserve_point(point_id, minutes):
    minutes = min(minutes, 60)
    
    data = request.json or {}
    username = data.get('username')
    
    if not username:
        return make_error_response("Username is required for reservation", 400)
    
    new_time, status = update_point_reservation(point_id, minutes, username)
    
    if status == "not_found":
        return make_error_response(f"Point {point_id} not found", 404)
    
    if status == "not_available":
        return make_error_response("Point is not available for reservation", 400)
    
    return jsonify({
        "pointid": point_id, 
        "status": status, 
        "reservationendtime": new_time.strftime('%Y-%m-%d %H:%M') if new_time else "1970-01-01 00:00",
    }), 200

# CANCEL RESERVATION (Checks User) 
@api_bp.route('/api/reserve/cancel/<int:point_id>', methods=['POST'])
def cancel_reservation(point_id):
    data = request.json
    
    if not all(k in data for k in ('username', 'role')):
        return jsonify({"error": "Missing required fields"}), 400

    success, message = process_cancel_reservation(
        point_id, 
        data['username'], 
        data['role']
    )

    if success:
        return jsonify({"status": "success"}), 200
    else:
        return jsonify({"error": message}), 403

@api_bp.route('/api/newsession', methods=['POST'])
def new_session():
    json_data = request.get_json() 
    if not json_data:
        return make_error_response("No input data provided", 401)
    
    try:
        data = session_schema.load(json_data)
    except Exception as e:
        return make_error_response(str(e), 400)
    
    success, error, client_secret, amount = create_new_session(data)
    
    if error == "Connection Failed":
        return make_error_response("Database connection failed", 400)
    
    if not success:
        return make_error_response(error or "Internal Server Error", 500)
     
    return jsonify({
        "status": "success",
        "stripe_client_secret": client_secret,
        "amount": amount
    }), 200

@api_bp.route('/api/sessionpayment', methods=['POST'])
def confirm_session_payment():
    data = request.get_json()
    
    point_id = data.get('point_id') or data.get('id')
    username = data.get('username')

    if not point_id or not username:
        return make_error_response("Missing required data (point_id, username)", 400)

    success, message, end_time = activate_session_after_payment(point_id, username)

    if success:
        return jsonify({
            "status": "success", 
            "message": message,
            "end_time": end_time.isoformat() if end_time else None
        }), 200
    else:
        return make_error_response(message, 400)
    
@api_bp.route('/api/sessions/<int:point_id>/<string:from_date>/<string:to_date>', methods=['GET'])
@support_csv_export 
def get_sessions(point_id, from_date, to_date):
    if "-" in from_date:
            # Handle CLI format with dashes/spaces
            from_date = datetime.strptime(from_date, '%Y-%m-%d %H:%M:%S')
            to_date = datetime.strptime(to_date, '%Y-%m-%d %H:%M:%S')
    else:
        # Handle compact format YYYYMMDD
        from_date = datetime.strptime(from_date, '%Y%m%d')
        to_date = datetime.strptime(to_date, '%Y%m%d')

    raw_sessions, error = fetch_session_history(point_id, from_date, to_date)
    
    if error:
        if error == "Connection Failed":
            return make_error_response("Database connection failed", 400)
        return make_error_response(error, 400)

    result = sessions_schema.dump(raw_sessions)
    return result, 200
    
 
@api_bp.route('/api/updpoint/<int:point_id>', methods=['POST'])
def update_point(point_id):
    data = request.json or {}
    new_status = data.get('status')
    new_price = data.get('kwhprice')

    updated_row, error = update_point_data(point_id, new_status, new_price)

    if error == "Point not found":
        return make_error_response("Point not found", 404)
    if error == "Connection Failed":
        return make_error_response("Database connection failed", 400)

    point_schema = PointSchema(only=(
        "pointid", 
        "status", 
        "kwhprice"
    ))
    return jsonify(point_schema.dump(updated_row)), 200

@api_bp.route('/api/charge/start/<int:point_id>', methods=['POST'])
def start_charging(point_id):
    data = request.json
    username = data.get('username')

    # Update point status to charging
    success, error = process_start_charging(point_id, username)
    
    if not success:
        return make_error_response(error, 400)

    return jsonify({
        "status": "started",
        "start_time": datetime.now().isoformat()
    }), 200 

@api_bp.route('/api/charge/stop/<int:point_id>', methods=['POST'])
def stop_charging(point_id):
    data = request.json
    username = data.get('username')
    role = data.get('role')

    # Update point status back to available
    success, error, total_cost = process_stop_charging(point_id, username, role)

    if not success:
        return make_error_response(error, 403)
    
    amount_cents = int(round(total_cost * 100))
    client_secret = None
    if amount_cents > 0: 
        client_secret, error = create_payment_intent(
            amount_cents=amount_cents, 
            metadata={'point_id': point_id, 'type': 'reservation_fee'}
        )
        
        if error:
            return make_error_response(f"Payment Gateway Error: {error}", 500)

    return jsonify({
        "status": "stopped",
        "point_id": point_id,
        "kwh_delivered": 30,
        "total_cost": total_cost,
        "currency": "EUR",
        "client_secret": client_secret,
        "msg": "Charging session finalized successfully"
    }), 200

@api_bp.route('/api/pointstatus/<int:point_id>/<string:from_date>/<string:to_date>', methods=['GET'])
@support_csv_export
def get_point_status_history(point_id, from_date, to_date):
    try:
        if "-" in from_date:
            # Handle CLI format with dashes/spaces
            from_date = datetime.strptime(from_date, '%Y-%m-%d %H:%M:%S')
            to_date = datetime.strptime(to_date, '%Y-%m-%d %H:%M:%S')
        else:
            # Handle compact format YYYYMMDD
            from_date = datetime.strptime(from_date, '%Y%m%d')
            to_date = datetime.strptime(to_date, '%Y%m%d')
        # 1. Get raw data from service
        raw_changes, error = fetch_status_history(point_id, from_date, to_date)
        if error:
            status_code = 400 if "format" in error or "Connection" in error else 500
            return make_error_response(error, status_code)
            
        # 2. Format data through Schema
        result = history_schema.dump(raw_changes)

        # 3. Return JSON (decorater handles csv result)
        return result, 200
        
    except ValueError:
        return jsonify({"status": "failed", "error": "Invalid date format. Use YYYYMMDD"}), 400
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 500

@api_bp.route('/api/point/<int:point_id>', methods=['DELETE'])
def delete_point(point_id):
    affected_rows, error = delete_point_from_db(point_id)
    
    if error == "Connection Failed":
        return make_error_response("Database connection failed", 400)
    
    if affected_rows == 0:
        return make_error_response(f"Point {point_id} not found", 404)
        
    return jsonify({
        "status": "OK", 
        "point_id": point_id,
        "msg": "Point deleted successfully"
    }), 200
    