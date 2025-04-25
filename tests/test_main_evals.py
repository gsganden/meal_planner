"""
LLM evals for main.py, rather than traditional unit tests.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from meal_planner.main import Recipe, extract_recipe_from_url

recipes = {
    # Path("data/classic-deviled-eggs-recipe-1911032.html"): {
    #     "expected_names": ["Classic Deviled Eggs"],
    #     "expected_ingredients": [
    #         "6 eggs",
    #         "1/4 cup mayonnaise",
    #         "1 teaspoon white vinegar",
    #         "1 teaspoon yellow mustard",
    #         "1/8 teaspoon salt",
    #         "Freshly ground black pepper",
    #         "Smoked Spanish paprika, for garnish",
    #     ],
    # },
    # Path("data/good-old-fashioned-pancakes.html"): {
    #     "expected_names": [
    #         "Good Old Fashioned Pancakes",
    #         "Good Old-Fashioned Pancakes",
    #         "Old-Fashioned Pancakes",
    #     ],
    #     "expected_ingredients": [
    #         "1 ½ cups all-purpose flour",
    #         "3 ½ teaspoons baking powder",
    #         "1 tablespoon white sugar",
    #         "¼ teaspoon salt, or more to taste",
    #         "1 ¼ cups milk",
    #         "3 tablespoons butter, melted",
    #         "1 large egg",
    #     ],
    # },
    Path("data/skillet-chicken-parmesan-with-gnocchi.html"): {
        "expected_names": ["Skillet Chicken Parmesan With Gnocchi"]
    },
    Path("data/gochujang-sloppy-joes.html"): {
        "expected_names": ["Gochujang Sloppy Joes"],
        "expected_ingredients": [
            "1 Tbsp. vegetable oil",
            "1 lb. ground beef (ideally 20% fat)",
            "1½ tsp. Diamond Crystal or ¾ tsp. Morton kosher salt, divided, plus more",
            "Freshly ground pepper",
            "1 medium green bell pepper, ribs and seeds removed, chopped",
            "1 medium onion, chopped",
            "6–8 garlic cloves, finely grated",
            "3 Tbsp. gochujang",
            "2 Tbsp. ketchup",
            "1 Tbsp. soy sauce",
            "1 Tbsp. Worcestershire sauce",
            "1 Tbsp. dark brown sugar",
            "1 tsp. yellow mustard",
            "1 15-oz. can tomato sauce",
            "1 Tbsp. balsamic vinegar",
            "4 potato rolls",
            "Kosher dill spears and potato chips (for serving; optional)",
        ],
    },
    # Path("data/mushroom-pasta-creamy.html"): {
    #     "expected_names": [
    #         "Pasta Ai Funghi",
    #         "Pasta Ai Funghi (Creamy Pasta With Mushrooms)",
    #         "Creamy Pasta With Mushrooms",
    #     ]
    # },
    # Path("data/easy-bok-choy-recipe_.html"): {
    #     "expected_names": ["Easy Bok Choy", "Bok Choy"],
    #     "expected_ingredients": [
    #         "3 Tbsp. vegetable oil, divided",
    #         "1 lb. baby bok choy, quartered lengthwise, washed, dried",
    #         "2 garlic cloves, finely chopped",
    #         '1 (1") piece ginger, peeled, finely chopped',
    #         "1 tsp. kosher salt, divided",
    #         "1 Tbsp. reduced-sodium soy sauce",
    #         "1/2 tsp. toasted sesame oil",
    #     ],
    # },
    # Path("data/sunshine-sauce-recipe-23706247.html"): {
    #     "expected_names": ["Sunshine Sauce"]
    # },
    # Path("data/quick-healthy-dinner-20-minute-honey-garlic-shrimp_.html"): {
    #     "expected_names": ["20 Minute Honey Garlic Shrimp", "Honey Garlic Shrimp"]
    # },
    # Path("data/prawn-salmon-burgers-spicy-mayo.html"): {
    #     "expected_names": ["Prawn & Salmon Burgers With Spicy Mayo"]
    # },
    # Path("data/easy-homemade-falafel-recipe_.html"): {
    #     "expected_names": ["Easy Homemade Falafel", "Homemade Falafel"],
    #     "expected_ingredients": [
    #         "1 cup dried chickpeas",
    #         "1/2 small white onion, coarsely chopped",
    #         "4 garlic cloves, coarsely chopped",
    #         "1/4 cup fresh cilantro, coarsely chopped",
    #         "1/4 cup fresh parsley, coarsely chopped",
    #         "1 1/2 tsp. kosher salt",
    #         "1 tsp. baking powder",
    #         "1 tsp. ground coriander",
    #         "1 tsp. ground cumin",
    #         "1/4 cup all-purpose flour",
    #         "Vegetable oil, for frying (6 to 8 cups)",
    #         "Tahini sauce, for serving",
    #     ],
    # },
}


@pytest.fixture(params=recipes.keys(), ids=[str(p.name) for p in recipes])
@patch("meal_planner.main.fetch_page_text")
async def extracted_recipe_fixture(mock_fetch, request, anyio_backend):
    """Fixture to extract recipe data for a given path."""
    path: Path = request.param
    raw_text = (Path(__file__).resolve().parent / path).read_text()
    mock_fetch.return_value = raw_text

    extracted_recipe = await extract_recipe_from_url("http://dummy-url.com")
    return extracted_recipe, path


@pytest.mark.slow
@pytest.mark.anyio
def test_extract_recipe_name(extracted_recipe_fixture, anyio_backend):
    """Tests the extracted recipe name against expected values."""
    extracted_recipe: Recipe
    path: Path
    extracted_recipe, path = extracted_recipe_fixture

    expected_names_list = recipes[path]["expected_names"]
    actual_name = extracted_recipe.name

    assert actual_name in expected_names_list


@pytest.mark.slow
@pytest.mark.anyio
def test_extract_recipe_ingredients(extracted_recipe_fixture, anyio_backend):
    """Tests the extracted recipe ingredients against expected values."""
    extracted_recipe: Recipe
    path: Path
    extracted_recipe, path = extracted_recipe_fixture

    expected = sorted([i.lower() for i in recipes[path]["expected_ingredients"]])
    actual = sorted([i.lower() for i in extracted_recipe.ingredients])

    assert actual == expected
