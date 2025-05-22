"""Tests for UI components and helpers in meal_planner.ui.recipe_editor."""

from typing import Any

import pytest
from bs4 import BeautifulSoup
from fasthtml.common import *
from httpx import AsyncClient

from meal_planner.models import RecipeBase
from meal_planner.ui.recipe_editor import (
    generate_diff_html,
    build_edit_review_form,
)
from tests.constants import (
    FIELD_INGREDIENTS,
    FIELD_INSTRUCTIONS,
    FIELD_NAME,
    FIELD_ORIGINAL_INGREDIENTS,
    FIELD_ORIGINAL_INSTRUCTIONS,
    FIELD_ORIGINAL_NAME,
)


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
