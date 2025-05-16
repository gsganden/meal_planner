from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup
from bs4.element import Tag
from httpx import AsyncClient

from meal_planner.models import RecipeBase

FIELD_NAME = "name"
FIELD_INGREDIENTS = "ingredients"
FIELD_INSTRUCTIONS = "instructions"
FIELD_MODIFICATION_PROMPT = "modification_prompt"
FIELD_ORIGINAL_NAME = "original_name"
FIELD_ORIGINAL_INGREDIENTS = "original_ingredients"
FIELD_ORIGINAL_INSTRUCTIONS = "original_instructions"

# URLs - Copied from test_main.py
RECIPES_EXTRACT_RUN_URL = "/recipes/extract/run"

# Text for recipe - Copied from test_main.py
FIELD_RECIPE_TEXT = "recipe_text"


def _extract_full_edit_form_data(html_content: str) -> dict[str, Any]:
    """
    Extracts all current and original recipe data from the edit-review-form.
    This includes visible inputs/textareas and hidden original_* fields.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    form_container = soup.find("div", id="edit-form-target")
    if not form_container:
        form_container = soup.find(
            "div", attrs={"hx-swap-oob": "innerHTML:#edit-form-target"}
        )

    if not form_container:
        # If neither the direct ID nor the OOB target is found,
        # fall back to searching the whole soup. This might happen if the
        # entire page is returned, not just an OOB fragment.
        form_container = soup

    form = form_container.find("form", attrs={"id": "edit-review-form"})

    if not isinstance(form, Tag):
        # Try to find the form without the specific container if not found initially
        form_in_soup = soup.find("form", attrs={"id": "edit-review-form"})
        if isinstance(form_in_soup, Tag):
            form = form_in_soup
        else:
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
        data[FIELD_NAME] = ""  # Default to empty string if not found or no value

    ingredients_inputs = form.find_all("input", attrs={"name": FIELD_INGREDIENTS})
    data[FIELD_INGREDIENTS] = [
        cast(str, ing_input["value"])
        for ing_input in ingredients_inputs
        if isinstance(ing_input, Tag) and "value" in ing_input.attrs
    ]

    instructions_areas = form.find_all("textarea", attrs={"name": FIELD_INSTRUCTIONS})
    data[FIELD_INSTRUCTIONS] = [
        inst_area.get_text(
            strip=True
        )  # Use strip=True to be consistent with how data is processed
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
        cast(str, orig_ing_input["value"])
        for orig_ing_input in original_ingredients_inputs
        if isinstance(orig_ing_input, Tag) and "value" in orig_ing_input.attrs
    ]

    original_instructions_inputs = form.find_all(
        "input", attrs={"name": FIELD_ORIGINAL_INSTRUCTIONS}
    )
    data[FIELD_ORIGINAL_INSTRUCTIONS] = [
        cast(str, orig_inst_input["value"])
        for orig_inst_input in original_instructions_inputs
        if isinstance(orig_inst_input, Tag) and "value" in orig_inst_input.attrs
    ]

    # Modification prompt might not always be present
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
class TestRecipeSortableListPersistence:
    INITIAL_RECIPE_TEXT = (
        "Sortable Test Recipe\\n"
        "Ingredients: Ing1, Ing2, Ing3\\n"
        "Instructions: Step1, Step2"
    )
    MOCK_INITIAL_RECIPE = RecipeBase(
        name="Sortable Test Recipe",
        ingredients=["Ing1", "Ing2", "Ing3"],
        instructions=["First instruction details", "Second instruction details"],
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

    @patch("meal_planner.main.llm_generate_recipe_from_text", new_callable=AsyncMock)
    async def test_sortable_after_ingredient_delete(
        self, mock_llm_extract: AsyncMock, client: AsyncClient
    ):
        mock_llm_extract.return_value = self.MOCK_INITIAL_RECIPE

        extract_response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: self.INITIAL_RECIPE_TEXT}
        )
        assert extract_response.status_code == 200
        html_after_extract = extract_response.text

        soup_after_extract = BeautifulSoup(html_after_extract, "html.parser")
        edit_form_target_oob_div = soup_after_extract.find(
            "div", attrs={"hx-swap-oob": "innerHTML:#edit-form-target"}
        )
        assert edit_form_target_oob_div is not None, (
            "OOB div for edit form target not found after extract"
        )
        assert isinstance(edit_form_target_oob_div, Tag)

        ingredients_list_div_extract = edit_form_target_oob_div.find(
            "div", id="ingredients-list"
        )
        self._assert_sortable_attributes(
            ingredients_list_div_extract, "ingredients-list (initial extract)"
        )

        form_data_for_delete = _extract_full_edit_form_data(html_after_extract)

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

    @patch("meal_planner.main.llm_generate_recipe_from_text", new_callable=AsyncMock)
    async def test_sortable_after_instruction_delete(
        self, mock_llm_extract: AsyncMock, client: AsyncClient
    ):
        mock_llm_extract.return_value = self.MOCK_INITIAL_RECIPE

        extract_response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: self.INITIAL_RECIPE_TEXT}
        )
        assert extract_response.status_code == 200
        html_after_extract = extract_response.text

        soup_after_extract = BeautifulSoup(html_after_extract, "html.parser")
        edit_form_target_oob_div = soup_after_extract.find(
            "div", attrs={"hx-swap-oob": "innerHTML:#edit-form-target"}
        )
        assert edit_form_target_oob_div is not None
        assert isinstance(edit_form_target_oob_div, Tag)

        instructions_list_div_extract = edit_form_target_oob_div.find(
            "div", id="instructions-list"
        )
        self._assert_sortable_attributes(
            instructions_list_div_extract, "instructions-list (initial extract)"
        )

        form_data_for_delete = _extract_full_edit_form_data(html_after_extract)
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
        # Note: Original test had "Second instruction details." - ensuring consistency
        assert textareas[0].get_text(strip=True) == "Second instruction details."

    @patch("meal_planner.main.llm_generate_recipe_from_text", new_callable=AsyncMock)
    async def test_sortable_after_ingredient_add(
        self, mock_llm_extract: AsyncMock, client: AsyncClient
    ):
        mock_llm_extract.return_value = self.MOCK_INITIAL_RECIPE

        extract_response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: self.INITIAL_RECIPE_TEXT}
        )
        assert extract_response.status_code == 200
        html_after_extract = extract_response.text

        soup_after_extract = BeautifulSoup(html_after_extract, "html.parser")
        edit_form_target_oob_div = soup_after_extract.find(
            "div", attrs={"hx-swap-oob": "innerHTML:#edit-form-target"}
        )
        assert edit_form_target_oob_div is not None
        assert isinstance(edit_form_target_oob_div, Tag)
        ingredients_list_div_extract = edit_form_target_oob_div.find(
            "div", id="ingredients-list"
        )
        self._assert_sortable_attributes(
            ingredients_list_div_extract, "ingredients-list (initial extract)"
        )

        form_data_for_add = _extract_full_edit_form_data(html_after_extract)

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
        assert inputs[3].get("value", "") == ""  # New item is empty

    @patch("meal_planner.main.llm_generate_recipe_from_text", new_callable=AsyncMock)
    async def test_sortable_after_instruction_add(
        self, mock_llm_extract: AsyncMock, client: AsyncClient
    ):
        mock_llm_extract.return_value = self.MOCK_INITIAL_RECIPE

        extract_response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: self.INITIAL_RECIPE_TEXT}
        )
        assert extract_response.status_code == 200
        html_after_extract = extract_response.text

        soup_after_extract = BeautifulSoup(html_after_extract, "html.parser")
        edit_form_target_oob_div = soup_after_extract.find(
            "div", attrs={"hx-swap-oob": "innerHTML:#edit-form-target"}
        )
        assert edit_form_target_oob_div is not None
        assert isinstance(edit_form_target_oob_div, Tag)
        instructions_list_div_extract = edit_form_target_oob_div.find(
            "div", id="instructions-list"
        )
        self._assert_sortable_attributes(
            instructions_list_div_extract, "instructions-list (initial extract)"
        )

        form_data_for_add = _extract_full_edit_form_data(html_after_extract)

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
        assert textareas[2].get_text(strip=True) == ""  # New item is empty
