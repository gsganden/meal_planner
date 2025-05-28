"""UI component for displaying a list of recipes."""

from fasthtml.common import *
from monsterui.all import *

from meal_planner.ui.common import ICON_DELETE


def format_recipe_list(recipes_data: list[dict]) -> FT:
    """Formats the recipe list data into a list of recipe items."""
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
