from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, Response  # Added Response

# Imports from meal_planner


def create_mock_api_response(
    status_code: int,
    json_data: list | dict | None = None,
    error_to_raise: Exception | None = None,
) -> AsyncMock:
    mock_resp = AsyncMock(spec=Response)
    mock_resp.status_code = status_code
    if json_data is not None:
        mock_resp.json = MagicMock(return_value=json_data)
    else:
        mock_resp.json = MagicMock(
            return_value={}
        )  # Default to empty dict if no json_data

    if error_to_raise:
        mock_resp.raise_for_status = MagicMock(side_effect=error_to_raise)
    else:
        mock_resp.raise_for_status = MagicMock()  # No error to raise
    return mock_resp


# Constants
RECIPES_LIST_PATH = "/recipes"


@pytest.mark.anyio
class TestGetRecipesPageSuccess:
    @patch("meal_planner.main.internal_api_client", autospec=True)
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
        assert "<title>Meal Planner</title>" in response.text
        assert 'id="recipe-list-area"' in response.text
        assert '<ul id="recipe-list-ul">' in response.text  # Check for the list
        assert "Recipe One" in response.text  # Check for recipe name
        assert 'id="recipe-item-1"' in response.text  # Check for recipe item id
        mock_api_client.get.assert_called_once_with("/v0/recipes")

    @patch("meal_planner.main.internal_api_client", autospec=True)
    async def test_get_recipes_page_success_htmx(
        self,
        mock_api_client: AsyncMock,
        client: AsyncClient,
    ):
        mock_api_client.get.return_value = create_mock_api_response(
            status_code=200, json_data=[{"id": 2, "name": "Recipe Two HTMX"}]
        )
        headers = {"HX-Request": "true"}
        response = await client.get(RECIPES_LIST_PATH, headers=headers)

        assert response.status_code == 200
        assert (
            "<title>Meal Planner</title>" not in response.text
        )  # Should be a fragment
        assert 'id="recipe-list-area"' in response.text
        assert "All Recipes" in response.text  # Part of the Titled component
        assert '<ul id="recipe-list-ul">' in response.text
        assert "Recipe Two HTMX" in response.text
        assert 'id="recipe-item-2"' in response.text
        mock_api_client.get.assert_called_once_with("/v0/recipes")

    @patch("meal_planner.main.internal_api_client", autospec=True)
    async def test_get_recipes_page_success_no_data(
        self,
        mock_api_client: AsyncMock,
        client: AsyncClient,
    ):
        mock_api_client.get.return_value = create_mock_api_response(
            status_code=200,
            json_data=[],  # Empty list
        )

        response = await client.get(RECIPES_LIST_PATH)
        assert response.status_code == 200
        assert "<title>Meal Planner</title>" in response.text
        assert "No recipes found." in response.text  # Check for the message
        assert 'id="recipe-list-area"' in response.text
        mock_api_client.get.assert_called_once_with("/v0/recipes")


@pytest.mark.anyio
class TestGetSingleRecipePageSuccess:
    # Test with a recipe that needs to be created via API first to ensure it exists
    async def test_get_single_recipe_page_success(self, client: AsyncClient):
        # Create a recipe first to ensure it exists
        recipe_payload = {
            "name": "Specific Page Success Test Recipe",
            "ingredients": ["Specific Ing A", "Specific Ing B"],
            "instructions": ["Specific Instruction 1.", "Specific Instruction 2."],
        }
        create_resp = await client.post("/api/v0/recipes", json=recipe_payload)
        assert create_resp.status_code == 201  # Ensure creation was successful
        created_recipe_id = create_resp.json()["id"]

        page_url = f"/recipes/{created_recipe_id}"
        response = await client.get(page_url)
        assert response.status_code == 200
        html_content = response.text

        assert recipe_payload["name"] in html_content
        assert recipe_payload["ingredients"][0] in html_content
        assert recipe_payload["instructions"][0] in html_content
        # Check for layout to confirm it's not an HTMX fragment by mistake
        assert "<title>Meal Planner</title>" in html_content
        assert "Meal Planner" in html_content  # Check for sidebar text
