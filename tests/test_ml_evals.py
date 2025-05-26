"""
LLM evals for main.py, rather than traditional unit tests.
"""

import json
from pathlib import Path

import pytest

from meal_planner.main import extract_recipe_from_text
from meal_planner.models import RecipeBase
from meal_planner.services.extract_webpage_text import clean_html_text

TEST_DATA_DIR = Path(__file__).parent / "data/recipes/processed"


def load_all_test_data(data_dir: Path) -> dict:
    all_data = {}
    for json_file in data_dir.glob("*.json"):
        with open(json_file, "r") as f:
            data = json.load(f)
            html_file_path = (json_file.parent / data["html_file"]).resolve()
            all_data[html_file_path] = data
    return all_data


recipes_data = load_all_test_data(TEST_DATA_DIR)


@pytest.fixture(
    params=recipes_data.keys(),
    ids=[str(p.relative_to(Path(__file__).parent.parent)) for p in recipes_data],
    scope="module",
)
async def extracted_recipe_fixture(request, anyio_backend):
    """Fixture to extract recipe data for a given path."""
    html_file_path: Path = request.param

    expected_data = recipes_data[html_file_path]
    extracted_recipe = await extract_recipe_from_text(
        clean_html_text(html_file_path.read_text())
    )
    return extracted_recipe, expected_data


@pytest.mark.slow
@pytest.mark.anyio
async def test_extract_recipe_name(extracted_recipe_fixture):
    """Tests the extracted recipe name against expected values."""
    extracted_recipe: RecipeBase
    expected_data: dict
    extracted_recipe, expected_data = extracted_recipe_fixture

    expected_names_list = expected_data["expected_names"]
    actual_name = extracted_recipe.name

    assert actual_name in expected_names_list


@pytest.mark.slow
@pytest.mark.anyio
def test_extract_recipe_ingredients(extracted_recipe_fixture):
    """Tests the extracted recipe ingredients against expected values."""
    extracted_recipe: RecipeBase
    expected_data: dict
    extracted_recipe, expected_data = extracted_recipe_fixture

    expected = sorted([i.lower() for i in expected_data["expected_ingredients"]])
    actual = sorted([i.lower() for i in extracted_recipe.ingredients])
    assert actual == expected


@pytest.mark.slow
@pytest.mark.anyio
def test_extract_recipe_instructions(extracted_recipe_fixture):
    """Tests the extracted recipe instructions against expected values."""
    extracted_recipe: RecipeBase
    expected_data: dict
    extracted_recipe, expected_data = extracted_recipe_fixture

    expected_instructions = expected_data["expected_instructions"]
    actual_instructions = extracted_recipe.instructions
    assert actual_instructions == expected_instructions
