"""UI components for recipe editing and display."""

import difflib

from fasthtml.common import *


def generate_diff_html(
    before_text: str, after_text: str
) -> tuple[list[str | FT], list[str | FT]]:
    """Generates two lists of fasthtml components/strings for diff display."""
    before_lines = before_text.splitlines()
    after_lines = after_text.splitlines()
    matcher = difflib.SequenceMatcher(None, before_lines, after_lines)
    before_items = []
    after_items = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in before_lines[i1:i2]:
                before_items.extend([line, "\n"])
                after_items.extend([line, "\n"])
        elif tag == "replace":
            for line in before_lines[i1:i2]:
                before_items.extend([Del(line), "\n"])
            for line in after_lines[j1:j2]:
                after_items.extend([Ins(line), "\n"])
        elif tag == "delete":
            for line in before_lines[i1:i2]:
                before_items.extend([Del(line), "\n"])
        elif tag == "insert":
            for line in after_lines[j1:j2]:
                after_items.extend([Ins(line), "\n"])

    if before_items and before_items[-1] == "\n":
        before_items.pop()
    if after_items and after_items[-1] == "\n":
        after_items.pop()

    return before_items, after_items
