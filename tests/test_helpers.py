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


class FormTargetDivNotFoundError(Exception):
    """Custom exception raised when the target div for form parsing is not found."""

    pass


def _get_edit_form_target_div(html_text: str) -> Tag:
    """Parses HTML and finds the specific div target for form edits.

    Raises:
        FormTargetDivNotFoundError: If the target div is not found.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    found_element = soup.find("div", attrs={"id": "edit-form-target"})
    if not found_element:
        found_element = soup.find(
            "div", attrs={"hx-swap-oob": "innerHTML:#edit-form-target"}
        )

    if isinstance(found_element, Tag):
        return found_element
    raise FormTargetDivNotFoundError(
        "Could not find div with id 'edit-form-target' or "
        "hx-swap-oob='innerHTML:#edit-form-target'"
    )


def _extract_form_value(html_text: str, name: str) -> str | None:
    """Extracts a single value from an input or textarea in the HTML form section.

    Can propagate FormTargetDivNotFoundError if the main form container is missing.
    Returns None if the specific field is not found within the container.
    """
    form_div = _get_edit_form_target_div(html_text)

    input_tag_candidate = form_div.find("input", attrs={"name": name})
    if isinstance(input_tag_candidate, Tag) and input_tag_candidate.has_attr("value"):
        value = input_tag_candidate["value"]
        if isinstance(value, str):
            return value
        elif isinstance(value, list) and value and isinstance(value[0], str):
            return value[0]

    textarea_tag_candidate = form_div.find("textarea", attrs={"name": name})
    if isinstance(textarea_tag_candidate, Tag):
        return (
            str(textarea_tag_candidate.string)
            if textarea_tag_candidate.string is not None
            else ""
        )

    return None


def _extract_form_list_values(html_text: str, name: str) -> list[str]:
    """Extracts all values from inputs/textareas with the same name.

    Can propagate FormTargetDivNotFoundError if the main form container is missing.
    Returns an empty list if no specific fields are found within the container.
    """
    form_div = _get_edit_form_target_div(html_text)

    values: list[str] = []
    elements = form_div.find_all(
        lambda tag: isinstance(tag, Tag)
        and tag.name in ["input", "textarea"]
        and tag.get("name") == name
    )

    for element in elements:
        if isinstance(element, Tag):
            if element.name == "input" and element.has_attr("value"):
                value_attr = element["value"]
                if isinstance(value_attr, str):
                    values.append(value_attr)
                elif (
                    isinstance(value_attr, list)
                    and value_attr
                    and isinstance(value_attr[0], str)
                ):
                    values.append(value_attr[0])
            elif element.name == "textarea":
                values.append(str(element.string) if element.string is not None else "")

    return values


def _extract_full_edit_form_data(html_content: str) -> dict[str, Any]:
    """
    Extracts all current and original recipe data from the edit-review-form.
    This includes visible inputs/textareas and hidden original_* fields.
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
        raise ValueError(
            "Form with id 'edit-review-form' not found or is not a Tag "
            "in HTML content provided to _extract_full_edit_form_data."
        )

    data: dict[str, Any] = {}

    name_input = form.find("input", attrs={"name": FIELD_NAME})
    if name_input and isinstance(name_input, Tag) and "value" in name_input.attrs:
        name_value = name_input["value"]
        data[FIELD_NAME] = name_value[0] if isinstance(name_value, list) else name_value
    else:
        data[FIELD_NAME] = ""

    ingredients_inputs = form.find_all("input", attrs={"name": FIELD_INGREDIENTS})
    data[FIELD_INGREDIENTS] = [
        cast(str, ing_input["value"])
        for ing_input in ingredients_inputs
        if isinstance(ing_input, Tag) and "value" in ing_input.attrs
    ]

    instructions_areas = form.find_all("textarea", attrs={"name": FIELD_INSTRUCTIONS})
    data[FIELD_INSTRUCTIONS] = [
        inst_area.get_text(strip=True)
        for inst_area in instructions_areas
        if isinstance(inst_area, Tag)
    ]

    original_name_input = form.find("input", attrs={"name": FIELD_ORIGINAL_NAME})
    if (
        original_name_input
        and isinstance(original_name_input, Tag)
        and "value" in original_name_input.attrs
    ):
        og_name_value = original_name_input["value"]
        data[FIELD_ORIGINAL_NAME] = (
            og_name_value[0] if isinstance(og_name_value, list) else og_name_value
        )
    else:
        data[FIELD_ORIGINAL_NAME] = ""

    original_ingredients_inputs = form.find_all(
        "input", attrs={"name": FIELD_ORIGINAL_INGREDIENTS}
    )
    data[FIELD_ORIGINAL_INGREDIENTS] = [
        cast(str, orig_ing_input["value"])
        for orig_ing_input in original_ingredients_inputs
        if isinstance(orig_ing_input, Tag) and "value" in orig_ing_input.attrs
    ]

    original_instructions_inputs = form.find_all(
        "input", attrs={"name": FIELD_ORIGINAL_INSTRUCTIONS}
    )
    data[FIELD_ORIGINAL_INSTRUCTIONS] = [
        cast(str, orig_inst_input["value"])
        for orig_inst_input in original_instructions_inputs
        if isinstance(orig_inst_input, Tag) and "value" in orig_inst_input.attrs
    ]

    prompt_input = form.find("input", attrs={"name": FIELD_MODIFICATION_PROMPT})
    if prompt_input and isinstance(prompt_input, Tag) and "value" in prompt_input.attrs:
        prompt_value = prompt_input["value"]
        data[FIELD_MODIFICATION_PROMPT] = (
            prompt_value[0] if isinstance(prompt_value, list) else prompt_value
        )
    else:
        data[FIELD_MODIFICATION_PROMPT] = ""

    return data


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
