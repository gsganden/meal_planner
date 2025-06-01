"""Recipe extraction form components for the Meal Planner application.

This module provides UI components for the recipe extraction workflow,
including URL input, text input, and form submission handling with
proper validation and user feedback.
"""

from fasthtml.common import *
from monsterui.all import *

from meal_planner.ui.common import create_loading_indicator


def create_extraction_form() -> Card:
    """Create the main recipe extraction form interface.

    Builds a comprehensive form allowing users to either:
    1. Enter a URL to fetch recipe content automatically
    2. Paste recipe text directly into a textarea

    The form includes loading indicators, error message placeholders,
    and HTMX attributes for dynamic content updates without page refresh.

    Returns:
        Card component containing the complete extraction form with all
        necessary inputs, buttons, and placeholder elements for dynamic
        content injection.
    """
    url_input_component = Div(
        Div(
            Input(
                id="input_url",
                name="input_url",
                type="url",
                placeholder="https://example.com/recipe",
                cls="uk-input flex-grow mr-2",
            ),
            Div(
                Button(
                    "Fetch Text from URL",
                    hx_post="/recipes/fetch-text",
                    hx_target="#recipe_text_container",
                    hx_swap="outerHTML",
                    hx_include="[name='input_url']",
                    hx_indicator="#fetch-indicator",
                    cls=ButtonT.primary,
                ),
                create_loading_indicator("fetch-indicator"),
                cls="flex items-center",
            ),
            cls="flex items-end",
        ),
        cls="mb-4",
    )

    fetch_url_error_display_div = Div(
        id="fetch-url-error-display",
        cls="mt-2 mb-2",
    )

    text_area_container = Div(
        TextArea(
            id="recipe_text",
            name="recipe_text",
            placeholder="Paste full recipe text here, or fetch from URL above.",
            rows=15,
            cls="mb-4",
        ),
        id="recipe_text_container",
    )

    extract_button_group = Div(
        Button(
            "Extract Recipe",
            hx_post="/recipes/extract/run",
            hx_target="#recipe-results",
            hx_swap="innerHTML",
            hx_include="#recipe_text_container",
            hx_indicator="#extract-indicator",
            cls=ButtonT.primary,
        ),
        create_loading_indicator("extract-indicator"),
        cls="mt-4",
    )

    disclaimer = P(
        "Recipe extraction uses AI and may not be perfectly accurate. Always "
        "double-check the results.",
        cls=f"{TextT.muted}",
    )

    results_div = Div(id="recipe-results")

    return Card(
        H2("Extract Recipe"),
        H3("URL"),
        url_input_component,
        fetch_url_error_display_div,
        H3("Text"),
        text_area_container,
        extract_button_group,
        disclaimer,
        results_div,
    )
