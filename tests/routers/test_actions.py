"""Tests for route handlers defined in meal_planner.routers.actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from bs4 import BeautifulSoup, Tag
from httpx import AsyncClient
from pydantic import ValidationError

from meal_planner.models import RecipeBase
from meal_planner.ui.common import CSS_ERROR_CLASS
from tests.constants import (
    FIELD_INGREDIENTS,
    FIELD_INSTRUCTIONS,
    FIELD_MODIFICATION_PROMPT,
    FIELD_NAME,
    FIELD_ORIGINAL_INGREDIENTS,
    FIELD_ORIGINAL_INSTRUCTIONS,
    FIELD_ORIGINAL_NAME,
    RECIPES_MODIFY_URL,
    RECIPES_SAVE_URL,
)
from tests.test_helpers import (
    extract_current_recipe_data_from_html,
    extract_full_edit_form_data,
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


# Fixtures for TestModifyRecipeEndpoint
@pytest.fixture
def mock_original_recipe_fixture() -> RecipeBase:
    return RecipeBase(
        name="Original Recipe",
        ingredients=["orig ing 1"],
        instructions=["orig inst 1"],
    )


@pytest.fixture
def mock_current_recipe_before_modify_fixture() -> RecipeBase:
    return RecipeBase(
        name="Current Recipe",
        ingredients=["curr ing 1"],
        instructions=["curr inst 1"],
    )


@pytest.fixture
def mock_llm_modified_recipe_fixture() -> RecipeBase:
    return RecipeBase(
        name="Modified",
        ingredients=["mod ing 1"],
        instructions=["mod inst 1"],
    )


@pytest.mark.anyio
class TestModifyRecipeEndpoint:
    @patch(
        "meal_planner.routers.actions.generate_modified_recipe", new_callable=AsyncMock
    )
    async def test_modify_recipe_happy_path(
        self,
        mock_llm_modify: AsyncMock,
        client: AsyncClient,
        mock_original_recipe_fixture: RecipeBase,
        mock_llm_modified_recipe_fixture: RecipeBase,
    ):
        """Test successful recipe modification and UI update."""
        mock_llm_modify.return_value = mock_llm_modified_recipe_fixture
        modification_prompt = "Make it spicier"

        current_recipe_before_llm = mock_original_recipe_fixture

        form_data = {
            FIELD_NAME: current_recipe_before_llm.name,
            FIELD_INGREDIENTS: current_recipe_before_llm.ingredients,
            FIELD_INSTRUCTIONS: current_recipe_before_llm.instructions,
            FIELD_ORIGINAL_NAME: mock_original_recipe_fixture.name,
            FIELD_ORIGINAL_INGREDIENTS: mock_original_recipe_fixture.ingredients,
            FIELD_ORIGINAL_INSTRUCTIONS: mock_original_recipe_fixture.instructions,
            FIELD_MODIFICATION_PROMPT: modification_prompt,
        }

        response = await client.post(RECIPES_MODIFY_URL, data=form_data)
        assert response.status_code == 200

        mock_llm_modify.assert_called_once_with(
            current_recipe=current_recipe_before_llm,
            modification_request=modification_prompt,
        )

        html_content = response.text

        current_data_from_html = extract_current_recipe_data_from_html(html_content)
        assert current_data_from_html["name"] == mock_llm_modified_recipe_fixture.name
        assert (
            current_data_from_html["ingredients"]
            == mock_llm_modified_recipe_fixture.ingredients
        )
        assert (
            current_data_from_html["instructions"]
            == mock_llm_modified_recipe_fixture.instructions
        )

        full_form_data_from_html = extract_full_edit_form_data(html_content)
        assert (
            full_form_data_from_html[FIELD_ORIGINAL_NAME]
            == mock_original_recipe_fixture.name
        )
        assert (
            full_form_data_from_html[FIELD_ORIGINAL_INGREDIENTS]
            == mock_original_recipe_fixture.ingredients
        )
        assert (
            full_form_data_from_html[FIELD_ORIGINAL_INSTRUCTIONS]
            == mock_original_recipe_fixture.instructions
        )

        soup = BeautifulSoup(html_content, "html.parser")
        review_section_oob_container = soup.find(
            "div", attrs={"hx-swap-oob": "innerHTML:#review-section-target"}
        )
        assert review_section_oob_container is not None, (
            "Review section OOB container not found"
        )
        assert isinstance(review_section_oob_container, Tag)

        review_card_div = review_section_oob_container.find("div", id="review-card")
        assert review_card_div is not None, (
            "Review card div not found within OOB container"
        )
        assert isinstance(review_card_div, Tag)

        assert mock_original_recipe_fixture.name in review_card_div.get_text(), (
            "Original recipe name not in review card"
        )
        for ing in mock_original_recipe_fixture.ingredients:
            assert ing in review_card_div.get_text(), (
                f"Original ingredient '{ing}' not in review card"
            )
        for inst in mock_original_recipe_fixture.instructions:
            assert inst in review_card_div.get_text(), (
                f"Original instruction '{inst}' not in review card"
            )

        diff_before_pre = soup.find("pre", id="diff-before-pre")
        diff_after_pre = soup.find("pre", id="diff-after-pre")
        assert diff_before_pre is not None, "Diff before <pre> not found"
        assert diff_after_pre is not None, "Diff after <pre> not found"

        original_recipe_text_parts = [
            f"# {mock_original_recipe_fixture.name}",
            *mock_original_recipe_fixture.ingredients,
            *mock_original_recipe_fixture.instructions,
        ]
        for part in original_recipe_text_parts:
            assert part in diff_before_pre.get_text(), f"'{part}' not in diff-before"

        llm_modified_recipe_text_parts = [
            f"# {mock_llm_modified_recipe_fixture.name}",
            *mock_llm_modified_recipe_fixture.ingredients,
            *mock_llm_modified_recipe_fixture.instructions,
        ]
        for part in llm_modified_recipe_text_parts:
            assert part in diff_after_pre.get_text(), f"'{part}' not in diff-after"

    @patch(
        "meal_planner.routers.actions.generate_modified_recipe", new_callable=AsyncMock
    )
    async def test_modify_recipe_initial_validation_error(
        self,
        mock_llm_modify: AsyncMock,
        client: AsyncClient,
        mock_original_recipe_fixture: RecipeBase,
    ):
        """Test UI response when initial form data fails Pydantic validation."""
        modification_prompt = "Make it vegan"

        invalid_form_data = {
            FIELD_NAME: "",
            FIELD_INGREDIENTS: mock_original_recipe_fixture.ingredients,
            FIELD_INSTRUCTIONS: mock_original_recipe_fixture.instructions,
            FIELD_ORIGINAL_NAME: mock_original_recipe_fixture.name,
            FIELD_ORIGINAL_INGREDIENTS: mock_original_recipe_fixture.ingredients,
            FIELD_ORIGINAL_INSTRUCTIONS: mock_original_recipe_fixture.instructions,
            FIELD_MODIFICATION_PROMPT: modification_prompt,
        }

        response = await client.post(RECIPES_MODIFY_URL, data=invalid_form_data)
        assert response.status_code == 200

        mock_llm_modify.assert_not_called()

        html_content = response.text
        soup = BeautifulSoup(html_content, "html.parser")

        error_div = soup.find(
            "div", string="Invalid recipe data. Please check the fields."
        )
        assert error_div is not None, "Validation error message not found"
        assert CSS_ERROR_CLASS in error_div.get("class", []), (
            "Error message does not have the error CSS class"
        )

        form_data_from_html = extract_full_edit_form_data(html_content)
        assert form_data_from_html[FIELD_NAME] == ""
        assert (
            form_data_from_html[FIELD_INGREDIENTS]
            == mock_original_recipe_fixture.ingredients
        )
        assert (
            form_data_from_html[FIELD_ORIGINAL_NAME]
            == mock_original_recipe_fixture.name
        )
        assert form_data_from_html[FIELD_MODIFICATION_PROMPT] == modification_prompt

        review_card_div = soup.find("div", id="review-card")
        assert review_card_div is not None, "Review card not found"
        assert mock_original_recipe_fixture.name in review_card_div.get_text()

    @patch(
        "meal_planner.routers.actions.generate_modified_recipe", new_callable=AsyncMock
    )
    async def test_modify_recipe_empty_prompt(
        self,
        mock_llm_modify: AsyncMock,
        client: AsyncClient,
        mock_current_recipe_before_modify_fixture: RecipeBase,
        mock_original_recipe_fixture: RecipeBase,
    ):
        """Test UI response when modification prompt is empty."""
        current_recipe = mock_current_recipe_before_modify_fixture
        original_recipe = mock_original_recipe_fixture

        form_data = {
            FIELD_NAME: current_recipe.name,
            FIELD_INGREDIENTS: current_recipe.ingredients,
            FIELD_INSTRUCTIONS: current_recipe.instructions,
            FIELD_ORIGINAL_NAME: original_recipe.name,
            FIELD_ORIGINAL_INGREDIENTS: original_recipe.ingredients,
            FIELD_ORIGINAL_INSTRUCTIONS: original_recipe.instructions,
            FIELD_MODIFICATION_PROMPT: "",
        }

        response = await client.post(RECIPES_MODIFY_URL, data=form_data)
        assert response.status_code == 200

        mock_llm_modify.assert_not_called()

        html_content = response.text
        soup = BeautifulSoup(html_content, "html.parser")

        error_div = soup.find("div", string="Please enter modification instructions.")
        assert error_div is not None, "Empty prompt error message not found"
        assert CSS_ERROR_CLASS in error_div.get("class", []), (
            "Error message does not have the error CSS class"
        )

        form_data_from_html = extract_full_edit_form_data(html_content)
        assert form_data_from_html[FIELD_NAME] == current_recipe.name
        assert form_data_from_html[FIELD_INGREDIENTS] == current_recipe.ingredients
        assert form_data_from_html[FIELD_ORIGINAL_NAME] == original_recipe.name
        assert form_data_from_html[FIELD_MODIFICATION_PROMPT] == ""

        review_card_div = soup.find("div", id="review-card")
        assert review_card_div is not None, "Review card not found"
        assert original_recipe.name in review_card_div.get_text()

    @patch(
        "meal_planner.routers.actions.generate_modified_recipe", new_callable=AsyncMock
    )
    @patch("meal_planner.routers.actions.postprocess_recipe")
    async def test_modify_recipe_postprocess_validation_error(
        self,
        mock_postprocess,
        mock_llm_modify: AsyncMock,
        client: AsyncClient,
        mock_current_recipe_before_modify_fixture: RecipeBase,
        mock_original_recipe_fixture: RecipeBase,
        mock_llm_modified_recipe_fixture: RecipeBase,
    ):
        """Test ValidationError during postprocessing after LLM success."""
        mock_llm_modify.return_value = mock_llm_modified_recipe_fixture

        validation_error = ValidationError.from_exception_data(
            title="PostprocessValidationError", line_errors=[]
        )
        mock_postprocess.side_effect = validation_error

        current_recipe = mock_current_recipe_before_modify_fixture
        original_recipe = mock_original_recipe_fixture
        modification_prompt = "Make it healthier"

        form_data = {
            FIELD_NAME: current_recipe.name,
            FIELD_INGREDIENTS: current_recipe.ingredients,
            FIELD_INSTRUCTIONS: current_recipe.instructions,
            FIELD_ORIGINAL_NAME: original_recipe.name,
            FIELD_ORIGINAL_INGREDIENTS: original_recipe.ingredients,
            FIELD_ORIGINAL_INSTRUCTIONS: original_recipe.instructions,
            FIELD_MODIFICATION_PROMPT: modification_prompt,
        }

        response = await client.post(RECIPES_MODIFY_URL, data=form_data)
        assert response.status_code == 200

        mock_llm_modify.assert_called_once_with(
            current_recipe=current_recipe, modification_request=modification_prompt
        )
        mock_postprocess.assert_called_once_with(mock_llm_modified_recipe_fixture)

        html_content = response.text
        soup = BeautifulSoup(html_content, "html.parser")

        error_div = soup.find(
            "div", string="Invalid recipe data after modification attempt."
        )
        assert error_div is not None, "Post-LLM validation error message not found"
        assert CSS_ERROR_CLASS in error_div.get("class", []), (
            "Error message does not have the error CSS class"
        )

        form_data_from_html = extract_full_edit_form_data(html_content)
        assert form_data_from_html[FIELD_NAME] == current_recipe.name
        assert form_data_from_html[FIELD_INGREDIENTS] == current_recipe.ingredients
        assert form_data_from_html[FIELD_MODIFICATION_PROMPT] == modification_prompt

    @patch(
        "meal_planner.routers.actions.generate_modified_recipe", new_callable=AsyncMock
    )
    async def test_modify_recipe_generic_exception(
        self,
        mock_llm_modify: AsyncMock,
        client: AsyncClient,
        mock_current_recipe_before_modify_fixture: RecipeBase,
        mock_original_recipe_fixture: RecipeBase,
    ):
        """Test generic Exception during modification flow."""
        generic_exception = TypeError("Unexpected error during recipe modification")
        mock_llm_modify.side_effect = generic_exception

        current_recipe = mock_current_recipe_before_modify_fixture
        original_recipe = mock_original_recipe_fixture
        modification_prompt = "Make it spicy"

        form_data = {
            FIELD_NAME: current_recipe.name,
            FIELD_INGREDIENTS: current_recipe.ingredients,
            FIELD_INSTRUCTIONS: current_recipe.instructions,
            FIELD_ORIGINAL_NAME: original_recipe.name,
            FIELD_ORIGINAL_INGREDIENTS: original_recipe.ingredients,
            FIELD_ORIGINAL_INSTRUCTIONS: original_recipe.instructions,
            FIELD_MODIFICATION_PROMPT: modification_prompt,
        }

        response = await client.post(RECIPES_MODIFY_URL, data=form_data)
        assert response.status_code == 200

        mock_llm_modify.assert_called_once_with(
            current_recipe=current_recipe, modification_request=modification_prompt
        )

        html_content = response.text
        soup = BeautifulSoup(html_content, "html.parser")

        error_div = soup.find(
            "div",
            string=(
                "Critical Error: An unexpected error occurred. "
                "Please refresh and try again."
            ),
        )
        assert error_div is not None, "Generic error message not found"
        assert CSS_ERROR_CLASS in error_div.get("class", []), (
            "Error message does not have the error CSS class"
        )

        form_data_from_html = extract_full_edit_form_data(html_content)
        assert form_data_from_html[FIELD_NAME] == current_recipe.name
        assert form_data_from_html[FIELD_INGREDIENTS] == current_recipe.ingredients
        assert form_data_from_html[FIELD_MODIFICATION_PROMPT] == modification_prompt

    @patch(
        "meal_planner.routers.actions.generate_modified_recipe", new_callable=AsyncMock
    )
    async def test_modify_recipe_runtime_error(
        self,
        mock_llm_modify: AsyncMock,
        client: AsyncClient,
        mock_current_recipe_before_modify_fixture: RecipeBase,
        mock_original_recipe_fixture: RecipeBase,
    ):
        """Test RuntimeError during LLM modification."""
        modification_error = RuntimeError("LLM service failed to modify recipe")
        mock_llm_modify.side_effect = modification_error

        current_recipe = mock_current_recipe_before_modify_fixture
        original_recipe = mock_original_recipe_fixture
        modification_prompt = "Make it gluten-free"

        form_data = {
            FIELD_NAME: current_recipe.name,
            FIELD_INGREDIENTS: current_recipe.ingredients,
            FIELD_INSTRUCTIONS: current_recipe.instructions,
            FIELD_ORIGINAL_NAME: original_recipe.name,
            FIELD_ORIGINAL_INGREDIENTS: original_recipe.ingredients,
            FIELD_ORIGINAL_INSTRUCTIONS: original_recipe.instructions,
            FIELD_MODIFICATION_PROMPT: modification_prompt,
        }

        response = await client.post(RECIPES_MODIFY_URL, data=form_data)
        assert response.status_code == 200

        mock_llm_modify.assert_called_once_with(
            current_recipe=current_recipe, modification_request=modification_prompt
        )

        html_content = response.text
        soup = BeautifulSoup(html_content, "html.parser")

        error_div = soup.find("div", string="LLM service failed to modify recipe")
        assert error_div is not None, "RuntimeError message not found"
        assert CSS_ERROR_CLASS in error_div.get("class", []), (
            "Error message does not have the error CSS class"
        )

        form_data_from_html = extract_full_edit_form_data(html_content)
        assert form_data_from_html[FIELD_NAME] == current_recipe.name
        assert form_data_from_html[FIELD_INGREDIENTS] == current_recipe.ingredients
        assert form_data_from_html[FIELD_MODIFICATION_PROMPT] == modification_prompt

    @patch(
        "meal_planner.routers.actions.generate_modified_recipe", new_callable=AsyncMock
    )
    async def test_modify_recipe_file_not_found_error(
        self,
        mock_llm_modify: AsyncMock,
        client: AsyncClient,
        mock_current_recipe_before_modify_fixture: RecipeBase,
        mock_original_recipe_fixture: RecipeBase,
    ):
        """Test FileNotFoundError during LLM modification (missing prompt file)."""
        file_not_found_error = FileNotFoundError(
            2, "No such file or directory", "missing_prompt.txt"
        )
        mock_llm_modify.side_effect = file_not_found_error

        current_recipe = mock_current_recipe_before_modify_fixture
        original_recipe = mock_original_recipe_fixture
        modification_prompt = "Make it vegan"

        form_data = {
            FIELD_NAME: current_recipe.name,
            FIELD_INGREDIENTS: current_recipe.ingredients,
            FIELD_INSTRUCTIONS: current_recipe.instructions,
            FIELD_ORIGINAL_NAME: original_recipe.name,
            FIELD_ORIGINAL_INGREDIENTS: original_recipe.ingredients,
            FIELD_ORIGINAL_INSTRUCTIONS: original_recipe.instructions,
            FIELD_MODIFICATION_PROMPT: modification_prompt,
        }

        response = await client.post(RECIPES_MODIFY_URL, data=form_data)
        assert response.status_code == 200

        mock_llm_modify.assert_called_once_with(
            current_recipe=current_recipe, modification_request=modification_prompt
        )

        html_content = response.text
        soup = BeautifulSoup(html_content, "html.parser")

        error_div = soup.find(
            "div", string="Service configuration error. Please try again later."
        )
        assert error_div is not None, "FileNotFoundError message not found"
        assert CSS_ERROR_CLASS in error_div.get("class", []), (
            "Error message does not have the error CSS class"
        )

        form_data_from_html = extract_full_edit_form_data(html_content)
        assert form_data_from_html[FIELD_NAME] == current_recipe.name
        assert form_data_from_html[FIELD_INGREDIENTS] == current_recipe.ingredients
        assert form_data_from_html[FIELD_MODIFICATION_PROMPT] == modification_prompt
