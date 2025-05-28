"""Tests for route handlers defined in meal_planner.main."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import AsyncClient

from tests.constants import (
    RECIPES_FETCH_TEXT_URL,
)
from tests.test_helpers import (
    create_mock_api_response,
)


@pytest.mark.anyio
class TestDeleteRecipeEndpoint:
    DELETE_PATH = "/recipes/delete"

    @patch("meal_planner.main.internal_api_client", autospec=True)
    async def test_delete_recipe_success(
        self,
        mock_api_client: AsyncMock,
        client: AsyncClient,
    ):
        """Test successful recipe deletion."""
        mock_api_client.delete.return_value = create_mock_api_response(status_code=204)

        response = await client.post(self.DELETE_PATH, params={"id": 123})
        assert response.status_code == 200
        assert response.headers.get("HX-Trigger") == "recipeListChanged"
        mock_api_client.delete.assert_called_once_with("/v0/recipes/123")

    @patch("meal_planner.main.internal_api_client", autospec=True)
    async def test_delete_recipe_not_found(
        self,
        mock_api_client: AsyncMock,
        client: AsyncClient,
    ):
        """Test deletion of non-existent recipe."""
        http_error = httpx.HTTPStatusError(
            "Not Found",
            request=httpx.Request("DELETE", "/v0/recipes/999"),
            response=httpx.Response(404),
        )
        mock_api_client.delete.return_value = create_mock_api_response(
            status_code=404, error_to_raise=http_error
        )

        response = await client.post(self.DELETE_PATH, params={"id": 999})
        assert response.status_code == 404
        mock_api_client.delete.assert_called_once_with("/v0/recipes/999")

    @patch("meal_planner.main.internal_api_client", autospec=True)
    async def test_delete_recipe_api_error(
        self,
        mock_api_client: AsyncMock,
        client: AsyncClient,
    ):
        """Test API error during deletion."""
        http_error = httpx.HTTPStatusError(
            "Internal Server Error",
            request=httpx.Request("DELETE", "/v0/recipes/123"),
            response=httpx.Response(500),
        )
        mock_api_client.delete.return_value = create_mock_api_response(
            status_code=500, error_to_raise=http_error
        )

        response = await client.post(self.DELETE_PATH, params={"id": 123})
        assert response.status_code == 500
        mock_api_client.delete.assert_called_once_with("/v0/recipes/123")

    @patch("meal_planner.main.internal_api_client", autospec=True)
    async def test_delete_recipe_generic_error(
        self,
        mock_api_client: AsyncMock,
        client: AsyncClient,
    ):
        """Test generic error during deletion."""
        mock_api_client.delete.side_effect = Exception("Generic API failure")

        response = await client.post(self.DELETE_PATH, params={"id": 123})
        assert response.status_code == 500
        mock_api_client.delete.assert_called_once_with("/v0/recipes/123")


@pytest.mark.anyio
class TestFetchTextEndpoint:
    FETCH_TEXT_URL = RECIPES_FETCH_TEXT_URL
