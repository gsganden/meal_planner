from datetime import datetime
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlmodel import Session as SQLModelSession

from meal_planner.models import User

pytestmark = pytest.mark.asyncio


@pytest.mark.anyio
class TestGetUserById:
    @pytest.fixture
    def setup_user(self, dbsession: SQLModelSession) -> UUID:
        """Inserts a user into the test database and returns their ID."""
        test_user = User(
            id=uuid4(),
            username="test_user",
        )
        dbsession.add(test_user)
        dbsession.commit()
        dbsession.refresh(test_user)
        assert test_user.id is not None
        return test_user.id

    async def test_get_user_by_id_success(self, client: AsyncClient, setup_user: UUID):
        """Test GET /api/v0/users/{user_id} returns the correct user."""
        user_id = setup_user
        response = await client.get(f"/api/v0/users/{user_id}")

        assert response.status_code == 200
        response_json = response.json()
        assert response_json["id"] == str(user_id)
        assert response_json["username"] == "test_user"

        # Verify timestamps are present
        assert "created_at" in response_json
        assert "updated_at" in response_json
        assert isinstance(response_json["created_at"], str)
        assert isinstance(response_json["updated_at"], str)

    async def test_get_user_not_found(self, client: AsyncClient):
        """Test GET /api/v0/users/{user_id} returns 404 for a non-existent ID."""
        non_existent_id = str(uuid4())
        response = await client.get(f"/api/v0/users/{non_existent_id}")
        assert response.status_code == 404
        assert response.json() == {"detail": "User not found"}

    async def test_get_user_invalid_uuid(self, client: AsyncClient):
        """Test GET /api/v0/users/{user_id} returns 422 for invalid UUID."""
        invalid_uuid = "not-a-uuid"
        response = await client.get(f"/api/v0/users/{invalid_uuid}")
        assert response.status_code == 422
        assert "detail" in response.json()

    async def test_get_user_db_fetch_error(
        self, client: AsyncClient, monkeypatch, setup_user: UUID
    ):
        """Test handling of database errors during GET /api/v0/users/{user_id}."""
        with patch("sqlmodel.Session.get") as mock_get:
            mock_get.side_effect = Exception("Database fetch error")

            user_id = setup_user
            response = await client.get(f"/api/v0/users/{user_id}")

            assert response.status_code == 500
            assert response.json() == {"detail": "Database error retrieving user"}
            mock_get.assert_called_once_with(User, user_id)


class TestDemoUserMigration:
    """Test demo user migration structure and format."""

    def test_demo_user_migration_format(self):
        """Test that demo user can be created with expected format."""
        from uuid import UUID
        # This tests the structure expected by the migration
        demo_user = User(
            id=UUID("7dfc4e17-5b0c-4e08-8de1-8db9e7321711"),
            username="demo_user"
        )
        
        # Verify the model accepts the expected values
        assert demo_user.id == UUID("7dfc4e17-5b0c-4e08-8de1-8db9e7321711")
        assert demo_user.username == "demo_user"
        assert demo_user.created_at is None  # Will be set by database
        assert demo_user.updated_at is None  # Will be set by database


class TestUserModel:
    """Test User model functionality and database operations."""

    def test_user_model_creation(self, dbsession: SQLModelSession):
        """Test creating a User model instance."""
        user = User(username="model_test_user")

        # Verify default values
        assert user.id is not None  # Should be auto-generated
        assert isinstance(user.id, UUID)
        assert user.username == "model_test_user"
        assert user.created_at is None  # Will be set by database
        assert user.updated_at is None  # Will be set by database

    def test_user_model_database_persistence(self, dbsession: SQLModelSession):
        """Test that User model can be persisted to database."""
        user = User(username="persistence_test_user")

        dbsession.add(user)
        dbsession.commit()
        dbsession.refresh(user)

        # Verify database-managed fields are populated
        assert user.id is not None
        assert user.created_at is not None
        assert user.updated_at is not None
        assert isinstance(user.created_at, datetime)
        assert isinstance(user.updated_at, datetime)

    def test_user_model_unique_username_constraint(self, dbsession: SQLModelSession):
        """Test that username uniqueness is enforced."""
        user1 = User(username="unique_test_user")
        user2 = User(username="unique_test_user")  # Same username

        dbsession.add(user1)
        dbsession.commit()

        # Adding second user with same username should fail
        dbsession.add(user2)
        with pytest.raises((Exception, RuntimeError)):  # SQLite IntegrityError
            dbsession.commit()

    def test_user_model_username_validation(self):
        """Test username field validation."""
        # Empty username should fail validation when model is validated
        with pytest.raises((ValueError, Exception)):
            user = User(username="")
            user.model_validate(user)
