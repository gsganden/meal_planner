import logging

from meal_planner.main import rt
from meal_planner.ui.layout import with_layout

logger = logging.getLogger(__name__)


@rt("/")
def get():
    """Get the home page."""
    return with_layout("Meal Planner")
