"""Tests for route handlers defined in meal_planner.routers.actions."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

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
    FIELD_RECIPE_TEXT,
    RECIPES_EXTRACT_RUN_URL,
    RECIPES_MODIFY_URL,
    RECIPES_SAVE_URL,
)
from tests.test_helpers import (
    create_mock_api_response,
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
        UUID(saved_recipe_id)

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
            "meal_planner.routers.actions.internal_api_client.post", mock_post
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
    @patch("meal_planner.routers.actions.parse_recipe_form_data")
    async def test_save_recipe_parsing_exception(
        self,
        mock_form_processing: MagicMock,
        client: AsyncClient,
    ):
        "Test generic exception during form parsing in post_save_recipe."
        mock_form_processing.side_effect = Exception("Simulated parsing error")

        dummy_form_data = {
            FIELD_NAME: "Test",
            FIELD_INGREDIENTS: ["i"],
            FIELD_INSTRUCTIONS: ["s"],
        }

        response = await client.post(RECIPES_SAVE_URL, data=dummy_form_data)

        assert response.status_code == 200
        assert "Error processing form data." in response.text
        assert CSS_ERROR_CLASS in response.text
        mock_form_processing.assert_called_once()

    @pytest.mark.anyio
    async def test_save_recipe_api_call_generic_error(
        self, client: AsyncClient, monkeypatch
    ):
        """Test error handling when the internal API call raises a generic exception."""
        mock_post = AsyncMock(side_effect=Exception("Unexpected network issue"))
        monkeypatch.setattr(
            "meal_planner.routers.actions.internal_api_client.post", mock_post
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
            "meal_planner.routers.actions.internal_api_client.post", mock_post
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
            "meal_planner.routers.actions.internal_api_client.post", mock_post
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
            "meal_planner.routers.actions.internal_api_client.post", mock_post
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
            "meal_planner.routers.actions.internal_api_client.post", mock_post
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

    @pytest.mark.anyio
    async def test_save_recipe_api_call_422_too_short_instructions(
        self, client: AsyncClient, monkeypatch
    ):
        """Test 422 error from API when instructions are missing/too short."""
        error_detail = [
            {
                "type": "too_short",
                "loc": ["body", "instructions"],
                "msg": "List should have at least 1 item after validation, not 0",
                "input": {"name": "Test", "ingredients": ["i1"], "instructions": []},
            }
        ]
        mock_response = httpx.Response(
            status_code=422,
            json={"detail": error_detail},
            request=httpx.Request("POST", "/api/v0/recipes"),
        )
        mock_post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                message="Unprocessable Entity",
                request=httpx.Request("POST", "/api/v0/recipes"),
                response=mock_response,
            )
        )
        monkeypatch.setattr(
            "meal_planner.routers.actions.internal_api_client.post", mock_post
        )

        form_data = {
            FIELD_NAME: "Recipe Missing Instructions",
            FIELD_INGREDIENTS: ["ingredient1"],
            FIELD_INSTRUCTIONS: ["Actual instruction provided"],
        }
        response = await client.post(RECIPES_SAVE_URL, data=form_data)
        assert response.status_code == 200  # Action route itself returns 200
        soup = BeautifulSoup(response.text, "html.parser")
        error_span = soup.find("span", id="save-button-container")
        assert error_span is not None
        assert CSS_ERROR_CLASS in error_span.get("class", [])
        assert (
            "Please add at least one instruction to the recipe."
            in error_span.get_text(strip=True)
        )
        mock_post.assert_called_once()

    @pytest.mark.anyio
    async def test_save_recipe_api_call_422_malformed_detail(
        self, client: AsyncClient, monkeypatch
    ):
        """Test 422 error from API with malformed/unexpected detail structure."""
        # Scenario 1: Detail is a string, not a list of dicts
        mock_response_string_detail = httpx.Response(
            status_code=422,
            json={"detail": "A simple error string, not a list of error objects"},
            request=httpx.Request("POST", "/api/v0/recipes"),
        )
        mock_post_string_detail = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                message="Unprocessable Entity",
                request=httpx.Request("POST", "/api/v0/recipes"),
                response=mock_response_string_detail,
            )
        )
        monkeypatch.setattr(
            "meal_planner.routers.actions.internal_api_client.post",
            mock_post_string_detail,
        )

        form_data = {
            FIELD_NAME: "Malformed Detail Test 1",
            FIELD_INGREDIENTS: ["ingredient1"],
            FIELD_INSTRUCTIONS: ["instruction1"],
        }
        response = await client.post(RECIPES_SAVE_URL, data=form_data)
        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")
        error_span = soup.find("span", id="save-button-container")
        assert error_span is not None
        assert CSS_ERROR_CLASS in error_span.get("class", [])
        assert (
            "Could not save recipe: Invalid data for some fields."
            in error_span.get_text(strip=True)
        )
        mock_post_string_detail.assert_called_once()

        # Scenario 2: Response is not JSON
        mock_response_non_json = httpx.Response(
            status_code=422,
            content=b"This is not JSON content",
            request=httpx.Request("POST", "/api/v0/recipes"),
        )
        mock_post_non_json = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                message="Unprocessable Entity",
                request=httpx.Request("POST", "/api/v0/recipes"),
                response=mock_response_non_json,
            )
        )
        monkeypatch.setattr(
            "meal_planner.routers.actions.internal_api_client.post", mock_post_non_json
        )

        form_data_2 = {
            FIELD_NAME: "Malformed Detail Test 2",
            FIELD_INGREDIENTS: ["ingredient1"],
            FIELD_INSTRUCTIONS: ["instruction1"],
        }
        response_2 = await client.post(RECIPES_SAVE_URL, data=form_data_2)
        assert response_2.status_code == 200
        soup_2 = BeautifulSoup(response_2.text, "html.parser")
        error_span_2 = soup_2.find("span", id="save-button-container")
        assert error_span_2 is not None
        assert CSS_ERROR_CLASS in error_span_2.get("class", [])
        assert (
            "Could not save recipe: Invalid data for some fields."
            in error_span_2.get_text(strip=True)
        )
        mock_post_non_json.assert_called_once()


# Fixtures for TestModifyRecipeEndpoint
@pytest.fixture
def mock_original_recipe_fixture() -> RecipeBase:
    return RecipeBase(
        name="Original",
        ingredients=["orig ing 1."],
        instructions=["orig inst 1."],
    )


@pytest.fixture
def mock_current_recipe_before_modify_fixture() -> RecipeBase:
    return RecipeBase(
        name="Current",
        ingredients=["curr ing 1."],
        instructions=["curr inst 1."],
    )


@pytest.fixture
def mock_llm_modified_recipe_fixture() -> RecipeBase:
    return RecipeBase(
        name="Modified",
        ingredients=["mod ing 1."],
        instructions=["mod inst 1."],
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
        assert current_data_from_html["instructions"] == ["mod inst 1."]

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


@pytest.mark.anyio
class TestExtractRecipeEndpoint:
    @patch(
        "meal_planner.routers.actions.generate_recipe_from_text", new_callable=AsyncMock
    )
    async def test_success(self, mock_llm_generate_recipe, client: AsyncClient):
        expected_recipe = RecipeBase(
            name="Test",
            ingredients=["ingredient1"],
            instructions=["Mix the ingredients well."],
        )
        mock_llm_generate_recipe.return_value = expected_recipe

        form_data = {FIELD_RECIPE_TEXT: "Some recipe text"}
        response = await client.post(RECIPES_EXTRACT_RUN_URL, data=form_data)

        assert response.status_code == 200
        mock_llm_generate_recipe.assert_called_once_with(text="Some recipe text")

        # Check that the response text contains key information from the recipe
        assert "Test" in response.text
        assert expected_recipe.ingredients[0] in response.text
        if expected_recipe.instructions:
            assert "Mix the ingredients well." in response.text

        soup = BeautifulSoup(response.text, "html.parser")

        # Find the OOB swapped div by its ID
        edit_oob_div = soup.find("div", id="edit-form-target")
        assert edit_oob_div is not None, (
            "OOB div with id='edit-form-target' not found. Response: "
            f"{response.text[:500]}..."
        )
        assert edit_oob_div.get("hx-swap-oob") == "innerHTML", (
            "hx-swap-oob attribute missing or incorrect on edit-form-target"
        )

        review_oob_div = soup.find("div", id="review-section-target")
        assert review_oob_div is not None, (
            "OOB div with id='review-section-target' not found. Response: "
            f"{response.text[:500]}..."
        )
        assert review_oob_div.get("hx-swap-oob") == "innerHTML", (
            "hx-swap-oob attribute missing or incorrect on review-section-target"
        )

        clear_error_oob_div = soup.find("div", id="error-message-container")
        assert clear_error_oob_div is not None, (
            "OOB div with id='error-message-container' not found for clearing. "
            f"Response: {response.text[:500]}..."
        )
        assert clear_error_oob_div.get("hx-swap-oob") == "innerHTML", (
            "hx-swap-oob attribute missing or incorrect on error-message-container"
        )
        assert not clear_error_oob_div.get_text(strip=True), (
            "Error message container should be empty"
        )

        # Further checks within the OOB divs
        name_input = edit_oob_div.find("input", {"name": "name"})
        assert name_input is not None
        assert name_input.get("value") == "Test"

        ingredient_inputs = edit_oob_div.find_all("input", {"name": "ingredients"})
        assert len(ingredient_inputs) >= 1
        assert ingredient_inputs[0].get("value") == expected_recipe.ingredients[0]

        instruction_textareas = edit_oob_div.find_all(
            "textarea", {"name": "instructions"}
        )

        assert len(instruction_textareas) >= 1
        assert expected_recipe.instructions[0] in instruction_textareas[0].get_text()

    @patch(
        "meal_planner.routers.actions.generate_recipe_from_text", new_callable=AsyncMock
    )
    @patch("meal_planner.routers.actions.logger.error")
    async def test_extraction_error(
        self, mock_logger_error, mock_llm_generate_recipe, client: AsyncClient
    ):
        error_message = "LLM extraction failed"
        mock_llm_generate_recipe.side_effect = Exception(error_message)

        form_data = {FIELD_RECIPE_TEXT: "Some recipe text"}
        response = await client.post(RECIPES_EXTRACT_RUN_URL, data=form_data)

        assert response.status_code == 200
        mock_llm_generate_recipe.assert_called_once_with(text="Some recipe text")

        assert "Recipe extraction failed" in response.text
        assert f'class="{CSS_ERROR_CLASS}"' in response.text

        assert mock_logger_error.call_count == 2
        call_args_list = mock_logger_error.call_args_list

        assert (
            "LLM service failed to generate recipe from text" in call_args_list[0][0][0]
        )
        assert call_args_list[0][1].get("exc_info") is True

        assert "Error during recipe extraction" in call_args_list[1][0][0]
        assert call_args_list[1][1].get("exc_info") is True

    async def test_no_text_input_provided(self, client: AsyncClient):
        response = await client.post(RECIPES_EXTRACT_RUN_URL, data={})
        assert response.status_code == 200
        assert "No text content provided for extraction." in response.text
        assert f'class="{CSS_ERROR_CLASS}"' in response.text

    @patch("meal_planner.routers.actions.postprocess_recipe")
    @patch(
        "meal_planner.routers.actions.generate_recipe_from_text", new_callable=AsyncMock
    )
    async def test_extract_run_missing_instructions(
        self, mock_llm_generate_recipe, mock_postprocess, client: AsyncClient
    ):
        initial_recipe = RecipeBase.model_construct(
            name="Test Recipe", ingredients=["ingredient1"], instructions=[]
        )

        mock_llm_generate_recipe.return_value = initial_recipe

        form_data = {FIELD_RECIPE_TEXT: "Recipe with missing instructions"}
        response = await client.post(RECIPES_EXTRACT_RUN_URL, data=form_data)

        assert response.status_code == 200
        mock_llm_generate_recipe.assert_called_once_with(
            text="Recipe with missing instructions"
        )
        mock_postprocess.assert_not_called()  # Ensure postprocessing is skipped

        # The response text should BE the OOB error div fragment.
        # Basic string checks on the raw response text:
        assert "Recipe extraction resulted in missing instructions." in response.text
        assert 'id="error-message-container"' in response.text
        assert 'hx-swap-oob="innerHTML"' in response.text
        assert f'class="{CSS_ERROR_CLASS} mt-2"' in response.text

        soup = BeautifulSoup(response.text, "html.parser")

        # Find the error div by its ID; it should be the primary content
        # of the OOB response.
        error_div = soup.find("div", id="error-message-container")

        # If BS wraps the fragment in <html><body>, adjust the search.
        if not error_div and soup.body:
            error_div = soup.body.find("div", id="error-message-container")

        assert error_div is not None, (
            f"Div with id='error-message-container' not found. "
            f"Response: {response.text[:200]}... "
            f"{response.text[200:500]}..."
        )

        assert (
            "Recipe extraction resulted in missing instructions."
            in error_div.get_text()
        )
        assert CSS_ERROR_CLASS in error_div.get("class", [])
        assert error_div.get("hx-swap-oob") == "innerHTML"

        # Ensure that the main form content is NOT part of this OOB error response
        edit_form_target_div = soup.find("div", id="edit-form-target")
        assert edit_form_target_div is None, (
            "#edit-form-target should not be present in an OOB error response"
            " for #error-message-container."
        )
        name_input = soup.find("input", {"name": "name"})
        assert name_input is None, (
            "Recipe name input should not be present in this specific"
            " OOB error response."
        )

    @patch(
        "meal_planner.routers.actions.generate_recipe_from_text", new_callable=AsyncMock
    )
    async def test_extract_run_no_diff_immediately_after_extraction(
        self, mock_llm_generate_recipe, client: AsyncClient
    ):
        """Regression test: Confirm there's no diff immediately after recipe extraction.

        This test prevents the bug where postprocessing changes would show up as
        modifications in the diff view right after extraction, making it appear
        like the user had already made changes.
        """
        expected_recipe = RecipeBase(
            name="Test Recipe with postprocessing changes",
            ingredients=["1 cup flour", "2 eggs"],
            instructions=["Mix ingredients.", "Bake for 30 minutes."],
        )
        mock_llm_generate_recipe.return_value = expected_recipe

        form_data = {FIELD_RECIPE_TEXT: "Some recipe text"}
        response = await client.post(RECIPES_EXTRACT_RUN_URL, data=form_data)

        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")

        # Find the diff elements
        diff_before_pre = soup.find("pre", id="diff-before-pre")
        diff_after_pre = soup.find("pre", id="diff-after-pre")
        assert diff_before_pre is not None, "Diff before <pre> not found"
        assert diff_after_pre is not None, "Diff after <pre> not found"

        # Extract text content from both diff panes
        before_text = diff_before_pre.get_text()
        after_text = diff_after_pre.get_text()

        # The key assertion: both sides should be identical (no modifications)
        assert before_text == after_text, (
            "Diff shows modifications immediately after extraction. "
            f"Before: {before_text[:100]}... After: {after_text[:100]}..."
        )

        # Additional check: there should be no <ins> or <del> tags (no modifications)
        ins_tags = soup.find_all("ins")
        del_tags = soup.find_all("del")
        assert len(ins_tags) == 0, f"Found unexpected <ins> tags: {ins_tags}"
        assert len(del_tags) == 0, f"Found unexpected <del> tags: {del_tags}"

    @patch("meal_planner.routers.actions.postprocess_recipe")
    @patch(
        "meal_planner.routers.actions.generate_recipe_from_text", new_callable=AsyncMock
    )
    async def test_extract_run_missing_ingredients(
        self, mock_llm_generate_recipe, mock_postprocess, client: AsyncClient
    ):
        initial_recipe = RecipeBase(
            name="Test Recipe", ingredients=["placeholder"], instructions=["step1"]
        )
        final_recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["Default ingredient"],
            instructions=["step1"],
        )

        mock_llm_generate_recipe.return_value = initial_recipe
        mock_postprocess.return_value = final_recipe

        form_data = {FIELD_RECIPE_TEXT: "Recipe with missing ingredients"}
        response = await client.post(RECIPES_EXTRACT_RUN_URL, data=form_data)

        assert response.status_code == 200
        mock_llm_generate_recipe.assert_called_once_with(
            text="Recipe with missing ingredients"
        )
        mock_postprocess.assert_called_once_with(initial_recipe)

        soup = BeautifulSoup(response.text, "html.parser")
        edit_oob_div = soup.find("div", id="edit-form-target")
        assert edit_oob_div is not None, (
            "OOB div with id='edit-form-target' not found. Response: "
            f"{response.text[:500]}..."
        )
        assert edit_oob_div.get("hx-swap-oob") == "innerHTML"

        ingredient_inputs = edit_oob_div.find_all("input", {"name": "ingredients"})
        assert len(ingredient_inputs) >= 1
        assert ingredient_inputs[0].get("value") == "Default ingredient"

    @patch(
        "meal_planner.routers.actions.generate_recipe_from_text", new_callable=AsyncMock
    )
    @patch("meal_planner.routers.actions.postprocess_recipe")
    @patch("meal_planner.routers.actions.logger.error")
    async def test_extract_run_validation_error_during_postprocessing(
        self,
        mock_logger_error: MagicMock,
        mock_postprocess: MagicMock,
        mock_llm_generate_recipe: AsyncMock,
        client: AsyncClient,
    ):
        """Test ValidationError raised by postprocess_recipe after LLM extraction."""
        # LLM returns a seemingly valid recipe
        llm_extracted_recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["Raw Ingredient 1", "  "],  # One valid, one to be filtered
            instructions=["Raw Instruction 1."],
        )
        mock_llm_generate_recipe.return_value = llm_extracted_recipe

        # Create a genuine ValidationError instance for mocking
        from pydantic import BaseModel  # Alias Field
        from pydantic import Field as PydanticField

        class _TempModel(BaseModel):
            ingredients: list[str] = PydanticField(min_length=1)

        validation_error_instance = None
        try:
            _TempModel(ingredients=[])
        except ValidationError as e:
            validation_error_instance = e

        assert validation_error_instance is not None, (
            "Failed to create ValidationError for mock"
        )
        mock_postprocess.side_effect = validation_error_instance

        form_data = {
            FIELD_RECIPE_TEXT: "Some recipe text that leads to validation error"
        }
        response = await client.post(RECIPES_EXTRACT_RUN_URL, data=form_data)

        assert response.status_code == 200
        mock_llm_generate_recipe.assert_called_once_with(
            text="Some recipe text that leads to validation error"
        )
        mock_postprocess.assert_called_once_with(llm_extracted_recipe)

        # Check log call
        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        assert "Validation error during recipe extraction or postprocessing" in args[0]
        assert args[1] is validation_error_instance  # Check against the instance
        assert "Some recipe text that leads to validation error"[:100] in args[2]
        assert kwargs.get("exc_info") is True

        # Check UI response
        soup = BeautifulSoup(response.text, "html.parser")
        error_div = soup.find("div", id="error-message-container")
        if not error_div and soup.body:
            error_div = soup.body.find("div", id="error-message-container")

        assert error_div is not None, (
            f"OOB Error div 'error-message-container' not found. "
            f"Response: {response.text[:200]}... "
            f"{response.text[200:500]}..."
        )
        assert (
            "Recipe data is invalid after extraction. Please check the input text."
            in error_div.get_text(strip=True)
        )
        assert error_div.get("hx-swap-oob") == "innerHTML"
        assert CSS_ERROR_CLASS in error_div.get("class", [])

        # Ensure main form is not sent
        assert soup.find("div", id="edit-form-target") is None


@pytest.mark.anyio
async def test_extract_run_returns_save_form(
    client: AsyncClient, monkeypatch, mock_recipe_data_fixture: RecipeBase
):
    async def mock_extract(*args, **kwargs):
        return mock_recipe_data_fixture

    monkeypatch.setattr(
        "meal_planner.routers.actions.generate_recipe_from_text", mock_extract
    )
    # Also mock postprocess_recipe to ensure it doesn't interfere
    mock_postprocess = MagicMock(return_value=mock_recipe_data_fixture)
    monkeypatch.setattr(
        "meal_planner.routers.actions.postprocess_recipe", mock_postprocess
    )

    form_data = {FIELD_RECIPE_TEXT: "Some recipe text"}
    response = await client.post(RECIPES_EXTRACT_RUN_URL, data=form_data)

    assert response.status_code == 200
    mock_postprocess.assert_called_once_with(mock_recipe_data_fixture)

    soup = BeautifulSoup(response.text, "html.parser")
    edit_oob_div = soup.find("div", id="edit-form-target")
    assert edit_oob_div is not None, (
        "OOB div with id='edit-form-target' not found. Response: "
        f"{response.text[:500]}..."
    )
    assert edit_oob_div.get("hx-swap-oob") == "innerHTML"

    review_oob_div = soup.find("div", id="review-section-target")
    assert review_oob_div is not None, (
        "OOB div with id='review-section-target' not found. Response: "
        f"{response.text[:500]}..."
    )
    assert review_oob_div.get("hx-swap-oob") == "innerHTML"

    save_button = review_oob_div.find("button", string="Save Recipe")
    assert save_button is not None, "Save Recipe button not found"

    form_tag = edit_oob_div.find("form")
    assert form_tag is not None, "Form tag not found"

    # Check for original data hidden fields (critical for save and modify)
    original_name_input = edit_oob_div.find(
        "input", {"name": "original_name", "type": "hidden"}
    )
    assert original_name_input is not None
    assert original_name_input.get("value") == mock_recipe_data_fixture.name

    original_ingredient_inputs = edit_oob_div.find_all(
        "input", {"name": "original_ingredients", "type": "hidden"}
    )
    assert len(original_ingredient_inputs) == len(mock_recipe_data_fixture.ingredients)
    for i, ing_input in enumerate(original_ingredient_inputs):
        assert ing_input.get("value") == mock_recipe_data_fixture.ingredients[i]

    original_instruction_inputs = edit_oob_div.find_all(
        "input", {"name": "original_instructions", "type": "hidden"}
    )
    assert len(original_instruction_inputs) == len(
        mock_recipe_data_fixture.instructions
    )
    for i, inst_input in enumerate(original_instruction_inputs):
        assert inst_input.get("value") == mock_recipe_data_fixture.instructions[i]


@pytest.fixture
def mock_recipe_data_fixture() -> RecipeBase:
    return RecipeBase(
        name="Mock Recipe Name",
        ingredients=["Mock Ing 1", "Mock Ing 2"],
        instructions=["Mock Inst 1.", "Mock Inst 2."],
    )


@pytest.mark.anyio
class TestDeleteRecipeEndpoint:
    DELETE_PATH = "/recipes/delete"
    TEST_UUID = "12345678-1234-1234-1234-123456789012"
    NOT_FOUND_UUID = "99999999-9999-9999-9999-999999999999"

    @patch("meal_planner.routers.actions.internal_api_client", autospec=True)
    async def test_delete_recipe_success(
        self,
        mock_api_client: AsyncMock,
        client: AsyncClient,
    ):
        """Test successful recipe deletion."""
        mock_api_client.delete.return_value = create_mock_api_response(status_code=204)

        response = await client.post(
            self.DELETE_PATH, params={"recipe_id": self.TEST_UUID}
        )
        assert response.status_code == 200
        assert response.headers.get("HX-Trigger") == "recipeListChanged"
        mock_api_client.delete.assert_called_once_with(f"/v0/recipes/{self.TEST_UUID}")

    @patch("meal_planner.routers.actions.internal_api_client", autospec=True)
    async def test_delete_recipe_not_found(
        self,
        mock_api_client: AsyncMock,
        client: AsyncClient,
    ):
        """Test deletion of non-existent recipe."""
        http_error = httpx.HTTPStatusError(
            "Not Found",
            request=httpx.Request("DELETE", f"/v0/recipes/{self.NOT_FOUND_UUID}"),
            response=httpx.Response(404),
        )
        mock_api_client.delete.return_value = create_mock_api_response(
            status_code=404, error_to_raise=http_error
        )

        response = await client.post(
            self.DELETE_PATH, params={"recipe_id": self.NOT_FOUND_UUID}
        )
        assert response.status_code == 404
        mock_api_client.delete.assert_called_once_with(
            f"/v0/recipes/{self.NOT_FOUND_UUID}"
        )

    @patch("meal_planner.routers.actions.internal_api_client", autospec=True)
    async def test_delete_recipe_api_error(
        self,
        mock_api_client: AsyncMock,
        client: AsyncClient,
    ):
        """Test API error during deletion."""
        http_error = httpx.HTTPStatusError(
            "Internal Server Error",
            request=httpx.Request("DELETE", f"/v0/recipes/{self.TEST_UUID}"),
            response=httpx.Response(500),
        )
        mock_api_client.delete.return_value = create_mock_api_response(
            status_code=500, error_to_raise=http_error
        )

        response = await client.post(
            self.DELETE_PATH, params={"recipe_id": self.TEST_UUID}
        )
        assert response.status_code == 500
        mock_api_client.delete.assert_called_once_with(f"/v0/recipes/{self.TEST_UUID}")

    @patch("meal_planner.routers.actions.internal_api_client", autospec=True)
    async def test_delete_recipe_generic_error(
        self,
        mock_api_client: AsyncMock,
        client: AsyncClient,
    ):
        """Test generic error during deletion."""
        mock_api_client.delete.side_effect = Exception("Generic API failure")

        response = await client.post(
            self.DELETE_PATH, params={"recipe_id": self.TEST_UUID}
        )
        assert response.status_code == 500
        mock_api_client.delete.assert_called_once_with(f"/v0/recipes/{self.TEST_UUID}")
