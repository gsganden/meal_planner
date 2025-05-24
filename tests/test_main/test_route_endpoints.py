"""Tests for route handlers defined in meal_planner.main."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from bs4 import BeautifulSoup
from httpx import ASGITransport, AsyncClient, Request, Response
from pydantic import ValidationError

from meal_planner.main import (
    CSS_ERROR_CLASS,
    app,
)
from meal_planner.models import RecipeBase
from tests.constants import (
    FIELD_INGREDIENTS,
    FIELD_INSTRUCTIONS,
    FIELD_NAME,
    FIELD_ORIGINAL_INGREDIENTS,
    FIELD_ORIGINAL_INSTRUCTIONS,
    FIELD_ORIGINAL_NAME,
    RECIPES_LIST_PATH,
    RECIPES_SAVE_URL,
)
from tests.test_helpers import (
    create_mock_api_response,
)

# Constants
TRANSPORT = ASGITransport(app=app)
TEST_URL = "http://test-recipe.com"


@pytest.mark.anyio
async def test_root(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    assert "Meal Planner" in response.text


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
        monkeypatch.setattr("meal_planner.main.internal_client.post", mock_post)

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
    @patch("meal_planner.main._parse_recipe_form_data")
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
        monkeypatch.setattr("meal_planner.main.internal_client.post", mock_post)

        form_data = {
            FIELD_NAME: "Generic API Error Test",
            FIELD_INGREDIENTS: ["ingredient"],
            FIELD_INSTRUCTIONS: ["instruction"],
        }
        response = await client.post(RECIPES_SAVE_URL, data=form_data)
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        error_span = soup.find("span", id="save-button-container")

        assert error_span is not None, "Error message container span not found."
        assert "An unexpected error occurred" in error_span.get_text(strip=True)

        mock_post.assert_awaited_once()

    @pytest.mark.anyio
    async def test_save_recipe_api_call_request_error(
        self, client: AsyncClient, monkeypatch
    ):
        """Test handling when the internal API call raises httpx.RequestError."""
        mock_post = AsyncMock(
            side_effect=httpx.RequestError(
                "Network error", request=httpx.Request("POST", "/api/v0/recipes")
            )
        )
        monkeypatch.setattr("meal_planner.main.internal_client.post", mock_post)

        form_data = {
            FIELD_NAME: "RequestError Test",
            FIELD_INGREDIENTS: ["ingredient"],
            FIELD_INSTRUCTIONS: ["instruction"],
        }
        response = await client.post(RECIPES_SAVE_URL, data=form_data)
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        error_span = soup.find("span", id="save-button-container")

        assert error_span is not None, "Error message container span not found."
        assert "due to a network issue" in error_span.get_text(strip=True)

        mock_post.assert_awaited_once()

    @pytest.mark.anyio
    async def test_save_recipe_api_call_non_json_error_response(
        self, client: AsyncClient, monkeypatch
    ):
        """Test handling when API returns non-201 status with non-JSON content."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.text = "Server Error Text, Not JSON"
        mock_response.json = MagicMock(side_effect=Exception("Invalid JSON"))

        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Server Error",
                request=Request("POST", "/api/v0/recipes"),
                response=mock_response,
            )
        )

        mock_post = AsyncMock(return_value=mock_response)
        monkeypatch.setattr("meal_planner.main.internal_client.post", mock_post)

        form_data = {
            FIELD_NAME: "Non Json Error Test",
            FIELD_INGREDIENTS: ["ingredient"],
            FIELD_INSTRUCTIONS: ["instruction"],
        }
        response = await client.post(RECIPES_SAVE_URL, data=form_data)
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        error_span = soup.find("span", id="save-button-container")

        assert error_span is not None, "Error message container span not found."
        assert "Could not save recipe. Please check input" in error_span.get_text(
            strip=True
        )

        mock_post.assert_awaited_once()

    @pytest.mark.anyio
    async def test_save_recipe_api_call_422_error(
        self, client: AsyncClient, monkeypatch
    ):
        """Test error handling for HTTP 422 error from the internal API."""
        mock_response_422 = AsyncMock(spec=httpx.Response)
        mock_response_422.status_code = 422
        mock_response_422.text = "Unprocessable Entity"
        mock_response_422.json = MagicMock(
            return_value={"detail": "API validation error"}
        )

        mock_post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "API 422 Error",
                request=httpx.Request("POST", "/api/v0/recipes"),
                response=mock_response_422,
            )
        )
        monkeypatch.setattr("meal_planner.main.internal_client.post", mock_post)

        form_data = {
            FIELD_NAME: "Test 422 Error",
            FIELD_INGREDIENTS: ["ingredient"],
            FIELD_INSTRUCTIONS: ["instruction"],
        }
        response = await client.post(RECIPES_SAVE_URL, data=form_data)
        assert response.status_code == 200
        expected_msg = "Could not save recipe: Invalid data for some fields."
        soup = BeautifulSoup(response.text, "html.parser")
        error_span = soup.find("span", id="save-button-container")
        assert error_span is not None
        assert error_span.get_text(strip=True) == expected_msg
        mock_post.assert_awaited_once()

    @pytest.mark.anyio
    @patch("meal_planner.main.logger.debug")
    async def test_save_recipe_api_call_json_error_with_detail(
        self, mock_logger_debug: MagicMock, client: AsyncClient, monkeypatch
    ):
        """Test error handling when internal API returns HTTPStatusError with JSON
        detail."""
        error_detail_text = "Specific error detail from JSON"

        mock_api_response = AsyncMock(spec=httpx.Response)
        mock_api_response.status_code = 400
        mock_api_response.text = f'{{"detail": "{error_detail_text}"}}'
        mock_api_response.json = MagicMock(return_value={"detail": error_detail_text})

        mock_post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "API JSON Error",
                request=httpx.Request("POST", "/api/v0/recipes"),
                response=mock_api_response,
            )
        )
        monkeypatch.setattr("meal_planner.main.internal_client.post", mock_post)

        form_data = {
            FIELD_NAME: "API JSON Error Test",
            FIELD_INGREDIENTS: ["ingredient"],
            FIELD_INSTRUCTIONS: ["instruction"],
        }
        response = await client.post(RECIPES_SAVE_URL, data=form_data)
        assert response.status_code == 200

        expected_user_msg = "Could not save recipe. Please check input and try again."
        soup = BeautifulSoup(response.text, "html.parser")
        error_span = soup.find("span", id="save-button-container")
        assert error_span is not None
        assert error_span.get_text(strip=True) == expected_user_msg

        mock_post.assert_awaited_once()


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
class TestGetRecipeListPage:
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

        response = await client.get(RECIPES_LIST_PATH)
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
        response = await client.get(RECIPES_LIST_PATH, headers=headers)

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

        response = await client.get(RECIPES_LIST_PATH)
        assert response.status_code == 200
        assert "<title>Meal Planner</title>" in response.text
        assert "An unexpected error occurred while fetching recipes." in response.text
        assert 'id="recipe-list-area"' in response.text
        mock_api_client.get.assert_called_once_with("/v0/recipes")

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
        assert '<ul id="recipe-list-ul">' in response.text
        assert "Recipe One" in response.text
        assert 'id="recipe-item-1"' in response.text
        mock_api_client.get.assert_called_once_with("/v0/recipes")

    @patch("meal_planner.main.internal_api_client", autospec=True)
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
        assert "<title>Meal Planner</title>" not in response.text
        assert 'id="recipe-list-area"' in response.text
        assert "All Recipes" in response.text
        assert '<ul id="recipe-list-ul">' in response.text
        assert "Recipe One HTMX" in response.text
        assert 'id="recipe-item-1"' in response.text
        mock_api_client.get.assert_called_once_with("/v0/recipes")

    @patch("meal_planner.main.internal_api_client", autospec=True)
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
        assert "<title>Meal Planner</title>" in response.text
        assert "No recipes found." in response.text
        assert 'id="recipe-list-area"' in response.text
        mock_api_client.get.assert_called_once_with("/v0/recipes")


@pytest.mark.anyio
class TestGetSingleRecipePage:
    RECIPE_ID = 123
    API_URL = f"/api/v0/recipes/{RECIPE_ID}"
    PAGE_URL = f"/recipes/{RECIPE_ID}"

    @patch("meal_planner.main.internal_client.get")
    async def test_get_single_recipe_page_api_404(
        self, mock_api_get, client: AsyncClient
    ):
        """Test handling when the API returns 404 for the recipe ID."""
        mock_api_get.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=httpx.Request("GET", self.API_URL),
            response=httpx.Response(404),
        )
        response = await client.get(self.PAGE_URL)
        assert response.status_code == 200
        assert "Recipe Not Found" in response.text
        mock_api_get.assert_awaited_once_with(self.API_URL)

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

    RECIPE_ID = 456
    API_URL = f"/api/v0/recipes/{RECIPE_ID}"
    PAGE_URL = f"/recipes/{RECIPE_ID}"

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
