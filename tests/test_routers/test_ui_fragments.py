"""Tests for route handlers defined in meal_planner.routers.ui_fragments."""

from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import monsterui.all as mu
import pytest
from bs4 import BeautifulSoup, Tag
from httpx import AsyncClient
from pydantic import ValidationError

from meal_planner.models import RecipeBase
from meal_planner.routers.ui_fragments import _get_http_error_message
from meal_planner.ui.common import CSS_ERROR_CLASS
from tests.constants import (
    FIELD_INGREDIENTS,
    FIELD_INSTRUCTIONS,
    FIELD_NAME,
    FIELD_ORIGINAL_INGREDIENTS,
    FIELD_ORIGINAL_INSTRUCTIONS,
    FIELD_ORIGINAL_NAME,
    FIELD_RECIPE_TEXT,  # For TestRecipeSortableListPersistence
    FIELD_RECIPE_URL,
    RECIPES_EXTRACT_RUN_URL,  # For TestRecipeSortableListPersistence
    RECIPES_FETCH_TEXT_URL,
)
from tests.test_helpers import extract_full_edit_form_data


def _build_ui_fragment_form_data(
    name="Test Recipe",
    ingredients=None,
    instructions=None,
    original_name=None,
    original_ingredients=None,
    original_instructions=None,
) -> dict:
    ingredients = ingredients if ingredients is not None else ["ing1"]
    instructions = instructions if instructions is not None else ["step1"]
    original_name = original_name if original_name is not None else name
    original_ingredients = (
        original_ingredients if original_ingredients is not None else ingredients
    )
    original_instructions = (
        original_instructions if original_instructions is not None else instructions
    )

    return {
        "name": name,
        "ingredients": ingredients,
        "instructions": instructions,
        "original_name": original_name,
        "original_ingredients": original_ingredients,
        "original_instructions": original_instructions,
    }


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

    @patch("meal_planner.routers.ui_fragments.build_diff_content_children")
    @patch("meal_planner.routers.ui_fragments.logger.error")
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

    async def test_update_diff_happy_path(self, client: AsyncClient):
        """Test successful diff generation and rendering."""
        current = RecipeBase(
            name="New Name", ingredients=["ing1", "new_ing"], instructions=["s1"]
        )
        original = RecipeBase(
            name="Old Name", ingredients=["ing1"], instructions=["s1", "old_s2"]
        )
        form_data = self._build_diff_form_data(current, original)

        response = await client.post(self.UPDATE_DIFF_URL, data=form_data)
        assert response.status_code == 200
        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        wrapper_div = soup.find("div", id="diff-content-wrapper")
        assert wrapper_div is not None
        assert "flex" in wrapper_div.get("class", [])
        assert "space-x-4" in wrapper_div.get("class", [])
        assert "mt-4" in wrapper_div.get("class", [])

        before_pre = wrapper_div.find("pre", id="diff-before-pre")
        after_pre = wrapper_div.find("pre", id="diff-after-pre")
        assert before_pre is not None
        assert after_pre is not None

        assert before_pre.find("del") is not None, "<del> tag missing in before_pre"
        assert after_pre.find("ins") is not None, "<ins> tag missing in after_pre"
        assert "Old Name" in before_pre.get_text()
        assert "New Name" in after_pre.get_text()

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
    @patch("meal_planner.routers.ui_fragments.logger.warning")
    async def test_update_diff_validation_error(
        self,
        mock_logger_warning,
        client: AsyncClient,
        invalid_field: str,
        invalid_value: str | list[str],
        error_title_suffix: str,
    ):
        valid_recipe = RecipeBase(name="Valid", ingredients=["i"], instructions=["s"])
        form_data = self._build_diff_form_data(valid_recipe, valid_recipe)
        form_data[invalid_field] = invalid_value

        response = await client.post(self.UPDATE_DIFF_URL, data=form_data)

        assert response.status_code == 200
        html = response.text
        assert "Please check your recipe fields - there may be invalid values." in html
        assert "diff-content-wrapper" not in html

        mock_logger_warning.assert_called_once()
        args, kwargs = mock_logger_warning.call_args
        assert args[0] == "Validation error during diff update: %s"
        assert isinstance(args[1], ValidationError)
        assert kwargs.get("exc_info") is False

    @pytest.mark.anyio
    @patch("meal_planner.routers.ui_fragments.logger.error")
    @patch("meal_planner.routers.ui_fragments.parse_recipe_form_data")
    async def test_update_diff_parsing_exception(
        self, mock_parse, mock_logger_error: MagicMock, client: AsyncClient
    ):
        dummy_form_data = {FIELD_NAME: "Test", "original_name": "Orig"}

        with patch(
            "meal_planner.routers.ui_fragments.parse_recipe_form_data",
            side_effect=Exception("Simulated parsing error"),
        ) as mock_parse_cm:
            response = await client.post(
                TestUpdateDiffEndpoint.UPDATE_DIFF_URL, data=dummy_form_data
            )

        assert response.status_code == 200
        assert "Error updating diff view." in response.text
        assert CSS_ERROR_CLASS in response.text
        assert mock_parse_cm.call_count == 1
        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        assert "Error updating diff: %s" in args[0]
        assert kwargs.get("exc_info") is True


