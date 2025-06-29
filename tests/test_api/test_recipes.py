from datetime import datetime
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlmodel import Session as SQLModelSession

from meal_planner.models import Recipe

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def valid_recipe_payload():
    return {
        "name": "Test Recipe",
        "ingredients": ["1 cup flour", "2 eggs"],
        "instructions": ["Mix ingredients", "Bake at 350F"],
    }


class TestCreateRecipeSuccess:
    @pytest_asyncio.fixture()
    async def create_recipe_response(
        self, client: AsyncClient, valid_recipe_payload: dict
    ):
        return await client.post("/api/v0/recipes", json=valid_recipe_payload)

    async def test_create_recipe_returns_201(self, create_recipe_response: Response):
        assert create_recipe_response.status_code == 201

    async def test_create_recipe_returns_location_header(
        self, create_recipe_response: Response
    ):
        assert "Location" in create_recipe_response.headers
        response_json = create_recipe_response.json()
        recipe_id_from_body = response_json["id"]
        expected_location = f"/api/v0/recipes/{recipe_id_from_body}"
        assert create_recipe_response.headers["Location"] == expected_location

    async def test_create_recipe_returns_id_in_body(
        self, create_recipe_response: Response
    ):
        response_json = create_recipe_response.json()
        assert "id" in response_json
        recipe_id_from_body = response_json["id"]
        # Verify it's a valid UUID string format
        import uuid

        uuid.UUID(recipe_id_from_body)  # Should not raise exception

    async def test_create_recipe_response_contains_payload_data(
        self, create_recipe_response: Response, valid_recipe_payload: dict
    ):
        response_json = create_recipe_response.json()
        assert response_json["name"] == valid_recipe_payload["name"]
        assert response_json["ingredients"] == valid_recipe_payload["ingredients"]
        assert response_json["instructions"] == valid_recipe_payload["instructions"]


