import logging

from fastapi import Request
from fasthtml.common import FT, Div, Group, P  # type: ignore
from pydantic import ValidationError

from meal_planner.form_processing import _parse_recipe_form_data
from meal_planner.main import rt
from meal_planner.models import RecipeBase
from meal_planner.ui.common import CSS_ERROR_CLASS
from meal_planner.ui.edit_recipe import (
    build_diff_content_children,
    render_ingredient_list_items,
    render_instruction_list_items,
)

logger = logging.getLogger(__name__)


@rt("/recipes/ui/delete-ingredient/{index:int}")
async def post_delete_ingredient_row(request: Request, index: int):
    form_data = await request.form()
    try:
        parsed_data = _parse_recipe_form_data(form_data)
        current_ingredients = parsed_data.get("ingredients", [])

        if 0 <= index < len(current_ingredients):
            del current_ingredients[index]
        else:
            logger.warning(f"Attempted to delete ingredient at invalid index {index}")

        parsed_data["ingredients"] = current_ingredients
        new_current_recipe = RecipeBase(**parsed_data)

        original_data = _parse_recipe_form_data(form_data, prefix="original_")
        original_recipe = RecipeBase(**original_data)

        new_ingredient_item_components = render_ingredient_list_items(
            new_current_recipe.ingredients
        )
        return _build_sortable_list_with_oob_diff(
            list_id="ingredients-list",
            rendered_list_items=new_ingredient_item_components,
            original_recipe=original_recipe,
            current_recipe=new_current_recipe,
        )

    except ValidationError as e:
        logger.error(
            f"Validation error processing ingredient deletion at index {index}: {e}",
            exc_info=True,
        )
        data_for_error_render = _parse_recipe_form_data(form_data)
        ingredients_for_error_render = data_for_error_render.get("ingredients", [])

        error_items_list = render_ingredient_list_items(ingredients_for_error_render)
        ingredients_list_component = Div(
            P(
                "Error updating list after delete. Validation failed.",
                cls=CSS_ERROR_CLASS,
            ),
            *error_items_list,
            id="ingredients-list",
            cls="mb-4",
        )
        return ingredients_list_component

    except Exception as e:
        logger.error(f"Error deleting ingredient at index {index}: {e}", exc_info=True)
        return Div(
            "Error processing delete request.",
            cls=CSS_ERROR_CLASS,
            id="ingredients-list",
        )


@rt("/recipes/ui/delete-instruction/{index:int}")
async def post_delete_instruction_row(request: Request, index: int):
    form_data = await request.form()
    try:
        parsed_data = _parse_recipe_form_data(form_data)
        current_instructions = parsed_data.get("instructions", [])

        if 0 <= index < len(current_instructions):
            del current_instructions[index]
        else:
            logger.warning(f"Attempted to delete instruction at invalid index {index}")

        parsed_data["instructions"] = current_instructions
        new_current_recipe = RecipeBase(**parsed_data)

        original_data = _parse_recipe_form_data(form_data, prefix="original_")
        original_recipe = RecipeBase(**original_data)

        new_instruction_item_components = render_instruction_list_items(
            new_current_recipe.instructions
        )
        return _build_sortable_list_with_oob_diff(
            list_id="instructions-list",
            rendered_list_items=new_instruction_item_components,
            original_recipe=original_recipe,
            current_recipe=new_current_recipe,
        )

    except ValidationError as e:
        logger.error(
            f"Validation error processing instruction deletion at index {index}: {e}",
            exc_info=True,
        )
        data_for_error_render = _parse_recipe_form_data(form_data)
        instructions_for_error_render = data_for_error_render.get("instructions", [])

        error_items_list = render_instruction_list_items(instructions_for_error_render)
        instructions_list_component = Div(
            P(
                "Error updating list after delete. Validation failed.",
                cls=CSS_ERROR_CLASS,
            ),
            *error_items_list,
            id="instructions-list",
            cls="mb-4",
        )
        return instructions_list_component

    except Exception as e:
        logger.error(f"Error deleting instruction at index {index}: {e}", exc_info=True)
        return Div(
            "Error processing delete request.",
            cls=CSS_ERROR_CLASS,
            id="instructions-list",
        )


@rt("/recipes/ui/add-ingredient")
async def post_add_ingredient_row(request: Request):
    form_data = await request.form()
    try:
        parsed_data = _parse_recipe_form_data(form_data)
        current_ingredients = parsed_data.get("ingredients", [])
        current_ingredients.append("")

        parsed_data["ingredients"] = current_ingredients
        new_current_recipe = RecipeBase(**parsed_data)

        original_data = _parse_recipe_form_data(form_data, prefix="original_")
        original_recipe = RecipeBase(**original_data)

        new_ingredient_item_components = render_ingredient_list_items(
            new_current_recipe.ingredients
        )
        return _build_sortable_list_with_oob_diff(
            list_id="ingredients-list",
            rendered_list_items=new_ingredient_item_components,
            original_recipe=original_recipe,
            current_recipe=new_current_recipe,
        )

    except ValidationError as e:
        logger.error(
            f"Validation error processing ingredient addition: {e}", exc_info=True
        )
        current_ingredients_before_error = _parse_recipe_form_data(form_data).get(
            "ingredients", []
        )
        error_items = render_ingredient_list_items(current_ingredients_before_error)
        return Div(
            P("Error updating list after add.", cls=CSS_ERROR_CLASS),
            *error_items,
            id="ingredients-list",
            cls="mb-4",
        )
    except Exception as e:
        logger.error(f"Error adding ingredient: {e}", exc_info=True)
        return Div(
            "Error processing add request.", cls=CSS_ERROR_CLASS, id="ingredients-list"
        )


@rt("/recipes/ui/add-instruction")
async def post_add_instruction_row(request: Request):
    form_data = await request.form()
    try:
        parsed_data = _parse_recipe_form_data(form_data)
        current_instructions = parsed_data.get("instructions", [])
        current_instructions.append("")

        parsed_data["instructions"] = current_instructions
        new_current_recipe = RecipeBase(**parsed_data)

        original_data = _parse_recipe_form_data(form_data, prefix="original_")
        original_recipe = RecipeBase(**original_data)

        new_instruction_item_components = render_instruction_list_items(
            new_current_recipe.instructions
        )
        return _build_sortable_list_with_oob_diff(
            list_id="instructions-list",
            rendered_list_items=new_instruction_item_components,
            original_recipe=original_recipe,
            current_recipe=new_current_recipe,
        )

    except ValidationError as e:
        logger.error(
            f"Validation error processing instruction addition: {e}", exc_info=True
        )
        current_instructions_before_error = _parse_recipe_form_data(form_data).get(
            "instructions", []
        )
        error_items = render_instruction_list_items(current_instructions_before_error)
        return Div(
            P("Error updating list after add.", cls=CSS_ERROR_CLASS),
            *error_items,
            id="instructions-list",
            cls="mb-4",
        )
    except Exception as e:
        logger.error(f"Error adding instruction: {e}", exc_info=True)
        return Div(
            "Error processing add request.", cls=CSS_ERROR_CLASS, id="instructions-list"
        )


@rt("/recipes/ui/update-diff")
async def update_diff(request: Request) -> FT:
    """Updates the diff view based on current form data."""
    form_data = await request.form()
    try:
        current_data = _parse_recipe_form_data(form_data)
        original_data = _parse_recipe_form_data(form_data, prefix="original_")
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
