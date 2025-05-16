from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup
from bs4.element import Tag
from httpx import AsyncClient

from meal_planner.models import RecipeBase
from meal_planner.ui.common import CSS_ERROR_CLASS  # Import the correct CSS_ERROR_CLASS

# Constants from test_main.py that are relevant
RECIPES_EXTRACT_RUN_URL = "/recipes/extract/run"
FIELD_RECIPE_TEXT = "recipe_text"
FIELD_NAME = "name"
FIELD_INGREDIENTS = "ingredients"
FIELD_INSTRUCTIONS = "instructions"


# Helper Exception and Functions (copied from test_main.py)
class FormTargetDivNotFoundError(Exception):
    """Custom exception raised when the target div for form parsing is not found."""

    pass


def _get_edit_form_target_div(html_text: str) -> Tag:
    """Parses HTML and finds the specific div target for form edits."""
    soup = BeautifulSoup(html_text, "html.parser")
    found_element = soup.find("div", attrs={"id": "edit-form-target"})
    if not found_element:
        found_element = soup.find(
            "div", attrs={"hx-swap-oob": "innerHTML:#edit-form-target"}
        )

    if isinstance(found_element, Tag):
        return found_element
    raise FormTargetDivNotFoundError(
        "Could not find div with id 'edit-form-target' or "
        "hx-swap-oob='innerHTML:#edit-form-target'"
    )


def _extract_form_value(html_text: str, name: str) -> str | None:
    """Extracts a single value from an input or textarea in the HTML form section."""
    form_div = _get_edit_form_target_div(html_text)

    input_tag_candidate = form_div.find("input", attrs={"name": name})
    if isinstance(input_tag_candidate, Tag) and input_tag_candidate.has_attr("value"):
        value = input_tag_candidate["value"]
        if isinstance(value, str):
            return value
        elif isinstance(value, list) and value and isinstance(value[0], str):
            return value[0]

    textarea_tag_candidate = form_div.find("textarea", attrs={"name": name})
    if isinstance(textarea_tag_candidate, Tag):
        return (
            str(textarea_tag_candidate.string)
            if textarea_tag_candidate.string is not None
            else ""
        )
    return None


def _extract_form_list_values(html_text: str, name: str) -> list[str]:
    """Extracts all values from inputs/textareas with the same name."""
    form_div = _get_edit_form_target_div(html_text)
    values: list[str] = []
    elements = form_div.find_all(
        lambda tag: isinstance(tag, Tag)
        and tag.name in ["input", "textarea"]
        and tag.get("name") == name
    )
    for element in elements:
        if isinstance(element, Tag):
            if element.name == "input" and element.has_attr("value"):
                value_attr = element["value"]
                if isinstance(value_attr, str):
                    values.append(value_attr)
                elif (
                    isinstance(value_attr, list)
                    and value_attr
                    and isinstance(value_attr[0], str)
                ):
                    values.append(value_attr[0])
            elif element.name == "textarea":
                values.append(str(element.string) if element.string is not None else "")
    return values


