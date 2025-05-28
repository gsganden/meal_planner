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
from meal_planner.ui.common import CSS_ERROR_CLASS, CSS_SUCCESS_CLASS

logger = logging.getLogger(__name__)


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
            result = FtResponse(  # type: ignore
                Span(user_final_message, id="save-button-container", cls=css_class),
                headers={"HX-Trigger": "recipeListChanged"},
            )

    return result
