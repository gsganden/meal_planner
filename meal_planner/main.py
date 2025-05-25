import logging
from pathlib import Path

import httpx
from bs4.element import Tag
from fastapi import FastAPI, Request, Response
from fasthtml.common import *
from httpx import ASGITransport
from monsterui.all import *
from pydantic import ValidationError
from starlette import status
from starlette.datastructures import FormData
from starlette.staticfiles import StaticFiles

from meal_planner.api.recipes import API_ROUTER as RECIPES_API_ROUTER
from meal_planner.models import RecipeBase
from meal_planner.services.call_llm import (
    generate_modified_recipe,
    generate_recipe_from_text,
)
from meal_planner.services.extract_webpage_text import (
    fetch_and_clean_text_from_url,
)
from meal_planner.services.process_recipe import postprocess_recipe
from meal_planner.ui.common import (
    CSS_ERROR_CLASS,
    CSS_SUCCESS_CLASS,
)
from meal_planner.ui.edit_recipe import (
    build_diff_content_children,
    build_edit_review_form,
    build_modify_form_response,
    build_recipe_display,
    render_ingredient_list_items,
    render_instruction_list_items,
)
from meal_planner.ui.extract_recipe import create_extraction_form
from meal_planner.ui.layout import is_htmx, with_layout
from meal_planner.ui.list_recipes import format_recipe_list

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
        with_layout(Titled(title, content_with_attrs))
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

    return with_layout(Titled(title, content))


