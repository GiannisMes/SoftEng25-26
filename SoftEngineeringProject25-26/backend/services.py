#sql queries and business rules
import csv
import io
import os
import json
from .database import get_db_connection
from datetime import datetime, timedelta
import random

# SIMULATE PAYMENT API WITH STRIPE 
import stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

# User Account

def authenticate_or_register(username, password):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        account = cursor.fetchone()

        if account:
            if account['password'] == password:
                role = 'admin' if account['is_admin'] else ('member' if account['has_subscription'] else 'user')
                return True, {"username": account['username'], "role": role}, None
            return False, None, "Wrong password"
        
        # automatically assigns an email
        email = f"{username}@test.com"
        cursor.execute(
            "INSERT INTO users (username, password, email, is_admin, has_subscription, created_at) VALUES (%s, %s, %s, 0, 0, NOW())",
            (username, password, email)
        )
        conn.commit()
        return True, {"username": username, "role": "user"}, None

    except Exception as e:
        return False, None, str(e)
    finally:
        conn.close()

def start_upgrade_process(username):
    try:
        amount = 1000 
        intent = stripe.PaymentIntent.create(
        amount=amount,
        currency='eur',
        metadata={
            'username': username
        }
    )
        
        return True, intent.client_secret, None
    except Exception as e:
        return False, None, str(e)

def update_subscription(username):
    conn = get_db_connection() 
    cursor = conn.cursor()
    try:
        query = "UPDATE users SET has_subscription = TRUE WHERE username = %s"
        cursor.execute(query, (username,))
        conn.commit()
        
        if cursor.rowcount == 0:
            return False, f"User '{username}' not found."
        
        return True, None
    except Exception as e:
        return False, str(e)
    finally:
        cursor.close()
        conn.close()

# --- Admin Services ---

# USING cursor.execute for parametrized queries to prevent SQL injections

def get_health_stats():
    conn = get_db_connection()
    if not conn: 
        return None, "Connection Failed"
    
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COUNT(*) as count FROM points")
        total = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM points WHERE status = 'offline'")
        offline = cursor.fetchone()['count']
        stats = {
            "total": total,
            "online": total - offline,
            "offline": offline
        }
        return stats, None
    except Exception as e:
        return None, str(e)
    finally:
        cursor.close()
        conn.close()

# --- Point Services ---

# Helper function to validate status

def validate_and_normalize_status(raw_status):
    """
    returns status if valid, 
    else returns offline.
    """
    ALLOWED_STATUSES = {'available', 'charging', 'reserved', 'malfunction', 'offline'}

    if not raw_status:
        return 'offline'
        
    normalized = str(raw_status).strip().lower()
    
    if normalized in ALLOWED_STATUSES:
        return normalized
    return None 

# Helper function to parse endpoints

def map_to_point_tuple(data_dict):
    """Turn a dictionary entry (json or csv) to tuple value for sql database"""
        
    # handle nested data
    stations = data_dict.get('stations', [])
    if stations and isinstance(stations, list):
        outlets = stations[0].get('outlets', [])
        kilowatts = outlets[0].get('kilowatts', 0) if outlets else 0
        raw_status = outlets[0].get('status', 'offline') if outlets else 'offline'
    else:
        # if from a 'flat' csv:
        kilowatts = data_dict.get('kilowatts', 0)
        raw_status = data_dict.get('status', 'UNKNOWN')
        
    status = validate_and_normalize_status(raw_status)
    if status is None:
        status = 'offline'

    return (
        data_dict.get('id'),                # point_id
        data_dict.get('name'),              # provider_name
        data_dict.get('longitude'),
        data_dict.get('latitude'),
        status,
        kilowatts,
        data_dict.get('kwh_price', 0.35),   # Default τιμή αν λείπει
        data_dict.get('address')            # state_or_province/address
    )

# Define the global hardwired path as requested by the documentation
JSON_DATA_PATH = "database/parts1234.json" 

