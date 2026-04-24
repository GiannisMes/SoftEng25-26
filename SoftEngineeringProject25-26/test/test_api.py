import sys
import os
import io
import pytest
from flask import Flask
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# --- FIX: Προσθήκη του root φακέλου στο path ---
# Αυτό επιτρέπει στο test να βρει το 'api' και το 'backend'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import του Blueprint αφού φτιάξαμε το path
from api.routes import api_bp

@pytest.fixture
def client():
    app = Flask(__name__)
    # Register the blueprint to the test app
    app.register_blueprint(api_bp) 
    app.config['TESTING'] = True
    
    with app.test_client() as client:
        yield client

# ---------------- Admin endpoints tests ----------------

def test_healthcheck_success(client):
    with patch('api.routes.get_health_stats') as mock_stats:
        mock_stats.return_value = ({
            'total': 100, 
            'online': 80, 
            'offline': 20
        }, None) # Tuple return (stats, error)
        
        response = client.get('/api/admin/healthcheck')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == "OK"
        assert data['n_charge_points'] == 100

def test_healthcheck_db_failure(client):
    with patch('api.routes.get_health_stats') as mock_stats:
        mock_stats.return_value = (None, "Connection Failed")  
        response = client.get('/api/admin/healthcheck')
        
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

def test_reset_points_success(client):
    with patch('api.routes.reset_all_points') as mock_reset:
        mock_reset.return_value = (True, None)
        response = client.post('/api/admin/resetpoints')
        assert response.status_code == 200

def test_reset_points_failure(client):
    with patch('api.routes.reset_all_points') as mock_reset:
        mock_reset.return_value = (False, 'Some error')
        response = client.post('/api/admin/resetpoints')
        assert response.status_code == 400
        assert b'Reset failed' in response.data or 'Reset failed' in response.get_json().get('error', '')

def test_add_points_success(client):
    with patch('api.routes.add_points_from_csv') as mock_add:
        mock_add.return_value = (True, None, 5)
        
        data = {
            'file': (io.BytesIO(b"id,status\n1,online"), 'points.csv')
        }
        
        response = client.post(
            '/api/admin/addpoints', 
            data=data, 
            content_type='multipart/form-data'
        )
        
        assert response.status_code == 200
        assert response.get_json()['status'] == 'OK'

def test_add_points_no_file(client):
    response = client.post('/api/admin/addpoints')
    assert response.status_code == 400
    # Marshmallow/Flask error format check
    assert b'No file part' in response.data or 'No file part' in response.get_json().get('error', '')

# ---------------- User/Data endpoints tests ----------------

def test_get_points_success(client):
    with patch('api.routes.fetch_all_points') as mock_fetch:
        mock_fetch.return_value = [
            {"provider_name": "EV_Provider", "point_id": "P01", "lon": "23.7", "lat": "37.9", "status": "available", "cap": 50}
        ]
        response = client.get('/api/points')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        if len(data) > 0:
            assert data[0]['pointid'] == "P01" # Check schema mapping

def test_get_point_details_success(client):
    with patch('api.routes.fetch_point_by_id') as mock_fetch:
        mock_fetch.return_value = {
            "point_id": "42",                  
            "lon": "23.7275",                
            "lat": "37.9838",                
            "status": "available",           
            "cap": 22,                       
            "reservation_end_time": None,   
            "kwh_price": 0.35,
            "provider_name": "TestProvider",
            "holder_username": None
        }
        
        response = client.get('/api/point/42')
        data = response.get_json()
        
        assert response.status_code == 200
        assert data['pointid'] == "42"
        assert data['status'] == "available"

def test_get_point_details_not_found(client):
    with patch('api.routes.fetch_point_by_id') as mock_fetch:
        mock_fetch.return_value = None
        response = client.get('/api/point/999')
        assert response.status_code == 404

def test_reserve_point_success(client):
    future_time = datetime.now() + timedelta(minutes=30)
    
    with patch('api.routes.update_point_reservation') as mock_update:
        mock_update.return_value = (future_time, "reserved")
        
        # Must send username in JSON
        response = client.post('/api/reserve/42/45', json={"username": "user1"})
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['pointid'] == 42
        assert data['status'] == "reserved"

def test_reserve_point_not_available(client):
    with patch('api.routes.update_point_reservation') as mock_update:
        mock_update.return_value = (None, "not_available")
        
        response = client.post('/api/reserve/42', json={"username": "user1"}) 
        assert response.status_code == 400

# ---------------- Session tests ----------------

def test_new_session_success(client):
    session_payload = {
        "id": "42",                         # ΑΛΛΑΓΗ 1: Το schema περιμένει "id" (λόγω data_key="id")
        "starttime": "2026-01-26T10:00:00", # ΑΛΛΑΓΗ 2: ISO format (με T και δευτερόλεπτα)
        "endtime": "2026-01-26T11:00:00",   # ΑΛΛΑΓΗ 3: ISO format
        "startsoc": 20,
        "endsoc": 80,
        "totalkwh": 45.5,
        "kwhprice": 0.35,
        "amount": 15.92,
        "username": "user1"
    }
    
    with patch('api.routes.create_new_session') as mock_create:
        # success, error, client_secret, amount
        mock_create.return_value = (True, None, "secret_123", 15.92)
        
        response = client.post('/api/newsession', json=session_payload)
        
        # Αν αποτύχει πάλι, τυπώνουμε το error για να δούμε τι φταίει
        if response.status_code != 200:
            print(f"\nDEBUG ERROR: {response.get_json()}")

        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'success'
        assert data['stripe_client_secret'] == 'secret_123'

def test_new_session_validation_error(client):
    incomplete_payload = {
        "pointid": "42",
        "endtime": "2026-01-26 11:00"
    }
    response = client.post('/api/newsession', json=incomplete_payload)
    assert response.status_code == 400

def test_get_sessions_success(client):
    with patch('api.routes.fetch_session_history') as mock_fetch:
        mock_fetch.return_value = ([{
            "pointid": 42,
            "start_time": datetime(2026, 1, 26, 10, 0),
            "end_time": datetime(2026, 1, 26, 11, 0),
            "total_kwh": 15.5,
            "session_kwh_price": 0.30,
            "amount": 5.0
        }], None)
        
        response = client.get('/api/sessions/42/20260101/20260126')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data[0]['id'] == 42 # Schema maps pointid -> id
        # Check starttime format matches schema output (ISO or formatted)
        assert "2026-01-26" in data[0]['starttime']

def test_update_point_success(client):
    with patch('api.routes.update_point_data') as mock_update:
        mock_update.return_value = ({
            "point_id": "42",
            "status": "charging",
            "kwh_price": 0.45,
            "lon": "23.5",
            "lat": "38.0",
            "provider_name": "Test",
            "cap": 22
        }, None)
        
        payload = {"status": "charging", "kwhprice": 0.45}
        response = client.post('/api/updpoint/42', json=payload)
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['pointid'] == "42"
        assert data['status'] == "charging"

def test_get_point_status_history_success(client):
    with patch('api.routes.fetch_status_history') as mock_fetch:    
        mock_fetch.return_value = ([{
            "timeref": datetime(2026, 1, 26, 10, 0),
            "old_state": "available",
            "new_state": "charging"
        }], None)
        
        response = client.get('/api/pointstatus/42/20260101/20260126')
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert data[0]['old_state'] == "available"
        assert data[0]['new_state'] == "charging"