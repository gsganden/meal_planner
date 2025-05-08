import logging
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import Connection
from sqlmodel import Session as SQLModelSession
from sqlmodel import create_engine

from alembic import command
from alembic.config import Config
from meal_planner.database import get_session
from meal_planner.main import api_app, app

logger = logging.getLogger(__name__)

TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def test_engine():
    """Creates an in-memory SQLite engine for each test function."""
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def dbsession(test_engine):
    """Provides a transactional session with tables created via Alembic migrations."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    connection: Connection | None = None
    try:
        connection = test_engine.connect()
        assert connection is not None

        alembic_cfg.attributes["connection"] = connection
        command.upgrade(alembic_cfg, "head")
        alembic_cfg.attributes.pop("connection", None)

        transaction = connection.begin()
        session = SQLModelSession(bind=connection)

        yield session

        session.close()
        transaction.rollback()

    finally:
        if connection is not None:
            downgrade_cfg = Config("alembic.ini")
            downgrade_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
            command.downgrade(downgrade_cfg, "base")
            connection.close()


@pytest_asyncio.fixture(scope="function")
async def client(dbsession: SQLModelSession) -> AsyncGenerator[AsyncClient, None]:
    def override_get_session():
        return dbsession

    api_app.dependency_overrides[get_session] = override_get_session

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
