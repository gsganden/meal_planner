from unittest.mock import AsyncMock, patch

import httpx
import pytest
from bs4 import BeautifulSoup
from httpx import AsyncClient, Request, Response

from meal_planner.main import CSS_ERROR_CLASS
from meal_planner.models import RecipeBase
from tests.constants import (
    FIELD_RECIPE_TEXT,
    FIELD_RECIPE_URL,
    RECIPES_EXTRACT_RUN_URL,
    RECIPES_FETCH_TEXT_URL,
)


@pytest.mark.anyio
class TestRecipeFetchTextEndpoint:
    TEST_URL = "http://example.com/fetch-success"

    async def test_success(self, client: AsyncClient):
        mock_text = "Fetched and cleaned recipe text."

        with patch(
            "meal_planner.main.fetch_and_clean_text_from_url",
            new_callable=AsyncMock,
        ) as local_mock_fetch_clean:
            local_mock_fetch_clean.return_value = mock_text

            response = await client.post(
                RECIPES_FETCH_TEXT_URL, data={FIELD_RECIPE_URL: self.TEST_URL}
            )

        assert response.status_code == 200
        local_mock_fetch_clean.assert_called_once_with(self.TEST_URL)
        assert "<textarea" in response.text
        assert f'id="{FIELD_RECIPE_TEXT}"' in response.text
        assert f'name="{FIELD_RECIPE_TEXT}"' in response.text
        assert f">{mock_text}</textarea>" in response.text

    async def test_missing_url(self, client: AsyncClient):
        response = await client.post(RECIPES_FETCH_TEXT_URL, data={})
        assert response.status_code == 200
        assert "Please provide a Recipe URL to fetch." in response.text
        assert f'class="{CSS_ERROR_CLASS}"' in response.text

    @pytest.mark.parametrize(
        "exception_type, exception_args, expected_message",
        [
            (
                httpx.RequestError,
                ("Network connection failed",),
                "Error fetching URL. Please check the URL and your connection.",
            ),
            (
                httpx.HTTPStatusError,
                (
                    "404 Client Error",
                    {
                        "request": Request("GET", "http://example.com/fetch-success"),
                        "response": Response(
                            404,
                            request=Request("GET", "http://example.com/fetch-success"),
                        ),
                    },
                ),
                "Error fetching URL: The server returned an error.",
            ),
            (
                RuntimeError,
                ("Processing failed",),
                "Failed to process the content from the URL.",
            ),
            (
                Exception,
                ("Unexpected error",),
                "An unexpected error occurred while fetching text.",
            ),
        ],
    )
    async def test_fetch_text_errors(
        self,
        client: AsyncClient,
        exception_type,
        exception_args,
        expected_message,
    ):
        """Test that various exceptions from the service are handled correctly."""
        with patch(
            "meal_planner.main.fetch_and_clean_text_from_url", new_callable=AsyncMock
        ) as local_mock_fetch_clean:
            if exception_type == httpx.HTTPStatusError:
                local_mock_fetch_clean.side_effect = exception_type(
                    exception_args[0],
                    request=exception_args[1]["request"],
                    response=exception_args[1]["response"],
                )
            else:
                local_mock_fetch_clean.side_effect = exception_type(*exception_args)

            response = await client.post(
                RECIPES_FETCH_TEXT_URL, data={FIELD_RECIPE_URL: self.TEST_URL}
            )

            local_mock_fetch_clean.assert_called_once_with(self.TEST_URL)

            assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")

        text_area_container = soup.find("div", id="recipe_text_container")
        assert text_area_container is not None
        text_area = text_area_container.find("textarea", id="recipe_text")
        assert text_area is not None
        assert text_area.get_text(strip=True) == ""

        error_div = soup.find("div", id="fetch-url-error-display")
        assert error_div is not None
        assert error_div.text.strip() == expected_message
        expected_classes = set(CSS_ERROR_CLASS.split())
        actual_classes = set(error_div.get("class", []))
        assert expected_classes.issubset(actual_classes)

        parent_of_error_div = error_div.parent
        assert parent_of_error_div is not None, "Parent of error_div not found"
        assert isinstance(parent_of_error_div, BeautifulSoup) or hasattr(
            parent_of_error_div, "get"
        ), "Parent of error_div is not a Tag"
        assert (
            parent_of_error_div.get("hx-swap-oob")
            == "outerHTML:#fetch-url-error-display"
        ), (
            f"hx-swap-oob attribute incorrect or missing on parent of error_div. "
            f"Got: {parent_of_error_div.get('hx-swap-oob')}"
        )