@pytest.mark.usefixtures("client")
class TestCreateRecipeValidation:
    async def _post_recipe(self, client: AsyncClient, payload: dict):
        return await client.post("/api/v0/recipes", json=payload)

    @pytest.mark.parametrize(
        "invalid_payload, expected_error_detail",
        [
            (
                {"ingredients": ["i1"], "instructions": ["s1"]},
                [
                    {
                        "loc": ("body", "name"),
                        "msg": "Field required",
                        "type": "missing",
                    }
                ],
            ),
            (
                {"name": "Test", "instructions": ["s1"]},
                [
                    {
                        "loc": ("body", "ingredients"),
                        "msg": "Field required",
                        "type": "missing",
                    }
                ],
            ),
            (
                {"name": "Test", "ingredients": ["i1"]},
                [
                    {
                        "loc": ("body", "instructions"),
                        "msg": "Field required",
                        "type": "missing",
                    }
                ],
            ),
            (
                {
                    "name": 123,
                    "ingredients": ["i1"],
                    "instructions": ["s1"],
                },
                [
                    {
                        "loc": ("body", "name"),
                        "msg": "Input should be a valid string",
                        "type": "string_type",
                    }
                ],
            ),
            (
                {
                    "name": "Test",
                    "ingredients": "not-a-list",
                    "instructions": ["s1"],
                },
                [
                    {
                        "loc": ("body", "ingredients"),
                        "msg": "Input should be a valid list",
                        "type": "list_type",
                    }
                ],
            ),
            (
                {
                    "name": "Test",
                    "ingredients": ["i1"],
                    "instructions": {"step": 1},
                },
                [
                    {
                        "loc": ("body", "instructions"),
                        "msg": "Input should be a valid list",
                        "type": "list_type",
                    }
                ],
            ),
            (
                {
                    "name": "Test",
                    "ingredients": ["i1"],
                    "instructions": [],
                },
                [
                    {
                        "loc": ("body", "instructions"),
                        "msg": (
                            "List should have at least 1 item after validation, not 0"
                        ),
                        "type": "too_short",
                    }
                ],
            ),
            (
                {
                    "name": "Test",
                    "ingredients": [],
                    "instructions": ["s1"],
                },
                [
                    {
                        "loc": ("body", "ingredients"),
                        "msg": (
                            "List should have at least 1 item after validation, not 0"
                        ),
                        "type": "too_short",
                    }
                ],
            ),
        ],
    )
    async def test_create_recipe_validation_error(
        self,
        client: AsyncClient,
        invalid_payload: dict,
        expected_error_detail: list[dict],
    ):
        response = await self._post_recipe(client, invalid_payload)
        assert response.status_code == 422
        actual_detail_full = response.json().get("detail", [])

        fields_to_compare = ["loc", "msg", "type"]
        actual_detail_filtered = []
        for error in actual_detail_full:
            filtered_error = {k: v for k, v in error.items() if k in fields_to_compare}
            if "loc" in filtered_error and isinstance(filtered_error["loc"], list):
                filtered_error["loc"] = tuple(filtered_error["loc"])
            actual_detail_filtered.append(filtered_error)

        for error in actual_detail_filtered:
            if isinstance(error.get("type"), str) and "." in error["type"]:
                error["type"] = error["type"].split(".")[-1]

        assert actual_detail_filtered == expected_error_detail

    async def test_create_recipe_invalid_json(self, client: AsyncClient):
        invalid_json_string = (
            '{"name": "Test", "ingredients": ["i1"], "instructions": ["s1"}'
        )
        response = await client.post(
            "/api/v0/recipes",
            content=invalid_json_string,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
        assert "detail" in response.json()
        assert isinstance(response.json()["detail"], list)
        assert len(response.json()["detail"]) > 0
        assert "msg" in response.json()["detail"][0]


@pytest.mark.usefixtures("client")
class TestCreateRecipeDBErrors:
    @pytest.mark.anyio
    async def test_create_recipe_db_insert_error(
        self, client: AsyncClient, monkeypatch, valid_recipe_payload: dict
    ):
        """Test handling of database insertion errors."""
        with patch("sqlmodel.Session.commit") as mock_commit:
            mock_commit.side_effect = Exception("Database write error")

            response = await client.post("/api/v0/recipes", json=valid_recipe_payload)

            assert response.status_code == 500
            assert response.json() == {"detail": "Database error creating recipe"}


@pytest.mark.anyio
class TestGetRecipes:
    async def test_get_recipes_populated(self, client: AsyncClient):
        """Test GET /api/recipes returns all recipes when populated via API calls."""
        recipe1_payload = {
            "name": "Recipe One",
            "ingredients": ["ing1a", "ing1b"],
            "instructions": ["step1a", "step1b"],
        }
        recipe2_payload = {
            "name": "Recipe Two",
            "ingredients": ["ing2a"],
            "instructions": ["step2a"],
        }

        response1 = await client.post("/api/v0/recipes", json=recipe1_payload)
        assert response1.status_code == 201
        response2 = await client.post("/api/v0/recipes", json=recipe2_payload)
        assert response2.status_code == 201

        response = await client.get("/api/v0/recipes")

        assert response.status_code == 200
        response_json = response.json()
        assert isinstance(response_json, list)
        assert len(response_json) == 2

        names = {r["name"] for r in response_json}
        assert names == {"Recipe One", "Recipe Two"}

    async def test_get_recipes_empty(self, client: AsyncClient):
        """Test GET /api/recipes returns an empty list when the database is empty."""
        response = await client.get("/api/v0/recipes")

        assert response.status_code == 200
        response_json = response.json()
        assert response_json == []

    @pytest.mark.anyio
    async def test_get_recipes_general_db_error(self, client: AsyncClient, monkeypatch):
        """Test handling of general database errors during GET /api/recipes."""
        with patch("sqlmodel.Session.exec") as mock_exec:
            mock_exec.side_effect = Exception("Database query error")

            response = await client.get("/api/v0/recipes")

            assert response.status_code == 500
            assert response.json() == {"detail": "Database error retrieving recipes"}
            mock_exec.assert_called_once()


@pytest.mark.anyio
class TestGetRecipeById:
    @pytest.fixture
    def setup_recipe(self, dbsession: SQLModelSession) -> str:
        """Inserts a recipe into the test database and returns its ID."""
        test_recipe = Recipe(
            name="Detailed Test Recipe",
            ingredients=["Detail ingredient 1", "Detail ingredient 2"],
            instructions=["Detail instruction 1", "Detail instruction 2"],
        )
        dbsession.add(test_recipe)
        dbsession.commit()
        dbsession.refresh(test_recipe)
        assert test_recipe.id is not None
        return test_recipe.id

    async def test_get_recipe_by_id_success(
        self, client: AsyncClient, setup_recipe: str
    ):
        """Test GET /api/recipes/{recipe_id} returns the correct recipe."""
        recipe_id = setup_recipe
        response = await client.get(f"/api/v0/recipes/{recipe_id}")

        assert response.status_code == 200
        response_json = response.json()
        assert response_json["id"] == str(recipe_id)
        assert response_json["name"] == "Detailed Test Recipe"
        assert response_json["ingredients"] == [
            "Detail ingredient 1",
            "Detail ingredient 2",
        ]
        assert response_json["instructions"] == [
            "Detail instruction 1",
            "Detail instruction 2",
        ]

    async def test_get_recipe_not_found(self, client: AsyncClient):
        """Test GET /api/recipes/{recipe_id} returns 404 for a non-existent ID."""
        non_existent_id = "12345678-1234-1234-1234-123456789012"
        response = await client.get(f"/api/v0/recipes/{non_existent_id}")
        assert response.status_code == 404
        assert response.json() == {"detail": "Recipe not found"}

    async def test_get_recipe_db_fetch_error(
        self, client: AsyncClient, monkeypatch, setup_recipe: str
    ):
        """Test handling of database errors during GET /api/recipes/{recipe_id}."""
        with patch("sqlmodel.Session.exec") as mock_exec:
            mock_exec.side_effect = Exception("Database fetch error")

            recipe_id = setup_recipe
            response = await client.get(f"/api/v0/recipes/{recipe_id}")

            assert response.status_code == 500
            assert response.json() == {"detail": "Database error retrieving recipe"}
            mock_exec.assert_called_once()


@pytest.mark.anyio
class TestDeleteRecipe:
    @pytest_asyncio.fixture()
    async def created_recipe_id(
        self, client: AsyncClient, valid_recipe_payload: dict
    ) -> str:
        """Creates a recipe and returns its ID."""
        response = await client.post("/api/v0/recipes", json=valid_recipe_payload)
        assert response.status_code == 201
        return response.json()["id"]

    async def test_delete_recipe_success(
        self, client: AsyncClient, created_recipe_id: str
    ):
        """Test successful deletion of an existing recipe."""
        delete_response = await client.delete(f"/api/v0/recipes/{created_recipe_id}")
        assert delete_response.status_code == 204

        get_response = await client.get(f"/api/v0/recipes/{created_recipe_id}")
        assert get_response.status_code == 404

    async def test_delete_non_existent_recipe(self, client: AsyncClient):
        """Test deleting a recipe that does not exist."""
        non_existent_id = "12345678-1234-1234-1234-123456789012"
        response = await client.delete(f"/api/v0/recipes/{non_existent_id}")
        assert response.status_code == 404
        assert response.json() == {"detail": "Recipe not found"}

    async def test_delete_recipe_db_fetch_error(
        self, client: AsyncClient, monkeypatch, created_recipe_id: str
    ):
        """Test handling of database errors when fetching a recipe for deletion."""
        with patch("sqlmodel.Session.get") as mock_get:
            mock_get.side_effect = Exception("Simulated DB error on get")

            response = await client.delete(f"/api/v0/recipes/{created_recipe_id}")

            assert response.status_code == 500
            assert response.json() == {
                "detail": "Database error fetching recipe for deletion"
            }
            mock_get.assert_called_once_with(Recipe, created_recipe_id)

    async def test_delete_recipe_db_delete_error(
        self, client: AsyncClient, monkeypatch, created_recipe_id: str
    ):
        """Test handling of database errors during the actual delete operation."""
        get_response = await client.get(f"/api/v0/recipes/{created_recipe_id}")
        assert get_response.status_code == 200

        with (
            patch("sqlmodel.Session.delete"),
            patch("sqlmodel.Session.commit") as mock_commit,
        ):
            mock_commit.side_effect = Exception("Simulated DB error on commit")

            response = await client.delete(f"/api/v0/recipes/{created_recipe_id}")

            assert response.status_code == 500
            assert response.json() == {"detail": "Database error deleting recipe"}
            mock_commit.assert_called_once()


@pytest.mark.anyio
class TestRecipeTimestamps:
    """Test timestamp functionality for recipe creation and retrieval."""

    async def test_create_recipe_includes_timestamps_in_response(
        self, client: AsyncClient, valid_recipe_payload: dict
    ):
        """Test that creating a recipe includes timestamps in response."""
        response = await client.post("/api/v0/recipes", json=valid_recipe_payload)

        assert response.status_code == 201
        response_json = response.json()

        # Verify timestamps are present in response
        assert "created_at" in response_json
        assert "updated_at" in response_json

        # Verify timestamps are valid datetime strings
        created_at_str = response_json["created_at"]
        updated_at_str = response_json["updated_at"]

        assert isinstance(created_at_str, str)
        assert isinstance(updated_at_str, str)

        # Verify timestamps can be parsed as datetime
        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))

        # For new recipes, created_at and updated_at should be very close/identical
        time_diff = abs((updated_at - created_at).total_seconds())
        assert time_diff < 5, f"created_at and updated_at differ by {time_diff} seconds"

    async def test_create_recipe_timestamps_stored_in_database(
        self,
        client: AsyncClient,
        dbsession: SQLModelSession,
        valid_recipe_payload: dict,
    ):
        """Test that timestamps are correctly stored in the database."""
        response = await client.post("/api/v0/recipes", json=valid_recipe_payload)

        assert response.status_code == 201
        recipe_id = response.json()["id"]

        # Fetch the recipe directly from database
        db_recipe = dbsession.get(Recipe, recipe_id)
        assert db_recipe is not None

        # Verify timestamps are populated in database
        assert db_recipe.created_at is not None
        assert db_recipe.updated_at is not None

        # Verify timestamps are datetime objects
        assert isinstance(db_recipe.created_at, datetime)
        assert isinstance(db_recipe.updated_at, datetime)

        # For new recipes, created_at and updated_at should be very close/identical
        time_diff = abs((db_recipe.updated_at - db_recipe.created_at).total_seconds())
        assert time_diff < 5, f"DB timestamps differ by {time_diff} seconds"

    async def test_get_recipe_by_id_includes_timestamps(
        self, client: AsyncClient, valid_recipe_payload: dict
    ):
        """Test that retrieving a recipe by ID includes timestamps."""
        # Create recipe first
        create_response = await client.post(
            "/api/v0/recipes", json=valid_recipe_payload
        )
        assert create_response.status_code == 201
        recipe_id = create_response.json()["id"]

        # Retrieve the recipe
        get_response = await client.get(f"/api/v0/recipes/{recipe_id}")
        assert get_response.status_code == 200

        response_json = get_response.json()

        # Verify timestamps are present
        assert "created_at" in response_json
        assert "updated_at" in response_json

        # Verify timestamps match creation response
        create_created_at = create_response.json()["created_at"]
        create_updated_at = create_response.json()["updated_at"]

        assert response_json["created_at"] == create_created_at
        assert response_json["updated_at"] == create_updated_at

    async def test_get_all_recipes_includes_timestamps(
        self, client: AsyncClient, valid_recipe_payload: dict
    ):
        """Test that retrieving all recipes includes timestamps for each recipe."""
        # Create a couple of recipes
        recipe1_payload = {**valid_recipe_payload, "name": "Recipe One"}
        recipe2_payload = {**valid_recipe_payload, "name": "Recipe Two"}

        create_response1 = await client.post("/api/v0/recipes", json=recipe1_payload)
        create_response2 = await client.post("/api/v0/recipes", json=recipe2_payload)

        assert create_response1.status_code == 201
        assert create_response2.status_code == 201

        # Get all recipes
        get_response = await client.get("/api/v0/recipes")
        assert get_response.status_code == 200

        recipes = get_response.json()
        assert len(recipes) == 2

        # Verify timestamps are present for all recipes
        for recipe in recipes:
            assert "created_at" in recipe
            assert "updated_at" in recipe
            assert isinstance(recipe["created_at"], str)
            assert isinstance(recipe["updated_at"], str)

            # Verify timestamps can be parsed
            created_at = datetime.fromisoformat(
                recipe["created_at"].replace("Z", "+00:00")
            )
            # Verify timestamps are reasonable (recent)
            now = datetime.now(created_at.tzinfo)
            time_since_creation = (now - created_at).total_seconds()
            assert time_since_creation < 60, (
                f"Recipe seems too old: {time_since_creation}s ago"
            )

    async def test_recipe_timestamps_are_approximately_equal_for_new_recipes(
        self, client: AsyncClient, valid_recipe_payload: dict
    ):
        """Test that timestamps are approximately equal for new recipes."""
        response = await client.post("/api/v0/recipes", json=valid_recipe_payload)
        assert response.status_code == 201

        response_json = response.json()
        created_at = datetime.fromisoformat(
            response_json["created_at"].replace("Z", "+00:00")
        )
        updated_at = datetime.fromisoformat(
            response_json["updated_at"].replace("Z", "+00:00")
        )

        # For new recipes, timestamps should be identical or very close
        time_diff = abs((updated_at - created_at).total_seconds())
        assert time_diff < 1, f"New recipe timestamps differ by {time_diff} seconds"


