from unittest.mock import AsyncMock, patch

import httpx  # for httpx.HTTPStatusError
import pytest
from httpx import AsyncClient, Request, Response

from tests.constants import RECIPES_LIST_PATH
from tests.test_helpers import create_mock_api_response


@pytest.mark.anyio
async def test_root(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    assert "Meal Planner" in response.text


@pytest.mark.anyio
class TestGetRecipeListPage:
    @patch("meal_planner.routers.pages.internal_api_client", autospec=True)
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

        response = await client.get(RECIPES_LIST_PATH)
        assert response.status_code == 200
        assert "<title>Error</title>" in response.text
        assert "Error fetching recipes from API." in response.text
        assert 'id="recipe-list-area"' in response.text
        mock_api_client.get.assert_called_once_with("/v0/recipes")

    @patch("meal_planner.routers.pages.internal_api_client", autospec=True)
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
        response = await client.get(RECIPES_LIST_PATH, headers=headers)

        assert response.status_code == 200
        assert "<title>" not in response.text
        assert 'id="recipe-list-area"' in response.text
        assert "Error fetching recipes from API." in response.text
        mock_api_client.get.assert_called_once_with("/v0/recipes")

    @patch("meal_planner.routers.pages.internal_api_client", autospec=True)
    async def test_get_recipes_page_api_generic_error(
        self,
        mock_api_client: AsyncMock,
        client: AsyncClient,
    ):
        mock_api_client.get.side_effect = Exception("Generic API failure")

        response = await client.get(RECIPES_LIST_PATH)
        assert response.status_code == 200
        assert "<title>Error</title>" in response.text
        assert "An unexpected error occurred while fetching recipes." in response.text
        assert 'id="recipe-list-area"' in response.text
        mock_api_client.get.assert_called_once_with("/v0/recipes")

    @patch("meal_planner.routers.pages.internal_api_client", autospec=True)
    async def test_get_recipes_page_api_generic_error_htmx(
        self,
        mock_api_client: AsyncMock,
        client: AsyncClient,
    ):
        """Test generic error handling via HTMX request."""
        mock_api_client.get.side_effect = Exception("Generic API failure")

        headers = {"HX-Request": "true"}
        response = await client.get(RECIPES_LIST_PATH, headers=headers)

        assert response.status_code == 200
        assert "<title>" not in response.text
        assert 'id="recipe-list-area"' in response.text
        assert "An unexpected error occurred while fetching recipes." in response.text
        mock_api_client.get.assert_called_once_with("/v0/recipes")

    @patch("meal_planner.routers.pages.internal_api_client", autospec=True)
    async def test_get_recipes_page_success_with_data(
        self,
        mock_api_client: AsyncMock,
        client: AsyncClient,
    ):
        mock_api_client.get.return_value = create_mock_api_response(
            status_code=200, json_data=[{"id": 1, "name": "Recipe One"}]
        )

        response = await client.get(RECIPES_LIST_PATH)
        assert response.status_code == 200
        assert "<title>All Recipes</title>" in response.text
        assert 'id="recipe-list-area"' in response.text
        assert '<ul id="recipe-list-ul">' in response.text
        assert "Recipe One" in response.text
        assert 'id="recipe-item-1"' in response.text
        mock_api_client.get.assert_called_once_with("/v0/recipes")

    @patch("meal_planner.routers.pages.internal_api_client", autospec=True)
    async def test_get_recipes_page_success_htmx(
        self,
        mock_api_client: AsyncMock,
        client: AsyncClient,
    ):
        """Test successful recipe list retrieval via HTMX request."""
        mock_api_client.get.return_value = create_mock_api_response(
            status_code=200, json_data=[{"id": 1, "name": "Recipe One HTMX"}]
        )

        headers = {"HX-Request": "true"}
        response = await client.get(RECIPES_LIST_PATH, headers=headers)

        assert response.status_code == 200
        assert "<title>" not in response.text
        assert 'id="recipe-list-area"' in response.text
        assert '<ul id="recipe-list-ul">' in response.text
        assert "Recipe One HTMX" in response.text
        assert 'id="recipe-item-1"' in response.text
        mock_api_client.get.assert_called_once_with("/v0/recipes")

    @patch("meal_planner.routers.pages.internal_api_client", autospec=True)
    async def test_get_recipes_page_success_no_data(
        self,
        mock_api_client: AsyncMock,
        client: AsyncClient,
    ):
        mock_api_client.get.return_value = create_mock_api_response(
            status_code=200, json_data=[]
        )

        response = await client.get(RECIPES_LIST_PATH)
        assert response.status_code == 200
        assert "<title>All Recipes</title>" in response.text
        assert "No recipes found." in response.text
        assert 'id="recipe-list-area"' in response.text
        mock_api_client.get.assert_called_once_with("/v0/recipes")
