import logging

import httpx
from fastapi import Request
from fasthtml.common import *
from monsterui.all import *

from meal_planner.main import internal_api_client, rt
from meal_planner.ui.extract_recipe import create_extraction_form
from meal_planner.ui.layout import is_htmx, with_layout
from meal_planner.ui.list_recipes import format_recipe_list

logger = logging.getLogger(__name__)


@rt("/")
def get():
    """Get the home page."""
    return with_layout("Meal Planner")


@rt("/recipes/extract")
def get_recipe_extraction_page():
    return with_layout(
        "Create Recipe",
        Div(
            Div(create_extraction_form()),
            Div(id="edit-form-target"),
            Div(id="review-section-target"),
            cls="space-y-4",
        ),
    )


@rt("/recipes")
async def get_recipe_list_page(request: Request):
    """Get the recipes list page."""
    try:
        response = await internal_api_client.get("/v0/recipes")
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error(
            "API error fetching recipes: %s Response: %s",
            e,
            e.response.text,
            exc_info=True,
        )
        title = "Error"
        content = Div("Error fetching recipes from API.", cls=f"{TextT.error} mb-4")
    except Exception as e:
        logger.error("Error fetching recipes: %s", e, exc_info=True)
        title = "Error"
        content = Div(
            "An unexpected error occurred while fetching recipes.",
            cls=f"{TextT.error} mb-4",
        )
    else:
        title = "All Recipes"
        content = (
            format_recipe_list(response.json())
            if response.json()
            else Div("No recipes found.")
        )

    content_with_attrs = Div(
        content,
        id="recipe-list-area",
        hx_trigger="recipeListChanged from:body",
        hx_get="/recipes",
        hx_swap="outerHTML",
    )

    return (
        with_layout(title, content_with_attrs)
        if not is_htmx(request)
        else content_with_attrs
    )
