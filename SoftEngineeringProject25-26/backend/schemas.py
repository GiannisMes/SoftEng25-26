from marshmallow import Schema, fields, validate, post_load
from datetime import datetime

# --- POINT SCHEMA ---
class PointSchema(Schema):
    # 'attribute' links the JSON name to the Database column name
    pointid = fields.Str(attribute="point_id")
    providerName = fields.Str(attribute="provider_name", required=True)
    lon = fields.Str(required=True)
    lat = fields.Str(required=True)
    status = fields.Str(validate=validate.OneOf(["available", "charging", "reserved", "malfunction", "offline"]))
    cap = fields.Int()
    # format handles the strftime automatically
    reservationendtime = fields.DateTime(attribute="reservation_end_time", format='%Y-%m-%d %H:%M')
    kwhprice = fields.Float(attribute="kwh_price")
    holder = fields.Str(attribute="holder_username", allow_none=True)
    
class SessionSchema(Schema):
    pointid = fields.Int(data_key="id", attribute="pointid", required=True)    
    starttime = fields.DateTime(attribute="start_time", format='iso', required=True)
    endtime = fields.DateTime(attribute="end_time", format='iso', allow_none=True)
    startsoc = fields.Int(attribute="start_soc", load_default=0)
    endsoc = fields.Int(attribute="end_soc", load_default=0, allow_none = True)
    totalkwh = fields.Float(attribute="total_kwh", load_default=0.0)
    kwhprice = fields.Float(attribute="session_kwh_price", load_default=0.0)
    amount = fields.Float(load_default=0.0)
    username = fields.Str(load_only=True) 
    role = fields.Str(load_only=True)
    minutes = fields.Int(load_only=True)

# --- STATUS HISTORY SCHEMA ---
class StatusHistorySchema(Schema):
    timeref = fields.DateTime(format='%Y-%m-%d %H:%M')
    old_state = fields.Str()
    new_state = fields.Str()