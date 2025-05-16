from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bs4 import BeautifulSoup
from bs4.element import Tag  # Added Tag
from httpx import AsyncClient
from pydantic import ValidationError  # Added ValidationError

import meal_planner.main as main_module  # Added main_module for patching
from meal_planner.models import RecipeBase
from meal_planner.ui.common import CSS_ERROR_CLASS  # Added CSS_ERROR_CLASS

# Constants from test_main.py
RECIPES_EXTRACT_RUN_URL = "/recipes/extract/run"
RECIPES_MODIFY_URL = "/recipes/modify"
FIELD_RECIPE_TEXT = "recipe_text"
FIELD_NAME = "name"
FIELD_INGREDIENTS = "ingredients"
FIELD_INSTRUCTIONS = "instructions"
FIELD_MODIFICATION_PROMPT = "modification_prompt"
FIELD_ORIGINAL_NAME = "original_name"
FIELD_ORIGINAL_INGREDIENTS = "original_ingredients"
FIELD_ORIGINAL_INSTRUCTIONS = "original_instructions"


# Helper function _extract_current_recipe_data_from_html (copied from test_main.py)
def _extract_current_recipe_data_from_html(html_content: str) -> dict:
    soup = BeautifulSoup(html_content, "html.parser")
    form_container = soup.find("div", id="edit-form-target")
    if not form_container:
        form_container = soup.find(
            "div", attrs={"hx-swap-oob": "innerHTML:#edit-form-target"}
        )

    if not form_container:  # Fallback if OOB swap also not found (e.g. initial load)
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
        name = name[0]  # Take the first element if list

    ingredients_inputs = form.find_all("input", attrs={"name": FIELD_INGREDIENTS})
    ingredients = [
        (
            ing_input.get("value", "")
            if isinstance(ing_input.get("value"), str)
            else (
                ing_input.get("value")[0]
                if isinstance(ing_input.get("value"), list) and ing_input.get("value")
                else ""  # handle case of empty list value
            )
        )
        for ing_input in ingredients_inputs
        if isinstance(ing_input, Tag) and "value" in ing_input.attrs
    ]
    instructions_areas = form.find_all("textarea", attrs={"name": FIELD_INSTRUCTIONS})
    instructions = [
        inst_area.get_text()  # Use .get_text() for textareas
        for inst_area in instructions_areas
        if isinstance(inst_area, Tag)
    ]
    return {"name": str(name), "ingredients": ingredients, "instructions": instructions}


# Fixtures (copied from test_main.py or similar might be needed)
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


