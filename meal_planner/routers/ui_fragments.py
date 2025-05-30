"""Routers for generating and returning HTML UI fragments, often for HTMX swaps."""

import logging

import httpx
from fastapi import Request
from fasthtml.common import FT, Div, Group, P  # type: ignore
from monsterui.all import TextArea
from pydantic import ValidationError

from meal_planner.core import rt
from meal_planner.form_processing import parse_recipe_form_data
from meal_planner.models import RecipeBase
from meal_planner.services.extract_webpage_text import (
    fetch_and_clean_text_from_url,
)
from meal_planner.ui.common import CSS_ERROR_CLASS
from meal_planner.ui.edit_recipe import (
    build_diff_content_children,
    render_ingredient_list_items,
    render_instruction_list_items,
)

logger = logging.getLogger(__name__)


async def _delete_list_item(request: Request, index: int, item_type: str) -> FT:
    """Helper function to delete an item from a list (ingredients or instructions)."""
    form_data = await request.form()
    list_id = f"{item_type}-list"
    render_func = (
        render_ingredient_list_items
        if item_type == "ingredients"
        else render_instruction_list_items
    )

    try:
        parsed_data = parse_recipe_form_data(form_data)
        current_items = parsed_data.get(item_type, [])

        if 0 <= index < len(current_items):
            del current_items[index]
        else:
            logger.warning(
                f"Attempted to delete {item_type[:-1]} at invalid index {index}"
            )

        parsed_data[item_type] = current_items
        new_current_recipe = RecipeBase(**parsed_data)

        original_data = parse_recipe_form_data(form_data, prefix="original_")
        original_recipe = RecipeBase(**original_data)

        new_item_components = render_func(getattr(new_current_recipe, item_type))
        return _build_sortable_list_with_oob_diff(
            list_id=list_id,
            rendered_list_items=new_item_components,
            original_recipe=original_recipe,
            current_recipe=new_current_recipe,
        )

    except ValidationError as e:
        logger.error(
            f"Validation error processing {item_type[:-1]} deletion at index {index}: "
            f"{e}",
            exc_info=True,
        )
        data_for_error_render = parse_recipe_form_data(form_data)
        items_for_error_render = data_for_error_render.get(item_type, [])

        error_items_list = render_func(items_for_error_render)
        items_list_component = Div(
            P(
                "Error updating list after delete. Validation failed.",
                cls=CSS_ERROR_CLASS,
            ),
            *error_items_list,
            id=list_id,
            cls="mb-4",
        )
        return items_list_component

    except Exception as e:
        logger.error(
            f"Error deleting {item_type[:-1]} at index {index}: {e}", exc_info=True
        )
        return Div(
            "Error processing delete request.",
            cls=CSS_ERROR_CLASS,
            id=list_id,
        )


@rt("/recipes/ui/delete-ingredient/{index:int}")
async def post_delete_ingredient_row(request: Request, index: int):
    return await _delete_list_item(request, index, "ingredients")


@rt("/recipes/ui/delete-instruction/{index:int}")
async def post_delete_instruction_row(request: Request, index: int):
    return await _delete_list_item(request, index, "instructions")


async def _add_list_item(request: Request, item_type: str) -> FT:
    """Helper function to add an item to a list (ingredients or instructions)."""
    form_data = await request.form()
    list_id = f"{item_type}-list"
    render_func = (
        render_ingredient_list_items
        if item_type == "ingredients"
        else render_instruction_list_items
    )

    try:
        parsed_data = parse_recipe_form_data(form_data)
        current_items = parsed_data.get(item_type, [])
        current_items.append("")  # Add an empty item

        parsed_data[item_type] = current_items
        new_current_recipe = RecipeBase(**parsed_data)

        original_data = parse_recipe_form_data(form_data, prefix="original_")
        original_recipe = RecipeBase(**original_data)

        new_item_components = render_func(getattr(new_current_recipe, item_type))
        return _build_sortable_list_with_oob_diff(
            list_id=list_id,
            rendered_list_items=new_item_components,
            original_recipe=original_recipe,
            current_recipe=new_current_recipe,
        )

    except ValidationError as e:
        logger.error(
            f"Validation error processing {item_type[:-1]} addition: {e}", exc_info=True
        )
        items_before_error = parse_recipe_form_data(form_data).get(item_type, [])
        error_items = render_func(items_before_error)
        return Div(
            P("Error updating list after add.", cls=CSS_ERROR_CLASS),
            *error_items,
            id=list_id,
            cls="mb-4",
        )
    except Exception as e:
        logger.error(f"Error adding {item_type[:-1]}: {e}", exc_info=True)
        return Div("Error processing add request.", cls=CSS_ERROR_CLASS, id=list_id)


