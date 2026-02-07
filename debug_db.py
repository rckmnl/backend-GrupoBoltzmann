import sqlite3
import os

def check_db():
    db_file = "boltzman_local.db"
    print(f"Checking {db_file}...")
    if not os.path.exists(db_file):
        print("File does not exist!")
        return
        
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        # List all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"Tables: {tables}")
        
        if ('users',) in tables:
            cursor.execute("SELECT email, role, push_token FROM users WHERE push_token IS NOT NULL")
            rows = cursor.fetchall()
            print(f"--- Users with push tokens ({len(rows)}) ---")
            for row in rows:
                token_display = row[2][:20] + "..." if row[2] else "None"
                print(f"Email: {row[0]} | Role: {row[1]} | Token: {token_display}")
        else:
            print("Table 'users' NOT FOUND in database!")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_db()