@pytest.mark.anyio
class TestRecipeSortableListPersistence:
    INITIAL_RECIPE_TEXT = (
        "Sortable Test Recipe\\\n"
        "Ingredients: Ing1, Ing2, Ing3\\\n"
        "Instructions: Step1, Step2"
    )
    MOCK_INITIAL_RECIPE = RecipeBase(
        name="Sortable Test",
        ingredients=["Ing1", "Ing2", "Ing3"],
        instructions=["First instruction details.", "Second instruction details."],
    )

    def _assert_sortable_attributes(
        self, sortable_div: Tag | None, list_id_prefix: str
    ):
        assert sortable_div is not None, f"Sortable div '{list_id_prefix}' not found"
        assert isinstance(sortable_div, Tag)
        assert sortable_div.get("uk-sortable") == "handle: .drag-handle", (
            f"uk-sortable missing or incorrect for {list_id_prefix}"
        )
        assert sortable_div.get("hx-trigger") == "moved", (
            f"hx-trigger missing or incorrect for {list_id_prefix}"
        )
        assert sortable_div.get("hx-post") == "/recipes/ui/update-diff", (
            f"hx-post missing or incorrect for {list_id_prefix}"
        )
        assert sortable_div.get("hx-target") == "#diff-content-wrapper", (
            f"hx-target missing or incorrect for {list_id_prefix}"
        )
        assert sortable_div.get("hx-swap") == "innerHTML", (
            f"hx-swap missing or incorrect for {list_id_prefix}"
        )
        assert sortable_div.get("hx-include") == "closest form", (
            f"hx-include missing or incorrect for {list_id_prefix}"
        )

    @patch("meal_planner.routers.actions.generate_recipe_from_text")
    @patch("meal_planner.routers.actions.postprocess_recipe")
    async def test_sortable_after_ingredient_delete(
        self, mock_postprocess, mock_llm_extract, client: AsyncClient
    ):
        mock_llm_extract.return_value = self.MOCK_INITIAL_RECIPE
        mock_postprocess.return_value = self.MOCK_INITIAL_RECIPE

        extract_response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: self.INITIAL_RECIPE_TEXT}
        )
        assert extract_response.status_code == 200
        html_after_extract = extract_response.text

        soup_after_extract = BeautifulSoup(html_after_extract, "html.parser")
        edit_form_target_oob_div = soup_after_extract.find("div", id="edit-form-target")
        assert edit_form_target_oob_div is not None, (
            "OOB div with id='edit-form-target' not found after extract. "
            f"Response: {html_after_extract[:500]}..."
        )
        assert edit_form_target_oob_div.get("hx-swap-oob") == "innerHTML", (
            "hx-swap-oob attribute missing or incorrect on edit-form-target"
        )

        form_in_oob = edit_form_target_oob_div.find("form", id="edit-review-form")
        ingredients_list_div_extract = form_in_oob.find("div", id="ingredients-list")
        self._assert_sortable_attributes(
            ingredients_list_div_extract, "ingredients-list (initial extract)"
        )

        form_data_for_delete = extract_full_edit_form_data(html_after_extract)

        assert form_data_for_delete[FIELD_NAME] == self.MOCK_INITIAL_RECIPE.name
        assert (
            form_data_for_delete[FIELD_INGREDIENTS]
            == self.MOCK_INITIAL_RECIPE.ingredients
        )

        index_to_delete = 1
        delete_url = f"/recipes/ui/delete-ingredient/{index_to_delete}"
        delete_response = await client.post(delete_url, data=form_data_for_delete)
        assert delete_response.status_code == 200
        html_after_delete = delete_response.text

        soup_after_delete = BeautifulSoup(html_after_delete, "html.parser")
        ingredients_list_div_after_delete = soup_after_delete.find(
            "div", id="ingredients-list"
        )
        self._assert_sortable_attributes(
            ingredients_list_div_after_delete, "ingredients-list (after delete)"
        )

        assert isinstance(ingredients_list_div_after_delete, Tag), (
            "ingredients_list_div_after_delete is not a Tag"
        )
        inputs = ingredients_list_div_after_delete.find_all(
            "input", attrs={"name": FIELD_INGREDIENTS}
        )
        assert len(inputs) == 2, f"Expected 2 ingredients, got {len(inputs)}"
        assert inputs[0].get("value") == "Ing1"
        assert inputs[1].get("value") == "Ing3"

    @patch("meal_planner.routers.actions.generate_recipe_from_text")
    @patch("meal_planner.routers.actions.postprocess_recipe")
    async def test_sortable_after_instruction_delete(
        self, mock_postprocess, mock_llm_extract, client: AsyncClient
    ):
        mock_llm_extract.return_value = self.MOCK_INITIAL_RECIPE
        mock_postprocess.return_value = self.MOCK_INITIAL_RECIPE

        extract_response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: self.INITIAL_RECIPE_TEXT}
        )
        assert extract_response.status_code == 200
        html_after_extract = extract_response.text

        soup_after_extract = BeautifulSoup(html_after_extract, "html.parser")
        edit_form_target_oob_div = soup_after_extract.find("div", id="edit-form-target")
        assert edit_form_target_oob_div is not None, (
            "OOB div with id='edit-form-target' not found after extract. "
            f"Response: {html_after_extract[:500]}..."
        )
        assert edit_form_target_oob_div.get("hx-swap-oob") == "innerHTML", (
            "hx-swap-oob attribute missing or incorrect on edit-form-target"
        )

        form_in_oob = edit_form_target_oob_div.find("form", id="edit-review-form")
        instructions_list_div_extract = form_in_oob.find("div", id="instructions-list")
        self._assert_sortable_attributes(
            instructions_list_div_extract, "instructions-list (initial extract)"
        )

        form_data_for_delete = extract_full_edit_form_data(html_after_extract)
        assert (
            form_data_for_delete[FIELD_INSTRUCTIONS]
            == self.MOCK_INITIAL_RECIPE.instructions
        )

        index_to_delete = 0
        delete_url = f"/recipes/ui/delete-instruction/{index_to_delete}"
        delete_response = await client.post(delete_url, data=form_data_for_delete)
        assert delete_response.status_code == 200
        html_after_delete = delete_response.text

        soup_after_delete = BeautifulSoup(html_after_delete, "html.parser")
        instructions_list_div_after_delete = soup_after_delete.find(
            "div", id="instructions-list"
        )
        self._assert_sortable_attributes(
            instructions_list_div_after_delete, "instructions-list (after delete)"
        )

        assert isinstance(instructions_list_div_after_delete, Tag)
        textareas = instructions_list_div_after_delete.find_all(
            "textarea", attrs={"name": FIELD_INSTRUCTIONS}
        )
        assert len(textareas) == 1, f"Expected 1 instruction, got {len(textareas)}"
        assert (
            textareas[0].get_text(strip=True) == "Second instruction details."
        )  # Original was "Second instruction details"

    @patch("meal_planner.routers.actions.generate_recipe_from_text")
    @patch("meal_planner.routers.actions.postprocess_recipe")
    async def test_sortable_after_ingredient_add(
        self, mock_postprocess, mock_llm_extract, client: AsyncClient
    ):
        mock_llm_extract.return_value = self.MOCK_INITIAL_RECIPE
        mock_postprocess.return_value = self.MOCK_INITIAL_RECIPE

        extract_response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: self.INITIAL_RECIPE_TEXT}
        )
        assert extract_response.status_code == 200
        html_after_extract = extract_response.text

        soup_after_extract = BeautifulSoup(html_after_extract, "html.parser")
        edit_form_target_oob_div = soup_after_extract.find("div", id="edit-form-target")
        assert edit_form_target_oob_div is not None, (
            "OOB div with id='edit-form-target' not found after extract. "
            f"Response: {html_after_extract[:500]}..."
        )
        assert edit_form_target_oob_div.get("hx-swap-oob") == "innerHTML", (
            "hx-swap-oob attribute missing or incorrect on edit-form-target"
        )

        form_in_oob = edit_form_target_oob_div.find("form", id="edit-review-form")
        ingredients_list_div_extract = form_in_oob.find("div", id="ingredients-list")
        self._assert_sortable_attributes(
            ingredients_list_div_extract, "ingredients-list (initial extract)"
        )

        form_data_for_add = extract_full_edit_form_data(html_after_extract)

        add_url = "/recipes/ui/add-ingredient"
        add_response = await client.post(add_url, data=form_data_for_add)
        assert add_response.status_code == 200
        html_after_add = add_response.text

        soup_after_add = BeautifulSoup(html_after_add, "html.parser")
        ingredients_list_div_after_add = soup_after_add.find(
            "div", id="ingredients-list"
        )
        self._assert_sortable_attributes(
            ingredients_list_div_after_add, "ingredients-list (after add)"
        )

        assert isinstance(ingredients_list_div_after_add, Tag)
        inputs = ingredients_list_div_after_add.find_all(
            "input", attrs={"name": FIELD_INGREDIENTS}
        )
        assert len(inputs) == 4, f"Expected 4 ingredients, got {len(inputs)}"
        assert inputs[0].get("value") == "Ing1"
        assert inputs[1].get("value") == "Ing2"
        assert inputs[2].get("value") == "Ing3"
        assert inputs[3].get("value", "") == ""

    @patch("meal_planner.routers.actions.generate_recipe_from_text")
    @patch("meal_planner.routers.actions.postprocess_recipe")
    async def test_sortable_after_instruction_add(
        self, mock_postprocess, mock_llm_extract, client: AsyncClient
    ):
        mock_llm_extract.return_value = self.MOCK_INITIAL_RECIPE
        mock_postprocess.return_value = self.MOCK_INITIAL_RECIPE

        extract_response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: self.INITIAL_RECIPE_TEXT}
        )
        assert extract_response.status_code == 200
        html_after_extract = extract_response.text

        soup_after_extract = BeautifulSoup(html_after_extract, "html.parser")
        edit_form_target_oob_div = soup_after_extract.find("div", id="edit-form-target")
        assert edit_form_target_oob_div is not None, (
            "OOB div with id='edit-form-target' not found after extract. "
            f"Response: {html_after_extract[:500]}..."
        )
        assert edit_form_target_oob_div.get("hx-swap-oob") == "innerHTML", (
            "hx-swap-oob attribute missing or incorrect on edit-form-target"
        )

        form_in_oob = edit_form_target_oob_div.find("form", id="edit-review-form")
        instructions_list_div_extract = form_in_oob.find("div", id="instructions-list")
        self._assert_sortable_attributes(
            instructions_list_div_extract, "instructions-list (initial extract)"
        )

        form_data_for_add = extract_full_edit_form_data(html_after_extract)

        add_url = "/recipes/ui/add-instruction"
        add_response = await client.post(add_url, data=form_data_for_add)
        assert add_response.status_code == 200
        html_after_add = add_response.text

        soup_after_add = BeautifulSoup(html_after_add, "html.parser")
        instructions_list_div_after_add = soup_after_add.find(
            "div", id="instructions-list"
        )
        self._assert_sortable_attributes(
            instructions_list_div_after_add, "instructions-list (after add)"
        )

        assert isinstance(instructions_list_div_after_add, Tag)
        textareas = instructions_list_div_after_add.find_all(
            "textarea", attrs={"name": FIELD_INSTRUCTIONS}
        )
        assert len(textareas) == 3, f"Expected 3 instructions, got {len(textareas)}"
        assert textareas[0].get_text(strip=True) == "First instruction details."
        assert textareas[1].get_text(strip=True) == "Second instruction details."
        assert textareas[2].get_text(strip=True) == ""


