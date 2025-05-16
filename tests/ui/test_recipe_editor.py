"""Tests for UI components and helpers in meal_planner.ui.recipe_editor."""

from typing import Any

from fasthtml.common import *  # Use import * as per original style and rules

# Del and Ins are not directly used in _to_comparable by isinstance,
# but are expected types produced by generate_diff_html.
# Their structure (tag, children) will be checked by hasattr.
from meal_planner.ui.recipe_editor import generate_diff_html


class TestGenerateDiffHtml:
    def _to_comparable(self, items: list[Any]) -> list[tuple[str, str]]:
        """Converts items (strings/FT objects) to a list of (type_name_str, content_str)
        tuples for comparison. This is the original version from test_main.py."""
        result = []
        for item in items:
            if isinstance(item, str):
                result.append(("str", item))
            elif (
                isinstance(item, FT)  # FT will now be from fasthtml.common
                or hasattr(item, "tag")
                and hasattr(item, "children")  # Check for .children attribute
            ):
                result.append(
                    (item.tag, str(item.children[0]) if item.children else "")
                )
            else:
                result.append((type(item).__name__, str(item)))
        return result

    def test_diff_insert(self):
        before = "line1\nline3"
        after = "line1\nline2\nline3"
        # Call the imported generate_diff_html directly
        before_items, after_items = generate_diff_html(before, after)
        assert self._to_comparable(before_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("str", "line3"),
        ]
        assert self._to_comparable(after_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("ins", "line2"),
            ("str", "\n"),
            ("str", "line3"),
        ]

    def test_diff_delete(self):
        before = "line1\nline2\nline3"
        after = "line1\nline3"
        before_items, after_items = generate_diff_html(before, after)
        assert self._to_comparable(before_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("del", "line2"),
            ("str", "\n"),
            ("str", "line3"),
        ]
        assert self._to_comparable(after_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("str", "line3"),
        ]

    def test_diff_replace(self):
        before = "line1\nline TWO\nline3"
        after = "line1\nline 2\nline3"
        before_items, after_items = generate_diff_html(before, after)
        assert self._to_comparable(before_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("del", "line TWO"),
            ("str", "\n"),
            ("str", "line3"),
        ]
        assert self._to_comparable(after_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("ins", "line 2"),
            ("str", "\n"),
            ("str", "line3"),
        ]

    def test_diff_equal(self):
        before = "line1\nline2"
        after = "line1\nline2"
        before_items, after_items = generate_diff_html(before, after)
        assert self._to_comparable(before_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("str", "line2"),
        ]
        assert self._to_comparable(after_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("str", "line2"),
        ]

    def test_diff_combined(self):
        before = "line1\nline to delete\nline3\nline4"
        after = "line1\nline3\nline inserted\nline4"
        before_items, after_items = generate_diff_html(before, after)
        assert self._to_comparable(before_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("del", "line to delete"),
            ("str", "\n"),
            ("str", "line3"),
            ("str", "\n"),
            ("str", "line4"),
        ]
        assert self._to_comparable(after_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("str", "line3"),
            ("str", "\n"),
            ("ins", "line inserted"),
            ("str", "\n"),
            ("str", "line4"),
        ]
