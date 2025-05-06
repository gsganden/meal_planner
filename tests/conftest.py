import contextlib
import logging
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from sqlmodel import create_engine, Session as SQLModelSession, SQLModel as SQLModelBase
from meal_planner.database import get_session
from meal_planner.main import api_app, app
from sqlalchemy import inspect

logger = logging.getLogger(__name__)

# In-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def test_engine():
    """Creates an in-memory SQLite engine for each test function."""
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    yield engine
    # Engine disposal might happen automatically, but being explicit can help
    engine.dispose()


@pytest.fixture(scope="function")
def dbsession(test_engine):
    """Provides a transactional session with tables created for each test function."""
    # Create tables for this specific engine instance
    SQLModelBase.metadata.create_all(test_engine)

    connection = test_engine.connect()
    transaction = connection.begin()
    session = SQLModelSession(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()

    # Drop tables after test
    SQLModelBase.metadata.drop_all(test_engine)


@pytest_asyncio.fixture(scope="function")
async def client(dbsession: SQLModelSession) -> AsyncGenerator[AsyncClient, None]:
    """Provides an HTTP client for testing the FastAPI app with overridden DB session."""

    def override_get_session():
        return dbsession

    # Need to override on the app that the endpoint is actually part of
    api_app.dependency_overrides[get_session] = override_get_session

    # Use the main 'app' for the transport, as it handles the /api mount
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c

    api_app.dependency_overrides.clear()


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
