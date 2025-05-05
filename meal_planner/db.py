from pathlib import Path

import fastlite as fl

DB_NAME = "meal_planner.db"
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / DB_NAME


def get_initialized_db(db_path_override: Path | None = None) -> fl.Database:
    """Get a database connection.

    Ensures that the database has been initialized with `recipes` table.

    Args:
        db_path_override: If provided, use this path instead of the default.
    """
    db_conn = fl.database(db_path_override if db_path_override else DB_PATH)

    db_conn.conn.execute(
        """CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            ingredients TEXT NOT NULL,
            instructions TEXT NOT NULL
        );"""
    )

    return db_conn
