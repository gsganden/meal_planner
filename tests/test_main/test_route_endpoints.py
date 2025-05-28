"""Tests for route handlers defined in meal_planner.main."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from meal_planner.main import CSS_ERROR_CLASS
from meal_planner.models import RecipeBase
from tests.constants import (
    FIELD_INGREDIENTS,
    FIELD_INSTRUCTIONS,
    FIELD_NAME,
    FIELD_ORIGINAL_INGREDIENTS,
    FIELD_ORIGINAL_INSTRUCTIONS,
    FIELD_ORIGINAL_NAME,
)
from tests.test_helpers import (
    create_mock_api_response,
)


@pytest.mark.anyio
class TestUpdateDiffEndpoint:
    UPDATE_DIFF_URL = "/recipes/ui/update-diff"

    def _build_diff_form_data(
        self, current: RecipeBase, original: RecipeBase | None = None
    ) -> dict:
        if original is None:
            original = current
        form_data = {
            FIELD_NAME: current.name,
            FIELD_INGREDIENTS: current.ingredients,
            FIELD_INSTRUCTIONS: current.instructions,
            FIELD_ORIGINAL_NAME: original.name,
            FIELD_ORIGINAL_INGREDIENTS: original.ingredients,
            FIELD_ORIGINAL_INSTRUCTIONS: original.instructions,
        }
        return form_data

    @patch("meal_planner.main.build_diff_content_children")
    @patch("meal_planner.main.logger.error")
    async def test_diff_generation_error(
        self, mock_logger_error, mock_build_diff, client: AsyncClient
    ):
        diff_exception = Exception("Simulated diff error")
        mock_build_diff.side_effect = diff_exception
        recipe = RecipeBase(name="Error Recipe", ingredients=["i"], instructions=["s"])
        form_data = self._build_diff_form_data(recipe, recipe)

        response = await client.post(self.UPDATE_DIFF_URL, data=form_data)
        assert response.status_code == 200
        html = response.text
        assert f'class="{CSS_ERROR_CLASS}"' in html
        assert "Error updating diff view" in html

        mock_build_diff.assert_called_once()
        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        assert args[0] == "Error updating diff: %s"
        assert args[1] is diff_exception
        assert kwargs.get("exc_info") is True

    @pytest.mark.parametrize(
        "invalid_field, invalid_value, error_title_suffix",
        [
            pytest.param(FIELD_NAME, "", "curr_name", id="current_empty_name"),
            pytest.param(
                FIELD_INGREDIENTS, [""], "curr_ing", id="current_empty_ingredient"
            ),
            pytest.param(
                FIELD_ORIGINAL_NAME, "", "orig_name", id="original_empty_name"
            ),
            pytest.param(
                FIELD_ORIGINAL_INGREDIENTS,
                [""],
                "orig_ing",
                id="original_empty_ingredient",
            ),
        ],
    )
    @patch("meal_planner.main.logger.warning")
    async def test_update_diff_validation_error(
        self,
        mock_logger_warning,
        client: AsyncClient,
        invalid_field: str,
        invalid_value: str | list[str],
        error_title_suffix: str,
    ):
        """Test that update diff returns 200 OK even with empty list inputs,
        as validation might happen later."""
        valid_recipe = RecipeBase(name="Valid", ingredients=["i"], instructions=["s"])
        form_data = self._build_diff_form_data(valid_recipe, valid_recipe)
        form_data[invalid_field] = invalid_value

        response = await client.post(self.UPDATE_DIFF_URL, data=form_data)

        assert response.status_code == 200
        html = response.text
        assert "Recipe state invalid for diff. Please check all fields." in html
        assert "diff-content-wrapper" not in html

        mock_logger_warning.assert_called_once()
        args, kwargs = mock_logger_warning.call_args
        assert args[0] == "Validation error during diff update: %s"
        assert isinstance(args[1], ValidationError)
        assert kwargs.get("exc_info") is False

    @pytest.mark.anyio
    @patch("meal_planner.main._parse_recipe_form_data")
    async def test_update_diff_parsing_exception(self, mock_parse, client: AsyncClient):
        "Test generic exception during form parsing in post_update_diff."
        mock_parse.side_effect = Exception("Simulated parsing error")
        dummy_form_data = {FIELD_NAME: "Test", "original_name": "Orig"}

        response = await client.post(
            TestUpdateDiffEndpoint.UPDATE_DIFF_URL, data=dummy_form_data
        )

        assert response.status_code == 200
        assert "Error updating diff view." in response.text
        assert CSS_ERROR_CLASS in response.text
        assert mock_parse.call_count == 1


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
