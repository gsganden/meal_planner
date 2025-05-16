from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch as mock_patch

import httpx
from fasthtml.common import *
from monsterui.all import *
import pytest
from bs4 import BeautifulSoup
from bs4.element import Tag
from fastapi.testclient import TestClient
from fastcore.xml import FT
from httpx import ASGITransport, AsyncClient, Request, Response
from pydantic import ValidationError
from pytest_mock import MockerFixture
from starlette.datastructures import FormData

import meal_planner.main as main_module
from meal_planner.main import (
    CSS_ERROR_CLASS,
    ModifyFormError,
    _parse_recipe_form_data,
    app,
)
from meal_planner.models import RecipeBase

# Constants
TRANSPORT = ASGITransport(app=app)
TEST_URL = "http://test-recipe.com"

# URLs
RECIPES_LIST_PATH = "/recipes"
RECIPES_EXTRACT_URL = "/recipes/extract"
RECIPES_FETCH_TEXT_URL = "/recipes/fetch-text"
RECIPES_EXTRACT_RUN_URL = "/recipes/extract/run"
RECIPES_MODIFY_URL = "/recipes/modify"
RECIPES_SAVE_URL = "/recipes/save"

# Form Field Names
FIELD_RECIPE_URL = "input_url"
FIELD_RECIPE_TEXT = "recipe_text"
FIELD_NAME = "name"
FIELD_INGREDIENTS = "ingredients"
FIELD_INSTRUCTIONS = "instructions"
FIELD_MODIFICATION_PROMPT = "modification_prompt"
FIELD_ORIGINAL_NAME = "original_name"
FIELD_ORIGINAL_INGREDIENTS = "original_ingredients"
FIELD_ORIGINAL_INSTRUCTIONS = "original_instructions"


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
class TestRecipeSortableListPersistence:
    INITIAL_RECIPE_TEXT = (
        "Sortable Test Recipe\\\\n"
        "Ingredients: Ing1, Ing2, Ing3\\\\n"
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

    async def test_sortable_after_ingredient_delete(
        self, mocker: MockerFixture, client: AsyncClient
    ):
        mock_llm_extract = mocker.patch(
            "meal_planner.main.llm_generate_recipe_from_text", new_callable=AsyncMock
        )
        mock_llm_extract.return_value = self.MOCK_INITIAL_RECIPE

        extract_response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: self.INITIAL_RECIPE_TEXT}
        )
        assert extract_response.status_code == 200
        html_after_extract = extract_response.text

        soup_after_extract = BeautifulSoup(html_after_extract, "html.parser")
        edit_form_target_oob_div = soup_after_extract.find("div", id="edit-form-target")
        assert edit_form_target_oob_div is not None, (
            "OOB div for edit form target not found after extract"
        )
        assert edit_form_target_oob_div.get("hx-swap-oob") == "innerHTML", (
            "OOB hx-swap-oob for edit form is not 'innerHTML' or missing"
        )

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
        delete_url = (
            f"{TestRecipeUIFragments.DELETE_INGREDIENT_BASE_URL}/{index_to_delete}"
        )
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

    async def test_sortable_after_instruction_delete(
        self, mocker: MockerFixture, client: AsyncClient
    ):
        mock_llm_extract = mocker.patch(
            "meal_planner.main.llm_generate_recipe_from_text", new_callable=AsyncMock
        )
        mock_llm_extract.return_value = self.MOCK_INITIAL_RECIPE

        extract_response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: self.INITIAL_RECIPE_TEXT}
        )
        assert extract_response.status_code == 200
        html_after_extract = extract_response.text

        soup_after_extract = BeautifulSoup(html_after_extract, "html.parser")
        edit_form_target_oob_div = soup_after_extract.find("div", id="edit-form-target")
        assert edit_form_target_oob_div is not None, (
            "OOB div for edit form target not found after extract (instruction delete)"
        )
        assert edit_form_target_oob_div.get("hx-swap-oob") == "innerHTML", (
            "hx-swap-oob for edit form target is not 'innerHTML' (instruction delete)"
        )

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
        delete_url = (
            f"{TestRecipeUIFragments.DELETE_INSTRUCTION_BASE_URL}/{index_to_delete}"
        )
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
        assert textareas[0].get_text(strip=True) == "Second instruction details."

    async def test_sortable_after_ingredient_add(
        self, mocker: MockerFixture, client: AsyncClient
    ):
        mock_llm_extract = mocker.patch(
            "meal_planner.main.llm_generate_recipe_from_text", new_callable=AsyncMock
        )
        mock_llm_extract.return_value = self.MOCK_INITIAL_RECIPE

        extract_response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: self.INITIAL_RECIPE_TEXT}
        )
        assert extract_response.status_code == 200
        html_after_extract = extract_response.text

        soup_after_extract = BeautifulSoup(html_after_extract, "html.parser")
        edit_form_target_oob_div = soup_after_extract.find("div", id="edit-form-target")
        assert edit_form_target_oob_div is not None, (
            "OOB div for edit form target not found after extract (ingredient add)"
        )
        assert edit_form_target_oob_div.get("hx-swap-oob") == "innerHTML", (
            "hx-swap-oob for edit form target is not 'innerHTML' (ingredient add)"
        )

        ingredients_list_div_extract = edit_form_target_oob_div.find(
            "div", id="ingredients-list"
        )
        self._assert_sortable_attributes(
            ingredients_list_div_extract, "ingredients-list (initial extract)"
        )

        form_data_for_add = _extract_full_edit_form_data(html_after_extract)

        add_url = TestRecipeUIFragments.ADD_INGREDIENT_URL
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

    async def test_sortable_after_instruction_add(
        self, mocker: MockerFixture, client: AsyncClient
    ):
        mock_llm_extract = mocker.patch(
            "meal_planner.main.llm_generate_recipe_from_text", new_callable=AsyncMock
        )
        mock_llm_extract.return_value = self.MOCK_INITIAL_RECIPE

        extract_response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: self.INITIAL_RECIPE_TEXT}
        )
        assert extract_response.status_code == 200
        html_after_extract = extract_response.text

        soup_after_extract = BeautifulSoup(html_after_extract, "html.parser")
        edit_form_target_oob_div = soup_after_extract.find("div", id="edit-form-target")
        assert edit_form_target_oob_div is not None, (
            "OOB div for edit form target not found after extract (instruction add)"
        )
        assert edit_form_target_oob_div.get("hx-swap-oob") == "innerHTML", (
            "hx-swap-oob for edit form target is not 'innerHTML' (instruction add)"
        )

        instructions_list_div_extract = edit_form_target_oob_div.find(
            "div", id="instructions-list"
        )
        self._assert_sortable_attributes(
            instructions_list_div_extract, "instructions-list (initial extract)"
        )

        form_data_for_add = _extract_full_edit_form_data(html_after_extract)

        add_url = TestRecipeUIFragments.ADD_INSTRUCTION_URL
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
class TestSmokeEndpoints:
    async def test_root(self, client: AsyncClient):
        response = await client.get("/")
        assert response.status_code == 200
        assert "Meal Planner" in response.text

    async def test_extract_recipe_page_loads(self, client: AsyncClient):
        response = await client.get(RECIPES_EXTRACT_URL)
        assert response.status_code == 200
        assert 'id="input_url"' in response.text
        assert 'name="input_url"' in response.text
        assert 'placeholder="https://example.com/recipe"' in response.text
        assert f'hx-post="{RECIPES_FETCH_TEXT_URL}"' in response.text
        assert "hx-include=\"[name='input_url']\"" in response.text
        assert "Fetch Text from URL" in response.text
        assert 'id="recipe_text"' in response.text
        assert (
            'placeholder="Paste full recipe text here, or fetch from URL above."'
            in response.text
        )
        assert f'hx-post="{RECIPES_EXTRACT_RUN_URL}"' in response.text
        assert "Extract Recipe" in response.text
        assert 'id="recipe-results"' in response.text


