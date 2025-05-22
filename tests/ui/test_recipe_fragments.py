from typing import cast
from unittest.mock import patch

import monsterui.all as mu
import pytest
from bs4 import BeautifulSoup
from bs4.element import Tag
from httpx import AsyncClient
from pydantic import ValidationError

from meal_planner.main import CSS_ERROR_CLASS


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

    async def test_add_instruction(self, client: AsyncClient):
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["existing step"]
        )
        response = await client.post(self.ADD_INSTRUCTION_URL, data=form_data)
        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")

        instructions_list_div = soup.find("div", id="instructions-list")
        assert instructions_list_div, "Instructions list div not found"
        assert isinstance(instructions_list_div, Tag)
        instruction_textareas = instructions_list_div.find_all(
            "textarea", {"name": "instructions"}
        )
        assert len(instruction_textareas) == 2, (
            f"Expected 2 instruction textareas, got {len(instruction_textareas)}"
        )

        new_instruction_textarea = instruction_textareas[-1]
        assert isinstance(new_instruction_textarea, Tag)
        assert new_instruction_textarea.text == ""
        assert new_instruction_textarea["placeholder"] == "Instruction Step"

        new_item_div = new_instruction_textarea.find_parent("div", class_="flex")
        assert new_item_div, "Parent div for new instruction not found"
        assert isinstance(new_item_div, Tag)
        delete_button = new_item_div.find(
            "button",
            {
                "hx-post": lambda x: bool(
                    x and x.startswith(f"{self.DELETE_INSTRUCTION_BASE_URL}/")
                )
            },
        )
        assert delete_button, "Delete button for new instruction not found"
        assert isinstance(delete_button, Tag)
        icon_element = delete_button.find("uk-icon", attrs={"icon": "minus-circle"})
        assert icon_element, (
            "UkIcon 'minus-circle' not found in instruction delete button"
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
    @patch("meal_planner.main.logger.warning")
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
    @patch("meal_planner.main.logger.warning")
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

    @patch("meal_planner.main._parse_recipe_form_data")
    @patch("meal_planner.main.logger.error")
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
            validation_exc,
            form_data_dict.copy(),
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
        assert str(validation_exc) in args[0]
        assert kwargs.get("exc_info") is True

        soup = BeautifulSoup(response.text, "html.parser")
        ingredients_list_div = soup.find("div", id="ingredients-list")
        assert ingredients_list_div, "Ingredients list div for error case not found"
        assert isinstance(ingredients_list_div, Tag)
        ingredient_inputs = ingredients_list_div.find_all(
            "input", {"name": "ingredients"}
        )
        assert len(ingredient_inputs) == len(initial_ingredients)

        oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#diff-content-wrapper"})
        assert not oob_div, "OOB diff wrapper should NOT be present on validation error"

    @patch("meal_planner.main._parse_recipe_form_data")
    @patch("meal_planner.main.logger.error")
    async def test_delete_ingredient_generic_exception(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        generic_exc = Exception("Generic parse error for del_ing")
        mock_parse.side_effect = generic_exc
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

    @patch("meal_planner.main._parse_recipe_form_data")
    @patch("meal_planner.main.logger.error")
    async def test_delete_instruction_validation_error(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        validation_exc = ValidationError.from_exception_data(
            title="TestVE_del_inst", line_errors=[]
        )
        initial_instructions = ["s1_to_delete", "s2_remains"]
        form_data_dict = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=initial_instructions
        )

        mock_parse.side_effect = [
            validation_exc,
            form_data_dict.copy(),
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
        assert str(validation_exc) in args[0]
        assert kwargs.get("exc_info") is True

        soup = BeautifulSoup(response.text, "html.parser")
        instructions_list_div = soup.find("div", id="instructions-list")
        assert instructions_list_div, "Instructions list div for error case not found"
        assert isinstance(instructions_list_div, Tag)
        instruction_textareas = instructions_list_div.find_all(
            "textarea", {"name": "instructions"}
        )
        assert len(instruction_textareas) == len(initial_instructions)

        oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#diff-content-wrapper"})
        assert not oob_div, "OOB diff wrapper should NOT be present on validation error"

    @patch("meal_planner.main._parse_recipe_form_data")
    @patch("meal_planner.main.logger.error")
    async def test_delete_instruction_generic_exception(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        generic_exc = Exception("Generic parse error for del_inst")
        mock_parse.side_effect = generic_exc
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["s1"]
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

    @patch("meal_planner.main._parse_recipe_form_data")
    @patch("meal_planner.main.logger.error")
    async def test_add_ingredient_validation_error(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        validation_exc = ValidationError.from_exception_data(
            title="TestVE_add_ing", line_errors=[]
        )
        mock_parse.side_effect = [
            validation_exc,
            _build_ui_fragment_form_data(ingredients=["fallback_ing"]),
        ]
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["s1"]
        )

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

    @patch("meal_planner.main._parse_recipe_form_data")
    @patch("meal_planner.main.logger.error")
    async def test_add_ingredient_generic_exception(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        generic_exc = Exception("Generic parse error for add_ing")
        mock_parse.side_effect = generic_exc
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["s1"]
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

    @patch("meal_planner.main._parse_recipe_form_data")
    @patch("meal_planner.main.logger.error")
    async def test_add_instruction_validation_error(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        validation_exc = ValidationError.from_exception_data(
            title="TestVE_add_inst", line_errors=[]
        )
        mock_parse.side_effect = [
            validation_exc,
            _build_ui_fragment_form_data(instructions=["fallback_inst"]),
        ]
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["s1"]
        )

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

    @patch("meal_planner.main._parse_recipe_form_data")
    @patch("meal_planner.main.logger.error")
    async def test_add_instruction_generic_exception(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        generic_exc = Exception("Generic parse error for add_inst")
        mock_parse.side_effect = generic_exc
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["s1"]
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
        initial_instructions = ["step_to_keep1", "step_to_delete", "step_to_keep2"]
        index_to_delete = 1

        form_data_dict = {
            "name": "Test Recipe Name",
            "instructions": initial_instructions,
            "original_name": "Test Recipe Name",
            "original_instructions": initial_instructions,
        }

        response = await client.post(
            f"{self.DELETE_INSTRUCTION_BASE_URL}/{index_to_delete}", data=form_data_dict
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")

        assert "Error updating list after delete. Validation failed." in response.text

        instructions_list_div = soup.find("div", id="instructions-list")
        assert instructions_list_div, "Instructions list div for delete error not found"
        assert isinstance(instructions_list_div, Tag)
        instruction_textareas = instructions_list_div.find_all(
            "textarea", {"name": "instructions"}
        )
        assert len(instruction_textareas) == len(initial_instructions)

        oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#diff-content-wrapper"})
        assert not oob_div, (
            "OOB diff wrapper should NOT be present on validation error path"
        )