def reset_all_points():
    if not os.path.exists(JSON_DATA_PATH):
        return False, f"JSON file not found at {JSON_DATA_PATH}"

    conn = get_db_connection()
    if not conn: 
        return None, "Connection Failed"
    
    cursor = conn.cursor()
    with open(JSON_DATA_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Use foreign keys to clear columns properly 
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
        cursor.execute("TRUNCATE TABLE sessions")
        cursor.execute("TRUNCATE TABLE point_changes")
        cursor.execute("TRUNCATE TABLE points")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")

    query = """
        INSERT INTO points
        (point_id, provider_name, lon, lat, status, cap, reservation_end_time, kwh_price, state_or_province, holder_username)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    for item in data:
        try:
            point_id = item.get('id')
            provider_name = item.get('name')
            lon = item.get('longitude')
            lat = item.get('latitude')
            address = item.get('address')

            stations = item.get('stations') or []
            first_station = stations[0] if stations else {}
            outlets = first_station.get('outlets') if first_station else []
            outlet = outlets[0] if outlets else {}
            
            raw_status = (outlet.get('status') or '').lower()
            valid_statuses = ['available', 'charging', 'reserved', 'malfunction', 'offline']
            status = raw_status if raw_status in valid_statuses else 'available'

            raw_kw = outlet.get('kilowatts')
            if raw_kw is not None and raw_kw > 0:
                    cap = raw_kw
            else:
                cap = 11
            default_kwh_price = 0.4

            cursor.execute(
                query,
                (point_id, provider_name, lon, lat, status, cap, None, default_kwh_price, address, None)
            )
        except Exception as e:
            print(f"Skipping item due to error: {e}")

    conn.commit()
    conn.close()
    return True, None
        
def add_points_from_csv(file_stream):
    if not file_stream.filename.endswith('.csv'):
        return False, "Invalid file type", 0
    
    conn = get_db_connection()
    if not conn: return None, "Connection Failed"
    
    cursor = conn.cursor()
    try:
        stream = io.StringIO(file_stream.read().decode("UTF8"), newline=None)
        csv_input = csv.DictReader(stream) # use headers as keys

        points_to_add = [map_to_point_tuple(row) for row in csv_input]

        if not points_to_add:
            return False, "No valid data found in CSV", 0

        sql = """INSERT INTO points 
                 (point_id, provider_name, lon, lat, status, cap, kwh_price, state_or_province) 
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
        
        cursor.executemany(sql, points_to_add)
        conn.commit()
        return True, None, len(points_to_add)
        
    except Exception as e:
        return False, f"CSV Import Error: {str(e)}", 0
    finally:
        conn.close()
        

def fetch_all_points(status_filter=None):
    conn = get_db_connection()
    if not conn:
        return None, "Connection Failed"
    
    cursor = conn.cursor(dictionary=True)
    try:
        query = "SELECT * FROM points"
        params = []
        if status_filter:
            query += " WHERE status = %s"
            params.append(status_filter)
        cursor.execute(query, params)
        return cursor.fetchall()
    finally:
        conn.close()

def fetch_point_by_id(point_id):
    conn = get_db_connection()
    if not conn: 
        return None, "Connection Failed."
    
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM points WHERE point_id = %s", (point_id,))
        return cursor.fetchone()
    finally:
        conn.close()
        
def update_point_data(point_id, new_status=None, new_price=None):
    conn = get_db_connection()
    if not conn:
        return None, "Connection Failed"
    
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Check if point exists
        cursor.execute("SELECT * FROM points WHERE point_id = %s", (point_id,))
        point = cursor.fetchone()
        if not point:
            return None, "Point not found"

        # 2. Apply updates selectively
        if new_status:
            cursor.execute("UPDATE points SET status = %s WHERE point_id = %s", (new_status, point_id))
        
        if new_price is not None:
            cursor.execute("UPDATE points SET kwh_price = %s WHERE point_id = %s", (new_price, point_id))
        
        conn.commit()

        # 3. Fetch the updated version to return to the user
        cursor.execute("SELECT * FROM points WHERE point_id = %s", (point_id,))
        return cursor.fetchone(), None
    finally:
        conn.close()
        
# PAYMENT API FUNCTIONS

def check_user_subscription(username):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT has_subscription FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    conn.close()
    return user['has_subscription'] if user else False

def create_payment_intent(amount_cents, metadata):
    """
    Creates a PaymentIntent in Stripe.
    amount_euro: float (eg. 5.0)
    metadata: dict with extra information
    """
    try:
        
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='eur',
            metadata=metadata   # point_id, reservation fee
        )
        return intent.client_secret, None
    except Exception as e:
        return None, str(e)