@rt("/recipes/ui/add-ingredient")
async def post_add_ingredient_row(request: Request):
    return await _add_list_item(request, "ingredients")


@rt("/recipes/ui/add-instruction")
async def post_add_instruction_row(request: Request):
    return await _add_list_item(request, "instructions")


@rt("/recipes/ui/update-diff")
async def update_diff(request: Request) -> FT:
    """Updates the diff view based on current form data."""
    form_data = await request.form()
    try:
        current_data = parse_recipe_form_data(form_data)
        original_data = parse_recipe_form_data(form_data, prefix="original_")
        current_recipe = RecipeBase(**current_data)
        original_recipe = RecipeBase(**original_data)

        before_component, after_component = build_diff_content_children(
            original_recipe, current_recipe.markdown
        )
        return Div(
            before_component,
            after_component,
            cls="flex space-x-4 mt-4",
            id="diff-content-wrapper",
        )
    except ValidationError as e:
        logger.warning("Validation error during diff update: %s", e, exc_info=False)
        error_message = "Recipe state invalid for diff. Please check all fields."
        return Div(error_message, cls=CSS_ERROR_CLASS)
    except Exception as e:
        logger.error("Error updating diff: %s", e, exc_info=True)
        return Div("Error updating diff view.", cls=CSS_ERROR_CLASS)


@rt("/recipes/fetch-text")
async def post_fetch_text(input_url: str | None = None):
    def _prepare_error_response(error_message_str: str):
        error_div = Div(
            error_message_str, cls=CSS_ERROR_CLASS, id="fetch-url-error-display"
        )
        error_oob = Div(error_div, hx_swap_oob="outerHTML:#fetch-url-error-display")
        text_area = Div(
            TextArea(
                id="recipe_text",
                name="recipe_text",
                placeholder="Paste full recipe text here, or fetch from URL above.",
                rows=15,
                cls="mb-4",
            ),
            id="recipe_text_container",
        )
        return Group(text_area, error_oob)

    if not input_url:
        logger.error("Fetch text called without URL.")
        return _prepare_error_response("Please provide a Recipe URL to fetch.")

    try:
        logger.info("Fetching and cleaning text from URL: %s", input_url)
        cleaned_text = await fetch_and_clean_text_from_url(input_url)
    except httpx.RequestError as e:
        logger.error("Network error fetching URL %s: %s", input_url, e, exc_info=True)
        result = _prepare_error_response(
            "Error fetching URL. Please check the URL and your connection."
        )
    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTP error fetching URL %s: %s. Response: %s",
            input_url,
            e,
            e.response.text,
            exc_info=True,
        )
        result = _prepare_error_response(
            "Error fetching URL: The server returned an error."
        )
    except RuntimeError as e:
        logger.error(
            "RuntimeError processing URL content from %s: %s",
            input_url,
            e,
            exc_info=True,
        )
        result = _prepare_error_response("Failed to process the content from the URL.")
    except Exception as e:
        logger.error(
            "Unexpected error fetching text from %s: %s", input_url, e, exc_info=True
        )
        result = _prepare_error_response(
            "An unexpected error occurred while fetching text."
        )
    else:
        text_area = Div(
            TextArea(
                cleaned_text,
                id="recipe_text",
                name="recipe_text",
                placeholder="Paste full recipe text here, or fetch from URL above.",
                rows=15,
                cls="mb-4",
            ),
            id="recipe_text_container",
        )
        clear_error_oob = Div(
            Div(id="fetch-url-error-display"),
            hx_swap_oob="outerHTML:#fetch-url-error-display",
        )
        result = Group(text_area, clear_error_oob)

    return result


def _build_sortable_list_with_oob_diff(
    list_id: str,
    rendered_list_items: list[FT],
    original_recipe: RecipeBase,
    current_recipe: RecipeBase,
) -> FT:
    """
    Builds a sortable list component and an OOB diff component.

    Args:
        list_id: The HTML ID for the list container (e.g., "ingredients-list").
        rendered_list_items: A list of FastHTML components representing the items.
        original_recipe: The baseline recipe for the diff.
        current_recipe: The current state of the recipe for the diff.

    Returns:
        A tuple containing the list component Div and the OOB diff component Div.
    """
    list_component = Div(
        *rendered_list_items,
        id=list_id,
        cls="mb-4",
        uk_sortable="handle: .drag-handle",
        hx_trigger="moved",
        hx_post="/recipes/ui/update-diff",
        hx_target="#diff-content-wrapper",
        hx_swap="innerHTML",
        hx_include="closest form",
    )

    before_notstr, after_notstr = build_diff_content_children(
        original_recipe, current_recipe.markdown
    )
    oob_diff_component = Div(
        before_notstr,
        after_notstr,
        hx_swap_oob="innerHTML:#diff-content-wrapper",
    )
    return Group(list_component, oob_diff_component)
