"""UI components for recipe editing and display."""

import difflib

from fasthtml.common import *
from monsterui.all import *

from meal_planner.models import RecipeBase


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


def _build_diff_content_children(
    original_recipe: RecipeBase, current_markdown: str
) -> tuple[FT, FT]:
    """Builds fasthtml.Div components for 'before' and 'after' diff areas."""
    before_items, after_items = generate_diff_html(
        original_recipe.markdown, current_markdown
    )

    pre_style = "white-space: pre-wrap; overflow-wrap: break-word;"
    base_classes = (
        "border p-2 rounded bg-gray-100 dark:bg-gray-700 mt-1 overflow-auto text-xs"
    )

    before_div_component = Card(
        Strong("Initial Extracted Recipe (Reference)"),
        Pre(
            *before_items,
            id="diff-before-pre",
            cls=base_classes,
            style=pre_style,
        ),
        cls=CardT.secondary,
    )

    after_div_component = Card(
        Strong("Current Edited Recipe"),
        Pre(
            *after_items,
            id="diff-after-pre",
            cls=base_classes,
            style=pre_style,
        ),
        cls=CardT.secondary,
    )

    return before_div_component, after_div_component


def _build_recipe_display(recipe_data: dict) -> FT:
    """Builds a Card containing the formatted recipe details.

    Args:
        recipe_data: A dictionary containing 'name', 'ingredients', 'instructions'.

    Returns:
        A monsterui.Card component ready for display.
    """
    components = [
        H3(recipe_data["name"]),
        H4("Ingredients"),
        Ul(
            *[Li(ing) for ing in recipe_data.get("ingredients", [])],
            cls=ListT.bullet,
        ),
    ]
    instructions = recipe_data.get("instructions", [])
    if instructions:
        components.extend(
            [
                H4("Instructions"),
                Ul(
                    *[Li(inst) for inst in instructions],
                    cls=ListT.bullet,
                ),
            ]
        )

    return Card(
        *components,
        cls=CardT.secondary,
    )
