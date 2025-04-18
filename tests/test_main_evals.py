"""
LLM evals for main.py, rather than traditional unit tests.
"""

from pathlib import Path

import pytest

from meal_planner.main import Recipe, call_llm

recipes = {
    "data/classic-deviled-eggs-recipe-1911032.html": Recipe(
        name="Classic Deviled Eggs"
    ),
}


@pytest.mark.anyio
@pytest.mark.parametrize("path, expected_name", recipes.items())
async def test_call_llm_returns_recipe(path, expected_name, anyio_backend):
    text = (Path(__file__).resolve().parent / path).read_text()
    recipe = await call_llm(
        f"Extract the recipe from the following HTML content: {text}", Recipe
    )
    assert recipe.name == expected_name.name
