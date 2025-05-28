"""Core application components for Meal Planner."""

import logging
from pathlib import Path

import httpx
from fastapi import FastAPI
from fasthtml.common import FastHTMLWithLiveReload
from httpx import ASGITransport
from monsterui.all import Theme

from meal_planner.api.recipes import API_ROUTER as RECIPES_API_ROUTER

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastHTMLWithLiveReload(hdrs=(Theme.blue.headers()))
rt = app.route

api_app = FastAPI()
api_app.include_router(RECIPES_API_ROUTER)

internal_client = httpx.AsyncClient(
    transport=ASGITransport(app=app),
    base_url="http://internal",  # arbitrary
)

internal_api_client = httpx.AsyncClient(
    transport=ASGITransport(app=api_app),
    base_url="http://internal-api",  # arbitrary
)
