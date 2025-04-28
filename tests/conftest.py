import sqlite3
from pathlib import Path

import fastlite
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import meal_planner.api.recipes as api_recipes_module
import meal_planner.main as main_module
from meal_planner.main import app

TEST_DB_PATH = Path("meal_planner_local.db")


@pytest.fixture(scope="session")
def test_db_session():
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    # Use standard sqlite3 connection for setup/teardown
    conn = sqlite3.connect(TEST_DB_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                ingredients TEXT,
                instructions TEXT
            )
            """
        )
        conn.commit()
        # Yield the path, let fastlite handle connection in tests if needed
        yield TEST_DB_PATH  # Yielding path for simplicity first
    finally:
        conn.close()
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()


@pytest.fixture(autouse=True)
def clean_test_db(test_db_session):
    db_path = test_db_session  # Now receives the path
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM recipes")
        conn.commit()
        yield
    finally:
        conn.close()  # Ensure connection is closed after cleanup


@pytest_asyncio.fixture(scope="function")
async def client(test_db_session, monkeypatch):
    test_db_path = test_db_session
    test_db = fastlite.database(test_db_path)
    test_recipes_table = test_db.t.recipes

    # Ensure the app code uses the test table object
    monkeypatch.setattr(api_recipes_module, "recipes_table", test_recipes_table)
    # Use raising=False for main_module in case recipes_table isn't directly used there
    monkeypatch.setattr(main_module, "recipes_table", test_recipes_table, raising=False)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    # Close the test db connection after tests in this function are done
    test_db.conn.close()


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
