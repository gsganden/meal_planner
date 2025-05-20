import logging
from pathlib import Path

import httpx
from bs4.element import Tag
from fastapi import FastAPI, Request, status
from fasthtml.common import *
from httpx import ASGITransport
from monsterui.all import *
from pydantic import ValidationError
from starlette import status
from starlette.datastructures import FormData
from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles

from meal_planner.api.recipes import API_ROUTER as RECIPES_API_ROUTER
from meal_planner.models import RecipeBase
from meal_planner.services.llm_service import (
    generate_modified_recipe as llm_generate_modified_recipe,
)
from meal_planner.services.llm_service import (
    generate_recipe_from_text as llm_generate_recipe_from_text,
)
from meal_planner.services.recipe_processing import postprocess_recipe
from meal_planner.services.webpage_text_extractor import (
    fetch_and_clean_text_from_url,
)
from meal_planner.ui.common import (
    CSS_ERROR_CLASS,
    CSS_SUCCESS_CLASS,
)
from meal_planner.ui.layout import _wrap_for_full_page_iff_not_htmx, with_layout
from meal_planner.ui.recipe_editor import (
    _build_edit_review_form,
    build_diff_content_children,
    build_recipe_display,
    render_ingredient_list_items,
    render_instruction_list_items,
)
from meal_planner.ui.recipe_form import create_extraction_form
from meal_planner.ui.recipe_list import format_recipe_list

MODEL_NAME = "gemini-2.0-flash"

STATIC_DIR = Path(__file__).resolve().parent / "static"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


app = FastHTMLWithLiveReload(hdrs=(Theme.blue.headers()))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
rt = app.route

api_app = FastAPI()
api_app.include_router(RECIPES_API_ROUTER)

app.mount("/api", api_app)

internal_client = httpx.AsyncClient(
    transport=ASGITransport(app=app),
    base_url="http://internal",  # arbitrary
)

internal_api_client = httpx.AsyncClient(
    transport=ASGITransport(app=api_app),
    base_url="http://internal-api",  # arbitrary
)


@rt("/")
def get():
    """Get the home page."""
    return with_layout(Titled("Meal Planner"))