@pytest.mark.anyio
class TestUpdateRecipe:
    """Test suite for the PUT /api/v0/recipes/{recipe_id} endpoint."""

    @pytest_asyncio.fixture()
    async def created_recipe(
        self, client: AsyncClient, valid_recipe_payload: dict
    ) -> dict:
        """Creates a recipe and returns the response JSON with ID."""
        response = await client.post("/api/v0/recipes", json=valid_recipe_payload)
        assert response.status_code == 201
        return response.json()

    @pytest.fixture()
    def updated_recipe_payload(self):
        """Payload for updating a recipe."""
        return {
            "name": "Updated Test Recipe",
            "ingredients": ["2 cups flour", "3 eggs", "1 cup milk"],
            "instructions": ["Combine ingredients", "Bake at 375F for 25 minutes"],
        }

    async def test_update_recipe_success(
        self,
        client: AsyncClient,
        created_recipe: dict,
        updated_recipe_payload: dict,
    ):
        """Test successful update of an existing recipe."""
        recipe_id = created_recipe["id"]
        response = await client.put(
            f"/api/v0/recipes/{recipe_id}", json=updated_recipe_payload
        )

        assert response.status_code == 200
        response_json = response.json()

        # Verify updated data is returned
        assert response_json["id"] == recipe_id
        assert response_json["name"] == updated_recipe_payload["name"]
        assert response_json["ingredients"] == updated_recipe_payload["ingredients"]
        assert response_json["instructions"] == updated_recipe_payload["instructions"]

    async def test_update_recipe_includes_last_modified_header(
        self,
        client: AsyncClient,
        created_recipe: dict,
        updated_recipe_payload: dict,
    ):
        """Test that update response includes Last-Modified header."""
        recipe_id = created_recipe["id"]
        response = await client.put(
            f"/api/v0/recipes/{recipe_id}", json=updated_recipe_payload
        )

        assert response.status_code == 200
        assert "Last-Modified" in response.headers

        # Verify header format (should be valid HTTP date)
        last_modified = response.headers["Last-Modified"]
        assert isinstance(last_modified, str)
        assert len(last_modified) > 20  # Basic sanity check

    async def test_update_recipe_preserves_created_at(
        self,
        client: AsyncClient,
        created_recipe: dict,
        updated_recipe_payload: dict,
    ):
        """Test that update preserves the original created_at timestamp."""
        recipe_id = created_recipe["id"]
        original_created_at = created_recipe["created_at"]

        response = await client.put(
            f"/api/v0/recipes/{recipe_id}", json=updated_recipe_payload
        )

        assert response.status_code == 200
        response_json = response.json()

        # created_at should remain unchanged
        assert response_json["created_at"] == original_created_at

    async def test_update_recipe_updates_updated_at(
        self,
        client: AsyncClient,
        created_recipe: dict,
        updated_recipe_payload: dict,
    ):
        """Test that update changes the updated_at timestamp."""
        recipe_id = created_recipe["id"]
        original_updated_at = created_recipe["updated_at"]

        # Add small delay to ensure timestamp difference
        import asyncio

        await asyncio.sleep(0.1)

        response = await client.put(
            f"/api/v0/recipes/{recipe_id}", json=updated_recipe_payload
        )

        assert response.status_code == 200
        response_json = response.json()

        # updated_at should be different from original
        assert response_json["updated_at"] != original_updated_at

        # Parse timestamps to verify updated_at is more recent
        original_dt = datetime.fromisoformat(original_updated_at.replace("Z", "+00:00"))
        updated_dt = datetime.fromisoformat(
            response_json["updated_at"].replace("Z", "+00:00")
        )
        assert updated_dt > original_dt

    async def test_update_recipe_persists_to_database(
        self,
        client: AsyncClient,
        created_recipe: dict,
        updated_recipe_payload: dict,
    ):
        """Test that update changes are persisted to database."""
        recipe_id = created_recipe["id"]

        # Update the recipe
        update_response = await client.put(
            f"/api/v0/recipes/{recipe_id}", json=updated_recipe_payload
        )
        assert update_response.status_code == 200

        # Fetch the recipe again to verify persistence
        get_response = await client.get(f"/api/v0/recipes/{recipe_id}")
        assert get_response.status_code == 200

        response_json = get_response.json()
        assert response_json["name"] == updated_recipe_payload["name"]
        assert response_json["ingredients"] == updated_recipe_payload["ingredients"]
        assert response_json["instructions"] == updated_recipe_payload["instructions"]

    async def test_update_recipe_not_found(
        self, client: AsyncClient, updated_recipe_payload: dict
    ):
        """Test updating a non-existent recipe returns 404."""
        non_existent_id = "99999999-9999-9999-9999-999999999999"
        response = await client.put(
            f"/api/v0/recipes/{non_existent_id}", json=updated_recipe_payload
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "Recipe not found"}

    @pytest.mark.parametrize(
        "invalid_payload, expected_status",
        [
            ({"ingredients": ["i1"], "instructions": ["s1"]}, 422),  # missing name
            ({"name": "Test", "instructions": ["s1"]}, 422),  # missing ingredients
            ({"name": "Test", "ingredients": ["i1"]}, 422),  # missing instructions
            (
                {"name": "", "ingredients": ["i1"], "instructions": ["s1"]},
                422,
            ),  # empty name
            (
                {"name": "Test", "ingredients": [], "instructions": ["s1"]},
                422,
            ),  # empty ingredients
            (
                {"name": "Test", "ingredients": ["i1"], "instructions": []},
                422,
            ),  # empty instructions
        ],
    )
    async def test_update_recipe_validation_errors(
        self,
        client: AsyncClient,
        created_recipe: dict,
        invalid_payload: dict,
        expected_status: int,
    ):
        """Test that invalid update payloads return 422 validation errors."""
        recipe_id = created_recipe["id"]
        response = await client.put(
            f"/api/v0/recipes/{recipe_id}", json=invalid_payload
        )

        assert response.status_code == expected_status
        if expected_status == 422:
            assert "detail" in response.json()

    async def test_update_recipe_db_fetch_error(
        self, client: AsyncClient, created_recipe: dict, updated_recipe_payload: dict
    ):
        """Test handling of database errors when fetching recipe for update."""
        recipe_id = created_recipe["id"]

        with patch("sqlmodel.Session.get") as mock_get:
            mock_get.side_effect = Exception("Database fetch error")

            response = await client.put(
                f"/api/v0/recipes/{recipe_id}", json=updated_recipe_payload
            )

            assert response.status_code == 500
            assert response.json() == {"detail": "Database error retrieving recipe"}
            mock_get.assert_called_once_with(Recipe, recipe_id)

    async def test_update_recipe_db_commit_error(
        self, client: AsyncClient, created_recipe: dict, updated_recipe_payload: dict
    ):
        """Test handling of database errors during commit operation."""
        recipe_id = created_recipe["id"]

        with patch("sqlmodel.Session.commit") as mock_commit:
            mock_commit.side_effect = Exception("Database commit error")

            response = await client.put(
                f"/api/v0/recipes/{recipe_id}", json=updated_recipe_payload
            )

            assert response.status_code == 500
            assert response.json() == {"detail": "Database error updating recipe"}
            mock_commit.assert_called_once()

    async def test_update_recipe_timestamp_verification(
        self,
        client: AsyncClient,
        dbsession: SQLModelSession,
        created_recipe: dict,
        updated_recipe_payload: dict,
    ):
        """Test that timestamps are properly managed in the database."""
        recipe_id = created_recipe["id"]

        # Get original timestamps from database
        original_recipe = dbsession.get(Recipe, recipe_id)
        assert original_recipe is not None
        original_created_at = original_recipe.created_at
        original_updated_at = original_recipe.updated_at

        # Add delay to ensure timestamp difference
        import time

        time.sleep(0.1)

        # Update the recipe
        response = await client.put(
            f"/api/v0/recipes/{recipe_id}", json=updated_recipe_payload
        )
        assert response.status_code == 200

        # Fetch updated recipe from database
        dbsession.expire_all()  # Clear session cache
        updated_recipe = dbsession.get(Recipe, recipe_id)
        assert updated_recipe is not None

        # Verify timestamp behavior
        assert updated_recipe.created_at == original_created_at  # unchanged
        assert updated_recipe.updated_at > original_updated_at  # updated
        assert updated_recipe.updated_at != original_updated_at


