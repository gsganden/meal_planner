"""
LLM evals for main.py, rather than traditional unit tests.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from meal_planner.main import extract_recipe_from_url

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
        "expected_names": ["Skillet Chicken Parmesan With Gnocchi"]
    },
    Path("data/gochujang-sloppy-joes.html"): {
        "expected_names": ["Gochujang Sloppy Joes"]
    },
    Path("data/mushroom-pasta-creamy.html"): {
        "expected_names": [
            "Pasta Ai Funghi",
            "Pasta Ai Funghi (Creamy Pasta With Mushrooms)",
            "Creamy Pasta With Mushrooms",
        ]
    },
    Path("data/easy-bok-choy-recipe_.html"): {
        "expected_names": ["Easy Bok Choy", "Bok Choy"]
    },
    Path("data/sunshine-sauce-recipe-23706247.html"): {
        "expected_names": ["Sunshine Sauce"]
    },
    Path("data/quick-healthy-dinner-20-minute-honey-garlic-shrimp_.html"): {
        "expected_names": ["20 Minute Honey Garlic Shrimp", "Honey Garlic Shrimp"]
    },
    Path("data/prawn-salmon-burgers-spicy-mayo.html"): {
        "expected_names": ["Prawn & Salmon Burgers With Spicy Mayo"]
    },
    Path("data/easy-homemade-falafel-recipe_.html"): {
        "expected_names": ["Easy Homemade Falafel", "Homemade Falafel"]
    },
}


@pytest.mark.slow
@pytest.mark.anyio
@pytest.mark.parametrize("path, expected_data", recipes.items())
@patch("meal_planner.main.fetch_page_text")
async def test_extract_recipe_from_url_helper(
    mock_fetch, path: Path, expected_data: dict, anyio_backend
):
    """Tests the extract_recipe_from_url helper function directly."""
    raw_text = (Path(__file__).resolve().parent / path).read_text()
    mock_fetch.return_value = raw_text

    actual_recipe = await extract_recipe_from_url("http://dummy-url.com")

    actual_name = actual_recipe.name

    expected_names_list = expected_data["expected_names"]

    assert actual_name in expected_names_list, (
        f"Extracted recipe name '{actual_name}' from helper not found in processed "
        f"expected names {expected_names_list}. "
    )
