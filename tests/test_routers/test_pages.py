from unittest.mock import AsyncMock, patch

import httpx
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


@pytest.mark.anyio
class TestGetSingleRecipePage:
    RECIPE_ID = 123
    API_URL = f"/v0/recipes/{RECIPE_ID}"
    PAGE_URL = f"/recipes/{RECIPE_ID}"

    @patch("meal_planner.routers.pages.internal_api_client.get")
    async def test_get_single_recipe_page_api_404(
        self, mock_api_get, client: AsyncClient
    ):
        """Test handling when the API returns 404 for the recipe ID."""
        mock_api_get.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=Request("GET", self.API_URL),
            response=Response(404, request=Request("GET", self.API_URL)),
        )
        response = await client.get(self.PAGE_URL)
        assert response.status_code == 200
        assert "Recipe Not Found" in response.text
        mock_api_get.assert_awaited_once_with(self.API_URL)

    @patch("meal_planner.routers.pages.internal_api_client.get")
    async def test_get_single_recipe_page_api_other_status_error(
        self, mock_api_get, client: AsyncClient
    ):
        """Test handling when the API returns a non-404 status error."""
        mock_api_get.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=Request("GET", self.API_URL),
            response=Response(500, request=Request("GET", self.API_URL)),
        )
        response = await client.get(self.PAGE_URL)
        assert response.status_code == 200
        assert "Error fetching recipe from API." in response.text
        assert "Error" in response.text
        mock_api_get.assert_awaited_once_with(self.API_URL)

    @patch("meal_planner.routers.pages.internal_api_client.get")
    async def test_get_single_recipe_page_api_generic_error(
        self, mock_api_get, client: AsyncClient
    ):
        """Test handling when the API call raises a generic exception."""
        mock_api_get.side_effect = Exception("Unexpected API failure")
        response = await client.get(self.PAGE_URL)
        assert response.status_code == 200
        assert "An unexpected error occurred." in response.text
        mock_api_get.assert_awaited_once_with(self.API_URL)

    async def test_get_single_recipe_page_success(self, client: AsyncClient):
        recipe_payload = {
            "name": "Specific Recipe Page Test",
            "ingredients": ["Specific Ing 1", "Specific Ing 2"],
            "instructions": ["Specific Step 1.", "Specific Step 2."],
        }
        create_resp = await client.post("/api/v0/recipes", json=recipe_payload)
        assert create_resp.status_code == 201
        created_recipe_id = create_resp.json()["id"]

        page_url = f"/recipes/{created_recipe_id}"
        response = await client.get(page_url)
        assert response.status_code == 200
        html_content = response.text

        assert recipe_payload["name"] in html_content
        assert recipe_payload["ingredients"][0] in html_content
        assert recipe_payload["ingredients"][1] in html_content
        assert recipe_payload["instructions"][0] in html_content
        assert recipe_payload["instructions"][1] in html_content
