import logging

from fasthtml.common import *

from meal_planner.main import rt
from meal_planner.ui.extract_recipe import create_extraction_form
from meal_planner.ui.layout import with_layout

logger = logging.getLogger(__name__)


@rt("/")
def get():
    """Get the home page."""
    return with_layout("Meal Planner")


@rt("/recipes/extract")
def get_recipe_extraction_page():
    return with_layout(
        "Create Recipe",
        Div(
            Div(create_extraction_form()),
            Div(id="edit-form-target"),
            Div(id="review-section-target"),
            cls="space-y-4",
        ),
    )