# Copied TestRecipeModifyEndpoint class (from test_main.py lines 220-423)
@pytest.mark.anyio
class TestRecipeModifyEndpoint:
    @pytest.fixture
    def mock_llm_generate_modified_recipe(self):
        with patch(
            "meal_planner.main.llm_generate_modified_recipe", new_callable=AsyncMock
        ) as mock_service_call:
            yield mock_service_call

    def _build_modify_form_data(
        self,
        current_recipe: RecipeBase,
        original_recipe: RecipeBase,
        modification_prompt: str | None = None,
    ) -> dict:
        data = {
            FIELD_NAME: current_recipe.name,
            FIELD_INGREDIENTS: current_recipe.ingredients,
            FIELD_INSTRUCTIONS: current_recipe.instructions,
            FIELD_ORIGINAL_NAME: original_recipe.name,
            FIELD_ORIGINAL_INGREDIENTS: original_recipe.ingredients,
            FIELD_ORIGINAL_INSTRUCTIONS: original_recipe.instructions,
        }
        if modification_prompt is not None:
            data[FIELD_MODIFICATION_PROMPT] = modification_prompt
        return data

    @patch("meal_planner.main.logger.info")
    async def test_modify_success(
        self,
        mock_logger_info,
        client: AsyncClient,
        mock_llm_generate_modified_recipe,
        mock_current_recipe_before_modify_fixture: RecipeBase,
        mock_original_recipe_fixture: RecipeBase,
        mock_llm_modified_recipe_fixture: RecipeBase,
    ):
        mock_llm_generate_modified_recipe.return_value = (
            mock_llm_modified_recipe_fixture
        )
        test_prompt = "Make it spicier"
        form_data = self._build_modify_form_data(
            mock_current_recipe_before_modify_fixture,
            mock_original_recipe_fixture,
            test_prompt,
        )

        response = await client.post(RECIPES_MODIFY_URL, data=form_data)

        assert response.status_code == 200
        mock_llm_generate_modified_recipe.assert_called_once_with(
            current_recipe=mock_current_recipe_before_modify_fixture,
            modification_request=test_prompt,
        )

        assert f'value="{mock_llm_modified_recipe_fixture.name}"' in response.text
        assert 'id="name"' in response.text
        assert (
            f'<input type="hidden" name="{FIELD_ORIGINAL_NAME}"'
            f' value="{mock_original_recipe_fixture.name}"' in response.text
        )

    async def test_modify_no_prompt(
        self,
        client: AsyncClient,
        mock_llm_generate_modified_recipe,
        mock_current_recipe_before_modify_fixture: RecipeBase,
        mock_original_recipe_fixture: RecipeBase,
    ):
        form_data = self._build_modify_form_data(
            mock_current_recipe_before_modify_fixture, mock_original_recipe_fixture, ""
        )

        response = await client.post(RECIPES_MODIFY_URL, data=form_data)

        assert response.status_code == 200
        assert "Please enter modification instructions." in response.text
        assert f'class="{CSS_ERROR_CLASS} mt-2"' in response.text
        assert 'id="name"' in response.text
        assert (
            f'<input type="hidden" name="{FIELD_ORIGINAL_NAME}"'
            f' value="{mock_original_recipe_fixture.name}"' in response.text
        )
        mock_llm_generate_modified_recipe.assert_not_called()

    async def test_modify_llm_error(
        self,
        client: AsyncClient,
        mock_llm_generate_modified_recipe,
        mock_current_recipe_before_modify_fixture: RecipeBase,
        mock_original_recipe_fixture: RecipeBase,
    ):
        mock_llm_generate_modified_recipe.side_effect = Exception(
            "LLM modification error"
        )
        test_prompt = "Cause an error"
        form_data = self._build_modify_form_data(
            mock_current_recipe_before_modify_fixture,
            mock_original_recipe_fixture,
            test_prompt,
        )

        response = await client.post(RECIPES_MODIFY_URL, data=form_data)

        assert response.status_code == 200
        assert (
            "Recipe modification failed. An unexpected error occurred during service "
            "call." in response.text
        )
        assert f'class="{CSS_ERROR_CLASS} mt-2"' in response.text
        assert 'id="name"' in response.text
        assert (
            f'<input type="hidden" name="{FIELD_ORIGINAL_NAME}"'
            f' value="{mock_original_recipe_fixture.name}"' in response.text
        )
        mock_llm_generate_modified_recipe.assert_called_once()

    async def test_modify_validation_error(
        self,
        client: AsyncClient,
        mock_current_recipe_before_modify_fixture: RecipeBase,
        mock_original_recipe_fixture: RecipeBase,
    ):
        """Test form parsing validation error returns correct HTML."""
        form_data = self._build_modify_form_data(
            mock_current_recipe_before_modify_fixture,
            mock_original_recipe_fixture,
            "A valid prompt",
        )
        form_data[FIELD_NAME] = ""  # Cause validation error

        response = await client.post(RECIPES_MODIFY_URL, data=form_data)

        assert response.status_code == 200
        assert "Invalid recipe data. Please check the fields." in response.text
        assert CSS_ERROR_CLASS in response.text  # Check for general error class
        # Ensure LLM was not called if form parsing failed early
        with patch(
            "meal_planner.main.llm_generate_modified_recipe", new_callable=AsyncMock
        ) as local_mock_llm:
            local_mock_llm.assert_not_called()

    @patch(
        "meal_planner.main.extract_recipe_from_text", new_callable=AsyncMock
    )  # This mock is from the original test context
    async def test_modify_recipe_multiple_times(
        self,
        mock_extract_recipe: AsyncMock,
        mock_llm_generate_modified_recipe: AsyncMock,  # This is from the class fixture
        client: AsyncClient,
    ):
        initial_recipe = RecipeBase(
            name="Initial Recipe",
            ingredients=["Pepper", "Garlic"],
            instructions=["Season well", "Cook slowly"],
        )
        modified_recipe_v1 = RecipeBase(
            name="Modified V1",
            ingredients=["Salt", "Pepper", "Garlic"],
            instructions=["Mix ingredients", "Season well", "Cook slowly"],
        )
        modified_recipe_v2 = RecipeBase(
            name="Modified V2 (Vegan)",
            ingredients=["Olive Oil", "Salt", "Pepper", "Garlic"],
            instructions=[
                "Sauté garlic",
                "Mix ingredients",
                "Season well",
                "Cook slowly",
            ],
        )

        mock_extract_recipe.return_value = initial_recipe
        extract_response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: "Some initial text"}
        )
        assert extract_response.status_code == 200
        mock_llm_generate_modified_recipe.return_value = modified_recipe_v1
        form_data_1 = self._build_modify_form_data(
            current_recipe=initial_recipe,
            original_recipe=initial_recipe,
            modification_prompt="Make it tastier",
        )
        modify_response_1 = await client.post(RECIPES_MODIFY_URL, data=form_data_1)
        assert modify_response_1.status_code == 200
        assert mock_llm_generate_modified_recipe.call_count == 1

        html_after_first_modify = ""
        async for chunk in modify_response_1.aiter_text():
            html_after_first_modify += chunk

        soup_v1 = BeautifulSoup(html_after_first_modify, "html.parser")
        edit_target_div = soup_v1.find("div", attrs={"id": "edit-form-target"})
        assert edit_target_div is not None, (
            "#edit-form-target div not found in response."
        )
        form_v1 = edit_target_div.find("form", attrs={"id": "edit-review-form"})
        assert form_v1 is not None, (
            "#edit-review-form not found within #edit-form-target."
        )
        modify_button_v1 = form_v1.find("button", string="Modify Recipe")
        assert modify_button_v1 is not None, (
            "Modify button not found after first modification."
        )
        assert modify_button_v1.has_attr("hx-indicator"), "hx-indicator missing."
        assert modify_button_v1.get("hx-indicator") == "#modify-indicator", (
            "hx-indicator incorrect."
        )

        mock_llm_generate_modified_recipe.return_value = modified_recipe_v2
        current_data_after_v1_modify = _extract_current_recipe_data_from_html(
            html_after_first_modify
        )

        form_data_2 = self._build_modify_form_data(
            current_recipe=RecipeBase(**current_data_after_v1_modify),
            original_recipe=initial_recipe,  # Original recipe remains the same baseline
            modification_prompt="Now make it vegan",
        )

        modify_response_2 = await client.post(RECIPES_MODIFY_URL, data=form_data_2)
        assert modify_response_2.status_code == 200
        assert mock_llm_generate_modified_recipe.call_count == 2, (
            "LLM not called for second mod."
        )

        html_after_second_modify = ""
        async for chunk in modify_response_2.aiter_text():
            html_after_second_modify += chunk
        soup_v2 = BeautifulSoup(html_after_second_modify, "html.parser")
        name_input_v2 = soup_v2.find("input", {"name": FIELD_NAME})
        assert name_input_v2 is not None
        assert name_input_v2["value"] == "Modified V2 (Vegan)"


