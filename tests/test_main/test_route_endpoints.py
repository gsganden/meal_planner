"""Tests for route handlers defined in meal_planner.main."""

import pytest

from tests.constants import (
    RECIPES_FETCH_TEXT_URL,
)


@pytest.mark.anyio
class TestFetchTextEndpoint:
    FETCH_TEXT_URL = RECIPES_FETCH_TEXT_URL
