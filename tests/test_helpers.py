"""Test utilities and helper functions for the meal planner test suite."""

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

from bs4 import BeautifulSoup
from bs4.element import Tag
from httpx import Response

from tests.constants import (
    FIELD_INGREDIENTS,
    FIELD_INSTRUCTIONS,
    FIELD_MODIFICATION_PROMPT,
    FIELD_NAME,
    FIELD_ORIGINAL_INGREDIENTS,
    FIELD_ORIGINAL_INSTRUCTIONS,
    FIELD_ORIGINAL_NAME,
)


def _find_form_container_and_form(html_content: str) -> Tag:
    """
    Finds and returns the form element from the HTML content.

    Looks for the form in the edit-form-target div or OOB div, falling back to
    searching the entire document if needed.

    Returns:
        The form Tag element.

    Raises:
        ValueError: If the form is not found or is not a Tag.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    form_container = soup.find("div", id="edit-form-target")
    if not form_container:
        form_container = soup.find(
            "div", attrs={"hx-swap-oob": "innerHTML:#edit-form-target"}
        )

    if not form_container:
        form_container = soup

    form = form_container.find("form", attrs={"id": "edit-review-form"})

    if not isinstance(form, Tag):
        raise ValueError("Form with id 'edit-review-form' not found or is not a Tag.")

    return form


def _extract_single_input_value(form: Tag, field_name: str) -> str:
    """
    Extracts a single value from an input field in the form.

    Args:
        form: The form Tag element to search in.
        field_name: The name attribute of the input field.

    Returns:
        The input value as a string, or empty string if not found.
    """
    input_element = form.find("input", attrs={"name": field_name})
    if (
        input_element
        and isinstance(input_element, Tag)
        and "value" in input_element.attrs
    ):
        value = input_element["value"]
        return value[0] if isinstance(value, list) else str(value)
    return ""


def _extract_input_list_values(form: Tag, field_name: str) -> list[str]:
    """
    Extracts all values from input fields with the same name.

    Args:
        form: The form Tag element to search in.
        field_name: The name attribute of the input fields.

    Returns:
        List of input values as strings.
    """
    inputs = form.find_all("input", attrs={"name": field_name})
    return [
        cast(str, input_elem["value"])
        for input_elem in inputs
        if isinstance(input_elem, Tag) and "value" in input_elem.attrs
    ]


def _extract_textarea_list_values(form: Tag, field_name: str) -> list[str]:
    """
    Extracts all text content from textarea fields with the same name.

    Args:
        form: The form Tag element to search in.
        field_name: The name attribute of the textarea fields.

    Returns:
        List of textarea text content as strings.
    """
    textareas = form.find_all("textarea", attrs={"name": field_name})
    return [
        textarea.get_text(strip=True)
        for textarea in textareas
        if isinstance(textarea, Tag)
    ]


def extract_full_edit_form_data(html_content: str) -> dict[str, Any]:
    """
    Extracts all current and original recipe data from the edit-review-form.
    This includes visible inputs/textareas and hidden original_* fields.
    """
    form = _find_form_container_and_form(html_content)

    return {
        FIELD_NAME: _extract_single_input_value(form, FIELD_NAME),
        FIELD_INGREDIENTS: _extract_input_list_values(form, FIELD_INGREDIENTS),
        FIELD_INSTRUCTIONS: _extract_textarea_list_values(form, FIELD_INSTRUCTIONS),
        FIELD_ORIGINAL_NAME: _extract_single_input_value(form, FIELD_ORIGINAL_NAME),
        FIELD_ORIGINAL_INGREDIENTS: _extract_input_list_values(
            form, FIELD_ORIGINAL_INGREDIENTS
        ),
        FIELD_ORIGINAL_INSTRUCTIONS: _extract_input_list_values(
            form, FIELD_ORIGINAL_INSTRUCTIONS
        ),
        FIELD_MODIFICATION_PROMPT: _extract_single_input_value(
            form, FIELD_MODIFICATION_PROMPT
        ),
    }


def extract_current_recipe_data_from_html(html_content: str) -> dict[str, Any]:
    """
    Extracts only the current recipe data (name, ingredients, instructions)
    from the edit-review-form, excluding original_* fields.
    """
    form = _find_form_container_and_form(html_content)

    return {
        "name": _extract_single_input_value(form, FIELD_NAME),
        "ingredients": _extract_input_list_values(form, FIELD_INGREDIENTS),
        "instructions": _extract_textarea_list_values(form, FIELD_INSTRUCTIONS),
    }


def create_mock_api_response(
    status_code: int,
    json_data: list | dict | None = None,
    error_to_raise: Exception | None = None,
) -> AsyncMock:
    mock_resp = AsyncMock(spec=Response)
    mock_resp.status_code = status_code
    if json_data is not None:
        mock_resp.json = MagicMock(return_value=json_data)
    else:
        mock_resp.json = MagicMock(return_value={})

    if error_to_raise:
        mock_resp.raise_for_status = MagicMock(side_effect=error_to_raise)
    else:
        mock_resp.raise_for_status = MagicMock()
    return mock_resp
