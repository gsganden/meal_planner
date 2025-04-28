# tests/test_api.py
import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from pathlib import Path  # Import Path
from fastlite import database  # Import database for test setup

from meal_planner.main import app
from meal_planner.models import Recipe

# Import production db path for monkeypatching target
import meal_planner.api.recipes as recipes_api

pytestmark = pytest.mark.asyncio

TEST_DB_PATH = Path("test_meal_planner.db")


# Session-scoped fixture for setting up/tearing down the test database
@pytest.fixture(scope="session")
def test_db_session():
    # Ensure clean start
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()

    test_db = database(TEST_DB_PATH)
    test_recipes_table = test_db.t.recipes
    # Define schema matching api/recipes.py
    test_recipes_table.create(
        id=uuid.UUID,
        name=str,
        ingredients=str,
        instructions=str,
        pk="id",
        if_not_exists=True,
    )
    yield test_db, test_recipes_table  # Provide db and table to tests/fixtures

    # Teardown: close connection and delete test db file
    test_db.conn.close()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest_asyncio.fixture(scope="function")
async def client(
    test_db_session, monkeypatch
):  # Inject session fixture and monkeypatch
    # Get the test db and table objects
    test_db, test_recipes_table = test_db_session

    # Monkeypatch the db and recipes_table objects in the api module
    monkeypatch.setattr(recipes_api, "db", test_db)
    monkeypatch.setattr(recipes_api, "recipes_table", test_recipes_table)

    # Now, when the app runs via ASGITransport, it uses the patched db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


# Fixture to clean the *test* recipes table before each test function
@pytest.fixture(autouse=True)
def clean_test_db(test_db_session):
    test_db, test_recipes_table = test_db_session
    try:
        test_db.conn.execute(f"DELETE FROM {test_recipes_table}")
        yield
    finally:
        test_db.conn.execute(f"DELETE FROM {test_recipes_table}")


@pytest.fixture()
def valid_recipe_payload():
    return {
        "name": "Test Recipe",
        "ingredients": ["1 cup flour", "2 eggs"],
        "instructions": ["Mix ingredients", "Bake at 350F"],
    }


class TestCreateRecipeSuccess:
    # Tests now accept client and payload, and make their own requests
    async def test_create_recipe_returns_201(
        self, client: AsyncClient, valid_recipe_payload: dict
    ):
        response = await client.post("/api/v1/recipes", json=valid_recipe_payload)
        assert response.status_code == 201

    async def test_create_recipe_returns_location_header(
        self, client: AsyncClient, valid_recipe_payload: dict
    ):
        response = await client.post("/api/v1/recipes", json=valid_recipe_payload)
        assert "Location" in response.headers
        recipe_id_str = response.json()["id"]
        assert isinstance(recipe_id_str, str)
        try:
            uuid.UUID(recipe_id_str, version=4)
        except ValueError:
            pytest.fail(f"Returned id '{recipe_id_str}' is not a valid UUID string.")

        expected_location = f"/api/v1/recipes/{recipe_id_str}"
        assert response.headers["Location"] == expected_location

    async def test_create_recipe_response_contains_id(
        self, client: AsyncClient, valid_recipe_payload: dict
    ):
        response = await client.post("/api/v1/recipes", json=valid_recipe_payload)
        response_json = response.json()
        assert "id" in response_json
        recipe_id_str = response_json["id"]
        assert isinstance(recipe_id_str, str)
        try:
            uuid.UUID(recipe_id_str, version=4)
        except ValueError:
            pytest.fail(f"Returned id '{recipe_id_str}' is not a valid UUID string.")

    async def test_create_recipe_response_contains_payload_data(
        self, client: AsyncClient, valid_recipe_payload: dict
    ):
        response = await client.post("/api/v1/recipes", json=valid_recipe_payload)
        response_json = response.json()
        assert response_json["name"] == valid_recipe_payload["name"]
        assert response_json["ingredients"] == valid_recipe_payload["ingredients"]
        assert response_json["instructions"] == valid_recipe_payload["instructions"]


@pytest.mark.usefixtures("client")
class TestCreateRecipeValidation:
    async def _post_recipe(self, client: AsyncClient, payload: dict):
        return await client.post("/api/v1/recipes", json=payload)

    @pytest.mark.parametrize(
        "invalid_payload, expected_error_detail",
        [
            (
                {"ingredients": ["i1"], "instructions": ["s1"]},
                [
                    {
                        "loc": ("name",),
                        "msg": "Field required",
                        "type": "missing",
                    }
                ],
            ),
            (
                {"name": "Test", "instructions": ["s1"]},
                [
                    {
                        "loc": ("ingredients",),
                        "msg": "Field required",
                        "type": "missing",
                    }
                ],
            ),
            (
                {"name": "Test", "ingredients": ["i1"]},
                [
                    {
                        "loc": ("instructions",),
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
                        "loc": ("name",),
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
                        "loc": ("ingredients",),
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
                        "loc": ("instructions",),
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
            # Convert actual 'loc' list to tuple for comparison
            if "loc" in filtered_error and isinstance(filtered_error["loc"], list):
                filtered_error["loc"] = tuple(filtered_error["loc"])
            actual_detail_filtered.append(filtered_error)

        for error in actual_detail_filtered:
            if isinstance(error.get("type"), str) and "." in error["type"]:
                error["type"] = error["type"].split(".")[-1]

        assert actual_detail_filtered == expected_error_detail