@pytest.mark.anyio
class TestRecipeFetchTextEndpoint:
    TEST_URL = "http://example.com/fetch-success"

    async def test_success(self, client: AsyncClient):
        mock_text = "Fetched and cleaned recipe text."

        with mock_patch(
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
                        "request": Request("GET", TEST_URL),
                        "response": Response(404, request=Request("GET", TEST_URL)),
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
        with mock_patch(
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
        assert isinstance(parent_of_error_div, Tag), "Parent of error_div is not a Tag"
        assert (
            parent_of_error_div.get("hx-swap-oob")
            == "outerHTML:#fetch-url-error-display"
        ), (
            f"hx-swap-oob attribute incorrect or missing on parent of error_div. "
            f"Got: {parent_of_error_div.get('hx-swap-oob')}"
        )


@pytest.mark.anyio
class TestRecipeExtractRunEndpoint:
    """Tests for the recipe extraction run endpoint."""

    async def test_success_with_text(self, client: AsyncClient, mocker: MockerFixture):
        """Test successful recipe extraction with text input."""
        mock_llm = mocker.patch(
            "meal_planner.main.llm_generate_recipe_from_text",
            new_callable=AsyncMock,
            return_value=RecipeBase(
                name="Test Recipe", ingredients=["ing"], instructions=["step"]
            ),
        )
        mock_postprocess = mocker.patch(
            "meal_planner.main.postprocess_recipe",
            side_effect=lambda r: r,  # Identity for simplicity
        )

        recipe_text = "Some recipe text"
        response = await client.post(
            "/recipes/extract/run", data={"recipe_text": recipe_text}
        )
        assert response.status_code == 200
        assert "Test Recipe" in response.text
        mock_llm.assert_awaited_once_with(recipe_text)
        mock_postprocess.assert_called_once()

    @pytest.mark.parametrize(
        ("form_data", "expected_contains"),
        [
            ({}, "No recipe text provided."),
            ({"recipe_text": ""}, "No recipe text provided."),
            # Parametrized test_missing_or_empty_input had field_name which is not used
        ],
    )
    async def test_missing_or_empty_input(
        self, client: AsyncClient, form_data: dict[str, str], expected_contains: str
    ):
        """Test missing or empty recipe text."""
        response = await client.post("/recipes/extract/run", data=form_data)
        assert response.status_code == 200  # HTMX needs 200
        assert expected_contains in response.text

    async def test_extraction_error(self, client: AsyncClient, mocker: MockerFixture):
        """Test error during recipe extraction."""
        mock_llm = mocker.patch(
            "meal_planner.main.llm_generate_recipe_from_text",
            new_callable=AsyncMock,
            side_effect=ValueError("LLM Extraction failed"),
        )

        recipe_text = "Some recipe text that causes error"
        response = await client.post(
            "/recipes/extract/run", data={"recipe_text": recipe_text}
        )
        assert response.status_code == 200  # HTMX OOB errors are 200
        assert "Recipe extraction failed. An unexpected error occurred" in response.text
        assert "LLM Extraction failed" not in response.text
        mock_llm.assert_awaited_once_with(recipe_text)


@pytest.mark.anyio
async def test_extract_run_returns_save_form(
    client: AsyncClient, mock_recipe_data_fixture: RecipeBase, mocker: MockerFixture
):
    """Test that the /recipes/extract/run endpoint returns the save form after successful extraction."""
    # Mock llm_generate_recipe_from_text
    mock_llm = mocker.patch(
        "meal_planner.main.llm_generate_recipe_from_text",
        new_callable=AsyncMock,
        return_value=mock_recipe_data_fixture,
    )
    # Mock postprocess_recipe
    mock_postprocess = mocker.patch(
        "meal_planner.main.postprocess_recipe",
        side_effect=lambda r: r,  # Identity function for simplicity
    )

    response = await client.post(
        RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: "some text"}
    )
    assert response.status_code == 200
    html_content = response.text

    # Check for OOB target div and key elements of the form within it
    soup = BeautifulSoup(html_content, "html.parser")
    oob_target_div = soup.find(
        "div", {"id": "edit-form-target", "hx-swap-oob": "innerHTML"}
    )
    assert oob_target_div is not None, "OOB target div #edit-form-target not found"

    form_within_oob = oob_target_div.find("form", id="edit-review-form")
    assert form_within_oob is not None, (
        "Form #edit-review-form not found within OOB target"
    )

    name_input = form_within_oob.find("input", id="name")
    assert name_input is not None, "Name input not found in form"
    assert name_input.get("value") == mock_recipe_data_fixture.name, (
        "Recipe name not pre-filled correctly"
    )

    save_button = form_within_oob.find("button", string="Save Recipe")
    assert save_button is not None, "Save Recipe button not found"
    assert save_button.get("hx-post") == RECIPES_SAVE_URL, (
        "Save button hx-post incorrect"
    )

    # Check that mocks were called
    mock_llm.assert_awaited_once_with("some text")
    mock_postprocess.assert_called_once_with(
        mock_recipe_data_fixture
    )  # Called with the result of llm_generate


@pytest.mark.anyio
class TestRecipeUpdateDiff:
    UPDATE_DIFF_URL = "/recipes/ui/update-diff"

    def _build_diff_form_data(
        self, current: RecipeBase, original: RecipeBase | None = None
    ) -> dict:
        if original is None:
            original = current
        form_data = {
            "name": current.name,
            "ingredients": current.ingredients,
            "instructions": current.instructions,
            "original_name": original.name,
            "original_ingredients": original.ingredients,
            "original_instructions": original.instructions,
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

    @mock_patch("meal_planner.main._build_diff_content_children")
    @mock_patch("meal_planner.main.logger.error")
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
    @mock_patch("meal_planner.main.logger.warning")
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
@mock_patch("meal_planner.main._parse_recipe_form_data")
async def test_update_diff_parsing_exception(mock_parse, client: AsyncClient):
    "Test generic exception during form parsing in post_update_diff."
    mock_parse.side_effect = Exception("Simulated parsing error")
    dummy_form_data = {FIELD_NAME: "Test", "original_name": "Orig"}

    response = await client.post(
        TestRecipeUpdateDiff.UPDATE_DIFF_URL, data=dummy_form_data
    )

    assert response.status_code == 200
    assert "Error updating diff view." in response.text
    assert CSS_ERROR_CLASS in response.text
    assert mock_parse.call_count == 1


@pytest.mark.anyio
@mock_patch("meal_planner.main._parse_recipe_form_data")
async def test_save_recipe_parsing_exception(mock_parse, client: AsyncClient):
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


def test_build_edit_review_form_no_original():
    "Test hitting the `original_recipe = current_recipe` line."
    current = RecipeBase(name="Test", ingredients=["i"], instructions=["s"])
    result = main_module._build_edit_review_form(current)
    assert result is not None


def test_build_edit_review_form_with_original():
    """Test hitting the logic where original_recipe is provided."""
    current = RecipeBase(
        name="Updated Name", ingredients=["i1", "i2"], instructions=["s1"]
    )
    original = RecipeBase(
        name="Original Name", ingredients=["i1"], instructions=["s1", "s2"]
    )
    result = main_module._build_edit_review_form(current, original)
    assert result is not None


@pytest.mark.anyio
class TestGetRecipesPageErrors:
    @mock_patch("meal_planner.main.internal_api_client", autospec=True)
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

    @mock_patch("meal_planner.main.internal_api_client", autospec=True)
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

    @mock_patch("meal_planner.main.internal_api_client", autospec=True)
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


@pytest.mark.anyio
class TestGetSingleRecipePageErrors:
    RECIPE_ID = 123
    API_URL = f"/api/v0/recipes/{RECIPE_ID}"
    PAGE_URL = f"/recipes/{RECIPE_ID}"

    @mock_patch("meal_planner.main.internal_client.get")
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

    @mock_patch("meal_planner.main.internal_client.get")
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

    @mock_patch("meal_planner.main.internal_client.get")
    async def test_get_single_recipe_page_api_generic_error(
        self, mock_api_get, client: AsyncClient
    ):
        """Test handling when the API call raises a generic exception."""
        mock_api_get.side_effect = Exception("Unexpected API failure")
        response = await client.get(self.PAGE_URL)
        assert response.status_code == 200
        assert "An unexpected error occurred." in response.text
        mock_api_get.assert_awaited_once_with(self.API_URL)


@pytest.mark.anyio
async def test_save_recipe_api_call_generic_error(client: AsyncClient, monkeypatch):
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
async def test_save_recipe_api_call_request_error(client: AsyncClient, monkeypatch):
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
class TestGetRecipesPageSuccess:
    @mock_patch("meal_planner.main.internal_api_client", autospec=True)
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

    @mock_patch("meal_planner.main.internal_api_client", autospec=True)
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

    @mock_patch("meal_planner.main.internal_api_client", autospec=True)
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
class TestGetSingleRecipePageSuccess:
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


class FormTargetDivNotFoundError(Exception):
    """Custom exception raised when the target div for form parsing is not found."""

    pass


def _get_edit_form_target_div(html_text: str) -> Tag:
    """Parses HTML and finds the specific div target for form edits.

    Raises:
        FormTargetDivNotFoundError: If the target div is not found.
    """
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
    """Extracts a single value from an input or textarea in the HTML form section.

    Can propagate FormTargetDivNotFoundError if the main form container is missing.
    Returns None if the specific field is not found within the container.
    """
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
    """Extracts all values from inputs/textareas with the same name.

    Can propagate FormTargetDivNotFoundError if the main form container is missing.
    Returns an empty list if no specific fields are found within the container.
    """
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
async def test_save_recipe_api_call_non_json_error_response(
    client: AsyncClient, monkeypatch
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
async def test_save_recipe_api_call_422_error(client: AsyncClient, monkeypatch):
    """Test error handling for HTTP 422 error from the internal API."""
    mock_response_422 = AsyncMock(spec=httpx.Response)
    mock_response_422.status_code = 422
    mock_response_422.text = "Unprocessable Entity"
    mock_response_422.json = MagicMock(return_value={"detail": "API validation error"})

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
@mock_patch("meal_planner.main.logger.debug")
async def test_save_recipe_api_call_json_error_with_detail(
    mock_logger_debug: MagicMock, client: AsyncClient, monkeypatch
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
    mock_logger_debug.assert_any_call("API error detail: %s", error_detail_text)


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
        cast(str, ing_input["value"])
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
@mock_patch("meal_planner.main._parse_and_validate_modify_form")
async def test_modify_unexpected_exception(mock_validate, client: AsyncClient):
    """Test the final unexpected exception handler in post_modify_recipe."""
    mock_validate.side_effect = Exception("Completely unexpected error")
    dummy_form_data = {FIELD_NAME: "Test", "original_name": "Orig"}

    response = await client.post(RECIPES_MODIFY_URL, data=dummy_form_data)

    assert response.status_code == 200
    assert (
        "Critical Error: An unexpected error occurred. Please refresh and try again."
        in response.text
    )
    mock_validate.assert_called_once()


@pytest.mark.anyio
@mock_patch("meal_planner.main._build_edit_review_form")
@mock_patch("meal_planner.main.RecipeBase")
@mock_patch("meal_planner.main._request_recipe_modification", new_callable=AsyncMock)
@mock_patch("meal_planner.main._parse_and_validate_modify_form")
async def test_modify_render_validation_error(
    mock_validate: MagicMock,
    mock_request_mod: AsyncMock,
    mock_recipe_base: MagicMock,
    mock_build_form: MagicMock,
    client: AsyncClient,
    mock_current_recipe_before_modify_fixture: RecipeBase,
    mock_original_recipe_fixture: RecipeBase,
):
    """Test ValidationError during form re-rendering in common error path."""
    mock_validate.return_value = (
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
        fallback_instance_mock,
    ]

    mock_build_form.return_value = (
        MagicMock(name="edit_card"),
        MagicMock(name="review_card"),
    )

    form_data = TestRecipeModifyEndpoint()._build_modify_form_data(
        mock_current_recipe_before_modify_fixture,
        mock_original_recipe_fixture,
        "Trigger LLM Error",
    )

    response = await client.post(RECIPES_MODIFY_URL, data=form_data)

    assert response.status_code == 200
    mock_validate.assert_called_once()
    mock_request_mod.assert_called_once()

    assert mock_recipe_base.call_count >= 2

    mock_build_form.assert_called_once()
    call_args, call_kwargs = mock_build_form.call_args

    assert call_kwargs["current_recipe"] is fallback_instance_mock
    assert call_kwargs["current_recipe"].name == "[Validation Error]"

    assert call_kwargs["original_recipe"] is mock_original_recipe_fixture


def create_mock_api_response(
    status_code: int,
    json_data: list | dict | None = None,
    error_to_raise: Exception | None = None,
) -> AsyncMock:
    mock_resp = AsyncMock(spec=Response)
    mock_resp.status_code = status_code
    if json_data is not None:
        mock_resp.json = MagicMock(return_value=json_data)
    else:
        mock_resp.json = MagicMock(return_value={})

    if error_to_raise:
        mock_resp.raise_for_status = MagicMock(side_effect=error_to_raise)
    else:
        mock_resp.raise_for_status = MagicMock()
    return mock_resp


@pytest.fixture
def mock_recipe_data_fixture() -> RecipeBase:
    return RecipeBase(
        name="Original Recipe",
        ingredients=["orig ing 1"],
        instructions=["orig inst 1"],
    )