@pytest.mark.anyio
class TestRecipeUIFragments:
    ADD_INGREDIENT_URL = "/recipes/ui/add-ingredient"
    ADD_INSTRUCTION_URL = "/recipes/ui/add-instruction"
    DELETE_INGREDIENT_BASE_URL = "/recipes/ui/delete-ingredient"
    DELETE_INSTRUCTION_BASE_URL = "/recipes/ui/delete-instruction"

    async def test_add_ingredient(self, client: AsyncClient):
        form_data = _build_ui_fragment_form_data(
            ingredients=["existing ing"], instructions=["step1"]
        )
        response = await client.post(self.ADD_INGREDIENT_URL, data=form_data)
        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")

        ingredients_list_div = soup.find("div", id="ingredients-list")
        assert ingredients_list_div, "Ingredients list div not found"
        assert isinstance(ingredients_list_div, Tag)
        ingredient_inputs = ingredients_list_div.find_all(
            "input", {"name": "ingredients"}
        )
        assert len(ingredient_inputs) == 2, (
            f"Expected 2 ingredient inputs, got {len(ingredient_inputs)}"
        )

        new_ingredient_input = ingredient_inputs[-1]
        assert isinstance(new_ingredient_input, Tag)
        assert new_ingredient_input.get("value", "") == ""
        assert new_ingredient_input["placeholder"] == "Ingredient"

        new_item_div = new_ingredient_input.find_parent("div", class_="flex")
        assert new_item_div, "Parent div for new ingredient not found"
        assert isinstance(new_item_div, Tag)
        delete_button = new_item_div.find(
            "button",
            {
                "hx-post": lambda x: bool(
                    x and x.startswith(f"{self.DELETE_INGREDIENT_BASE_URL}/")
                )
            },
        )
        assert delete_button, "Delete button for new ingredient not found"
        assert isinstance(delete_button, Tag)

        icon_element = delete_button.find("uk-icon", attrs={"icon": "minus-circle"})
        assert icon_element, (
            "UkIcon 'minus-circle' not found in ingredient delete button"
        )
        assert isinstance(icon_element, Tag)
        class_list = icon_element.get("class")
        if class_list is None:
            class_list = []
        assert str(mu.TextT.error) in class_list

        oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#diff-content-wrapper"})
        assert oob_div, "OOB diff wrapper not found"
        assert isinstance(oob_div, Tag)
        assert oob_div.find("pre", id="diff-before-pre"), "Diff before pre not found"
        assert oob_div.find("pre", id="diff-after-pre"), "Diff after pre not found"

    @patch("meal_planner.routers.ui_fragments.parse_recipe_form_data")
    @patch("meal_planner.routers.ui_fragments.logger.error")
    async def test_add_instruction_validation_error(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        validation_exc = ValidationError.from_exception_data(
            title="TestVE_add_inst", line_errors=[]
        )
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["inst1"]
        )

        # Set up mock to raise ValidationError on first call, return data on second call
        mock_parse.side_effect = [
            validation_exc,  # First call in try block
            form_data.copy(),  # Second call in except ValidationError block
        ]

        response = await client.post(self.ADD_INSTRUCTION_URL, data=form_data)
        assert response.status_code == 200
        assert "Error updating list after add." in response.text
        assert CSS_ERROR_CLASS in response.text

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        expected_log_msg = (
            f"Validation error processing instruction addition: {validation_exc}"
        )
        assert args[0] == expected_log_msg
        assert kwargs.get("exc_info") is True

    async def test_delete_ingredient(self, client: AsyncClient):
        initial_ingredients = ["ing_to_keep1", "ing_to_delete", "ing_to_keep2"]
        form_data = _build_ui_fragment_form_data(
            ingredients=initial_ingredients, instructions=["step1"]
        )
        index_to_delete = 1

        response = await client.post(
            f"{self.DELETE_INGREDIENT_BASE_URL}/{index_to_delete}", data=form_data
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")

        ingredients_list_div = soup.find("div", id="ingredients-list")
        assert ingredients_list_div, "Ingredients list div for delete not found"
        assert isinstance(ingredients_list_div, Tag)
        ingredient_inputs = ingredients_list_div.find_all(
            "input", {"name": "ingredients"}
        )
        assert len(ingredient_inputs) == 2, (
            f"Expected 2 ingredients after delete, got {len(ingredient_inputs)}"
        )

        rendered_ingredient_values = [
            cast(Tag, inp)["value"] for inp in ingredient_inputs
        ]
        assert "ing_to_keep1" in rendered_ingredient_values
        assert "ing_to_keep2" in rendered_ingredient_values
        assert "ing_to_delete" not in rendered_ingredient_values

        oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#diff-content-wrapper"})
        assert oob_div, "OOB diff wrapper for delete not found"
        assert isinstance(oob_div, Tag)
        assert oob_div.find("pre", id="diff-before-pre"), (
            "Diff before pre for delete not found"
        )
        assert oob_div.find("pre", id="diff-after-pre"), (
            "Diff after pre for delete not found"
        )

    async def test_delete_instruction(self, client: AsyncClient):
        initial_instructions = ["step_to_keep1", "step_to_delete", "step_to_keep2"]
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=initial_instructions
        )
        index_to_delete = 1

        response = await client.post(
            f"{self.DELETE_INSTRUCTION_BASE_URL}/{index_to_delete}", data=form_data
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")

        instructions_list_div = soup.find("div", id="instructions-list")
        assert instructions_list_div, "Instructions list div for delete not found"
        assert isinstance(instructions_list_div, Tag)
        instruction_textareas = instructions_list_div.find_all(
            "textarea", {"name": "instructions"}
        )
        assert len(instruction_textareas) == 2, (
            f"Expected 2 instructions after delete, got {len(instruction_textareas)}"
        )

        rendered_instruction_values = [ta.text for ta in instruction_textareas]
        assert "step_to_keep1" in rendered_instruction_values
        assert "step_to_keep2" in rendered_instruction_values
        assert "step_to_delete" not in rendered_instruction_values

        oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#diff-content-wrapper"})
        assert oob_div, "OOB diff wrapper for delete not found"
        assert isinstance(oob_div, Tag)
        assert oob_div.find("pre", id="diff-before-pre"), (
            "Diff before pre for delete not found"
        )
        assert oob_div.find("pre", id="diff-after-pre"), (
            "Diff after pre for delete not found"
        )

    @pytest.mark.parametrize("invalid_index", [5])
    @patch("meal_planner.routers.ui_fragments.logger.warning")
    async def test_delete_ingredient_invalid_index(
        self, mock_logger_warning, client: AsyncClient, invalid_index: int
    ):
        initial_ingredients = ["ing1", "ing2"]
        form_data = _build_ui_fragment_form_data(
            ingredients=initial_ingredients, instructions=["step1"]
        )

        response = await client.post(
            f"{self.DELETE_INGREDIENT_BASE_URL}/{invalid_index}", data=form_data
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")
        ingredient_inputs = soup.find_all("input", {"name": "ingredients"})
        assert len(ingredient_inputs) == len(initial_ingredients)
        mock_logger_warning.assert_called_once_with(
            f"Attempted to delete ingredient at invalid index {invalid_index}"
        )

    @pytest.mark.parametrize("invalid_index", [5])
    @patch("meal_planner.routers.ui_fragments.logger.warning")
    async def test_delete_instruction_invalid_index(
        self, mock_logger_warning, client: AsyncClient, invalid_index: int
    ):
        initial_instructions = ["inst1", "inst2"]
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=initial_instructions
        )

        response = await client.post(
            f"{self.DELETE_INSTRUCTION_BASE_URL}/{invalid_index}", data=form_data
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")
        instruction_textareas = soup.find_all("textarea", {"name": "instructions"})
        assert len(instruction_textareas) == len(initial_instructions)
        mock_logger_warning.assert_called_once_with(
            f"Attempted to delete instruction at invalid index {invalid_index}"
        )

    @patch("meal_planner.routers.ui_fragments.parse_recipe_form_data")
    @patch("meal_planner.routers.ui_fragments.logger.error")
    async def test_delete_ingredient_validation_error(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        validation_exc = ValidationError.from_exception_data(
            title="TestVE_del_ing", line_errors=[]
        )
        initial_ingredients = ["ing1_to_delete", "ing2_remains"]
        form_data_dict = _build_ui_fragment_form_data(
            ingredients=initial_ingredients, instructions=["s1"]
        )

        mock_parse.side_effect = [
            validation_exc,  # First call to parse_recipe_form_data in the try block
            form_data_dict.copy(),  # Second call in the except ValidationError block
        ]
        index_to_delete = 0

        response = await client.post(
            f"{self.DELETE_INGREDIENT_BASE_URL}/{index_to_delete}", data=form_data_dict
        )
        assert response.status_code == 200
        assert "Error updating list after delete. Validation failed." in response.text
        assert CSS_ERROR_CLASS in response.text

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        expected_log_msg_fragment = "Validation error processing ingredient deletion"
        assert expected_log_msg_fragment in args[0]
        # Ensure the specific exception 'e' is part of the log message
        assert str(validation_exc) in args[0]  # Check if the specific error is logged
        assert kwargs.get("exc_info") is True

        # Check that the list is re-rendered with original items on validation error
        soup = BeautifulSoup(response.text, "html.parser")
        ingredients_list_div = soup.find("div", id="ingredients-list")
        assert ingredients_list_div, "Ingredients list div for error case not found"
        assert isinstance(ingredients_list_div, Tag)
        ingredient_inputs = ingredients_list_div.find_all(
            "input", {"name": "ingredients"}
        )
        assert len(ingredient_inputs) == len(initial_ingredients)

        # Check that OOB diff is NOT sent
        oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#diff-content-wrapper"})
        assert not oob_div, "OOB diff wrapper should NOT be present on validation error"

    @patch("meal_planner.routers.ui_fragments.parse_recipe_form_data")
    @patch("meal_planner.routers.ui_fragments.logger.error")
    async def test_delete_ingredient_generic_exception(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        generic_exc = Exception("Generic parse error for del_ing")
        mock_parse.side_effect = generic_exc  # This will be raised by the first call
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["s1"]
        )
        index_to_delete = 0

        response = await client.post(
            f"{self.DELETE_INGREDIENT_BASE_URL}/{index_to_delete}", data=form_data
        )
        assert response.status_code == 200
        assert "Error processing delete request." in response.text
        assert CSS_ERROR_CLASS in response.text

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        expected_log_msg = (
            f"Error deleting ingredient at index {index_to_delete}: {generic_exc}"
        )
        assert args[0] == expected_log_msg
        assert kwargs.get("exc_info") is True

    @patch("meal_planner.routers.ui_fragments.parse_recipe_form_data")
    @patch("meal_planner.routers.ui_fragments.logger.error")
    async def test_delete_instruction_validation_error(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        validation_exc = ValidationError.from_exception_data(
            title="TestVE_del_inst", line_errors=[]
        )
        initial_instructions = ["inst1_to_delete", "inst2_remains"]
        form_data_dict = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=initial_instructions
        )

        mock_parse.side_effect = [
            validation_exc,  # First call in the try block
            form_data_dict.copy(),  # Second call in the except ValidationError block
        ]
        index_to_delete = 0

        response = await client.post(
            f"{self.DELETE_INSTRUCTION_BASE_URL}/{index_to_delete}", data=form_data_dict
        )
        assert response.status_code == 200
        assert "Error updating list after delete. Validation failed." in response.text
        assert CSS_ERROR_CLASS in response.text

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        expected_log_msg_fragment = "Validation error processing instruction deletion"
        assert expected_log_msg_fragment in args[0]
        # Ensure the specific exception 'e' is part of the log message
        assert str(validation_exc) in args[0]  # Check if the specific error is logged
        assert kwargs.get("exc_info") is True

        # Check that the list is re-rendered with original items on validation error
        soup = BeautifulSoup(response.text, "html.parser")
        instructions_list_div = soup.find("div", id="instructions-list")
        assert instructions_list_div, "Instructions list div for error case not found"
        assert isinstance(instructions_list_div, Tag)
        instruction_inputs = instructions_list_div.find_all(
            "textarea", {"name": "instructions"}
        )
        assert len(instruction_inputs) == len(initial_instructions)

        # Check that OOB diff is NOT sent
        oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#diff-content-wrapper"})
        assert not oob_div, "OOB diff wrapper should NOT be present on validation error"

    @patch("meal_planner.routers.ui_fragments.parse_recipe_form_data")
    @patch("meal_planner.routers.ui_fragments.logger.error")
    async def test_delete_instruction_generic_exception(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        generic_exc = Exception("Generic parse error for del_inst")
        mock_parse.side_effect = generic_exc
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["inst1"]
        )
        index_to_delete = 0

        response = await client.post(
            f"{self.DELETE_INSTRUCTION_BASE_URL}/{index_to_delete}", data=form_data
        )
        assert response.status_code == 200
        assert "Error processing delete request." in response.text
        assert CSS_ERROR_CLASS in response.text

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        expected_log_msg = (
            f"Error deleting instruction at index {index_to_delete}: {generic_exc}"
        )
        assert args[0] == expected_log_msg
        assert kwargs.get("exc_info") is True

    @patch("meal_planner.routers.ui_fragments.parse_recipe_form_data")
    @patch("meal_planner.routers.ui_fragments.logger.error")
    async def test_add_ingredient_validation_error(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        validation_exc = ValidationError.from_exception_data(
            title="TestVE_add_ing", line_errors=[]
        )
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["inst1"]
        )

        # Set up mock to raise ValidationError on first call, return data on second call
        mock_parse.side_effect = [
            validation_exc,  # First call in try block
            form_data.copy(),  # Second call in except ValidationError block
        ]

        response = await client.post(self.ADD_INGREDIENT_URL, data=form_data)
        assert response.status_code == 200
        assert "Error updating list after add." in response.text
        assert CSS_ERROR_CLASS in response.text

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        expected_log_msg = (
            f"Validation error processing ingredient addition: {validation_exc}"
        )
        assert args[0] == expected_log_msg
        assert kwargs.get("exc_info") is True

    @patch("meal_planner.routers.ui_fragments.parse_recipe_form_data")
    @patch("meal_planner.routers.ui_fragments.logger.error")
    async def test_add_ingredient_generic_exception(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        generic_exc = Exception("Generic parse error for add_ing")
        mock_parse.side_effect = generic_exc
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["inst1"]
        )

        response = await client.post(self.ADD_INGREDIENT_URL, data=form_data)
        assert response.status_code == 200
        assert "Error processing add request." in response.text
        assert CSS_ERROR_CLASS in response.text

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        expected_log_msg = f"Error adding ingredient: {generic_exc}"
        assert args[0] == expected_log_msg
        assert kwargs.get("exc_info") is True

    @patch("meal_planner.routers.ui_fragments.parse_recipe_form_data")
    @patch("meal_planner.routers.ui_fragments.logger.error")
    async def test_add_instruction_generic_exception(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        generic_exc = Exception("Generic parse error for add_inst")
        mock_parse.side_effect = generic_exc
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["inst1"]
        )

        response = await client.post(self.ADD_INSTRUCTION_URL, data=form_data)
        assert response.status_code == 200
        assert "Error processing add request." in response.text
        assert CSS_ERROR_CLASS in response.text

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        expected_log_msg = f"Error adding instruction: {generic_exc}"
        assert args[0] == expected_log_msg
        assert kwargs.get("exc_info") is True

    async def test_delete_instruction_missing_ingredients_in_form(
        self, client: AsyncClient
    ):
        # This test checks if the parse_recipe_form_data in the except ValidationError
        # block handles missing 'ingredients' gracefully (it should default to []).
        initial_instructions = ["step_to_keep1", "step_to_delete", "step_to_keep2"]
        index_to_delete = 1

        # Form data intentionally missing 'ingredients' and 'original_ingredients'
        form_data_dict = {
            "name": "Test Recipe Name",
            "instructions": initial_instructions,
            "original_name": "Test Recipe Name",
            "original_instructions": initial_instructions,
            # 'ingredients' and 'original_ingredients' are missing
        }

        # To trigger the ValidationError path in post_delete_instruction_row,
        # we need parse_recipe_form_data (the first call in the `try` block)
        # to raise a ValidationError.
        # We'll mock parse_recipe_form_data to do this for the first call,
        # and for the second call (in the `except` block), it will parse
        # the incomplete form_data_dict.
        with patch(
            "meal_planner.routers.ui_fragments.parse_recipe_form_data"
        ) as mock_parse_dynamic:
            validation_error = ValidationError.from_exception_data(
                title="mock VE", line_errors=[]
            )
            mock_parse_dynamic.side_effect = [
                validation_error,  # First call raises ValidationError
                {
                    "name": "Test Recipe Name",
                    "instructions": initial_instructions,
                    "ingredients": [],  # This is what parse_recipe_form_data would do
                    # when 'ingredients' is missing from form_data
                },  # Second call in except block
            ]

            response = await client.post(
                f"{self.DELETE_INSTRUCTION_BASE_URL}/{index_to_delete}",
                data=form_data_dict,
            )

        assert response.status_code == 200
        assert "Error updating list after delete. Validation failed." in response.text
        assert CSS_ERROR_CLASS in response.text

        # Verify that parse_recipe_form_data was called twice
        assert mock_parse_dynamic.call_count == 2

        # Check that the list is re-rendered with original items on validation error
        soup = BeautifulSoup(response.text, "html.parser")
        instructions_list_div = soup.find("div", id="instructions-list")
        assert instructions_list_div, "Instructions list div for error case not found"
        assert isinstance(instructions_list_div, Tag)
        instruction_inputs = instructions_list_div.find_all(
            "textarea", {"name": "instructions"}
        )
        assert len(instruction_inputs) == len(initial_instructions)


# Tests for generate_diff_html and build_edit_review_form are specific to ui.edit_recipe
# and should remain in tests/test_ui/test_recipe_editor.py, not moved here.
# This file is for testing the route handlers in ui_fragments.py.


@pytest.mark.anyio
class TestFetchTextEndpoint:
    TEST_URL = "http://example.com/fetch-success"

    async def test_success(self, client: AsyncClient):
        mock_text = "Fetched and cleaned recipe text."

        with patch(
            "meal_planner.routers.ui_fragments.fetch_and_clean_text_from_url",
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
        "exception_type, exception_args, exception_kwargs, expected_message",
        [
            (
                httpx.RequestError,
                ("Network connection failed",),
                {"request": httpx.Request("GET", "http://example.com/fetch-success")},
                "Error fetching URL. Please check the URL and your connection.",
            ),
            (
                httpx.HTTPStatusError,
                ("404 Client Error",),
                {
                    "request": httpx.Request("GET", "http://example.com/fetch-success"),
                    "response": httpx.Response(
                        404,
                        request=httpx.Request(
                            "GET", "http://example.com/fetch-success"
                        ),
                    ),
                },
                "The recipe page was not found. Please check the URL and try again.",
            ),
            (
                RuntimeError,
                ("Processing failed",),
                {},
                "Failed to process the content from the URL.",
            ),
            (
                Exception,
                ("Unexpected error",),
                {},
                "An unexpected error occurred while fetching text.",
            ),
        ],
    )
    async def test_fetch_text_errors(
        self,
        client: AsyncClient,
        exception_type,
        exception_args,
        exception_kwargs,
        expected_message,
    ):
        """Test that various exceptions from the service are handled correctly."""
        with patch(
            "meal_planner.routers.ui_fragments.fetch_and_clean_text_from_url",
            new_callable=AsyncMock,
        ) as local_mock_fetch_clean:
            local_mock_fetch_clean.side_effect = exception_type(
                *exception_args, **exception_kwargs
            )

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

    async def test_fetch_text_perimeterx_response(self, client: AsyncClient):
        """Test that PerimeterX responses are handled with specific messaging."""
        perimeterx_html = """
        <!DOCTYPE html> <html lang="en"> <head>
        <title>Access to this page has been denied.</title>
        </head> <body>
        <p>Access to this page has been denied because we believe you are using
        automation tools to browse the website.</p>
        <p>Powered by <a href="https://www.perimeterx.com/whywasiblocked">
        PerimeterX</a>, Inc.</p>
        </body> </html>
        """

        with patch(
            "meal_planner.routers.ui_fragments.fetch_and_clean_text_from_url",
            new_callable=AsyncMock,
        ) as local_mock_fetch_clean:
            local_mock_fetch_clean.side_effect = httpx.HTTPStatusError(
                "403 Forbidden",
                request=httpx.Request("GET", self.TEST_URL),
                response=httpx.Response(
                    403,
                    content=perimeterx_html,
                    request=httpx.Request("GET", self.TEST_URL),
                ),
            )

            response = await client.post(
                RECIPES_FETCH_TEXT_URL, data={FIELD_RECIPE_URL: self.TEST_URL}
            )

            assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        error_div = soup.find("div", id="fetch-url-error-display")
        assert error_div is not None
        error_text = error_div.text.strip()
        assert "security measures that block automated access" in error_text
        assert "copy and paste the recipe text below" in error_text

    @pytest.mark.parametrize(
        "invalid_url, expected_error_fragment",
        [
            # Invalid schemes
            ("ftp://example.com/recipe", "Only HTTP and HTTPS URLs are allowed"),
            ("file:///etc/passwd", "Only HTTP and HTTPS URLs are allowed"),
            ("javascript:alert(1)", "Only HTTP and HTTPS URLs are allowed"),
            # Missing domain
            ("http://", "Invalid URL: missing domain"),
            ("https://", "Invalid URL: missing domain"),
            # Private IP ranges
            ("http://127.0.0.1/admin", "Loopback addresses are not allowed"),
            ("https://localhost/metadata", "Internal hostnames are not allowed"),
            ("http://10.0.0.1/internal", "Private IP addresses are not allowed"),
            ("http://192.168.1.1/router", "Private IP addresses are not allowed"),
            ("http://172.16.0.1/service", "Private IP addresses are not allowed"),
            # Cloud metadata endpoints
            ("http://169.254.169.254/metadata", "Link-local addresses are not allowed"),
            ("http://metadata.google.internal/", "Internal hostnames are not allowed"),
            # Malformed URLs
            ("not-a-url", "Only HTTP and HTTPS URLs are allowed"),
            ("://invalid", "Only HTTP and HTTPS URLs are allowed"),
        ],
    )
    async def test_url_validation_blocks_unsafe_urls(
        self, client: AsyncClient, invalid_url: str, expected_error_fragment: str
    ):
        """Test that URL validation blocks potentially unsafe URLs."""
        response = await client.post(
            RECIPES_FETCH_TEXT_URL, data={FIELD_RECIPE_URL: invalid_url}
        )

        assert response.status_code == 200
        assert f"Invalid URL: {expected_error_fragment}" in response.text
        assert f'class="{CSS_ERROR_CLASS}"' in response.text

        # Ensure fetch_and_clean_text_from_url was never called
        with patch(
            "meal_planner.routers.ui_fragments.fetch_and_clean_text_from_url"
        ) as mock_fetch:
            mock_fetch.assert_not_called()

    @pytest.mark.parametrize(
        "safe_url",
        [
            "http://example.com/recipe",
            "https://www.allrecipes.com/recipe/123",
            "https://food.com/recipe/amazing-pasta",
            "http://cooking.nytimes.com/recipes/456",
            "https://epicurious.com/recipes/food/views/789",
        ],
    )
    async def test_url_validation_allows_safe_urls(
        self, client: AsyncClient, safe_url: str
    ):
        """Test that URL validation allows legitimate recipe URLs."""
        mock_text = "Fetched recipe content"

        with patch(
            "meal_planner.routers.ui_fragments.fetch_and_clean_text_from_url",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = mock_text

            response = await client.post(
                RECIPES_FETCH_TEXT_URL, data={FIELD_RECIPE_URL: safe_url}
            )

            assert response.status_code == 200
            mock_fetch.assert_called_once_with(safe_url)
            assert mock_text in response.text


class TestGetHttpErrorMessage:
    """Test the _get_http_error_message helper function."""

    @pytest.mark.parametrize(
        "status_code, response_text, expected_fragment",
        [
            # Bot protection detection
            (
                403,
                "PerimeterX access denied",
                "security measures that block automated access",
            ),
            (
                403,
                "Powered by PerimeterX",
                "security measures that block automated access",
            ),
            (
                403,
                "verify you are a human",
                "security measures that block automated access",
            ),
            (
                403,
                "automation tools to browse",
                "security measures that block automated access",
            ),
            (
                403,
                "Cloudflare security check",
                "security measures that block automated access",
            ),
            (
                200,
                "Please complete the CAPTCHA",
                "security measures that block automated access",
            ),
            # Specific status codes without bot protection
            (403, "Forbidden", "doesn't allow automated access"),
            (404, "Not Found", "recipe page was not found"),
            (401, "Unauthorized", "requires login to access recipes"),
            (429, "Too Many Requests", "limiting requests"),
            (500, "Internal Server Error", "server issues"),
            (502, "Bad Gateway", "server issues"),
            (503, "Service Unavailable", "server issues"),
            (504, "Gateway Timeout", "server issues"),
            (400, "Bad Request", "doesn't allow our recipe fetcher"),
            (418, "I'm a teapot", "doesn't allow our recipe fetcher"),  # Other 4xx
            # Fallback case
            (200, "Unknown error", "The server returned an error"),
            (201, "Created", "The server returned an error"),
        ],
    )
    def test_get_http_error_message(
        self, status_code: int, response_text: str, expected_fragment: str
    ):
        """Test that the error message function returns appropriate messages."""
        result = _get_http_error_message(status_code, response_text)
        assert expected_fragment in result, (
            f"Expected '{expected_fragment}' in result: '{result}'"
        )

    def test_bot_protection_case_insensitive(self):
        """Test that bot protection detection is case-insensitive."""
        result = _get_http_error_message(403, "PERIMETERX ACCESS DENIED")
        assert "security measures that block automated access" in result

    def test_real_perimeterx_response(self):
        """Test with actual PerimeterX response content."""
        perimeterx_response = """
        <!DOCTYPE html> <html lang="en"> <head>
        <title>Access to this page has been denied.</title>
        </head> <body>
        <p>Access to this page has been denied because we believe you are using
        automation tools to browse the website.</p>
        <p>Powered by <a href="https://www.perimeterx.com/whywasiblocked">
        PerimeterX</a>, Inc.</p>
        </body> </html>
        """
        result = _get_http_error_message(403, perimeterx_response)
        assert "security measures that block automated access" in result


@pytest.mark.anyio
class TestAdjustMakesEndpoint:
    """Test the /recipes/ui/adjust-makes endpoint."""

    ADJUST_MAKES_URL = "/recipes/ui/adjust-makes"

    def _build_makes_form_data(
        self,
        makes_min=None,
        makes_max=None,
        original_makes_min=None,
        original_makes_max=None,
        **kwargs,
    ) -> dict:
        """Build form data with makes fields."""
        base_data = _build_ui_fragment_form_data(**kwargs)

        if makes_min is not None:
            base_data["makes_min"] = str(makes_min)
        if makes_max is not None:
            base_data["makes_max"] = str(makes_max)
        if original_makes_min is not None:
            base_data["original_makes_min"] = str(original_makes_min)
        if original_makes_max is not None:
            base_data["original_makes_max"] = str(original_makes_max)

        return base_data

    async def test_adjust_makes_min_greater_than_max_adjust_max(
        self, client: AsyncClient
    ):
        """Test adjusting max when min is greater and min was changed."""
        form_data = self._build_makes_form_data(
            makes_min=6,
            makes_max=4,
            original_makes_min=2,  # min changed from 2 to 6
            original_makes_max=4,  # max unchanged
        )

        response = await client.post(self.ADJUST_MAKES_URL, data=form_data)
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        makes_section = soup.find("div", id="makes-section")
        assert makes_section

        min_input = soup.find("input", {"name": "makes_min"})
        max_input = soup.find("input", {"name": "makes_max"})
        assert min_input and min_input.get("value") == "6"
        assert max_input and max_input.get("value") == "6"

    async def test_adjust_makes_min_greater_than_max_adjust_min(
        self, client: AsyncClient
    ):
        """Test adjusting min when max is lower and max was changed."""
        form_data = self._build_makes_form_data(
            makes_min=6,
            makes_max=4,
            original_makes_min=6,  # min unchanged
            original_makes_max=8,  # max changed from 8 to 4
        )

        response = await client.post(self.ADJUST_MAKES_URL, data=form_data)
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        min_input = soup.find("input", {"name": "makes_min"})
        max_input = soup.find("input", {"name": "makes_max"})
        assert min_input and min_input.get("value") == "4"
        assert max_input and max_input.get("value") == "4"

    async def test_adjust_makes_with_changed_min_parameter(self, client: AsyncClient):
        """Test adjusting with explicit changed=min parameter."""
        form_data = self._build_makes_form_data(
            makes_min=8,
            makes_max=5,
        )

        response = await client.post(
            f"{self.ADJUST_MAKES_URL}?changed=min", data=form_data
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        min_input = soup.find("input", {"name": "makes_min"})
        max_input = soup.find("input", {"name": "makes_max"})
        assert min_input and min_input.get("value") == "8"
        assert max_input and max_input.get("value") == "8"

    async def test_adjust_makes_with_changed_max_parameter(self, client: AsyncClient):
        """Test adjusting with explicit changed=max parameter."""
        form_data = self._build_makes_form_data(
            makes_min=8,
            makes_max=5,
        )

        response = await client.post(
            f"{self.ADJUST_MAKES_URL}?changed=max", data=form_data
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        min_input = soup.find("input", {"name": "makes_min"})
        max_input = soup.find("input", {"name": "makes_max"})
        assert min_input and min_input.get("value") == "5"
        assert max_input and max_input.get("value") == "5"

    async def test_adjust_makes_valid_range_unchanged(self, client: AsyncClient):
        """Test that valid range is left unchanged."""
        form_data = self._build_makes_form_data(
            makes_min=4,
            makes_max=6,
        )

        response = await client.post(self.ADJUST_MAKES_URL, data=form_data)
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        min_input = soup.find("input", {"name": "makes_min"})
        max_input = soup.find("input", {"name": "makes_max"})
        assert min_input and min_input.get("value") == "4"
        assert max_input and max_input.get("value") == "6"

    async def test_adjust_makes_includes_diff_update(self, client: AsyncClient):
        """Test that adjust makes includes OOB diff update."""
        form_data = self._build_makes_form_data(
            makes_min=4,
            makes_max=6,
        )

        response = await client.post(self.ADJUST_MAKES_URL, data=form_data)
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")

        # Check for makes section
        makes_section = soup.find("div", id="makes-section")
        assert makes_section

        # Check for OOB diff update
        oob_diff = soup.find("div", {"hx-swap-oob": "innerHTML:#diff-content-wrapper"})
        assert oob_diff

    @patch("meal_planner.routers.ui_fragments.logger.warning")
    async def test_adjust_makes_validation_error(
        self, mock_logger_warning, client: AsyncClient
    ):
        """Test adjust makes with validation error."""
        # Create form data that will cause validation error (e.g., empty name)
        form_data = self._build_makes_form_data(
            makes_min=4,
            makes_max=6,
            name="",  # This will cause validation error
        )

        response = await client.post(self.ADJUST_MAKES_URL, data=form_data)
        assert response.status_code == 200

        # Should return makes section with error message
        soup = BeautifulSoup(response.text, "html.parser")
        makes_section = soup.find("div", id="makes-section")
        assert makes_section

        mock_logger_warning.assert_called_once()

    @patch("meal_planner.routers.ui_fragments.logger.error")
    @patch("meal_planner.routers.ui_fragments.build_diff_content_children")
    async def test_adjust_makes_general_exception(
        self, mock_build_diff, mock_logger_error, client: AsyncClient
    ):
        """Test adjust makes with general exception."""
        # Make build_diff_content_children raise an exception
        mock_build_diff.side_effect = RuntimeError("Test error")

        form_data = self._build_makes_form_data(makes_min=4, makes_max=6)

        response = await client.post(self.ADJUST_MAKES_URL, data=form_data)
        assert response.status_code == 200

        # Should return basic makes section without adjustment
        soup = BeautifulSoup(response.text, "html.parser")
        makes_section = soup.find("div", id="makes-section")
        assert makes_section

        mock_logger_error.assert_called_once()

    async def test_adjust_makes_default_when_no_original(self, client: AsyncClient):
        """Test adjustment logic when original values are not provided."""
        form_data = self._build_makes_form_data(
            makes_min=8,
            makes_max=4,  # Invalid range
            # No original values provided
        )

        response = await client.post(self.ADJUST_MAKES_URL, data=form_data)
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        min_input = soup.find("input", {"name": "makes_min"})
        max_input = soup.find("input", {"name": "makes_max"})
        # Should default to adjusting max when no original to compare
        assert min_input and min_input.get("value") == "8"
        assert max_input and max_input.get("value") == "8"

    async def test_adjust_makes_empty_both_values(self, client: AsyncClient):
        """Test adjust makes when both values are None/empty."""
        form_data = self._build_makes_form_data(
            # Both makes_min and makes_max are None
        )

        response = await client.post(self.ADJUST_MAKES_URL, data=form_data)
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        makes_section = soup.find("div", id="makes-section")
        assert makes_section

        min_input = soup.find("input", {"name": "makes_min"})
        max_input = soup.find("input", {"name": "makes_max"})
        assert min_input and (
            min_input.get("value") is None or min_input.get("value") == ""
        )
        assert max_input and (
            max_input.get("value") is None or max_input.get("value") == ""
        )

    async def test_adjust_makes_only_min_set_stays_empty(self, client: AsyncClient):
        """Test that when only min is set, max stays empty (no auto-population)."""
        form_data = {
            "name": "Test Recipe",
            "ingredients": ["ing1"],
            "instructions": ["step1"],
            "original_name": "Test Recipe",
            "original_ingredients": ["ing1"],
            "original_instructions": ["step1"],
            "makes_min": "4",
            # makes_max omitted - should stay empty
        }

        response = await client.post(self.ADJUST_MAKES_URL, data=form_data)
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        min_input = soup.find("input", {"name": "makes_min"})
        max_input = soup.find("input", {"name": "makes_max"})
        assert min_input and min_input.get("value") == "4"
        assert max_input and (
            max_input.get("value") is None or max_input.get("value") == ""
        )

    async def test_adjust_makes_only_max_set_stays_empty(self, client: AsyncClient):
        """Test that when only max is set, min stays empty (no auto-population)."""
        form_data = {
            "name": "Test Recipe",
            "ingredients": ["ing1"],
            "instructions": ["step1"],
            "original_name": "Test Recipe",
            "original_ingredients": ["ing1"],
            "original_instructions": ["step1"],
            "makes_max": "6",
            # makes_min omitted - should stay empty
        }

        response = await client.post(self.ADJUST_MAKES_URL, data=form_data)
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        min_input = soup.find("input", {"name": "makes_min"})
        max_input = soup.find("input", {"name": "makes_max"})
        assert min_input and (
            min_input.get("value") is None or min_input.get("value") == ""
        )
        assert max_input and max_input.get("value") == "6"

    async def test_adjust_makes_user_clears_value_stays_cleared(
        self, client: AsyncClient
    ):
        """Test that if user clears a value, it stays cleared."""
        form_data = {
            "name": "Test Recipe",
            "ingredients": ["ing1"],
            "instructions": ["step1"],
            "original_name": "Test Recipe",
            "original_ingredients": ["ing1"],
            "original_instructions": ["step1"],
            "original_makes_min": "4",
            "original_makes_max": "6",
            "makes_min": "4",
            # User cleared makes_max - should stay cleared
        }

        response = await client.post(self.ADJUST_MAKES_URL, data=form_data)
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        min_input = soup.find("input", {"name": "makes_min"})
        max_input = soup.find("input", {"name": "makes_max"})
        assert min_input and min_input.get("value") == "4"
        assert max_input and (
            max_input.get("value") is None or max_input.get("value") == ""
        )

    async def test_adjust_makes_parse_form_data_exception(
        self, client: AsyncClient, monkeypatch
    ):
        """Test adjust makes when parse_recipe_form_data raises exception."""
        from meal_planner.routers import ui_fragments

        def mock_parse_error(*args, **kwargs):
            raise ValueError("Parse error")

        monkeypatch.setattr(ui_fragments, "parse_recipe_form_data", mock_parse_error)

        form_data = self._build_makes_form_data(makes_min=4, makes_max=6)

        response = await client.post(self.ADJUST_MAKES_URL, data=form_data)
        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        makes_section = soup.find("div", id="makes-section")
        assert makes_section

        # Should have empty inputs when parse fails
        min_input = soup.find("input", {"name": "makes_min"})
        max_input = soup.find("input", {"name": "makes_max"})
        unit_input = soup.find("input", {"name": "makes_unit"})
        assert min_input and (
            min_input.get("value") is None or min_input.get("value") == ""
        )
        assert max_input and (
            max_input.get("value") is None or max_input.get("value") == ""
        )
        assert unit_input and (
            unit_input.get("value") is None or unit_input.get("value") == ""
        )


@pytest.mark.anyio
class TestMakesValidationErrorHandling:
    """Test makes validation error handling in update_diff endpoint."""

    UPDATE_DIFF_URL = "/recipes/ui/update-diff"

    def _build_makes_diff_form_data(
        self,
        makes_min=None,
        makes_max=None,
        original_makes_min=None,
        original_makes_max=None,
        **kwargs,
    ) -> dict:
        """Build form data for diff update with makes."""
        base_data = _build_ui_fragment_form_data(**kwargs)

        if makes_min is not None:
            base_data["makes_min"] = str(makes_min)
        if makes_max is not None:
            base_data["makes_max"] = str(makes_max)
        if original_makes_min is not None:
            base_data["original_makes_min"] = str(original_makes_min)
        if original_makes_max is not None:
            base_data["original_makes_max"] = str(original_makes_max)

        return base_data

    async def test_update_diff_makes_validation_error_specific_handling(
        self, client: AsyncClient
    ):
        """Test specific handling of makes validation errors in update_diff."""
        form_data = self._build_makes_diff_form_data(
            makes_min=6,
            makes_max=4,  # Invalid: max < min
            original_makes_min=4,
            original_makes_max=6,
        )

        response = await client.post(self.UPDATE_DIFF_URL, data=form_data)
        assert response.status_code == 200

        # Should return OOB makes section with specific error message
        soup = BeautifulSoup(response.text, "html.parser")

        # Check for OOB swap to makes section
        oob_makes = soup.find(attrs={"hx-swap-oob": "outerHTML:#makes-section"})
        assert oob_makes is not None

        # Should contain specific makes error message
        error_text = soup.get_text()
        assert "Max quantity cannot be less than min quantity" in error_text

    async def test_update_diff_non_makes_validation_error(self, client: AsyncClient):
        """Test that non-makes validation errors use generic handling."""
        form_data = self._build_makes_diff_form_data(
            name="",  # Empty name will cause validation error
            makes_min=4,
            makes_max=6,
        )

        response = await client.post(self.UPDATE_DIFF_URL, data=form_data)
        assert response.status_code == 200

        # Should return generic error message (not makes-specific)
        assert "Please check your recipe fields" in response.text
