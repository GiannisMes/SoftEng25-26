# database logic file 

import mysql.connector
from .db_config import db_config

def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except mysql.connector.Error as e:
        print(f"Error: Failed to connect to the database. Details: {e}") 
        return None
    
    