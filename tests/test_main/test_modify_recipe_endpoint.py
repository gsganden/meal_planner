from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup
from bs4.element import Tag
from httpx import AsyncClient
from pydantic import ValidationError

from meal_planner.main import CSS_ERROR_CLASS, RecipeModificationError
from meal_planner.models import RecipeBase
from tests.constants import (
    FIELD_INGREDIENTS,
    FIELD_INSTRUCTIONS,
    FIELD_MODIFICATION_PROMPT,
    FIELD_NAME,
    FIELD_ORIGINAL_INGREDIENTS,
    FIELD_ORIGINAL_INSTRUCTIONS,
    FIELD_ORIGINAL_NAME,
    RECIPES_MODIFY_URL,
)


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


def _extract_current_recipe_data_from_html(html_content: str) -> dict:
    soup = BeautifulSoup(html_content, "html.parser")
    form_container = soup.find("div", id="edit-form-target")
    if not form_container:
        form_container = soup.find(
            "div", attrs={"hx-swap-oob": "innerHTML:#edit-form-target"}
        )

    if not form_container:
        form_container = soup

    form = form_container.find("form", attrs={"id": "edit-review-form"})

    if not form:
        raise ValueError("Form with id 'edit-review-form' not found in HTML content.")
    if not isinstance(form, Tag):
        raise ValueError("Form element is not a Tag.")

    name_input = form.find("input", attrs={"name": FIELD_NAME})
    name = (
        name_input.get("value", "")
        if name_input and isinstance(name_input, Tag)
        else ""
    )
    if isinstance(name, list):
        name = name[0]

    ingredients_inputs = form.find_all("input", attrs={"name": FIELD_INGREDIENTS})
    ingredients = [
        (
            ing_input.get("value", "")
            if isinstance(ing_input.get("value"), str)
            else (
                ing_input.get("value")[0]
                if isinstance(ing_input.get("value"), list) and ing_input.get("value")
                else ""
            )
        )
        for ing_input in ingredients_inputs
        if isinstance(ing_input, Tag) and "value" in ing_input.attrs
    ]
    instructions_areas = form.find_all("textarea", attrs={"name": FIELD_INSTRUCTIONS})
    instructions = [
        inst_area.get_text()
        for inst_area in instructions_areas
        if isinstance(inst_area, Tag)
    ]
    return {"name": str(name), "ingredients": ingredients, "instructions": instructions}


def _extract_full_edit_form_data(html_content: str) -> dict[str, Any]:
    soup = BeautifulSoup(html_content, "html.parser")
    form_container = soup.find("div", id="edit-form-target")
    if not form_container:
        form_container = soup.find(
            "div", attrs={"hx-swap-oob": "innerHTML:#edit-form-target"}
        )

    if not form_container:
        form_container = soup

    form = form_container.find("form", attrs={"id": "edit-review-form"})

    if not isinstance(form, Tag):
        raise ValueError(
            "Form with id 'edit-review-form' not found or is not a Tag "
            "in HTML content provided to _extract_full_edit_form_data."
        )

    data: dict[str, Any] = {}

    name_input = form.find("input", attrs={"name": FIELD_NAME})
    if name_input and isinstance(name_input, Tag) and "value" in name_input.attrs:
        name_value = name_input["value"]
        data[FIELD_NAME] = name_value[0] if isinstance(name_value, list) else name_value
    else:
        data[FIELD_NAME] = ""

    ingredients_inputs = form.find_all("input", attrs={"name": FIELD_INGREDIENTS})
    data[FIELD_INGREDIENTS] = [
        str(ing_input["value"])
        for ing_input in ingredients_inputs
        if isinstance(ing_input, Tag) and "value" in ing_input.attrs
    ]

    instructions_areas = form.find_all("textarea", attrs={"name": FIELD_INSTRUCTIONS})
    data[FIELD_INSTRUCTIONS] = [
        inst_area.get_text(strip=True)
        for inst_area in instructions_areas
        if isinstance(inst_area, Tag)
    ]

    original_name_input = form.find("input", attrs={"name": FIELD_ORIGINAL_NAME})
    if (
        original_name_input
        and isinstance(original_name_input, Tag)
        and "value" in original_name_input.attrs
    ):
        og_name_value = original_name_input["value"]
        data[FIELD_ORIGINAL_NAME] = (
            og_name_value[0] if isinstance(og_name_value, list) else og_name_value
        )
    else:
        data[FIELD_ORIGINAL_NAME] = ""

    original_ingredients_inputs = form.find_all(
        "input", attrs={"name": FIELD_ORIGINAL_INGREDIENTS}
    )
    data[FIELD_ORIGINAL_INGREDIENTS] = [
        str(orig_ing_input["value"])
        for orig_ing_input in original_ingredients_inputs
        if isinstance(orig_ing_input, Tag) and "value" in orig_ing_input.attrs
    ]

    original_instructions_inputs = form.find_all(
        "input", attrs={"name": FIELD_ORIGINAL_INSTRUCTIONS}
    )
    data[FIELD_ORIGINAL_INSTRUCTIONS] = [
        str(orig_inst_input["value"])
        for orig_inst_input in original_instructions_inputs
        if isinstance(orig_inst_input, Tag) and "value" in orig_inst_input.attrs
    ]

    prompt_input = form.find("input", attrs={"name": FIELD_MODIFICATION_PROMPT})
    if prompt_input and isinstance(prompt_input, Tag) and "value" in prompt_input.attrs:
        prompt_value = prompt_input["value"]
        data[FIELD_MODIFICATION_PROMPT] = (
            prompt_value[0] if isinstance(prompt_value, list) else prompt_value
        )
    else:
        data[FIELD_MODIFICATION_PROMPT] = ""

    return data


