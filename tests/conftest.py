import contextlib
import logging
from pathlib import Path
from typing import AsyncGenerator

import fastlite
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from meal_planner.db import get_initialized_db
from meal_planner.main import api_app, app

TEST_DB_PATH = Path("meal_planner_test.db")
logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def test_db_session():
    """Creates and cleans up the test database file for the entire session.

    Ensures the necessary tables are initialized using the main app's logic.
    """
    if TEST_DB_PATH.exists():
        logger.info("Removing existing test database: %s", TEST_DB_PATH)
        TEST_DB_PATH.unlink()

    db_conn_for_setup = None
    try:
        logger.info("Initializing test database: %s", TEST_DB_PATH)
        db_conn_for_setup = get_initialized_db(db_path_override=TEST_DB_PATH)
        yield TEST_DB_PATH
    finally:
        if db_conn_for_setup is not None:
            logger.info("Closing setup connection for test database: %s", TEST_DB_PATH)
            with contextlib.suppress(Exception):
                db_conn_for_setup.conn.close()  # type: ignore
        if TEST_DB_PATH.exists():
            logger.info("Removing test database file after session: %s", TEST_DB_PATH)
            TEST_DB_PATH.unlink()


@pytest_asyncio.fixture(scope="function")
async def client(test_db_session: Path) -> AsyncGenerator[AsyncClient, None]:
    """Provides an HTTP client for testing the FastAPI app with overridden DB."""
    db_conn_for_test = fastlite.database(test_db_session)
    db_conn_for_test.conn.execute("DELETE FROM recipes")

    def override_get_db_for_test():
        """Dependency override that returns the function-scoped test database
        connection."
        """
        return db_conn_for_test

    api_app.dependency_overrides[get_initialized_db] = override_get_db_for_test

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client
    finally:
        api_app.dependency_overrides = {}
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