async def extract_recipe_from_text(page_text: str) -> RecipeBase:
    """Extracts a recipe from the given text and postprocesses it."""
    logger.info("Attempting to extract recipe from provided text.")
    try:
        extracted_recipe: RecipeBase = await generate_recipe_from_text(text=page_text)
    except Exception as e:
        logger.error(
            f"LLM service failed to generate recipe from text: {e!r}", exc_info=True
        )
        raise

    result = postprocess_recipe(extracted_recipe)
    logger.info(
        "Extraction (via call_llm) and postprocessing successful. Recipe Name: %s",
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

        edit_form_card, review_section_card = build_edit_review_form(
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
        result = Span(
            "Invalid recipe data. Please check the fields.",
            cls=CSS_ERROR_CLASS,
            id="save-button-container",
        )
    except Exception as e:
        logger.error("Error parsing form data during save: %s", e, exc_info=True)
        result = Span(
            "Error processing form data.",
            cls=CSS_ERROR_CLASS,
            id="save-button-container",
        )
    else:
        try:
            response = await internal_client.post(
                "/api/v0/recipes", json=recipe_obj.model_dump()
            )
            response.raise_for_status()
            logger.info("Saved recipe via API call from UI, Name: %s", recipe_obj.name)
        except httpx.HTTPStatusError as e:
            logger.error(
                "API error saving recipe: Status %s, Response: %s",
                e.response.status_code,
                e.response.text,
                exc_info=True,
            )
            if e.response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
                result = Span(
                    "Could not save recipe: Invalid data for some fields.",
                    cls=CSS_ERROR_CLASS,
                    id="save-button-container",
                )
            else:
                result = Span(
                    "Could not save recipe. Please check input and try again.",
                    cls=CSS_ERROR_CLASS,
                    id="save-button-container",
                )
        except httpx.RequestError as e:
            logger.error("Network error saving recipe: %s", e, exc_info=True)
            result = Span(
                "Could not save recipe due to a network issue. Please try again.",
                cls=CSS_ERROR_CLASS,
                id="save-button-container",
            )

        except Exception as e:
            logger.error("Unexpected error saving recipe via API: %s", e, exc_info=True)
            result = Span(
                "An unexpected error occurred while saving the recipe.",
                cls=CSS_ERROR_CLASS,
                id="save-button-container",
            )
        else:
            user_final_message = "Current Recipe Saved!"
            css_class = CSS_SUCCESS_CLASS
            result = FtResponse(
                Span(user_final_message, id="save-button-container", cls=css_class),
                headers={"HX-Trigger": "recipeListChanged"},
            )

    return result


@rt("/recipes/modify")
async def post_modify_recipe(request: Request):
    """
    Handles recipe modification requests from the recipe editing UI.

    This endpoint processes form data containing a current recipe, an original
    recipe (for diffing and reference), and an optional user-provided modification
    prompt. It orchestrates recipe data parsing, calls an LLM service for
    modifications if requested, and then re-renders the entire recipe edit form UI
    with any relevant messages.

    Expected form fields:
    - Current recipe: 'name', 'ingredients' (list), 'instructions' (list).
    - Original recipe (for diff): 'original_name', 'original_ingredients' (list),
      'original_instructions' (list).
    - AI modification: 'modification_prompt' (string, optional).

    Workflow and Error Handling:

    All responses from this endpoint will be HTTP 200 OK and will contain
    the full recipe modification form, updated as necessary.

    1.  **Initial Form Data Parsing and Validation:**
        -   The endpoint first parses all submitted recipe data.
        -   If essential data for the current or original recipe is missing or
            structurally invalid (e.g., fails Pydantic `RecipeBase` validation),
            the form is re-rendered with the error message "Invalid recipe data.
            Please check the fields." The submitted form data is used to
            repopulate the fields as much as possible.

    2.  **Modification Prompt Handling:**
        -   If no 'modification_prompt' is provided by the user (after successful
            initial parsing), the form is re-rendered with the error message
            "Please enter modification instructions." The current recipe data
            remains in the form.
        -   If a 'modification_prompt' is provided:
            -   The LLM service is called to generate a modified recipe.
            -   **On Successful LLM Modification:**
                -   The form is re-rendered, showing the new `modified_recipe`
                  as current, with no error message.
            -   **On LLM Service or Postprocessing Error (`RuntimeError`):**
                -   The error is logged.
                -   The form is re-rendered with the specific error message from
                    `RuntimeError`. The recipe data from *before* the
                    LLM call is used to populate the form.

    3.  **Other Unexpected Internal Errors (Generic `Exception`):**
        -   If any other unexpected `Exception` occurs:
            -   The error is logged with full details.
            -   The form is re-rendered with a generic "Critical Error..."
                message. The recipe data from before the failed operation is used.

    Args:
        request: The FastAPI request object, containing the form data.

    Returns:
        A `Group` of components representing the full recipe modification form.
    """
    form_data: FormData = await request.form()
    modification_prompt = str(form_data.get("modification_prompt", ""))
    current_recipe_data = _parse_recipe_form_data(form_data)
    original_recipe_data = _parse_recipe_form_data(form_data, prefix="original_")

    try:
        current_recipe = RecipeBase(**current_recipe_data)
        original_recipe = RecipeBase(**original_recipe_data)
    except ValidationError as ve:
        logger.error("Initial validation error in modify recipe: %s", ve)
        return build_modify_form_response(
            current_recipe=RecipeBase.model_construct(**current_recipe_data),
            original_recipe=RecipeBase.model_construct(**original_recipe_data),
            modification_prompt_value=modification_prompt,
            error_message_content=Div(
                "Invalid recipe data. Please check the fields.",
                cls=f"{CSS_ERROR_CLASS} mt-2",
            ),
        )

    if not modification_prompt:
        logger.debug("Empty modification prompt detected")
        return build_modify_form_response(
            current_recipe=current_recipe,
            original_recipe=original_recipe,
            modification_prompt_value=modification_prompt,  # Preserve entered prompt
            error_message_content=Div(
                "Please enter modification instructions.", cls=f"{CSS_ERROR_CLASS} mt-2"
            ),
        )

    try:
        modified_recipe: RecipeBase = await generate_modified_recipe(
            current_recipe=current_recipe, modification_request=modification_prompt
        )
        processed_recipe = postprocess_recipe(modified_recipe)
        logger.info("LLM modification successful. Building success response.")
        result = build_modify_form_response(
            current_recipe=processed_recipe,
            original_recipe=original_recipe,
            modification_prompt_value=modification_prompt,
            error_message_content=None,
        )

    except FileNotFoundError as fnf_e:
        logger.error("Configuration error - prompt file missing: %s", fnf_e)
        result = build_modify_form_response(
            current_recipe=current_recipe,
            original_recipe=original_recipe,
            modification_prompt_value=modification_prompt,
            error_message_content=Div(
                "Service configuration error. Please try again later.",
                cls=f"{CSS_ERROR_CLASS} mt-2",
            ),
        )

    except RuntimeError as llm_e:
        logger.error("LLM modification error: %s", llm_e)
        result = build_modify_form_response(
            current_recipe=current_recipe,  # Revert to recipe before LLM attempt
            original_recipe=original_recipe,
            modification_prompt_value=modification_prompt,
            error_message_content=Div(str(llm_e), cls=f"{CSS_ERROR_CLASS} mt-2"),
        )

    except ValidationError as ve:
        logger.error("Validation error post-LLM or unexpected: %s", ve)
        result = build_modify_form_response(
            current_recipe=current_recipe,  # Revert to recipe before this error
            original_recipe=original_recipe,
            modification_prompt_value=modification_prompt,
            error_message_content=Div(
                "Invalid recipe data after modification attempt.",
                cls=f"{CSS_ERROR_CLASS} mt-2",
            ),
        )
    except Exception as e:
        logger.error(
            "Unexpected error in recipe modification flow: %s", e, exc_info=True
        )
        result = build_modify_form_response(
            current_recipe=current_recipe,  # Revert to recipe before this error
            original_recipe=original_recipe,
            modification_prompt_value=modification_prompt,
            error_message_content=Div(
                "Critical Error: An unexpected error occurred. "
                "Please refresh and try again.",
                cls=CSS_ERROR_CLASS,
            ),
        )
    return result


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
    rendered_list_items: list[Tag],
    original_recipe: RecipeBase,
    current_recipe: RecipeBase,
) -> FT:
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
    return Group(list_component, oob_diff_component)


@rt("/recipes/delete")
async def post_delete_recipe(id: int):
    """Delete a recipe via POST request."""
    try:
        response = await internal_api_client.delete(f"/v0/recipes/{id}")
        response.raise_for_status()
        logger.info("Successfully deleted recipe ID %s", id)
        return Response(headers={"HX-Trigger": "recipeListChanged"})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning("Recipe ID %s not found for deletion", id)
            return Response(status_code=404)
        else:
            logger.error(
                "API error deleting recipe ID %s: Status %s, Response: %s",
                id,
                e.response.status_code,
                e.response.text,
                exc_info=True,
            )
            return Response(status_code=500)
    except Exception as e:
        logger.error("Error deleting recipe ID %s: %s", id, e, exc_info=True)
        return Response(status_code=500)
