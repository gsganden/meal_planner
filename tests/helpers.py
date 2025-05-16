"""Helper functions for tests."""

from unittest.mock import AsyncMock, MagicMock
from httpx import Response


def _build_ui_fragment_form_data(
    name="Test Recipe",
    ingredients=None,
    instructions=None,
    original_name=None,
    original_ingredients=None,
    original_instructions=None,
) -> dict:
    ingredients = ingredients if ingredients is not None else ["ing1"]
    instructions = instructions if instructions is not None else ["step1"]
    original_name = original_name if original_name is not None else name
    original_ingredients = (
        original_ingredients if original_ingredients is not None else ingredients
    )
    original_instructions = (
        original_instructions if original_instructions is not None else instructions
    )

    return {
        "name": name,
        "ingredients": ingredients,
        "instructions": instructions,
        "original_name": original_name,
        "original_ingredients": original_ingredients,
        "original_instructions": original_instructions,
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