# Copied TestRecipeUpdateDiff class (from test_main.py lines 479-677)
@pytest.mark.anyio
class TestRecipeUpdateDiff:
    UPDATE_DIFF_URL = "/recipes/ui/update-diff"

    def _build_diff_form_data(
        self, current: RecipeBase, original: RecipeBase | None = None
    ) -> dict:
        if original is None:
            original = current  # Diff current against itself
        form_data = {
            FIELD_NAME: current.name,
            FIELD_INGREDIENTS: current.ingredients,
            FIELD_INSTRUCTIONS: current.instructions,
            FIELD_ORIGINAL_NAME: original.name,
            FIELD_ORIGINAL_INGREDIENTS: original.ingredients,
            FIELD_ORIGINAL_INSTRUCTIONS: original.instructions,
        }
        return form_data

    async def test_diff_no_changes(self, client: AsyncClient):
        recipe = RecipeBase(name="Same", ingredients=["i1"], instructions=["s1"])
        form_data = self._build_diff_form_data(recipe, recipe)

        response = await client.post(self.UPDATE_DIFF_URL, data=form_data)
        assert response.status_code == 200
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        before_pre = soup.find("pre", id="diff-before-pre")
        after_pre = soup.find("pre", id="diff-after-pre")
        assert before_pre is not None
        assert after_pre is not None
        before_text_content = before_pre.get_text()
        after_text_content = after_pre.get_text()
        assert "<del>" not in html
        assert "<ins>" not in html
        assert "# Same" in before_text_content
        assert "- i1" in before_text_content
        assert "- s1" in before_text_content
        assert "# Same" in after_text_content
        assert "- i1" in after_text_content
        assert "- s1" in after_text_content
        assert before_text_content == after_text_content

    async def test_diff_addition(self, client: AsyncClient):
        original = RecipeBase(name="Orig", ingredients=["i1"], instructions=["s1"])
        current = RecipeBase(
            name="Current", ingredients=["i1", "i2"], instructions=["s1", "s2"]
        )
        form_data = self._build_diff_form_data(current, original)
        response = await client.post(self.UPDATE_DIFF_URL, data=form_data)
        assert response.status_code == 200
        html_text = response.text
        soup = BeautifulSoup(html_text, "html.parser")
        before_pre = soup.find("pre", id="diff-before-pre")
        after_pre = soup.find("pre", id="diff-after-pre")
        assert before_pre is not None, "Before diff <pre> block not found"
        assert after_pre is not None, "After diff <pre> block not found"
        orig_name_del_tag = before_pre.find("del", string=lambda t: t and "# Orig" in t)
        assert orig_name_del_tag is not None, (
            "<del># Orig</del> not found in before_pre"
        )
        current_name_ins_tag = after_pre.find(
            "ins", string=lambda t: t and "# Current" in t
        )
        assert current_name_ins_tag is not None, (
            "<ins># Current</ins> not found in after_pre"
        )
        assert "- i1" in before_pre.get_text()
        assert "- i1" in after_pre.get_text()
        assert not before_pre.find("del", string=lambda t: t and "- i1" in t)
        assert not after_pre.find("ins", string=lambda t: t and "- i1" in t)
        assert "- i2" not in before_pre.get_text()
        i2_ins_tag = after_pre.find("ins", string=lambda t: t and "- i2" in t)
        assert i2_ins_tag is not None, "<ins>- i2</ins> not found in after_pre"
        assert "- s1" in before_pre.get_text()
        assert "- s1" in after_pre.get_text()
        assert not before_pre.find("del", string=lambda t: t and "- s1" in t)
        assert not after_pre.find("ins", string=lambda t: t and "- s1" in t)
        assert "- s2" not in before_pre.get_text()
        s2_ins_tag = after_pre.find("ins", string=lambda t: t and "- s2" in t)
        assert s2_ins_tag is not None, "<ins>- s2</ins> not found in after_pre"

    async def test_diff_deletion(self, client: AsyncClient):
        original = RecipeBase(
            name="Orig", ingredients=["i1", "i2"], instructions=["s1", "s2"]
        )
        current = RecipeBase(name="Current", ingredients=["i1"], instructions=["s1"])
        form_data = self._build_diff_form_data(current, original)
        response = await client.post(self.UPDATE_DIFF_URL, data=form_data)
        assert response.status_code == 200
        html_text = response.text
        soup = BeautifulSoup(html_text, "html.parser")
        before_pre = soup.find("pre", id="diff-before-pre")
        after_pre = soup.find("pre", id="diff-after-pre")
        assert before_pre is not None, "Before diff <pre> block not found"
        assert after_pre is not None, "After diff <pre> block not found"
        orig_name_del_tag = before_pre.find("del", string=lambda t: t and "# Orig" in t)
        assert orig_name_del_tag is not None, (
            "<del># Orig</del> not found in before_pre"
        )
        current_name_ins_tag = after_pre.find(
            "ins", string=lambda t: t and "# Current" in t
        )
        assert current_name_ins_tag is not None, (
            "<ins># Current</ins> not found in after_pre"
        )
        assert "- i1" in before_pre.get_text()
        assert "- i1" in after_pre.get_text()
        i2_del_tag = before_pre.find("del", string=lambda t: t and "- i2" in t)
        assert i2_del_tag is not None, "<del>- i2</del> not found in before_pre"
        assert "- i2" not in after_pre.get_text()
        assert "- s1" in before_pre.get_text()
        assert "- s1" in after_pre.get_text()
        s2_del_tag = before_pre.find("del", string=lambda t: t and "- s2" in t)
        assert s2_del_tag is not None, "<del>- s2</del> not found in before_pre"
        assert "- s2" not in after_pre.get_text()

    async def test_diff_modification(self, client: AsyncClient):
        original = RecipeBase(name="Orig", ingredients=["i1"], instructions=["s1"])
        current = RecipeBase(
            name="Current", ingredients=["i1_mod"], instructions=["s1_mod"]
        )
        form_data = self._build_diff_form_data(current, original)
        response = await client.post(self.UPDATE_DIFF_URL, data=form_data)
        assert response.status_code == 200
        html_text = response.text
        soup = BeautifulSoup(html_text, "html.parser")
        before_pre = soup.find("pre", id="diff-before-pre")
        after_pre = soup.find("pre", id="diff-after-pre")
        assert before_pre is not None, "Before diff <pre> block not found"
        assert after_pre is not None, "After diff <pre> block not found"
        orig_name_del_tag = before_pre.find("del", string=lambda t: t and "# Orig" in t)
        assert orig_name_del_tag is not None, (
            "<del># Orig</del> not found in before_pre"
        )
        current_name_ins_tag = after_pre.find(
            "ins", string=lambda t: t and "# Current" in t
        )
        assert current_name_ins_tag is not None, (
            "<ins># Current</ins> not found in after_pre"
        )
        assert "# Orig" not in after_pre.get_text()
        i1_del_tag = before_pre.find("del", string=lambda t: t and "- i1" in t)
        assert i1_del_tag is not None, "<del>- i1</del> not found in before_pre"
        i1_mod_ins_tag = after_pre.find("ins", string=lambda t: t and "- i1_mod" in t)
        assert i1_mod_ins_tag is not None, "<ins>- i1_mod</ins> not found in after_pre"
        actual_after_text = after_pre.get_text()
        assert "- i1" not in actual_after_text.splitlines()
        assert "- i1_mod" in actual_after_text.splitlines()
        s1_del_tag = before_pre.find("del", string=lambda t: t and "- s1" in t)
        assert s1_del_tag is not None, "<del>- s1</del> not found in before_pre"
        s1_mod_ins_tag = after_pre.find("ins", string=lambda t: t and "- s1_mod" in t)
        assert s1_mod_ins_tag is not None, "<ins>- s1_mod</ins> not found in after_pre"
        assert "- s1" not in after_pre.get_text().splitlines()
        assert "- s1_mod" in after_pre.get_text().splitlines()

    @patch(
        "meal_planner.main.build_diff_content_children"
    )  # Path to function in main.py
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
        valid_recipe = RecipeBase(name="Valid", ingredients=["i"], instructions=["s"])
        form_data = self._build_diff_form_data(valid_recipe, valid_recipe)
        form_data[invalid_field] = invalid_value

        response = await client.post(self.UPDATE_DIFF_URL, data=form_data)
        assert response.status_code == 200
        html = response.text
        assert "Recipe state invalid for diff. Please check all fields." in html
        assert (
            "diff-content-wrapper" not in html
        )  # Check that the diff area is not rendered
        mock_logger_warning.assert_called_once()
        args, kwargs = mock_logger_warning.call_args
        assert args[0] == "Validation error during diff update: %s"
        assert isinstance(args[1], ValidationError)
        assert kwargs.get("exc_info") is False


