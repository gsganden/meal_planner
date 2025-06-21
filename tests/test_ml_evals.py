"""
LLM evals for main.py, rather than traditional unit tests.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from meal_planner.models import RecipeBase
from meal_planner.services.call_llm import generate_recipe_from_text
from meal_planner.services.extract_webpage_text import clean_html_text
from meal_planner.services.process_recipe import postprocess_recipe

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


@pytest.fixture(autouse=True)
async def ensure_real_llm_clients():
    """Ensure that this test module uses real LLM clients, not mocks from other
    tests."""
    # Stop any existing patches on instructor and AsyncOpenAI that might leak from
    # other test files
    import meal_planner.services.call_llm

    # Clear any cached client to force re-initialization with real modules
    meal_planner.services.call_llm._aclient = None
    meal_planner.services.call_llm._openai_client = None

    # Use patch.stopall() to ensure no patches from other tests are active
    patch.stopall()

    yield

    # Clean up after test - properly close async clients
    if meal_planner.services.call_llm._openai_client is not None:
        await meal_planner.services.call_llm._openai_client.close()
    meal_planner.services.call_llm._aclient = None
    meal_planner.services.call_llm._openai_client = None


@pytest.fixture(
    params=recipes_data.keys(),
    ids=[str(p.relative_to(Path(__file__).parent.parent)) for p in recipes_data],
    scope="function",
)
async def extracted_recipe_fixture(request, anyio_backend, ensure_real_llm_clients):
    """Fixture to extract recipe data for a given path."""
    html_file_path: Path = request.param

    expected_data = recipes_data[html_file_path]
    page_content = clean_html_text(html_file_path.read_text())

    llm_extracted_recipe = await generate_recipe_from_text(text=page_content)
    extracted_recipe = postprocess_recipe(llm_extracted_recipe)

    return extracted_recipe, expected_data


@pytest.mark.slow
@pytest.mark.anyio
async def test_extract_recipe(extracted_recipe_fixture):
    """Tests the extracted recipe name, ingredients, instructions, and makes.

    Note: We combine all checks (name, ingredients, instructions, makes) into a single
    test to enable efficient retry behavior. With function-scoped fixtures, each test
    function gets its own fixture execution. By having 1 test per HTML file instead of
    multiple separate tests, we maintain 1 LLM call per HTML file while allowing
    pytest-rerunfailures to properly re-execute the fixture on retry.
    """
    extracted_recipe: RecipeBase
    expected_data: dict
    extracted_recipe, expected_data = extracted_recipe_fixture

    # Test recipe name
    expected_names_list = expected_data["expected_names"]
    actual_name = extracted_recipe.name
    assert actual_name in expected_names_list, (
        f"Recipe name '{actual_name}' not in expected names {expected_names_list}"
    )

    # Test recipe ingredients
    expected_ingredients = sorted(
        [i.lower() for i in expected_data["expected_ingredients"]]
    )
    actual_ingredients = sorted([i.lower() for i in extracted_recipe.ingredients])
    assert actual_ingredients == expected_ingredients, (
        f"Ingredients don't match.\n"
        f"Expected: {expected_ingredients}\n"
        f"Actual: {actual_ingredients}"
    )

    # Test recipe instructions
    expected_instructions = expected_data["expected_instructions"]
    actual_instructions = extracted_recipe.instructions
    assert actual_instructions == expected_instructions, (
        f"Instructions don't match.\n"
        f"Expected: {expected_instructions}\n"
        f"Actual: {actual_instructions}"
    )

    # Test recipe makes
    expected_makes_min = expected_data.get("expected_makes_min")
    expected_makes_max = expected_data.get("expected_makes_max")
    actual_makes_min = extracted_recipe.makes_min
    actual_makes_max = extracted_recipe.makes_max
    assert actual_makes_min == expected_makes_min, (
        f"Makes min don't match.\n"
        f"Expected: {expected_makes_min}\n"
        f"Actual: {actual_makes_min}"
    )
    assert actual_makes_max == expected_makes_max, (
        f"Makes max don't match.\n"
        f"Expected: {expected_makes_max}\n"
        f"Actual: {actual_makes_max}"
    )

    # Test recipe makes unit
    expected_makes_units = expected_data.get("expected_makes_units")
    actual_makes_unit = extracted_recipe.makes_unit
    if expected_makes_units is None:
        assert actual_makes_unit is None, (
            f"Makes unit should be None.\nExpected: None\nActual: {actual_makes_unit}"
        )
    else:
        assert actual_makes_unit in expected_makes_units, (
            f"Makes unit not in expected units.\n"
            f"Expected one of: {expected_makes_units}\n"
            f"Actual: {actual_makes_unit}"
        )
