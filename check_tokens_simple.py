import sqlite3

def check_tokens():
    try:
        conn = sqlite3.connect("boltzman_local.db")
        cursor = conn.cursor()
        cursor.execute("SELECT email, role, push_token FROM users WHERE push_token IS NOT NULL")
        rows = cursor.fetchall()
        print(f"--- Users with push tokens ({len(rows)}) ---")
        for row in rows:
            token_display = row[2][:20] + "..." if row[2] else "None"
            print(f"Email: {row[0]} | Role: {row[1]} | Token: {token_display}")
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_tokens()