@pytest.mark.anyio
async def test_modify_critical_failure(client: AsyncClient):
    """Test critical failure during form parsing."""
    with patch(
        "meal_planner.main._parse_and_validate_modify_form"
    ) as mock_validate_form:
        mock_validate_form.side_effect = main_module.ModifyFormError(
            "Form validation error to trigger fallback"
        )

        with patch("meal_planner.main.parse_recipe_form_data") as mock_fallback_parse:
            mock_fallback_parse.side_effect = Exception(
                "Critical parsing error in fallback"
            )

            response = await client.post(RECIPES_MODIFY_URL, data={"name": "Test"})

            assert response.status_code == 200
            assert (
                "Critical Error: Could not recover the recipe form state. Please "
                "refresh and try again." in response.text
            )
            mock_validate_form.assert_called_once()
            assert mock_fallback_parse.called, (
                "Fallback parse_recipe_form_data was not called."
            )
            found_original_parse_call = False
            for call_args_tuple in mock_fallback_parse.call_args_list:
                _args, kwargs = call_args_tuple
                if kwargs.get("prefix") == "original_":
                    found_original_parse_call = True
                    break
            assert found_original_parse_call, (
                "Fallback parse_recipe_form_data for original_data "
                "(prefix='original_') not called as expected"
            )


