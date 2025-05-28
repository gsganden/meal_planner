"""Main application FastAPI instance, router setup, and entry point for Meal Planner."""

import logging
from pathlib import Path

import httpx
from fastapi import FastAPI
from fasthtml.common import *
from httpx import ASGITransport
from monsterui.all import *
from starlette.staticfiles import StaticFiles

from meal_planner.api.recipes import API_ROUTER as RECIPES_API_ROUTER

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
