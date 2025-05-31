"""Core application components for Meal Planner.

This module initializes the main FastHTML and FastAPI applications,
configures HTTP clients for internal communication, and sets up the
base application structure with theming and live reload capabilities.

Attributes:
    app: Main FastHTML application instance with live reload and theming.
    rt: Route decorator for FastHTML endpoints.
    api_app: FastAPI instance for RESTful API endpoints.
    internal_client: HTTP client for internal FastHTML routes.
    internal_api_client: HTTP client for internal API routes.
    STATIC_DIR: Path to static assets directory.
"""

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