@rt("/recipes/extract")
def get_recipe_extraction_page():
    return with_layout(
        Titled(
            "Create Recipe",
            Div(create_extraction_form()),
            Div(id="edit-form-target"),
            Div(id="review-section-target"),
            id="content",
            cls="space-y-4",
        )
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
        result = _wrap_for_full_page_iff_not_htmx(
            Titled(
                "Error",
                Div("Error fetching recipes from API.", cls=f"{TextT.error} mb-4"),
                id="recipe-list-area",
            ),
            request,
        )
    except Exception as e:
        logger.error("Error fetching recipes: %s", e, exc_info=True)
        result = _wrap_for_full_page_iff_not_htmx(
            Titled(
                "Error",
                Div(
                    "An unexpected error occurred while fetching recipes.",
                    cls=f"{TextT.error} mb-4",
                ),
                id="recipe-list-area",
            ),
            request,
        )
    else:
        result = _wrap_for_full_page_iff_not_htmx(
            Titled(
                "All Recipes",
                format_recipe_list(response.json())
                if response.json()
                else Div("No recipes found."),
                id="recipe-list-area",
                hx_trigger="recipeListChanged from:body",
                hx_get="/recipes",
                hx_swap="outerHTML",
            ),
            request,
        )

    return result


@rt("/recipes/{recipe_id:int}")
async def get_single_recipe_page(recipe_id: int):
    """Displays a single recipe page."""
    try:
        response = await internal_client.get(f"/api/v0/recipes/{recipe_id}")
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning("Recipe ID %s not found when loading page.", recipe_id)
            result = with_layout(
                Titled("Recipe Not Found", P("The requested recipe does not exist."))
            )
        else:
            logger.error(
                "API error fetching recipe ID %s: Status %s, Response: %s",
                recipe_id,
                e.response.status_code,
                e.response.text,
                exc_info=True,
            )
            result = with_layout(
                Titled(
                    "Error",
                    P(
                        "Error fetching recipe from API.",
                        cls=CSS_ERROR_CLASS,
                    ),
                )
            )
    except Exception as e:
        logger.error(
            "Unexpected error fetching recipe ID %s for page: %s",
            recipe_id,
            e,
            exc_info=True,
        )
        result = with_layout(
            Titled(
                "Error",
                P(
                    "An unexpected error occurred.",
                    cls=CSS_ERROR_CLASS,
                ),
            )
        )
    else:
        result = with_layout(build_recipe_display(response.json()))

    return result


async def extract_recipe_from_text(page_text: str) -> RecipeBase:
    """Extracts a recipe from the given text and postprocesses it."""
    logger.info("Attempting to extract recipe from provided text.")
    try:
        extracted_recipe: RecipeBase = await llm_generate_recipe_from_text(
            text=page_text
        )
    except Exception as e:
        logger.error(
            f"LLM service failed to generate recipe from text: {e!r}", exc_info=True
        )
        raise

    result = postprocess_recipe(extracted_recipe)
    logger.info(
        "Extraction (via llm_service) and postprocessing successful. Recipe Name: %s",
        result.name,
    )
    logger.debug("Processed Recipe Object: %r", result)
    return result


def _parse_recipe_form_data(form_data: FormData, prefix: str = "") -> dict:
    """Parses recipe form data into a dictionary, handling optional prefix."""
    name_value = form_data.get(f"{prefix}name")
    name = name_value if isinstance(name_value, str) else ""

    ingredients_values = form_data.getlist(f"{prefix}ingredients")
    ingredients = [
        ing for ing in ingredients_values if isinstance(ing, str) and ing.strip()
    ]

    instructions_values = form_data.getlist(f"{prefix}instructions")
    instructions = [
        inst for inst in instructions_values if isinstance(inst, str) and inst.strip()
    ]

    return {
        "name": name,
        "ingredients": ingredients,
        "instructions": instructions,
    }


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


@rt("/recipes/extract/run")
async def post(recipe_text: str | None = None):
    if not recipe_text:
        logging.error("Recipe extraction called without text.")
        return Div("No text content provided for extraction.", cls=CSS_ERROR_CLASS)

    try:
        logger.info("Calling extraction logic")
        processed_recipe = await extract_recipe_from_text(recipe_text)
        logger.info("Extraction successful")
        logger.info(
            f"Instructions before building form: {processed_recipe.instructions}"
        )
    except Exception as e:
        logger.error(
            "Error during recipe extraction: %s",
            e,
            exc_info=True,
        )
        result = Div(
            "Recipe extraction failed. An unexpected error occurred during processing.",
            cls=CSS_ERROR_CLASS,
        )
    else:
        rendered_recipe_html = Div(
            H2("Extracted Recipe (Reference)"),
            build_recipe_display(processed_recipe.model_dump()),
            cls="mb-6 space-y-4",
        )

        edit_form_card, review_section_card = _build_edit_review_form(
            processed_recipe, processed_recipe
        )

        edit_oob_div = Div(
            edit_form_card,
            hx_swap_oob="innerHTML:#edit-form-target",
        )

        review_oob_div = Div(
            review_section_card,
            hx_swap_oob="innerHTML:#review-section-target",
        )

        result = Group(rendered_recipe_html, edit_oob_div, review_oob_div)

    return result


@rt("/recipes/save")
async def post_save_recipe(request: Request):
    form_data: FormData = await request.form()
    try:
        parsed_data = _parse_recipe_form_data(form_data)
        recipe_obj = RecipeBase(**parsed_data)
    except ValidationError as e:
        logger.warning("Validation error saving recipe: %s", e, exc_info=False)
        return Span(
            "Invalid recipe data. Please check the fields.",
            cls=CSS_ERROR_CLASS,
            id="save-button-container",
        )
    except Exception as e:
        logger.error("Error parsing form data during save: %s", e, exc_info=True)
        return Span(
            "Error processing form data.",
            cls=CSS_ERROR_CLASS,
            id="save-button-container",
        )

    user_final_message = ""
    message_is_error = False
    headers = {}

    try:
        response = await internal_client.post(
            "/api/v0/recipes", json=recipe_obj.model_dump()
        )
        response.raise_for_status()
        logger.info("Saved recipe via API call from UI, Name: %s", recipe_obj.name)
        user_final_message = "Current Recipe Saved!"
        headers["HX-Trigger"] = "recipeListChanged"

    except httpx.HTTPStatusError as e:
        message_is_error = True
        logger.error(
            "API error saving recipe: Status %s, Response: %s",
            e.response.status_code,
            e.response.text,
            exc_info=True,
        )
        if e.response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
            user_final_message = "Could not save recipe: Invalid data for some fields."
        else:
            user_final_message = (
                "Could not save recipe. Please check input and try again."
            )
        try:
            detail = e.response.json().get("detail")
            if detail:
                logger.debug("API error detail: %s", detail)
        except Exception:
            logger.debug("Failed to parse API error detail: %s", e, exc_info=True)

    except httpx.RequestError as e:
        message_is_error = True
        logger.error("Network error saving recipe: %s", e, exc_info=True)
        user_final_message = (
            "Could not save recipe due to a network issue. Please try again."
        )

    except Exception as e:
        message_is_error = True
        logger.error("Unexpected error saving recipe via API: %s", e, exc_info=True)
        user_final_message = "An unexpected error occurred while saving the recipe."

    if message_is_error:
        return Span(
            user_final_message,
            cls=CSS_ERROR_CLASS,
            id="save-button-container",
        )
    else:
        user_final_message = "Current Recipe Saved!"
        css_class = CSS_SUCCESS_CLASS
        html_content = (
            f'<span id="save-button-container" class="{css_class}">{user_final_message}'
            "</span>"
        )
        return HTMLResponse(content=html_content, headers=headers)


class ModifyFormError(Exception):
    """Custom exception for errors during modification form parsing/validation."""

    pass


class RecipeModificationError(Exception):
    """Custom exception for errors during LLM recipe modification."""

    pass


@rt("/recipes/modify")
async def post_modify_recipe(request: Request):
    form_data = await request.form()
    modification_prompt = str(form_data.get("modification_prompt", ""))

    error_message_for_ui: FT | None = None
    current_data_for_form_render: dict
    original_recipe_for_form_render: RecipeBase

    try:
        (validated_current_recipe, validated_original_recipe, _) = (
            _parse_and_validate_modify_form(form_data)
        )

        current_data_for_form_render = validated_current_recipe.model_dump()
        original_recipe_for_form_render = validated_original_recipe

        if not modification_prompt:
            logger.info("Modification requested with empty prompt.")
            error_message_for_ui = Div(
                "Please enter modification instructions.", cls=f"{CSS_ERROR_CLASS} mt-2"
            )

        else:
            try:
                modified_recipe = await _request_recipe_modification(
                    validated_current_recipe, modification_prompt
                )
                edit_form_card, review_section_card = _build_edit_review_form(
                    current_recipe=modified_recipe,
                    original_recipe=validated_original_recipe,
                    modification_prompt_value=modification_prompt,
                    error_message_content=None,
                )
                oob_review = Div(
                    review_section_card, hx_swap_oob="innerHTML:#review-section-target"
                )
                return Div(
                    edit_form_card, oob_review, id="edit-form-target", cls="mt-6"
                )

            except RecipeModificationError as llm_e:
                logger.error("LLM modification error: %s", llm_e, exc_info=True)
                error_message_for_ui = Div(str(llm_e), cls=f"{CSS_ERROR_CLASS} mt-2")

    except ModifyFormError as form_e:
        logger.warning("Form validation/parsing error: %s", form_e, exc_info=False)
        error_message_for_ui = Div(str(form_e), cls=f"{CSS_ERROR_CLASS} mt-2")
        try:
            original_data_raw = _parse_recipe_form_data(form_data, prefix="original_")
            original_recipe_for_form_render = RecipeBase(**original_data_raw)
            current_data_for_form_render = original_data_raw
        except Exception as parse_orig_e:
            logger.error(
                "Critical: Could not parse original data during ModifyFormError "
                "handling: %s",
                parse_orig_e,
                exc_info=True,
            )
            critical_error_msg = Div(
                "Critical Error: Could not recover the recipe form state. Please "
                "refresh and try again.",
                cls=CSS_ERROR_CLASS,
                id="edit-form-target",
            )
            return critical_error_msg

    except Exception as e:
        logger.error(
            "Unexpected error in recipe modification flow: %s", e, exc_info=True
        )
        critical_error_msg = Div(
            "Critical Error: An unexpected error occurred. Please refresh and try "
            "again.",
            cls=CSS_ERROR_CLASS,
            id="edit-form-target",
        )
        return critical_error_msg

    try:
        current_recipe_for_render = RecipeBase(**current_data_for_form_render)
    except ValidationError:
        logger.error(
            "Data intended for form render failed validation: %s",
            current_data_for_form_render,
        )
        current_recipe_for_render = RecipeBase(
            name="[Validation Error]", ingredients=[], instructions=[]
        )

    edit_form_card, review_section_card = _build_edit_review_form(
        current_recipe=current_recipe_for_render,
        original_recipe=original_recipe_for_form_render,
        modification_prompt_value=modification_prompt,
        error_message_content=error_message_for_ui,
    )
    oob_review = Div(
        review_section_card, hx_swap_oob="innerHTML:#review-section-target"
    )
    return Div(edit_form_card, oob_review, id="edit-form-target", cls="mt-6")


def _parse_and_validate_modify_form(
    form_data: FormData,
) -> tuple[RecipeBase, RecipeBase, str]:
    """Parses and validates form data for the modify recipe request.

    Raises:
        ModifyFormError: If validation or parsing fails.
    """
    try:
        current_data = _parse_recipe_form_data(form_data)
        original_data = _parse_recipe_form_data(form_data, prefix="original_")
        modification_prompt = str(form_data.get("modification_prompt", ""))

        original_recipe = RecipeBase(**original_data)
        current_recipe = RecipeBase(**current_data)

        return current_recipe, original_recipe, modification_prompt

    except ValidationError as e:
        logger.warning("Validation error on modify form submit: %s", e, exc_info=False)
        user_message = "Invalid recipe data. Please check the fields."
        raise ModifyFormError(user_message) from e
    except Exception as e:
        logger.error("Error parsing modify form data: %s", e, exc_info=True)
        user_message = "Error processing modification request form."
        raise ModifyFormError(user_message) from e


async def _request_recipe_modification(
    current_recipe: RecipeBase, modification_prompt: str
) -> RecipeBase:
    """Requests recipe modification from LLM service and handles postprocessing."""
    logger.info(
        "Requesting recipe modification from llm_service. Current: %s, Prompt: %s",
        current_recipe.name,
        modification_prompt,
    )
    try:
        modified_recipe: RecipeBase = await llm_generate_modified_recipe(
            current_recipe=current_recipe, modification_request=modification_prompt
        )
        processed_recipe = postprocess_recipe(modified_recipe)
        logger.info(
            "Modification (via llm_service) and postprocessing successful. "
            "Recipe Name: %s",
            processed_recipe.name,
        )
        logger.debug("Modified Recipe Object: %r", processed_recipe)
        return processed_recipe
    except Exception as e:
        logger.error(
            "Error calling llm_generate_modified_recipe from "
            "_request_recipe_modification: %s",
            e,
            exc_info=True,
        )
        user_message = (
            "Recipe modification failed. "
            "An unexpected error occurred during service call."
        )
        raise RecipeModificationError(user_message) from e


@rt("/recipes/ui/delete-ingredient/{index:int}", methods=["POST"])
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


@rt("/recipes/ui/delete-instruction/{index:int}", methods=["POST"])
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


@rt("/recipes/ui/add-ingredient", methods=["POST"])
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


@rt("/recipes/ui/add-instruction", methods=["POST"])
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


@rt("/recipes/ui/update-diff", methods=["POST"])
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
    rendered_list_items: list[Tag],
    original_recipe: RecipeBase,
    current_recipe: RecipeBase,
) -> tuple[Div, Div]:
    """
    Builds a sortable list component and an OOB diff component.

    Args:
        list_id: The HTML ID for the list container (e.g., "ingredients-list").
        rendered_list_items: A list of fasthtml.Tag components representing the items.
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
    return list_component, oob_diff_component