@pytest.mark.anyio
class TestRecipeExtractRunEndpoint:
    @pytest.fixture
    def mock_llm_generate_recipe(self):
        with patch(
            "meal_planner.main.llm_generate_recipe_from_text", new_callable=AsyncMock
        ) as mock_service_call:
            yield mock_service_call

    async def test_success(self, client: AsyncClient, mock_llm_generate_recipe):
        test_text = (
            "Recipe Name\\nIngredients: ing1, ing2\\nInstructions: 1. First "
            "step text\\nStep 2: Second step text"
        )
        mock_llm_generate_recipe.return_value = RecipeBase(
            name=" text input success name recipe ",
            ingredients=[" ingA ", "ingB, "],
            instructions=[
                "1. Actual step A",
                " Step 2: Actual step B ",
            ],
        )

        response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: test_text}
        )
        assert response.status_code == 200
        mock_llm_generate_recipe.assert_called_once_with(text=test_text)

        html_content = response.text
        assert (
            _extract_form_value(html_content, FIELD_NAME) == "Text Input Success Name"
        )
        assert _extract_form_list_values(html_content, FIELD_INGREDIENTS) == [
            "ingA",
            "ingB,",
        ]
        assert _extract_form_list_values(html_content, FIELD_INSTRUCTIONS) == [
            "Actual step A.",
            "Actual step B.",
        ]

    @patch("meal_planner.main.logger.error")
    async def test_extraction_error(
        self, mock_logger_error, client: AsyncClient, mock_llm_generate_recipe
    ):
        test_text = "Some recipe text that causes an LLM error."
        llm_exception = Exception("LLM failed on text input")
        mock_llm_generate_recipe.side_effect = llm_exception

        response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: test_text}
        )
        assert response.status_code == 200
        expected_error_msg = (
            "Recipe extraction failed. An unexpected error occurred during processing."
        )
        assert expected_error_msg in response.text
        assert f'class="{CSS_ERROR_CLASS}"' in response.text
        mock_logger_error.assert_any_call(
            "Error during recipe extraction from %s: %s",
            "provided text",
            llm_exception,
            exc_info=True,
        )

    async def test_no_text_input_provided(self, client: AsyncClient):
        response = await client.post(RECIPES_EXTRACT_RUN_URL, data={})
        assert response.status_code == 200
        assert "No text content provided for extraction." in response.text
        assert f'class="{CSS_ERROR_CLASS}"' in response.text

    @patch("meal_planner.main.postprocess_recipe")
    @patch("meal_planner.main.llm_generate_recipe_from_text", new_callable=AsyncMock)
    async def test_extract_run_missing_instructions(
        self, mock_llm_generate_recipe, mock_postprocess, client: AsyncClient
    ):
        test_text = "Recipe without instructions"
        mock_recipe_from_llm_service = RecipeBase(
            name="Test Recipe Name", ingredients=["ing1"], instructions=[]
        )
        mock_llm_generate_recipe.return_value = mock_recipe_from_llm_service

        mock_postprocess.return_value = RecipeBase(
            name="Test Recipe Name", ingredients=["ing1"], instructions=[]
        )

        response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: test_text}
        )
        assert response.status_code == 200
        mock_llm_generate_recipe.assert_called_once_with(text=test_text)
        mock_postprocess.assert_called_once_with(mock_recipe_from_llm_service)

        html_content = response.text
        assert _extract_form_value(html_content, FIELD_NAME) == "Test Recipe Name"
        assert _extract_form_list_values(html_content, FIELD_INGREDIENTS) == ["ing1"]
        assert _extract_form_list_values(html_content, FIELD_INSTRUCTIONS) == []

    @patch("meal_planner.main.postprocess_recipe")
    @patch("meal_planner.main.llm_generate_recipe_from_text", new_callable=AsyncMock)
    async def test_extract_run_missing_ingredients(
        self, mock_llm_generate_recipe, mock_postprocess, client: AsyncClient
    ):
        test_text = "Recipe without ingredients"
        mock_recipe_input_to_postprocess = RecipeBase(
            name="Test Recipe Name", ingredients=[""], instructions=["step1"]
        )
        mock_llm_generate_recipe.return_value = mock_recipe_input_to_postprocess

        mock_postprocess.return_value = RecipeBase(
            name="Test Recipe Name",
            ingredients=["No ingredients found"],
            instructions=["step1"],
        )

        response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: test_text}
        )
        assert response.status_code == 200
        mock_llm_generate_recipe.assert_called_once_with(text=test_text)
        mock_postprocess.assert_called_once_with(mock_recipe_input_to_postprocess)

        html_content = response.text
        assert _extract_form_value(html_content, FIELD_NAME) == "Test Recipe Name"
        assert _extract_form_list_values(html_content, FIELD_INGREDIENTS) == [
            "No ingredients found"
        ]
        assert _extract_form_list_values(html_content, FIELD_INSTRUCTIONS) == ["step1"]
