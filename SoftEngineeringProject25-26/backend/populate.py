import mysql.connector
import sys
from datetime import datetime
from .db_config import db_config
from .services import reset_all_points

def execute_sql_file(cursor, filename):
    print(f"--- Reading Schema from {filename} ---")
    with open(filename, 'r', encoding='utf-8') as f:
        sql = f.read()

    # 1. DROP TABLES FIRST (Clean Slate)
    # We do this manually to ensure foreign keys don't block us
    drops = [
        "DROP TRIGGER IF EXISTS point_update",
        "DROP TABLE IF EXISTS point_changes",
        "DROP TABLE IF EXISTS sessions",
        "DROP TABLE IF EXISTS subscriptions",
        "DROP TABLE IF EXISTS points",
        "DROP TABLE IF EXISTS users"
    ]
    for d in drops:
        try: cursor.execute(d)
        except: pass

    # 2. PARSE AND EXECUTE THE SQL FILE
    # This regex splits the file by ';' but respects the 'DELIMITER $$' blocks
    # It looks for "DELIMITER $$ ... $$ DELIMITER ;" OR standard statements ending in ;
    
    # Simple approach: Remove 'DELIMITER' lines and split by '$$' or ';'
    # But since your file uses both, we will use a robust splitter:
    
    statement = ""
    delimiter = ";"
    
    for line in sql.splitlines():
        # Handle Delimiter Change
        if line.strip().upper().startswith("DELIMITER"):
            delimiter = line.strip().split()[1]
            continue
            
        if not line.strip(): continue # Skip empty lines
        
        statement += line + "\n"
        
        # Check if statement ends with current delimiter
        if statement.strip().endswith(delimiter):
            # Clean up the statement
            final_sql = statement.strip()[:-len(delimiter)]
            
            if final_sql.strip():
                try:
                    cursor.execute(final_sql)
                except mysql.connector.Error as err:
                    print(f"Warning executing SQL: {err}")
                    print(f"Snippet: {final_sql[:50]}...")
            
            statement = ""

    print("Schema applied successfully.")

def get_db_initial_connection():
    initial_config = db_config.copy()
    initial_config.pop('database', None)
    try:
        return mysql.connector.connect(**initial_config)
    except mysql.connector.Error as err:
        print(f"Error connecting to DB: {err}")
        return None

def main():
    conn = get_db_initial_connection()
    if not conn: sys.exit(1)
    cursor = conn.cursor()

    print("--- 1. Resetting Schema ---")

    # Execute the test.sql file, which has the database schema
    execute_sql_file(cursor, 'database/test.sql')
        
    print("--- 2. Creating Default Admin User ---")
    # We need a user so sessions don't break later
    try:
        cursor.execute(
            "INSERT INTO users (username, password, email, is_admin, created_at) VALUES (%s, %s, %s, %s, %s)",
            ('admin', '1234', 'admin@test.com', True, datetime.now())
        )
    except mysql.connector.Error as err:
        print(f"User Error: {err}")

    conn.commit()
    cursor.close()
    conn.close()

    # 2. Insert points from JSON
    reset_all_points()
    print("\nDone! Database reset to starting state.")

if __name__ == '__main__':
    main()