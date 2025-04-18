"""
LLM evals for main.py, rather than traditional unit tests.
"""

import time
from pathlib import Path

import pytest
from thefuzz import fuzz

from meal_planner.main import Recipe, call_llm

recipes = {
    "data/classic-deviled-eggs-recipe-1911032.html": Recipe(
        name="Classic Deviled Eggs"
    ),
    "data/good-old-fashioned-pancakes.html": Recipe(name="Good Old Fashioned Pancakes"),
    "data/skillet-chicken-parmesan-with-gnocchi.html": Recipe(
        name="Skillet Chicken Parmesan with Gnocchi"
    ),
    "data/gochujang-sloppy-joes.html": Recipe(name="Gochujang Sloppy Joes"),
    "data/mushroom-pasta-creamy.html": Recipe(
        name="Pasta ai Funghi (Creamy Pasta With Mushrooms)"
    ),
    "data/easy-bok-choy-recipe_.html": Recipe(name="Easy Bok Choy"),
    "data/sunshine-sauce-recipe-23706247.html": Recipe(name="Sunshine Sauce"),
    "data/quick-healthy-dinner-20-minute-honey-garlic-shrimp_.html": Recipe(
        name="20 Minute Honey Garlic Shrimp"
    ),
    "data/prawn-salmon-burgers-spicy-mayo.html": Recipe(
        name="Prawn & Salmon Burgers with Spicy Mayo"
    ),
    "data/easy-homemade-falafel-recipe_.html": Recipe(name="Easy Homemade Falafel"),
}


@pytest.mark.slow
@pytest.mark.anyio
@pytest.mark.parametrize("path, expected_recipe", recipes.items())
async def test_call_llm_returns_recipe(path, expected_recipe, anyio_backend):
    print(f"Testing {path}")
    text = (Path(__file__).resolve().parent / path).read_text()
    actual_recipe = await call_llm(
        f"Extract the recipe from the following HTML content: {text}", Recipe
    )

    score = fuzz.token_sort_ratio(
        actual_recipe.name.strip().lower(), expected_recipe.name.strip().lower()
    )

    similarity_threshold = 90
    assert score >= similarity_threshold, (
        f"Recipe name similarity score {score} below threshold {similarity_threshold}. "
        f"Expected: '{expected_recipe.name}', Got: '{actual_recipe.name}'"
    )
    time.sleep(8)