@pytest.mark.anyio
class TestModifyRecipeEndpoint:
    @patch("meal_planner.main.generate_modified_recipe", new_callable=AsyncMock)
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

        current_data_from_html = _extract_current_recipe_data_from_html(html_content)
        assert current_data_from_html["name"] == mock_llm_modified_recipe_fixture.name
        assert (
            current_data_from_html["ingredients"]
            == mock_llm_modified_recipe_fixture.ingredients
        )
        assert (
            current_data_from_html["instructions"]
            == mock_llm_modified_recipe_fixture.instructions
        )

        full_form_data_from_html = _extract_full_edit_form_data(html_content)
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

    @patch("meal_planner.main.generate_modified_recipe", new_callable=AsyncMock)
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

        form_data_from_html = _extract_full_edit_form_data(html_content)
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

    @patch("meal_planner.main.generate_modified_recipe", new_callable=AsyncMock)
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

        form_data_from_html = _extract_full_edit_form_data(html_content)
        assert form_data_from_html[FIELD_NAME] == current_recipe.name
        assert form_data_from_html[FIELD_INGREDIENTS] == current_recipe.ingredients
        assert form_data_from_html[FIELD_ORIGINAL_NAME] == original_recipe.name
        assert form_data_from_html[FIELD_MODIFICATION_PROMPT] == ""

        review_card_div = soup.find("div", id="review-card")
        assert review_card_div is not None, "Review card not found"
        assert original_recipe.name in review_card_div.get_text()

    @patch("meal_planner.main.generate_modified_recipe", new_callable=AsyncMock)
    async def test_modify_recipe_recipe_modification_error(
        self,
        mock_llm_modify: AsyncMock,
        client: AsyncClient,
        mock_current_recipe_before_modify_fixture: RecipeBase,
        mock_original_recipe_fixture: RecipeBase,
    ):
        """Test RecipeModificationError during LLM modification."""
        modification_error = RecipeModificationError(
            "LLM service failed to modify recipe"
        )
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
        assert error_div is not None, "RecipeModificationError message not found"
        assert CSS_ERROR_CLASS in error_div.get("class", []), (
            "Error message does not have the error CSS class"
        )

        form_data_from_html = _extract_full_edit_form_data(html_content)
        assert form_data_from_html[FIELD_NAME] == current_recipe.name
        assert form_data_from_html[FIELD_INGREDIENTS] == current_recipe.ingredients
        assert form_data_from_html[FIELD_MODIFICATION_PROMPT] == modification_prompt

    @patch("meal_planner.main.generate_modified_recipe", new_callable=AsyncMock)
    @patch("meal_planner.main.postprocess_recipe")
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

        form_data_from_html = _extract_full_edit_form_data(html_content)
        assert form_data_from_html[FIELD_NAME] == current_recipe.name
        assert form_data_from_html[FIELD_INGREDIENTS] == current_recipe.ingredients
        assert form_data_from_html[FIELD_MODIFICATION_PROMPT] == modification_prompt

    @patch("meal_planner.main.generate_modified_recipe", new_callable=AsyncMock)
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

        form_data_from_html = _extract_full_edit_form_data(html_content)
        assert form_data_from_html[FIELD_NAME] == current_recipe.name
        assert form_data_from_html[FIELD_INGREDIENTS] == current_recipe.ingredients
        assert form_data_from_html[FIELD_MODIFICATION_PROMPT] == modification_prompt