def update_point_reservation(point_id, minutes, username):
    conn = get_db_connection()
    if not conn:
        return None, "Connection Failed"
    
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT status FROM points WHERE point_id = %s", (point_id,))
        point = cursor.fetchone()
        
        if not point:
            return None, "not_found"
        
        if point['status'] != 'available':
            return None, "not_available"

        end_time = datetime.now() + timedelta(minutes=minutes)        
        cursor.execute(
            "UPDATE points SET status = 'reserved', reservation_end_time = %s, holder_username = %s WHERE point_id = %s", 
            (end_time, username, point_id)
        )
        conn.commit()
        return end_time, "reserved"
    finally:
        conn.close()

def process_cancel_reservation(point_id, username, role):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT holder_username FROM points WHERE point_id=%s", (point_id,))
        pt = cursor.fetchone()

        if not pt:
            return False, "Point not found"

        if pt['holder_username'] == username or role == 'admin':
            cursor.execute("""
                UPDATE points 
                SET status='available', holder_username=NULL, reservation_end_time=NULL 
                WHERE point_id=%s
            """, (point_id,))
            conn.commit()
            return True, None
        
        return False, "Permission Denied: Not your reservation."

    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def check_for_expired_reservations():
    conn = get_db_connection()
    if not conn:
        return

    cursor = conn.cursor(dictionary=True)
    try:
        now = datetime.now().isoformat()

        # Find points that are reserved but the time has run out
        cursor.execute("""
            UPDATE points 
            SET status = 'available', 
                holder_username = NULL, 
                reservation_end_time = NULL 
            WHERE status = 'reserved' 
            AND reservation_end_time < %s
        """, (now,))

        conn.commit()
        if cursor.rowcount > 0:
            print(f"Cleaned up {cursor.rowcount} expired reservations.")
            
    except Exception as e:
        print(f"Error cleaning reservations: {e}")
    finally:
        conn.close()