@pytest.mark.anyio
class TestUpdateRecipeIntegration:
    """Integration tests for recipe update functionality."""

    async def test_create_update_get_integration(
        self, client: AsyncClient, valid_recipe_payload: dict
    ):
        """Test complete create -> update -> get workflow."""
        # Create recipe
        create_response = await client.post(
            "/api/v0/recipes", json=valid_recipe_payload
        )
        assert create_response.status_code == 201
        recipe_id = create_response.json()["id"]

        # Update recipe
        updated_payload = {
            "name": "Integration Test Recipe",
            "ingredients": ["Updated ingredient 1", "Updated ingredient 2"],
            "instructions": ["Updated step 1", "Updated step 2"],
        }
        update_response = await client.put(
            f"/api/v0/recipes/{recipe_id}", json=updated_payload
        )
        assert update_response.status_code == 200

        # Verify via GET
        get_response = await client.get(f"/api/v0/recipes/{recipe_id}")
        assert get_response.status_code == 200

        final_recipe = get_response.json()
        assert final_recipe["name"] == updated_payload["name"]
        assert final_recipe["ingredients"] == updated_payload["ingredients"]
        assert final_recipe["instructions"] == updated_payload["instructions"]

        # Verify timestamps
        create_created_at = create_response.json()["created_at"]
        final_created_at = final_recipe["created_at"]
        assert final_created_at == create_created_at  # created_at preserved

        update_updated_at = update_response.json()["updated_at"]
        final_updated_at = final_recipe["updated_at"]
        assert final_updated_at == update_updated_at  # updated_at matches