@pytest.mark.anyio
@patch("meal_planner.main._parse_and_validate_modify_form")
async def test_modify_unexpected_exception(mock_validate, client: AsyncClient):
    """Test final unexpected exception handler in post_modify_recipe."""
    mock_validate.side_effect = Exception("Completely unexpected error")
    dummy_form_data = {
        FIELD_NAME: "Test",
        FIELD_ORIGINAL_NAME: "Orig",
        FIELD_MODIFICATION_PROMPT: "Test prompt",
    }

    response = await client.post(RECIPES_MODIFY_URL, data=dummy_form_data)

    assert response.status_code == 200
    assert (
        "Critical Error: An unexpected error occurred. Please refresh and try again."
        in response.text
    )
    mock_validate.assert_called_once()


# Copied test_modify_render_validation_error (from test_main.py lines 1162-1219)
@pytest.mark.anyio
@patch("meal_planner.main.build_edit_review_form")
@patch("meal_planner.main.RecipeBase")
@patch("meal_planner.main._request_recipe_modification", new_callable=AsyncMock)
@patch("meal_planner.main._parse_and_validate_modify_form")
async def test_modify_render_validation_error(
    mock_validate_form: MagicMock,
    mock_request_mod: AsyncMock,
    mock_recipe_base: MagicMock,
    mock_build_edit_form: MagicMock,
    client: AsyncClient,
    mock_current_recipe_before_modify_fixture: RecipeBase,  # Fixture from this file
    mock_original_recipe_fixture: RecipeBase,  # Fixture from this file
):
    """Test ValidationError during form re-rendering in common error path."""
    mock_validate_form.return_value = (
        mock_current_recipe_before_modify_fixture,
        mock_original_recipe_fixture,
        "Valid prompt",
    )

    mock_request_mod.side_effect = main_module.RecipeModificationError("LLM Failed")

    validation_error = ValidationError.from_exception_data(
        title="TestValError", line_errors=[]
    )
    fallback_instance_mock = MagicMock(spec=RecipeBase)
    fallback_instance_mock.name = "[Validation Error]"
    fallback_instance_mock.ingredients = []
    fallback_instance_mock.instructions = []

    mock_recipe_base.side_effect = [
        validation_error,
        fallback_instance_mock,
    ]

    mock_build_edit_form.return_value = (
        MagicMock(name="edit_card"),
        MagicMock(name="review_card"),
    )

    # Use the _build_modify_form_data from TestRecipeModifyEndpoint in this file
    form_data = TestRecipeModifyEndpoint()._build_modify_form_data(
        mock_current_recipe_before_modify_fixture,
        mock_original_recipe_fixture,
        "Trigger LLM Error",
    )

    response = await client.post(RECIPES_MODIFY_URL, data=form_data)

    assert response.status_code == 200
    mock_validate_form.assert_called_once()
    mock_request_mod.assert_called_once()
    assert mock_recipe_base.call_count >= 1
    mock_build_edit_form.assert_called_once()
    _call_args, call_kwargs = mock_build_edit_form.call_args
    assert call_kwargs["current_recipe"] is fallback_instance_mock
    assert call_kwargs["current_recipe"].name == "[Validation Error]"
    assert call_kwargs["original_recipe"] is mock_original_recipe_fixture


