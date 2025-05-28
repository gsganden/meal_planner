import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, Response
from fasthtml.common import *
from httpx import ASGITransport
from monsterui.all import *
from starlette.staticfiles import StaticFiles

from meal_planner.api.recipes import API_ROUTER as RECIPES_API_ROUTER

# from meal_planner.services.extract_webpage_text import (
#     fetch_and_clean_text_from_url,
# )

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
