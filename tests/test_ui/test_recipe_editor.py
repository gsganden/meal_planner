"""Tests for UI components and helpers in meal_planner.ui.edit_recipe."""

from typing import Any, cast
from unittest.mock import patch as mock_patch

import monsterui.all as mu
import pytest
from bs4 import BeautifulSoup
from bs4.element import Tag
from fasthtml.common import *
from httpx import AsyncClient
from pydantic import ValidationError

from meal_planner.models import RecipeBase
from meal_planner.ui.common import CSS_ERROR_CLASS
from meal_planner.ui.edit_recipe import (
    build_edit_review_form,
    generate_diff_html,
)
from tests.constants import (
    FIELD_INGREDIENTS,
    FIELD_INSTRUCTIONS,
    FIELD_NAME,
    FIELD_ORIGINAL_INGREDIENTS,
    FIELD_ORIGINAL_INSTRUCTIONS,
    FIELD_ORIGINAL_NAME,
    FIELD_RECIPE_TEXT,
    RECIPES_EXTRACT_RUN_URL,
)


def _extract_full_edit_form_data(html_content: str) -> dict:
    """Helper function to extract form data from HTML."""
    from tests.test_helpers import _extract_full_edit_form_data as helpers_extract

    return helpers_extract(html_content)


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


class TestGenerateDiffHtml:
    def _to_comparable(self, items: list[Any]) -> list[tuple[str, str]]:
        """Converts items (strings/FT objects) to a list of (type_name_str, content_str)
        tuples for comparison. This is the original version from test_main.py."""
        result = []
        for item in items:
            if isinstance(item, str):
                result.append(("str", item))
            elif (
                isinstance(item, FT)
                or hasattr(item, "tag")
                and hasattr(item, "children")
            ):
                content = ""
                if item.children and isinstance(item.children[0], str):
                    content = item.children[0]
                elif (
                    item.children
                    and isinstance(item.children, list)
                    and item.children[0]
                    and hasattr(item.children[0], "value")
                ):
                    content = str(item.children[0].value)

                result.append((item.tag, content))
            else:
                result.append((str(type(item)), str(item)))
        return result

    def test_diff_no_change(self):
        before = "line1\nline2\nline3"
        after = "line1\nline2\nline3"
        b_items, a_items = generate_diff_html(before, after)
        assert self._to_comparable(b_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("str", "line2"),
            ("str", "\n"),
            ("str", "line3"),
        ]
        assert self._to_comparable(a_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("str", "line2"),
            ("str", "\n"),
            ("str", "line3"),
        ]

    def test_diff_addition(self):
        before = "line1\nline3"
        after = "line1\nline2\nline3"
        b_items, a_items = generate_diff_html(before, after)
        assert self._to_comparable(b_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("str", "line3"),
        ]
        assert self._to_comparable(a_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("ins", "line2"),
            ("str", "\n"),
            ("str", "line3"),
        ]

    def test_diff_deletion(self):
        before = "line1\nline2\nline3"
        after = "line1\nline3"
        b_items, a_items = generate_diff_html(before, after)
        assert self._to_comparable(b_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("del", "line2"),
            ("str", "\n"),
            ("str", "line3"),
        ]
        assert self._to_comparable(a_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("str", "line3"),
        ]

    def test_diff_modification(self):
        before = "line1\nline2_orig\nline3"
        after = "line1\nline2_mod\nline3"
        b_items, a_items = generate_diff_html(before, after)
        assert self._to_comparable(b_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("del", "line2_orig"),
            ("str", "\n"),
            ("str", "line3"),
        ]
        assert self._to_comparable(a_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("ins", "line2_mod"),
            ("str", "\n"),
            ("str", "line3"),
        ]

    def test_diff_combined(self):
        before = "line1\nline2_delete\nline3_orig\nline5_delete"
        after = "line1\nline3_mod\nline4_add\nline6_add"
        b_items, a_items = generate_diff_html(before, after)
        assert self._to_comparable(b_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("del", "line2_delete"),
            ("str", "\n"),
            ("del", "line3_orig"),
            ("str", "\n"),
            ("del", "line5_delete"),
        ]
        assert self._to_comparable(a_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("ins", "line3_mod"),
            ("str", "\n"),
            ("ins", "line4_add"),
            ("str", "\n"),
            ("ins", "line6_add"),
        ]

    def test_html_escaping_prevents_xss(self):
        malicious_before = (
            "normal line\n<script>alert('xss')</script>\n<img src=x onerror=alert(1)>"
        )
        malicious_after = (
            'normal line\n<div onclick="evil()">click me</div>\n& < > " \' characters'
        )

        b_items, a_items = generate_diff_html(malicious_before, malicious_after)

        comparable_before = self._to_comparable(b_items)
        comparable_after = self._to_comparable(a_items)

        for tag_type, content in comparable_before:
            if tag_type in ("str", "del", "ins"):
                assert "<script>" not in content
                assert "<img" not in content
                if "script" in content:
                    assert "&lt;script&gt;" in content
                if "img" in content:
                    assert "&lt;img" in content

        for tag_type, content in comparable_after:
            if tag_type in ("str", "del", "ins"):
                assert "<div" not in content
                if "div" in content:
                    assert "&lt;div" in content
                if "&" in content and not content.startswith("&"):
                    assert "&amp;" in content
                if "<" in content:
                    assert "&lt;" in content
                if ">" in content:
                    assert "&gt;" in content
                if '"' in content:
                    assert "&quot;" in content


