"""Tests for route handlers defined in meal_planner.routers.actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from bs4 import BeautifulSoup
from httpx import AsyncClient

from meal_planner.main import CSS_ERROR_CLASS
from tests.constants import (
    FIELD_INGREDIENTS,
    FIELD_INSTRUCTIONS,
    FIELD_NAME,
    RECIPES_SAVE_URL,
)


@pytest.mark.anyio
class TestSaveRecipeEndpoint:
    @pytest.mark.anyio
    async def test_save_recipe_success(self, client: AsyncClient):
        form_data = {
            FIELD_NAME: "Saved Recipe Name",
            FIELD_INGREDIENTS: ["saved ing 1", "saved ing 2"],
            FIELD_INSTRUCTIONS: ["saved inst 1", "saved inst 2"],
        }

        save_response = await client.post(RECIPES_SAVE_URL, data=form_data)
        assert save_response.status_code == 200

        soup = BeautifulSoup(save_response.text, "html.parser")
        span_tag = soup.find("span", id="save-button-container")
        assert span_tag is not None, "Save success message span not found"
        assert "Current Recipe Saved!" in span_tag.get_text(strip=True), (
            "Success message text not found"
        )

        assert "HX-Trigger" in save_response.headers, "HX-Trigger header missing"
        assert save_response.headers["HX-Trigger"] == "recipeListChanged", (
            "HX-Trigger header incorrect"
        )

        get_all_response = await client.get("/api/v0/recipes")
        assert get_all_response.status_code == 200
        all_recipes_data = get_all_response.json()

        saved_recipe_api_data = None
        for recipe in all_recipes_data:
            if recipe["name"] == form_data[FIELD_NAME]:
                saved_recipe_api_data = recipe
                break

        assert saved_recipe_api_data is not None, (
            f"Recipe named '{form_data[FIELD_NAME]}' not found in API response"
        )
        saved_recipe_id = saved_recipe_api_data["id"]
        assert isinstance(saved_recipe_id, int)

        get_one_response = await client.get(f"/api/v0/recipes/{saved_recipe_id}")
        assert get_one_response.status_code == 200
        fetched_recipe = get_one_response.json()

        assert fetched_recipe["name"] == form_data[FIELD_NAME]
        assert fetched_recipe["ingredients"] == form_data[FIELD_INGREDIENTS]
        assert fetched_recipe["instructions"] == form_data[FIELD_INSTRUCTIONS]
        assert fetched_recipe["id"] == saved_recipe_id

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "form_data, expected_error_message, test_id",
        [
            pytest.param(
                {FIELD_NAME: "Only Name"},
                "Invalid recipe data. Please check the fields.",
                "missing_ingredients",
                id="missing_ingredients",
            ),
            pytest.param(
                {FIELD_INGREDIENTS: ["i"], FIELD_INSTRUCTIONS: ["s"]},
                "Invalid recipe data. Please check the fields.",
                "missing_name",
                id="missing_name",
            ),
        ],
    )
    async def test_save_recipe_missing_data(
        self,
        client: AsyncClient,
        form_data: dict,
        expected_error_message: str,
        test_id: str,
    ):
        response = await client.post(RECIPES_SAVE_URL, data=form_data)
        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")
        error_span = soup.find("span", id="save-button-container")
        assert error_span is not None
        assert error_span.get_text(strip=True) == expected_error_message

    @pytest.mark.anyio
    async def test_save_recipe_api_call_error(self, client: AsyncClient, monkeypatch):
        """Test error handling when the internal API call fails."""
        mock_post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "API Error",
                request=httpx.Request("POST", "/api/v0/recipes"),
                response=httpx.Response(500, content=b"Internal Server Error"),
            )
        )
        monkeypatch.setattr(
            "meal_planner.routers.actions.internal_client.post", mock_post
        )

        form_data = {
            FIELD_NAME: "API Error Test",
            FIELD_INGREDIENTS: ["ingredient"],
            FIELD_INSTRUCTIONS: ["instruction"],
        }
        response = await client.post(RECIPES_SAVE_URL, data=form_data)
        assert response.status_code == 200
        assert (
            "Could not save recipe. Please check input and try again." in response.text
        )

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "invalid_form_data, expected_error_message, test_id",
        [
            pytest.param(
                {FIELD_NAME: "", FIELD_INGREDIENTS: ["i1"], FIELD_INSTRUCTIONS: ["s1"]},
                "Invalid recipe data. Please check the fields.",
                "empty_name",
                id="empty_name",
            ),
            pytest.param(
                {
                    FIELD_NAME: "Valid",
                    FIELD_INGREDIENTS: [""],
                    FIELD_INSTRUCTIONS: ["s1"],
                },
                "Invalid recipe data. Please check the fields.",
                "empty_ingredient",
                id="empty_ingredient",
            ),
        ],
    )
    async def test_save_recipe_validation_error(
        self,
        client: AsyncClient,
        invalid_form_data: dict,
        expected_error_message: str,
        test_id: str,
    ):
        """Test saving recipe with data that causes Pydantic validation errors."""
        response = await client.post(RECIPES_SAVE_URL, data=invalid_form_data)
        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")
        error_span = soup.find("span", id="save-button-container")
        assert error_span is not None
        assert error_span.get_text(strip=True) == expected_error_message

    @pytest.mark.anyio
    @patch("meal_planner.routers.actions._parse_recipe_form_data")
    async def test_save_recipe_parsing_exception(self, mock_parse, client: AsyncClient):
        "Test generic exception during form parsing in post_save_recipe."
        mock_parse.side_effect = Exception("Simulated parsing error")
        dummy_form_data = {
            FIELD_NAME: "Test",
            FIELD_INGREDIENTS: ["i"],
            FIELD_INSTRUCTIONS: ["s"],
        }

        response = await client.post(RECIPES_SAVE_URL, data=dummy_form_data)

        assert response.status_code == 200
        assert "Error processing form data." in response.text
        assert CSS_ERROR_CLASS in response.text
        mock_parse.assert_called_once()

    @pytest.mark.anyio
    async def test_save_recipe_api_call_generic_error(
        self, client: AsyncClient, monkeypatch
    ):
        """Test error handling when the internal API call raises a generic exception."""
        mock_post = AsyncMock(side_effect=Exception("Unexpected network issue"))
        monkeypatch.setattr(
            "meal_planner.routers.actions.internal_client.post", mock_post
        )

        form_data = {
            FIELD_NAME: "Generic API Error Test",
            FIELD_INGREDIENTS: ["ingredient"],
            FIELD_INSTRUCTIONS: ["instruction"],
        }
        response = await client.post(RECIPES_SAVE_URL, data=form_data)
        assert response.status_code == 200
        assert "An unexpected error occurred while saving the recipe." in response.text

    @pytest.mark.anyio
    async def test_save_recipe_api_call_request_error(
        self, client: AsyncClient, monkeypatch
    ):
        """Test error handling when the internal API call raises a RequestError."""
        mock_post = AsyncMock(side_effect=httpx.RequestError("Network issue"))
        monkeypatch.setattr(
            "meal_planner.routers.actions.internal_client.post", mock_post
        )

        form_data = {
            FIELD_NAME: "Request Error Test",
            FIELD_INGREDIENTS: ["ingredient"],
            FIELD_INSTRUCTIONS: ["instruction"],
        }
        response = await client.post(RECIPES_SAVE_URL, data=form_data)
        assert response.status_code == 200
        assert (
            "Could not save recipe due to a network issue. Please try again."
            in response.text
        )

    @pytest.mark.anyio
    async def test_save_recipe_api_call_non_json_error_response(
        self, client: AsyncClient, monkeypatch
    ):
        """Test error handling when the API returns a non-JSON error response."""
        mock_response = httpx.Response(
            status_code=500,
            content=b"<html><body>Internal Server Error</body></html>",
            headers={"content-type": "text/html"},
        )
        mock_post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Server Error",
                request=httpx.Request("POST", "/api/v0/recipes"),
                response=mock_response,
            )
        )
        monkeypatch.setattr(
            "meal_planner.routers.actions.internal_client.post", mock_post
        )

        form_data = {
            FIELD_NAME: "Non-JSON Error Test",
            FIELD_INGREDIENTS: ["ingredient"],
            FIELD_INSTRUCTIONS: ["instruction"],
        }
        response = await client.post(RECIPES_SAVE_URL, data=form_data)
        assert response.status_code == 200
        assert (
            "Could not save recipe. Please check input and try again." in response.text
        )

    @pytest.mark.anyio
    async def test_save_recipe_api_call_422_error(
        self, client: AsyncClient, monkeypatch
    ):
        """Test error handling when the API returns a 422 Unprocessable Entity error."""
        mock_response = httpx.Response(
            status_code=422,
            json={"detail": "Validation error"},
        )
        mock_post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Validation Error",
                request=httpx.Request("POST", "/api/v0/recipes"),
                response=mock_response,
            )
        )
        monkeypatch.setattr(
            "meal_planner.routers.actions.internal_client.post", mock_post
        )

        form_data = {
            FIELD_NAME: "422 Error Test",
            FIELD_INGREDIENTS: ["ingredient"],
            FIELD_INSTRUCTIONS: ["instruction"],
        }
        response = await client.post(RECIPES_SAVE_URL, data=form_data)
        assert response.status_code == 200
        assert "Could not save recipe: Invalid data for some fields." in response.text

    @pytest.mark.anyio
    @patch("meal_planner.routers.actions.logger.debug")
    async def test_save_recipe_api_call_json_error_with_detail(
        self, mock_logger_debug: MagicMock, client: AsyncClient, monkeypatch
    ):
        """Test error handling when the API returns a JSON error response with
        detail."""
        error_detail = "Specific validation error message"
        mock_response = httpx.Response(
            status_code=400,
            json={"detail": error_detail},
        )
        mock_post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Bad Request",
                request=httpx.Request("POST", "/api/v0/recipes"),
                response=mock_response,
            )
        )
        monkeypatch.setattr(
            "meal_planner.routers.actions.internal_client.post", mock_post
        )

        form_data = {
            FIELD_NAME: "JSON Error Test",
            FIELD_INGREDIENTS: ["ingredient"],
            FIELD_INSTRUCTIONS: ["instruction"],
        }
        response = await client.post(RECIPES_SAVE_URL, data=form_data)
        assert response.status_code == 200
        assert (
            "Could not save recipe. Please check input and try again." in response.text
        )