@pytest.mark.anyio
class TestRecipeExtractRunEndpoint:
    @pytest.fixture
    def mock_llm_generate_recipe(self):
        with patch(
            "meal_planner.main.generate_recipe_from_text", new_callable=AsyncMock
        ) as mock_service_call:
            yield mock_service_call

    @patch("meal_planner.main.generate_recipe_from_text", new_callable=AsyncMock)
    async def test_success(self, mock_llm_generate_recipe, client: AsyncClient):
        expected_recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["ingredient1"],
            instructions=["Mix the ingredients well."],
        )
        mock_llm_generate_recipe.return_value = expected_recipe

        form_data = {FIELD_RECIPE_TEXT: "Some recipe text"}
        response = await client.post(RECIPES_EXTRACT_RUN_URL, data=form_data)

        assert response.status_code == 200
        mock_llm_generate_recipe.assert_called_once_with(text="Some recipe text")

        assert expected_recipe.name in response.text
        assert expected_recipe.ingredients[0] in response.text
        if expected_recipe.instructions:
            assert expected_recipe.instructions[0] in response.text

        soup = BeautifulSoup(response.text, "html.parser")

        # Find the edit form inside the edit OOB div
        edit_oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#edit-form-target"})
        assert edit_oob_div is not None, "OOB edit form div not found"

        # Find the save button in the review OOB div
        review_oob_div = soup.find(
            "div", {"hx-swap-oob": "innerHTML:#review-section-target"}
        )
        assert review_oob_div is not None, "OOB review section div not found"

        save_button = review_oob_div.find("button", string="Save Recipe")
        assert save_button is not None

        name_input = edit_oob_div.find("input", {"name": "name"})
        assert name_input is not None
        assert name_input.get("value") == expected_recipe.name

        ingredient_inputs = edit_oob_div.find_all("input", {"name": "ingredients"})
        assert len(ingredient_inputs) >= 1
        assert ingredient_inputs[0].get("value") == expected_recipe.ingredients[0]

        instruction_textareas = edit_oob_div.find_all(
            "textarea", {"name": "instructions"}
        )

        assert len(instruction_textareas) >= 1
        assert expected_recipe.instructions[0] in instruction_textareas[0].get_text()

    @patch("meal_planner.main.logger.error")
    async def test_extraction_error(
        self, mock_logger_error, client: AsyncClient, mock_llm_generate_recipe
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

    @patch("meal_planner.main.postprocess_recipe")
    @patch("meal_planner.main.generate_recipe_from_text", new_callable=AsyncMock)
    async def test_extract_run_missing_instructions(
        self, mock_llm_generate_recipe, mock_postprocess, client: AsyncClient
    ):
        initial_recipe = RecipeBase(
            name="Test Recipe", ingredients=["ingredient1"], instructions=[]
        )
        final_recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["ingredient1"],
            instructions=["Default instruction"],
        )

        mock_llm_generate_recipe.return_value = initial_recipe
        mock_postprocess.return_value = final_recipe

        form_data = {FIELD_RECIPE_TEXT: "Recipe with missing instructions"}
        response = await client.post(RECIPES_EXTRACT_RUN_URL, data=form_data)

        assert response.status_code == 200
        mock_llm_generate_recipe.assert_called_once_with(
            text="Recipe with missing instructions"
        )
        mock_postprocess.assert_called_once_with(initial_recipe)

        soup = BeautifulSoup(response.text, "html.parser")
        edit_oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#edit-form-target"})
        assert edit_oob_div is not None, "OOB edit form div not found"

        instruction_textareas = edit_oob_div.find_all(
            "textarea", {"name": "instructions"}
        )
        assert len(instruction_textareas) >= 1
        assert "Default instruction" in instruction_textareas[0].get_text()

    @patch("meal_planner.main.postprocess_recipe")
    @patch("meal_planner.main.generate_recipe_from_text", new_callable=AsyncMock)
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
        edit_oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#edit-form-target"})
        assert edit_oob_div is not None, "OOB edit form div not found"

        ingredient_inputs = edit_oob_div.find_all("input", {"name": "ingredients"})
        assert len(ingredient_inputs) >= 1
        assert ingredient_inputs[0].get("value") == "Default ingredient"


@pytest.mark.anyio
async def test_extract_run_returns_save_form(
    client: AsyncClient, monkeypatch, mock_recipe_data_fixture: RecipeBase
):
    async def mock_extract(*args, **kwargs):
        return mock_recipe_data_fixture

    monkeypatch.setattr("meal_planner.main.generate_recipe_from_text", mock_extract)

    form_data = {FIELD_RECIPE_TEXT: "Some recipe text"}
    response = await client.post(RECIPES_EXTRACT_RUN_URL, data=form_data)

    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    edit_oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#edit-form-target"})
    assert edit_oob_div is not None, "OOB edit form div not found"

    review_oob_div = soup.find(
        "div", {"hx-swap-oob": "innerHTML:#review-section-target"}
    )
    assert review_oob_div is not None, "OOB review section div not found"

    save_button = review_oob_div.find("button", string="Save Recipe")
    assert save_button is not None, "Save Recipe button not found"

    form_tag = edit_oob_div.find("form")
    assert form_tag is not None, "Form tag not found"


@pytest.fixture
def mock_recipe_data_fixture() -> RecipeBase:
    return RecipeBase(
        name="Test Recipe",
        ingredients=["Test Ingredient 1", "Test Ingredient 2"],
        instructions=["Test Instruction 1", "Test Instruction 2"],
    )
