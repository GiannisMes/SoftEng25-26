from flask import Flask, g
from flask_cors import CORS


# application object creation

def create_app(config_object):
    
    # creates the app instance
    app = Flask(__name__, template_folder='../frontend', instance_relative_config=True)
    
    # loads the app configuration
    app.config.from_object(config_object)
    
    # initializes the CORS extension which opens the door to the frontend
    CORS(app)
    
    # --- ΣΗΜΑΝΤΙΚΗ ΑΛΛΑΓΗ ---
    # Το import γίνεται ΕΔΩ (μέσα στη συνάρτηση), όχι στην αρχή του αρχείου.
    # Αυτό σπάει τον κυκλικό βρόχο (Circular Import).
    from api.routes import api_bp 
    app.register_blueprint(api_bp)

    # Tear down: Κλείνει τη σύνδεση στη βάση όταν τελειώνει το request
    @app.teardown_appcontext
    def close_db(error):
        db = getattr(g, 'db', None)
        if db is not None:
            db.close()

    return app