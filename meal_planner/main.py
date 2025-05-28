import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, Response
from fasthtml.common import *
from httpx import ASGITransport
from monsterui.all import *
from starlette.staticfiles import StaticFiles

from meal_planner.api.recipes import API_ROUTER as RECIPES_API_ROUTER
from meal_planner.models import RecipeBase
from meal_planner.services.call_llm import (
    generate_recipe_from_text,
)

# from meal_planner.services.extract_webpage_text import (
#     fetch_and_clean_text_from_url,
# )
from meal_planner.services.process_recipe import postprocess_recipe
from meal_planner.ui.common import (
    CSS_ERROR_CLASS,
)
from meal_planner.ui.edit_recipe import (
    build_edit_review_form,
    build_recipe_display,
)

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


from meal_planner.routers import (  # noqa: E402
    actions,  # noqa: F401
    pages,  # noqa: F401
    ui_fragments,  # noqa: F401
)


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