# Copied test_modify_parsing_exception (from test_main.py)
@pytest.mark.anyio
@patch("meal_planner.main._parse_and_validate_modify_form")
@patch("meal_planner.main.parse_recipe_form_data")
async def test_modify_parsing_exception(
    mock_fallback_parse: AsyncMock,
    mock_validate_form: AsyncMock,
    client: AsyncClient,
):
    """Test generic exception during form parsing."""
    mock_validate_form.side_effect = main_module.ModifyFormError(
        "Simulated validation error to trigger fallback path"
    )
    mock_fallback_parse.side_effect = Exception(
        "Simulated parsing error in fallback for original_data"
    )

    dummy_form_data = {
        FIELD_NAME: "Test",
        FIELD_ORIGINAL_NAME: "Orig",
        FIELD_MODIFICATION_PROMPT: "A prompt",  # And a prompt
    }
    response = await client.post(RECIPES_MODIFY_URL, data=dummy_form_data)

    assert response.status_code == 200
    assert (
        "Critical Error: Could not recover the recipe form state. Please refresh and "
        "try again." in response.text
    )
    mock_validate_form.assert_called_once()
    assert mock_fallback_parse.called, "Fallback parse_recipe_form_data was not called."
    found_original_parse_call = False
    for call_args_tuple in mock_fallback_parse.call_args_list:
        _args, kwargs = call_args_tuple
        if kwargs.get("prefix") == "original_":
            found_original_parse_call = True
            break
    assert found_original_parse_call, (
        "Fallback parse_recipe_form_data for original_data (prefix='original_') "
        "not called as expected"
    )
