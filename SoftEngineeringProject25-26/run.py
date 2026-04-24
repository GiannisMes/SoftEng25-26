from backend import create_app
from backend.db_config import Config

# initialize or start the server application
app = create_app(Config) # This calls the function in __init__.py

if __name__ == '__main__':
    print("Starting server on port 9876...")
    # view all endpoints
    with app.app_context():
        print(app.url_map)
    app.run(host='127.0.0.1', port=9876, debug=True)
