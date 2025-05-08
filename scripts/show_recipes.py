# scripts/show_recipes.py
import sqlite3
import os

# Use the same path as defined in deploy.py/environment variable
db_path = os.environ.get("MEAL_PLANNER_DB_PATH", "/data/meal_planner.db")


def query_db():
    if not os.path.exists(db_path):
        print(f"Database file not found at {db_path}")
        return

    print(f"Attempting to connect to {db_path}...")
    conn = None  # Initialize conn to None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        print("Executing SELECT * FROM recipes;")
        cursor.execute("SELECT * FROM recipes;")
        rows = cursor.fetchall()
        print(f"Found {len(rows)} rows:")
        for row in rows:
            print(row)
    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")


if __name__ == "__main__":
    query_db()