def process_start_charging(point_id, username):
    conn = get_db_connection()
    if not conn:
        return False, "Connection Failed"
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Check if the point is either available or already reserved by this user
        cursor.execute("SELECT status, holder_username, kwh_price FROM points WHERE point_id = %s", (point_id,))
        point = cursor.fetchone()
        
        if not point:
            return False, "Point not found"

        can_charge = (point['status'] == 'available') or \
                     (point['status'] == 'reserved' and point['holder_username'] == username)

        if not can_charge:
            return False, "Point is occupied or reserved by someone else"

        # Update to charging status and ensure holder_username is set to the current user
        cursor.execute("""
            UPDATE points 
            SET status = 'charging', holder_username = %s, reservation_end_time = NULL 
            WHERE point_id = %s
        """, (username, point_id))

        # Fill partially the session information
        start_time = datetime.now()
        session_kwh_price = point['kwh_price']
        cursor.execute("SELECT user_id FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        user_id = user['user_id']
        start_soc = random.choice([10, 15, 20, 25, 30, 35, 40, 45, 50])
        cursor.execute("""
            INSERT INTO sessions (point_id, user_id, start_time, start_soc, session_kwh_price, state)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (point_id, user_id, start_time, start_soc, session_kwh_price, 'active'))
        
        conn.commit()
        return True, None
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def process_stop_charging(point_id, username, role):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT status, holder_username, kwh_price, cap FROM points WHERE point_id=%s", (point_id,))
        point = cursor.fetchone()

        if not point or point['status'] != 'charging':
            return False, "Point is not currently charging", 0

        # Only the user or the admin can stop a charging session
        if point['holder_username'] == username or role == 'admin':

            # Find the session that is corresponding to the charging point
            cursor.execute("""
                SELECT session_id, start_time, start_soc, state 
                FROM sessions 
                WHERE point_id = %s AND (state = 'active' OR state = 'pending')
            """, (point_id,))
            session = cursor.fetchone()

            if not session:
                return False, "No active session found for this point", 0
            
            if session['state'] == 'active':
                # Calculate the cost for the charging session
                end_time = datetime.now()
                duration_hours = (end_time - session['start_time']).total_seconds() / 3600
                kwh_delivered = round(duration_hours * point['cap'], 2)
                total_cost = round(kwh_delivered * (point['kwh_price'] or 0.4), 2)
                # The cost is at minimum a half euro
                if total_cost < 0.5:
                    total_cost = 0.5
                battery_capacity = 60
                soc_added = (kwh_delivered / battery_capacity) * 100
                end_soc = min(100, round(session['start_soc'] + soc_added))

                # Complete inserting the session information
                cursor.execute("""
                    UPDATE sessions 
                    SET end_time = %s, end_soc = %s, total_kwh = %s, amount = %s, state = 'completed'
                    WHERE session_id = %s
                """, (end_time, end_soc, kwh_delivered, total_cost, session['session_id']))
            else:
                # Update the session state to completed and set cost to 0
                total_cost = 0
                cursor.execute("""UPDATE sessions SET state = 'completed' WHERE session_id = %s""", (session['session_id'],))
            
            # Make the point available again
            cursor.execute("""
                UPDATE points 
                SET status='available', holder_username=NULL, reservation_end_time=NULL 
                WHERE point_id=%s
            """, (point_id,))
            
            conn.commit()
            return True, None, total_cost
        
        return False, "Permission Denied", 0
    except Exception as e:
        return False, str(e), 0
    finally:
        conn.close()

# --- Session Services ---
def create_new_session(data):
    conn = get_db_connection()
    if not conn:
        return False, "Connection Failed", None, 0
    
    cursor = conn.cursor(dictionary=True)
    try:

        pid = data.get('point_id') or data.get('pointid')
        start_time = data.get('start_time')

        # Find the kwh_price of the session
        cursor.execute("""SELECT kwh_price, cap FROM points WHERE point_id = %s""", (pid,))
        point = cursor.fetchone()
        if not point:
            return False, "Point is not found", None, 0
        session_kwh_price = point['kwh_price']

        # If start_soc is given, use that, otherwise use a random one
        start_soc = data.get('start_soc')
        if start_soc is None:
            start_soc = random.choice([10, 15, 20, 25, 30, 35, 40, 45, 50])

        end_soc = data.get('end_soc')
        if end_soc <= start_soc:
            return False, "Target charging percent must be more than starting percent", None, 0
        
        # If CLI gives total_kwh and amount, use those
        if data.get('total_kwh') and data.get('amount'):
            total_kwh = data.get('total_kwh')
            amount = data.get('amount')
            
            # If CLI provided end_time, use it. Else calculate duration.
            if data.get('end_time'):
                end_time = data.get('end_time')
            else:
                # Fallback calculation if only amount was given
                hours = total_kwh / point['cap']
                minutes = hours * 60
                end_time = start_time + timedelta(minutes=minutes)
        else:
            soc_added = end_soc - start_soc
            battery_capacity = 60
            total_kwh = (soc_added * battery_capacity) / 100
        
            amount = total_kwh * session_kwh_price
            hours = total_kwh/point['cap']
            minutes = hours * 60
            end_time = start_time + timedelta(minutes=minutes)
        
        # Stripe Integration
        amount_cents = int(amount * 100)
        client_secret = None

        if amount_cents > 0:
            client_secret, pay_error = create_payment_intent(
                amount_cents=amount_cents,
                metadata={
                    'pointid': pid,
                    'type': 'charging_session',
                    'username': data.get('username')
                }
            )
            if pay_error:
                return False, f"Stripe Error: {pay_error}", None, 0

        username = data.get('username')
        if not username:
             # If CLI didn't send a username, it is the admin
             username = 'admin'
        cursor.execute("SELECT user_id FROM users WHERE username = %s", (username,))
        user_row = cursor.fetchone()
        user_id = user_row['user_id']

        query = """INSERT INTO sessions (point_id, user_id, start_time, end_time, start_soc, 
                 end_soc, total_kwh, session_kwh_price, amount, state) 
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                 
        values = (pid, user_id, start_time, end_time, 
                  start_soc, end_soc, total_kwh, session_kwh_price, amount, 'pending')
        
        cursor.execute(query, values)

        # Lock the Charger
        cursor.execute("""
            UPDATE points 
            SET status = 'charging', 
                holder_username = %s 
            WHERE point_id = %s
        """, (username, pid))
        
        # Change the automatic point trigger so it shows the change in the future
        cursor.execute("""
            UPDATE point_changes 
            SET timeref = %s 
            WHERE point_id = %s 
            ORDER BY point_changes_id DESC 
            LIMIT 1
        """, (start_time, pid))

        # Put the point change for the end of the charging as well
        query_2 = """INSERT INTO point_changes (point_id, timeref, old_state, new_state) 
                        VALUES (%s, %s, %s, %s)"""
        
        values = (pid, end_time, 'charging', 'available')

        cursor.execute(query_2, values)

        conn.commit()
        return True, None, client_secret, amount
    
    except Exception as e:
        print(f"Database Error: {e}") 
        return False, str(e), None, 0
    finally:
        conn.close()

def check_for_expired_sessions():
    conn = get_db_connection()
    if not conn:
        return

    cursor = conn.cursor(dictionary=True)
    try:
        now = datetime.now().isoformat()

        # 1. Find sessions that are 'active' but should be completed already
        cursor.execute("""
            SELECT session_id, point_id 
            FROM sessions 
            WHERE state = 'active' AND end_time < %s
        """, (now,))
        
        expired_sessions = cursor.fetchall()

        if expired_sessions:
            print(f"Found {len(expired_sessions)} expired sessions. Cleaning up...")

            for session in expired_sessions:
                # Mark session as 'completed'
                cursor.execute("""
                    UPDATE sessions 
                    SET state = 'completed' 
                    WHERE session_id = %s
                """, (session['session_id'],))

                # Free up the charging point
                cursor.execute("""
                    UPDATE points 
                    SET status = 'available', holder_username = NULL 
                    WHERE point_id = %s
                """, (session['point_id'],))

            conn.commit()
            
    except Exception as e:
        print(f"Error processing expired sessions: {e}")
    finally:
        conn.close()

def activate_session_after_payment(point_id, username):
    conn = get_db_connection()
    if not conn:
        return False, "Database connection failed", None

    cursor = conn.cursor(dictionary=True)
    try:
        # Find the active session for the point
        cursor.execute("""
            SELECT session_id, end_time 
            FROM sessions 
            WHERE point_id = %s AND state = 'pending' 
            LIMIT 1
        """, (point_id,))
        
        session = cursor.fetchone()
        
        if not session:
            return False, "No pending session found. It may have expired.", None
        
        conn.commit()
        
        return True, "Session activated successfully", session['end_time']

    except Exception as e:
        print(f"Activation Error: {e}")
        return False, f"Server error: {str(e)}", None
    finally:
        conn.close()        

def fetch_session_history(point_id, from_date, to_date):
    conn = get_db_connection()
    if not conn:
        return None, "Connection Failed"
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Convert date strings to SQL format
        try:
            from_d = from_date.strftime("%Y-%m-%d %H:%M:%S")
            to_d = to_date.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None, "Invalid date format."
            
        query = "SELECT * FROM sessions WHERE point_id = %s AND start_time >= %s AND start_time <= %s ORDER BY start_time DESC"
        cursor.execute(query, (point_id, from_d, to_d))
        results = cursor.fetchall()
        return results, None
    
    except Exception as e:
        return None, str(e)
    finally:
        conn.close()
        
        
def fetch_status_history(point_id, from_date, to_date):
    """Retrieves the history of status changes for a specific point."""
    conn = get_db_connection()
    if not conn:
        return None, "Connection Failed"
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Convert the object to a string format the DB likes
        from_d = from_date.strftime("%Y-%m-%d %H:%M:%S")
        to_d = to_date.strftime("%Y-%m-%d %H:%M:%S")
        
        query = """SELECT timeref, old_state, new_state 
                   FROM point_changes 
                   WHERE point_id = %s AND timeref >= %s AND timeref <= %s 
                   ORDER BY timeref DESC"""
        
        cursor.execute(query, (point_id, from_d, to_d))
        results = cursor.fetchall()
        
        return results, None  
        
    except Exception as e:
        return None, str(e)
    finally:
        conn.close()
        
def delete_point_from_db(point_id):
    """Deletes point from database, allowed only for admin"""
    conn = get_db_connection()
    if not conn:
        return 0, "Connection Failed"
    
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM points WHERE point_id = %s", (point_id,))
        affected = cursor.rowcount
        conn.commit()
        return affected, None
    except Exception as e:
        return 0, str(e)
    finally:
        conn.close()
        
        