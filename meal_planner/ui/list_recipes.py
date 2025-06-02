"""Recipe list display components for the Meal Planner application.

This module provides UI components for displaying collections of recipes
in list format with action buttons for viewing and deleting recipes.
"""

from fasthtml.common import *
from monsterui.all import *

from meal_planner.ui.common import ICON_DELETE


def format_recipe_list(recipes_data: list[dict]) -> FT:
    """Format a list of recipes as an interactive HTML list.

    Creates a styled list of recipe items, each with a clickable name
    that navigates to the recipe detail page and a delete button with
    confirmation dialog.

    Args:
        recipes_data: List of recipe dictionaries, each containing at least
            'id' and 'name' fields.

    Returns:
        MonsterUI List component containing all recipe items with actions,
        or a message if the list is empty.
    """
    if not recipes_data:
        return P("No recipes found.")
    return Ul(
        *[
            Li(
                A(
                    recipe["name"],
                    href=f"/recipes/{recipe['id']}",
                    hx_target="#content",
                    hx_push_url="true",
                    cls="mr-2",
                ),
                Button(
                    ICON_DELETE,
                    title="Delete",
                    hx_post=f"/recipes/delete?id={recipe['id']}",
                    hx_confirm=f"Are you sure you want to delete {recipe['name']}?",
                    cls=f"{ButtonT.sm} p-1",
                ),
                id=f"recipe-item-{recipe['id']}",
                cls="flex items-center justify-start gap-x-2 mb-1",
            )
            for recipe in recipes_data
        ],
        id="recipe-list-ul",
    )
