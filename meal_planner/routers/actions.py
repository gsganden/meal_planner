"""Routers for actions that process data or perform operations, often via POST."""

import logging

import httpx
from fastapi import Request, Response
from fasthtml.common import *
from pydantic import ValidationError
from starlette import status
from starlette.datastructures import FormData

from meal_planner.core import (
    internal_api_client,
    rt,
)
from meal_planner.form_processing import parse_recipe_form_data
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
)

logger = logging.getLogger(__name__)


@rt("/recipes/save")
async def post_save_recipe(request: Request):
    """Handles saving a new recipe.

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
        parsed_data = parse_recipe_form_data(form_data)
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
            response = await internal_api_client.post(
                "/v0/recipes", json=recipe_obj.model_dump()
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
                try:
                    error_detail = e.response.json().get("detail", [])
                    for error in error_detail:
                        if (
                            isinstance(error, dict)
                            and error.get("loc") == ["body", "instructions"]
                            and error.get("type") == "too_short"
                        ):
                            result = Span(
                                "Please add at least one instruction to the recipe.",
                                cls=CSS_ERROR_CLASS,
                                id="save-button-container",
                            )
                            break
                    else:
                        result = Span(
                            "Could not save recipe: Invalid data for some fields.",
                            cls=CSS_ERROR_CLASS,
                            id="save-button-container",
                        )
                except Exception:
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
    """Handles recipe modification requests from the recipe editing UI.

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
    current_recipe_data = parse_recipe_form_data(form_data)
    original_recipe_data = parse_recipe_form_data(form_data, prefix="original_")

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
            modification_prompt_value=modification_prompt,
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
            current_recipe=current_recipe,
            original_recipe=original_recipe,
            modification_prompt_value=modification_prompt,
            error_message_content=Div(str(llm_e), cls=f"{CSS_ERROR_CLASS} mt-2"),
        )

    except ValidationError as ve:
        logger.error(
            (
                "Validation error after LLM modification and postprocessing. "
                "Prompt: '%s', Original Recipe Name: '%s', Error: %s"
            ),
            modification_prompt,
            original_recipe.name,
            ve,
            exc_info=True,
        )
        result = build_modify_form_response(
            current_recipe=current_recipe,
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
            current_recipe=current_recipe,
            original_recipe=original_recipe,
            modification_prompt_value=modification_prompt,
            error_message_content=Div(
                "Critical Error: An unexpected error occurred. "
                "Please refresh and try again.",
                cls=CSS_ERROR_CLASS,
            ),
        )
    return result


@rt("/recipes/extract/run")
async def post_extract_recipe_run(
    recipe_text: str | None = None,
):
    """Handles recipe extraction from text.

    This endpoint takes raw text, attempts to extract a recipe from it using an
    LLM service, and then populates the recipe editing form with the
    extracted data.

    Args:
        recipe_text: The raw text input by the user, expected to contain a recipe.

    Returns:
        A Group of Divs for OOB swaps updating '#edit-form-target',
        '#review-section-target', and clearing '#error-message-container'
        if successful.
        If `recipe_text` is missing, returns an error message Div for OOB swap to
        '#error-message-container'.
        If LLM extraction fails, returns an error message Div for OOB swap to
        '#error-message-container'.
        If extracted recipe has no instructions, returns an error message Div for OOB
        swap to '#error-message-container'.
    """
    if not recipe_text:
        logger.warning("Recipe extraction called with no text provided.")
        return Div(
            "No text content provided for extraction.",
            id="error-message-container",
            hx_swap_oob="innerHTML",
            cls=CSS_ERROR_CLASS,
        )

    try:
        extracted_recipe: RecipeBase = await generate_recipe_from_text(text=recipe_text)
        logger.info(
            "LLM successfully generated recipe from text. Name: %s",
            extracted_recipe.name,
        )

        if not extracted_recipe.instructions:
            logger.warning(
                "Recipe extracted from text is missing instructions. Recipe name: %s",
                extracted_recipe.name,
            )
            return Div(
                (
                    "Recipe extraction resulted in missing instructions. "
                    "Please refine your input or try a different recipe text."
                ),
                id="error-message-container",
                hx_swap_oob="innerHTML",
                cls=f"{CSS_ERROR_CLASS} mt-2",
            )

        original_recipe_for_form = extracted_recipe
        processed_recipe = postprocess_recipe(extracted_recipe)
        logger.info("Recipe postprocessing successful. Name: %s", processed_recipe.name)

        edit_form_card, review_section_card = build_edit_review_form(
            current_recipe=processed_recipe,
            original_recipe=original_recipe_for_form,
            error_message_content=None,
        )

        edit_oob_div = Div(
            edit_form_card,
            id="edit-form-target",
            hx_swap_oob="innerHTML",
        )
        review_oob_div = Div(
            review_section_card,
            id="review-section-target",
            hx_swap_oob="innerHTML",
        )
        clear_error_message_div = Div(
            id="error-message-container", hx_swap_oob="innerHTML"
        )

        return Group(edit_oob_div, review_oob_div, clear_error_message_div)

    except ValidationError as ve:
        logger.error(
            (
                "Validation error during recipe extraction or postprocessing: %s. "
                "Text: '%s'"
            ),
            ve,
            recipe_text[:100],
            exc_info=True,
        )
        return Div(
            "Recipe data is invalid after extraction. Please check the input text.",
            id="error-message-container",
            hx_swap_oob="innerHTML",
            cls=CSS_ERROR_CLASS,
        )
    except Exception as e:
        logger.error(
            "LLM service failed to generate recipe from text: %s. Text: '%s'",
            e,
            recipe_text[:100],
            exc_info=True,
        )
        if not isinstance(e, (RuntimeError, FileNotFoundError)):
            logger.error(
                "Error during recipe extraction processing: %s", e, exc_info=True
            )
        return Div(
            "Recipe extraction failed. Please try again or check the input text.",
            id="error-message-container",
            hx_swap_oob="innerHTML",
            cls=CSS_ERROR_CLASS,
        )


@rt("/recipes/delete")
async def post_delete_recipe(id: int):
    """Handles recipe deletion requests, typically initiated from the UI.

    This endpoint attempts to delete a recipe by its ID using an internal API call.
    On successful deletion, it returns an empty response with an HX-Trigger header
    to signal a change in the recipe list for UI updates.

    Args:
        id: The integer ID of the recipe to be deleted.

    Returns:
        A FastAPI `Response` object.
        - On success: HTTP 200 with `HX-Trigger: recipeListChanged` header.
        - On failure (recipe not found): HTTP 404.
        - On other API or unexpected errors: HTTP 500.
    """
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
