import io
import csv
from functools import wraps
from flask import request, jsonify, Response
from datetime import datetime

def make_error_response(error_message, status_code, debug_info=""):
    error_log = {
        "call": request.url,                                   
        "timeref": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),   # IEEE 8601 convention
        "originator": request.remote_addr,                    
        "return_code": status_code,                          
        "error": error_message,                              
        "debuginfo": debug_info                              
    }
    return jsonify(error_log), status_code

def support_csv_export(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        data, status_code = f(*args, **kwargs)
        
        if status_code >= 400:
            msg = data.get('error') if isinstance(data, dict) else str(data)
            debug = data.get('debuginfo', "") if isinstance(data, dict) else ""
            return make_error_response(msg, status_code, debug)

        if request.args.get('format') == 'csv':
            if isinstance(data, list):
                output = io.StringIO()
                if len(data) > 0:
                    headers = data[0].keys()
                    writer = csv.DictWriter(output, fieldnames=headers)
                    writer.writeheader()
                    writer.writerows(data)
                return Response(output.getvalue(), mimetype='text/csv')
            else:
                return make_error_response("CSV format not supported for this resource", 400)

        return jsonify(data), status_code
    return decorated_function