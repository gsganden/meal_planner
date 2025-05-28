"""Tests for UI components and helpers in meal_planner.ui.edit_recipe."""

from typing import Any

from fasthtml.common import *

from meal_planner.models import RecipeBase
from meal_planner.ui.edit_recipe import (
    build_edit_review_form,
    generate_diff_html,
)


def _extract_full_edit_form_data(html_content: str) -> dict:
    """Helper function to extract form data from HTML."""
    from tests.test_helpers import extract_full_edit_form_data as helpers_extract

    return helpers_extract(html_content)


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
