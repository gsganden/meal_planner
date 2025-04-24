"""
LLM evals for main.py, rather than traditional unit tests.
"""

import time
from pathlib import Path

import pytest

from meal_planner.main import Recipe, call_llm

recipes = {
    Path("data/classic-deviled-eggs-recipe-1911032.html"): {
        "expected_names": ["Classic Deviled Eggs"]
    },
    Path("data/good-old-fashioned-pancakes.html"): {
        "expected_names": [
            "Good Old Fashioned Pancakes",
            "Good Old-Fashioned Pancakes",
            "Old-Fashioned Pancakes",
        ]
    },
    Path("data/skillet-chicken-parmesan-with-gnocchi.html"): {
        "expected_names": ["Skillet Chicken Parmesan with Gnocchi"]
    },
    Path("data/gochujang-sloppy-joes.html"): {
        "expected_names": ["Gochujang Sloppy Joes"]
    },
    Path("data/mushroom-pasta-creamy.html"): {
        "expected_names": [
            "Pasta ai Funghi",
            "Pasta ai Funghi (Creamy Pasta With Mushrooms)",
            "Creamy Pasta With Mushrooms",
        ]
    },
    Path("data/easy-bok-choy-recipe_.html"): {"expected_names": ["Easy Bok Choy"]},
    Path("data/sunshine-sauce-recipe-23706247.html"): {
        "expected_names": ["Sunshine Sauce"]
    },
    Path("data/quick-healthy-dinner-20-minute-honey-garlic-shrimp_.html"): {
        "expected_names": ["20 Minute Honey Garlic Shrimp", "Honey Garlic Shrimp"]
    },
    Path("data/prawn-salmon-burgers-spicy-mayo.html"): {
        "expected_names": ["Prawn & Salmon Burgers with Spicy Mayo"]
    },
    Path("data/easy-homemade-falafel-recipe_.html"): {
        "expected_names": ["Easy Homemade Falafel", "Homemade Falafel"]
    },
}


@pytest.mark.slow
@pytest.mark.anyio
@pytest.mark.parametrize("path, expected_data", recipes.items())
async def test_call_llm_returns_recipe(path: Path, expected_data: dict, anyio_backend):
    print(f"Testing {path}")
    text = (Path(__file__).resolve().parent / path).read_text()
    actual_recipe = await call_llm(
        f"Extract the recipe from the following HTML content: {text}", Recipe
    )

    actual_name = actual_recipe.name.strip().lower()
    expected_names = [name.strip().lower() for name in expected_data["expected_names"]]
    assert actual_name in expected_names, (
        f"Extracted recipe name '{actual_name}' not found in expected names {expected_names}. "
        f"Expected one of: {expected_names}, Got: '{actual_name}'"
    )
    time.sleep(8)
