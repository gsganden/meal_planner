# scripts/delete_recipes.py
import sqlite3
import os

# Use the same path as defined in deploy.py/environment variable
db_path = os.environ.get("MEAL_PLANNER_DB_PATH", "/data/meal_planner.db")


def delete_data():
    if not os.path.exists(db_path):
        print(f"Database file not found at {db_path}")
        return

    print(f"Attempting to connect to {db_path} to DELETE data...")
    conn = None  # Initialize conn to None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        print("Executing DELETE FROM recipes;")
        cursor.execute("DELETE FROM recipes;")
        conn.commit()  # Commit the changes
        print(f"Deleted {cursor.rowcount} rows from recipes table.")
    except sqlite3.Error as e:
        print(f"SQLite error during delete: {e}")
        if conn:
            conn.rollback()  # Rollback on error
    except Exception as e:
        print(f"An unexpected error occurred during delete: {e}")
        if conn:
            conn.rollback()  # Rollback on error
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")


if __name__ == "__main__":
    print("--- Running DELETE script --- ")
    delete_data()
