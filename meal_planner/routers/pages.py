"""Routers for user-facing HTML pages that render full page layouts."""

import logging

import httpx
from fastapi import Request
from fasthtml.common import *
from monsterui.all import *

from meal_planner.core import internal_api_client, rt
from meal_planner.ui.common import CSS_ERROR_CLASS
from meal_planner.ui.edit_recipe import build_recipe_display
from meal_planner.ui.extract_recipe import create_extraction_form
from meal_planner.ui.layout import is_htmx, with_layout
from meal_planner.ui.list_recipes import format_recipe_list

logger = logging.getLogger(__name__)


@rt("/")
def get():
    """Render the application home page.

    Displays the main landing page with navigation to recipe features.
    This is the entry point for users accessing the application.

    Returns:
        HTML page with site layout and home content.
    """
    return with_layout("Meal Planner")


@rt("/recipes/extract")
def get_recipe_extraction_page():
    """Render the recipe extraction page for creating new recipes.

    Provides forms for extracting recipes from URLs and editing the
    extracted content. The page includes multiple sections that are
    progressively populated via HTMX as the user proceeds.

    Returns:
        HTML page with extraction form and placeholder divs for
        dynamic content loading.
    """
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
    """Display all recipes in a paginated list view.

    Fetches recipes from the API and renders them in a list format.
    Supports both full page loads and HTMX partial updates when the
    recipe list changes (via HX-Trigger events).

    Args:
        request: FastAPI request object to detect HTMX requests.

    Returns:
        Full HTML page for standard requests, or just the recipe
        list div for HTMX requests.

    Note:
        The response includes HTMX attributes for automatic refresh
        when recipes are added, updated, or deleted.
    """
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
        content = format_recipe_list(response.json())

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


@rt("/recipes/{recipe_id}")
async def get_single_recipe_page(recipe_id: str):
    """Display a single recipe's details page.

    Fetches a specific recipe by ID and renders its full details
    including ingredients, instructions, and action buttons for
    editing or deletion.

    Args:
        recipe_id: Database UUID of the recipe to display.

    Returns:
        HTML page with recipe details or appropriate error message
        if the recipe is not found or an error occurs.
    """
    try:
        response = await internal_api_client.get(f"/v0/recipes/{recipe_id}")
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
