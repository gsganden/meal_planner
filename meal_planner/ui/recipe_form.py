from fasthtml.common import Button, Div, Input, P
from monsterui.all import ButtonT, Loading, TextArea, TextT


def create_extraction_form_parts() -> tuple[Div, Div, Div, Div, P, Div]:
    """Creates and returns the UI components for the recipe extraction form."""
    url_input_component = Div(
        Div(
            Input(
                id="input_url",
                name="input_url",
                type="url",
                placeholder="https://example.com/recipe",
                cls="flex-grow mr-2",
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
                Loading(id="fetch-indicator", cls="htmx-indicator ml-2"),
                cls="flex items-center",
            ),
            cls="flex items-end",
        ),
        cls="mb-4",
    )

    # Placeholder for URL fetch errors
    fetch_url_error_display_div = Div(id="fetch-url-error-display", cls="mt-2 mb-2")

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
            # Should this also include input_url if text is empty?
            hx_include="#recipe_text_container",
            hx_indicator="#extract-indicator",
            cls=ButtonT.primary,
        ),
        Loading(id="extract-indicator", cls="htmx-indicator ml-2"),
        cls="mt-4",
    )

    disclaimer = P(
        "Recipe extraction uses AI and may not be perfectly accurate. Always "
        "double-check the results.",
        cls=f"{TextT.muted} text-xs mt-1",
    )

    results_div = Div(id="recipe-results")

    return (
        url_input_component,
        fetch_url_error_display_div,
        text_area_container,
        extract_button_group,
        disclaimer,
        results_div,
    )
