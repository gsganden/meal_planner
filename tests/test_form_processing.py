"""Tests for the _parse_recipe_form_data() utility function from meal_planner.main."""

import pytest
from pydantic import ValidationError
from starlette.datastructures import FormData

from meal_planner.form_processing import (
    extract_recipe_id,
    generate_copy_name,
    parse_recipe_form_data,
)
from meal_planner.models import RecipeBase


class TestParseRecipeFormData:
    def test_parse_basic(self):
        form_data = FormData(
            [
                ("name", "Test Recipe"),
                ("ingredients", "Ing 1"),
                ("ingredients", "Ing 2"),
                ("instructions", "Step 1"),
                ("instructions", "Step 2"),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Test Recipe",
            "ingredients": ["Ing 1", "Ing 2"],
            "instructions": ["Step 1", "Step 2"],
        }
        RecipeBase(**parsed_data)

    def test_parse_with_prefix(self):
        form_data = FormData(
            [
                ("original_name", "Original Name"),
                ("original_ingredients", "Orig Ing 1"),
                ("original_instructions", "Orig Step 1"),
                ("name", "Current Name"),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data, prefix="original_")
        assert parsed_data == {
            "name": "Original Name",
            "ingredients": ["Orig Ing 1"],
            "instructions": ["Orig Step 1"],
        }
        RecipeBase(**parsed_data)

    def test_parse_missing_fields(self):
        form_data = FormData([("name", "Only Name")])
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Only Name",
            "ingredients": [],
            "instructions": [],
        }

    def test_parse_empty_strings_and_whitespace(self):
        form_data = FormData(
            [
                ("name", "  Spaced Name  "),
                ("ingredients", "Real Ing"),
                ("ingredients", "  "),
                ("ingredients", ""),
                ("instructions", "Real Step"),
                ("instructions", "  "),
                ("instructions", ""),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "  Spaced Name  ",
            "ingredients": ["Real Ing"],
            "instructions": ["Real Step"],
        }
        RecipeBase(**parsed_data)

    def test_parse_empty_form(self):
        form_data = FormData([])
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {"name": "", "ingredients": [], "instructions": []}
        with pytest.raises(ValidationError):
            RecipeBase(**parsed_data)


class TestExtractRecipeId:
    def test_extract_valid_recipe_id(self):
        form_data = FormData([("recipe_id", "123")])
        result = extract_recipe_id(form_data)
        assert result == 123

    def test_extract_recipe_id_missing(self):
        form_data = FormData([("name", "Test Recipe")])
        result = extract_recipe_id(form_data)
        assert result is None

    def test_extract_recipe_id_empty_string(self):
        form_data = FormData([("recipe_id", "")])
        result = extract_recipe_id(form_data)
        assert result is None

    def test_extract_recipe_id_invalid_number(self):
        form_data = FormData([("recipe_id", "not_a_number")])
        result = extract_recipe_id(form_data)
        assert result is None

    def test_extract_recipe_id_non_string(self):
        # This tests the edge case where the value isn't a string
        form_data = FormData([])
        form_data._list.append(("recipe_id", 123))  # Non-string value
        result = extract_recipe_id(form_data)
        assert result is None


class TestGenerateCopyName:
    def test_generate_copy_name_basic(self):
        result = generate_copy_name("Pasta Recipe")
        assert result == "Pasta Recipe (Copy)"

    def test_generate_copy_name_with_existing_copy(self):
        result = generate_copy_name("Pasta Recipe (Copy)")
        assert result == "Pasta Recipe (Copy 2)"

    def test_generate_copy_name_with_numbered_copy(self):
        result = generate_copy_name("Pasta Recipe (Copy 3)")
        assert result == "Pasta Recipe (Copy 4)"

    def test_generate_copy_name_with_copy_2(self):
        result = generate_copy_name("Pasta Recipe (Copy 2)")
        assert result == "Pasta Recipe (Copy 3)"

    def test_generate_copy_name_edge_case_partial_match(self):
        # Test a name that contains "(Copy)" but not at the end
        result = generate_copy_name("Recipe (Copy) with more text")
        assert result == "Recipe (Copy) with more text (Copy)"

    def test_generate_copy_name_invalid_pattern(self):
        # Test malformed copy pattern - should fallback to adding (Copy)
        result = generate_copy_name("Recipe (Copy abc)")
        assert result == "Recipe (Copy abc) (Copy)"
