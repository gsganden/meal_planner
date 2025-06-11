"""Main application FastAPI instance, router setup, and entry point for Meal Planner."""

import logging

from fasthtml.common import *
from monsterui.all import *
from starlette.staticfiles import StaticFiles

from meal_planner.core import (
    STATIC_DIR,
    api_app,
    app,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/api", api_app)

# Need to import routers here to register them with the app
# Import order matters: ui_fragments must come before pages to avoid route conflicts
from meal_planner.routers import actions  # noqa: E402,F401,I001
from meal_planner.routers import ui_fragments  # noqa: E402,F401,I001
from meal_planner.routers import pages  # noqa: E402,F401,I001
