import contextlib
import logging
import sqlite3
from pathlib import Path
from typing import AsyncGenerator

import fastlite
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from meal_planner.api.recipes import get_db
from meal_planner.main import api_app, app

TEST_DB_PATH = Path("meal_planner_test.db")
logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def test_db_session():
    """Creates and cleans up the test database file for the entire session."""
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    conn = sqlite3.connect(TEST_DB_PATH)
    db_obj = fastlite.database(TEST_DB_PATH)
    try:
        # Ensure the table exists in the test DB
        db_obj.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                ingredients TEXT,
                instructions TEXT
            )
            """
        )
        yield TEST_DB_PATH  # Yield path for potential direct use if needed
    finally:
        db_obj.conn.close()  # Close the fastlite connection
        conn.close()  # Close the initial sqlite3 connection (redundant?)
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()


@pytest_asyncio.fixture(scope="function")
async def client(test_db_session: Path) -> AsyncGenerator[AsyncClient, None]:
    """Provides an HTTP client for testing the FastAPI app with overridden DB."""

    # Create a single DB connection for the duration of the test function
    db_conn_for_test = fastlite.database(test_db_session)

    # Clear data at the beginning of the test using this connection
    try:
        db_conn_for_test.conn.execute("DELETE FROM recipes")
    except Exception as e:
        # Handle potential error during delete, maybe close connection and reraise?
        logger.error(f"Error clearing test DB: {e}")
        with contextlib.suppress(Exception):
            db_conn_for_test.conn.close()
        raise  # Reraise the exception to fail the test setup

    # Define the override function within the fixture scope
    def override_get_db_for_test():
        """Dependency override that returns the function-scoped test database
        connection."
        """
        # Simply return the connection created for this test function
        return db_conn_for_test

    # Apply the dependency override before creating the client
    api_app.dependency_overrides[get_db] = override_get_db_for_test

    try:
        async with AsyncClient(
            # Transport must target the main app which includes mounted API app
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client  # Yield the client for the test to use
    finally:
        # Clean up the override after the test function finishes
        api_app.dependency_overrides = {}
        # Ensure the function-scoped connection is closed
        try:
            db_conn_for_test.conn.close()
        except Exception as e:
            logger.error(f"Error closing test DB connection: {e}")


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


def pytest_addoption(parser):
    parser.addoption(
        "--runslow", action="store_true", default=False, help="run slow tests"
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow to run")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--runslow"):
        skip_slow = pytest.mark.skip(reason="need --runslow option to run")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)
