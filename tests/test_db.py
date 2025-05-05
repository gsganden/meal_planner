import contextlib
import json
from pathlib import Path

import pytest

# Assuming get_db is accessible like this, adjust if needed
from meal_planner.db import get_initialized_db

TEST_DB_NAME = "test_recipes.db"


def test_get_db_creates_and_connects(tmp_path: Path):
    """Test that get_db creates the directory and file, and connects."""
    # Define a unique path within the temporary directory provided by pytest
    test_data_dir = tmp_path / "test_data"
    test_db_file = test_data_dir / TEST_DB_NAME

    # Ensure they don't exist beforehand (should be true for tmp_path)
    assert not test_data_dir.exists()
    assert not test_db_file.exists()

    # Call get_db with the override path
    db_conn = None
    try:
        db_conn = get_initialized_db(db_path_override=test_db_file)

        # Assertions
        assert db_conn is not None
        assert hasattr(db_conn, "conn")
        assert hasattr(db_conn, "t")
        assert test_data_dir.exists()
        assert test_db_file.exists()

        # Verify table exists by trying to access it
        try:
            recipes_table = db_conn.t.recipes  # type: ignore
            count = recipes_table.count
            assert count == 0
        except Exception as e:
            pytest.fail(f"Could not verify 'recipes' table existence: {e}")

    finally:
        if db_conn is not None and hasattr(db_conn, "conn"):
            with contextlib.suppress(Exception):
                db_conn.conn.close()  # type: ignore
