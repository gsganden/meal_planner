"""Routers for user-facing HTML pages that render full page layouts."""

import logging

import httpx
from fastapi import Request
from fasthtml.common import *
from monsterui.all import *

from meal_planner.core import internal_api_client, internal_client, rt
from meal_planner.ui.common import CSS_ERROR_CLASS
from meal_planner.ui.edit_recipe import build_recipe_display
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


@rt("/recipes/{recipe_id:int}")
async def get_single_recipe_page(recipe_id: int):
    """Displays a single recipe page."""
    try:
        response = await internal_client.get(f"/api/v0/recipes/{recipe_id}")
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning("Recipe ID %s not found when loading page.", recipe_id)
            title = "Recipe Not Found"
            content = P("The requested recipe does not exist.")
        else:
            logger.error(
                "API error fetching recipe ID %s: Status %s, Response: %s",
                recipe_id,
                e.response.status_code,
                e.response.text,
                exc_info=True,
            )
            title = "Error"
            content = P(
                "Error fetching recipe from API.",
                cls=CSS_ERROR_CLASS,
            )
    except Exception as e:
        logger.error(
            "Unexpected error fetching recipe ID %s for page: %s",
            recipe_id,
            e,
            exc_info=True,
        )
        title = "Error"
        content = P(
            "An unexpected error occurred.",
            cls=CSS_ERROR_CLASS,
        )
    else:
        recipe_data = response.json()
        title = recipe_data["name"]
        content = build_recipe_display(recipe_data)

    return with_layout(title, content)
