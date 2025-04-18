"""
LLM evals for main.py, rather than traditional unit tests.
"""

import pytest

from meal_planner.main import Recipe, call_llm


@pytest.mark.anyio
async def test_call_llm_returns_recipe(anyio_backend):
    recipe = await call_llm(
        "Extract the recipe from the following HTML content: <html><body>Recipe Content</body></html>",
        Recipe,
    )
    assert recipe.title == "Recipe Content"
