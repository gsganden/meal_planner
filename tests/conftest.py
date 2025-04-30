import sqlite3
from pathlib import Path

import fastlite
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import meal_planner.api.recipes as api_recipes_module
import meal_planner.main as main_module
from meal_planner.main import app

# No longer using a file path
# TEST_DB_PATH = Path("meal_planner_local.db")


@pytest.fixture(scope="session")
def test_db_connection():
    # Use in-memory database
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute(
            """
            CREATE TABLE recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                ingredients TEXT,
                instructions TEXT
            )
            """
        )
        conn.commit()
        yield conn  # Yield the connection itself
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def clean_test_db(test_db_connection):
    # Use the connection from the session fixture
    conn = test_db_connection
    try:
        # Ensure table exists (redundant but safe)
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
        conn.execute("DELETE FROM recipes")
        conn.commit()
        yield
    finally:
        # No need to close conn here, handled by session fixture
        pass


@pytest_asyncio.fixture(scope="function")
async def client(test_db_connection, monkeypatch):
    # Use the connection from the session fixture
    conn = test_db_connection
    # Create fastlite wrapper around the connection
    test_db = fastlite.database(conn)
    test_recipes_table = test_db.t.recipes
    monkeypatch.setattr(api_recipes_module, "recipes_table", test_recipes_table)
    monkeypatch.setattr(main_module, "recipes_table", test_recipes_table, raising=False)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    # No need to close conn here, handled by session fixture


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
