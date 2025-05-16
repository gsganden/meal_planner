"""Tests for page rendering and top-level endpoint error handling."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import AsyncClient, Request, Response

from tests import constants
from tests.helpers import create_mock_api_response


@pytest.mark.anyio
class TestSmokeEndpoints:
    async def test_root(self, client: AsyncClient):
        response = await client.get("/")
        assert response.status_code == 200
        assert "Meal Planner" in response.text

    async def test_extract_recipe_page_loads(self, client: AsyncClient):
        response = await client.get(constants.RECIPES_EXTRACT_URL)
        assert response.status_code == 200
        assert 'id="input_url"' in response.text
        assert 'name="input_url"' in response.text
        assert 'placeholder="https://example.com/recipe"' in response.text
        assert f'hx-post="{constants.RECIPES_FETCH_TEXT_URL}"' in response.text
        assert "hx-include=\"[name='input_url']\"" in response.text
        assert "Fetch Text from URL" in response.text
        assert 'id="recipe_text"' in response.text
        assert (
            'placeholder="Paste full recipe text here, or fetch from URL above."'
            in response.text
        )
        assert f'hx-post="{constants.RECIPES_EXTRACT_RUN_URL}"' in response.text
        assert "Extract Recipe" in response.text
        assert 'id="recipe-results"' in response.text


@pytest.mark.anyio
class TestGetRecipesPageErrors:
    @patch("meal_planner.main.internal_api_client", autospec=True)
    async def test_get_recipes_page_api_status_error(
        self,
        mock_api_client: AsyncMock,
        client: AsyncClient,
    ):
        http_error = httpx.HTTPStatusError(
            "Internal Server Error",
            request=Request("GET", "/v0/recipes"),
            response=Response(500, request=Request("GET", "/v0/recipes")),
        )
        mock_api_client.get.return_value = create_mock_api_response(
            status_code=500, error_to_raise=http_error
        )

        response = await client.get(constants.RECIPES_LIST_PATH)
        assert response.status_code == 200
        assert "<title>Meal Planner</title>" in response.text
        assert "Error fetching recipes from API." in response.text
        assert 'id="recipe-list-area"' in response.text
        mock_api_client.get.assert_called_once_with("/v0/recipes")

    @patch("meal_planner.main.internal_api_client", autospec=True)
    async def test_get_recipes_page_api_error_htmx(
        self,
        mock_api_client: AsyncMock,
        client: AsyncClient,
    ):
        """Test API error handling via HTMX request."""
        http_error = httpx.HTTPStatusError(
            "Internal Server Error",
            request=Request("GET", "/v0/recipes"),
            response=Response(500, request=Request("GET", "/v0/recipes")),
        )
        mock_api_client.get.return_value = create_mock_api_response(
            status_code=500, error_to_raise=http_error
        )

        headers = {"HX-Request": "true"}
        response = await client.get(constants.RECIPES_LIST_PATH, headers=headers)

        assert response.status_code == 200
        assert "<title>Meal Planner</title>" not in response.text
        assert 'id="recipe-list-area"' in response.text
        assert "Error fetching recipes from API." in response.text
        mock_api_client.get.assert_called_once_with("/v0/recipes")

    @patch("meal_planner.main.internal_api_client", autospec=True)
    async def test_get_recipes_page_api_generic_error(
        self,
        mock_api_client: AsyncMock,
        client: AsyncClient,
    ):
        mock_api_client.get.side_effect = Exception("Generic API failure")

        response = await client.get(constants.RECIPES_LIST_PATH)
        assert response.status_code == 200
        assert "<title>Meal Planner</title>" in response.text
        assert "An unexpected error occurred while fetching recipes." in response.text
        assert 'id="recipe-list-area"' in response.text
        mock_api_client.get.assert_called_once_with("/v0/recipes")


@pytest.mark.anyio
class TestGetSingleRecipePageErrors:
    RECIPE_ID = 123
    API_URL = f"/api/v0/recipes/{RECIPE_ID}"
    PAGE_URL = f"/recipes/{RECIPE_ID}"

    @patch("meal_planner.main.internal_client.get")
    async def test_get_single_recipe_page_api_other_status_error(
        self, mock_api_get, client: AsyncClient
    ):
        """Test handling when the API returns a non-404 status error."""
        mock_api_get.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=httpx.Request("GET", self.API_URL),
            response=httpx.Response(500),
        )
        response = await client.get(self.PAGE_URL)
        assert response.status_code == 200
        assert "Error fetching recipe from API." in response.text
        assert "Error" in response.text
        mock_api_get.assert_awaited_once_with(self.API_URL)

    @patch("meal_planner.main.internal_client.get")
    async def test_get_single_recipe_page_api_generic_error(
        self, mock_api_get, client: AsyncClient
    ):
        """Test handling when the API call raises a generic exception."""
        mock_api_get.side_effect = Exception("Unexpected API failure")
        response = await client.get(self.PAGE_URL)
        assert response.status_code == 200
        assert "An unexpected error occurred." in response.text
        mock_api_get.assert_awaited_once_with(self.API_URL)
