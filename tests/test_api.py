from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastlite import database
from httpx import AsyncClient, Response

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
        assert isinstance(recipe_id_from_body, int)

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
        self, client: AsyncClient, monkeypatch
    ):
        """Test handling of database insertion errors."""
        with patch("fastlite.Table.insert") as mock_insert:
            mock_insert.side_effect = Exception("Database write error")

            valid_payload = {
                "name": "DB Error Recipe",
                "ingredients": ["ing1"],
                "instructions": ["inst1"],
            }
            response = await client.post("/api/v0/recipes", json=valid_payload)

            assert response.status_code == 500
            assert response.json() == {"detail": "Database error creating recipe"}
            mock_insert.assert_called_once()


@pytest.mark.anyio
class TestGetRecipes:
    async def test_get_recipes_populated(
        self, client: AsyncClient, test_db_session: Path
    ):
        """Test GET /api/recipes returns all recipes when the database is populated."""
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

    async def test_get_recipes_empty(self, client: AsyncClient, test_db_session: Path):
        """Test GET /api/recipes returns an empty list when the database is empty."""
        response = await client.get("/api/v0/recipes")

        assert response.status_code == 200
        response_json = response.json()
        assert response_json == []

    @pytest.mark.anyio
    async def test_get_recipes_row_processing_error(
        self, client: AsyncClient, test_db_session: Path
    ):
        """Test that row processing errors (e.g., bad JSON) are handled gracefully."""
        db = database(test_db_session)
        recipes_table = db.t.recipes
        recipes_table.insert(
            {
                "name": "Valid Recipe",
                "ingredients": '["ing1"]',
                "instructions": '["step1"]',
            }
        )
        recipes_table.insert(
            {
                "name": "Bad JSON Recipe",
                "ingredients": "not json",
                "instructions": '["step1"]',
            }
        )
        db.conn.close()

        response = await client.get("/api/v0/recipes")
        assert response.status_code == 200
        response_json = response.json()
        assert len(response_json) == 1
        assert response_json[0]["name"] == "Valid Recipe"

    @pytest.mark.anyio
    async def test_get_recipes_general_db_error(self, client: AsyncClient, monkeypatch):
        """Test handling of general DB errors during recipe fetch."""
        with patch("fastlite.Table.__call__") as mock_select:
            mock_select.side_effect = Exception("Simulated DB Query Error")

            response = await client.get("/api/v0/recipes")

            assert response.status_code == 500
            assert response.json() == {"detail": "Database error retrieving recipes"}
            mock_select.assert_called_once()


@pytest.mark.anyio
class TestGetRecipeById:
    @pytest.fixture
    def setup_recipe(self, test_db_session: Path) -> int:
        """Inserts a recipe and returns its ID."""
        db = database(test_db_session)
        recipe_id = db.t.recipes.insert(
            {
                "name": "Test Recipe for Get",
                "ingredients": '["ing1"]',
                "instructions": '["step1"]',
            }
        )["id"]
        db.conn.close()
        return recipe_id

    async def test_get_recipe_not_found(self, client: AsyncClient):
        """Test GET /v0/recipes/{recipe_id} returns 404 for non-existent ID."""
        non_existent_id = 9999
        response = await client.get(f"/api/v0/recipes/{non_existent_id}")
        assert response.status_code == 404
        assert response.json() == {"detail": "Recipe not found"}

    async def test_get_recipe_db_fetch_error(
        self, client: AsyncClient, monkeypatch, setup_recipe
    ):
        """Test handling of DB errors during get_recipe_by_id fetch."""
        recipe_id = setup_recipe
        with patch("fastlite.Table.get") as mock_get:
            mock_get.side_effect = Exception("Simulated DB Fetch Error")
            response = await client.get(f"/api/v0/recipes/{recipe_id}")
            assert response.status_code == 500
            assert response.json() == {"detail": "Database error retrieving recipe"}
            mock_get.assert_called_once_with(recipe_id)

    async def test_get_recipe_data_processing_error(
        self, client: AsyncClient, monkeypatch, test_db_session: Path
    ):
        """Test handling of data processing errors (e.g., bad JSON) after fetch."""
        db = database(test_db_session)
        recipe_id = db.t.recipes.insert(
            {
                "name": "Bad JSON Recipe",
                "ingredients": "not-a-valid-json-array",
                "instructions": '["step1"]',
            }
        )["id"]
        db.conn.close()

        response = await client.get(f"/api/v0/recipes/{recipe_id}")
        assert response.status_code == 500
        assert response.json() == {"detail": "Error processing recipe data"}
