from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response

import meal_planner.api.recipes as recipes_api

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
        return await client.post("/api/v1/recipes", json=valid_recipe_payload)

    async def test_create_recipe_returns_201(self, create_recipe_response: Response):
        assert create_recipe_response.status_code == 201

    async def test_create_recipe_returns_location_header(
        self, create_recipe_response: Response
    ):
        assert "Location" in create_recipe_response.headers
        response_json = create_recipe_response.json()
        recipe_id_from_body = response_json["id"]
        expected_location = f"/api/v1/recipes/{recipe_id_from_body}"
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
            "/api/v1/recipes",
            content=invalid_json_string,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        assert "Invalid JSON payload" in response.text


@pytest.mark.usefixtures("client")
class TestCreateRecipeDBErrors:
    async def test_create_recipe_db_insert_error(
        self, client: AsyncClient, valid_recipe_payload: dict, monkeypatch
    ):
        def mock_insert(*args, **kwargs):
            raise Exception("Simulated DB Error")

        monkeypatch.setattr(recipes_api.recipes_table, "insert", mock_insert)

        response = await client.post("/api/v1/recipes", json=valid_recipe_payload)

        assert response.status_code == 500
        assert "Database error creating recipe" in response.text
