import logging

import httpx  # Added based on post_save_recipe
from fastapi import Request
from fasthtml.common import *  # type: ignore
from pydantic import ValidationError
from starlette import status
from starlette.datastructures import FormData

from meal_planner.form_processing import _parse_recipe_form_data
from meal_planner.main import internal_client, rt  # Assuming internal_client is needed
from meal_planner.models import RecipeBase
from meal_planner.services.call_llm import (
    generate_modified_recipe,
    generate_recipe_from_text,
)
from meal_planner.services.process_recipe import postprocess_recipe
from meal_planner.ui.common import CSS_ERROR_CLASS, CSS_SUCCESS_CLASS
from meal_planner.ui.edit_recipe import (
    build_edit_review_form,
    build_modify_form_response,
    build_recipe_display,
)

logger = logging.getLogger(__name__)


@rt("/recipes/save")
async def post_save_recipe(request: Request):
    """
    Handles saving a new recipe submitted from the recipe editing UI.

    Parses recipe data from the form, validates it, and attempts to save it
    by making a POST request to the internal `/api/v0/recipes` endpoint.

    Args:
        request: The FastAPI request object, containing the form data for
                 'name', 'ingredients', and 'instructions'.

    Returns:
        An `FtResponse` containing a `Span` with a success message and an
        `HX-Trigger: recipeListChanged` header on successful save.
        Otherwise, returns a `Span` with an appropriate error message.
        All responses are targeted to the `save-button-container` an an
        `innerHTML` swap.
    """
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
            result = FtResponse(  # type: ignore
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


@rt("/recipes/extract/run")
async def post_extract_recipe_run(
    recipe_text: str | None = None,
):  # Renamed from 'post' to avoid conflict
    """
    Handles the extraction of a recipe from raw text input.

    This route is typically called via HTMX from the recipe extraction page.
    It takes raw text, attempts to extract a structured recipe from it using
    an LLM service (via the `extract_recipe_from_text` helper), and then
    returns HTML components to display the extracted recipe and populate
    an edit/review form.

    Args:
        recipe_text: The raw text string from which to extract a recipe.
                     Passed as a query parameter by FastHTML from form data.

    Returns:
        A `Group` of `Div` components containing the rendered extracted recipe
        for reference, and OOB-swapped `Div`s for the recipe edit form and
        review section.
        Returns a single `Div` with an error message if no text is provided
        or if extraction fails.
    """
    if not recipe_text:
        logger.error("Recipe extraction called without text.")
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