@pytest.mark.anyio
class TestRecipeUpdateDiffViaEndpoint:
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

    @mock_patch("meal_planner.main.generate_recipe_from_text")
    async def test_sortable_after_ingredient_delete(
        self, mock_llm_extract, client: AsyncClient
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

    @mock_patch("meal_planner.main.generate_recipe_from_text")
    async def test_sortable_after_instruction_delete(
        self, mock_llm_extract, client: AsyncClient
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
        assert textareas[0].get_text(strip=True) == "Second instruction details."

    @mock_patch("meal_planner.main.generate_recipe_from_text")
    async def test_sortable_after_ingredient_add(
        self, mock_llm_extract, client: AsyncClient
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
        assert inputs[3].get("value", "") == ""

    @mock_patch("meal_planner.main.generate_recipe_from_text")
    async def test_sortable_after_instruction_add(
        self, mock_llm_extract, client: AsyncClient
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
    @mock_patch("meal_planner.main.logger.warning")
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
    @mock_patch("meal_planner.main.logger.warning")
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

    @mock_patch("meal_planner.main._parse_recipe_form_data")
    @mock_patch("meal_planner.main.logger.error")
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

    @mock_patch("meal_planner.main._parse_recipe_form_data")
    @mock_patch("meal_planner.main.logger.error")
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

    @mock_patch("meal_planner.main._parse_recipe_form_data")
    @mock_patch("meal_planner.main.logger.error")
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

    @mock_patch("meal_planner.main._parse_recipe_form_data")
    @mock_patch("meal_planner.main.logger.error")
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

    @mock_patch("meal_planner.main._parse_recipe_form_data")
    @mock_patch("meal_planner.main.logger.error")
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

    @mock_patch("meal_planner.main._parse_recipe_form_data")
    @mock_patch("meal_planner.main.logger.error")
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

    @mock_patch("meal_planner.main._parse_recipe_form_data")
    @mock_patch("meal_planner.main.logger.error")
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

    @mock_patch("meal_planner.main._parse_recipe_form_data")
    @mock_patch("meal_planner.main.logger.error")
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


def test_build_edit_review_form_no_original():
    "Test hitting the `original_recipe = current_recipe` line."
    current = RecipeBase(name="Test", ingredients=["i"], instructions=["s"])
    result = build_edit_review_form(current)
    assert result is not None
    edit_card, review_card = result
    assert edit_card is not None
    assert review_card is not None


def test_build_edit_review_form_with_original():
    """Test hitting the logic where original_recipe is provided."""
    current = RecipeBase(
        name="Updated Name", ingredients=["i1", "i2"], instructions=["s1"]
    )
    original = RecipeBase(
        name="Original Name", ingredients=["i1"], instructions=["s1", "s2"]
    )
    result = build_edit_review_form(current, original)
    assert result is not None
    edit_card, review_card = result
    assert edit_card is not None
    assert review_card is not None
