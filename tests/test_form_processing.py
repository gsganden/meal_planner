"""Tests for the _parse_recipe_form_data() utility function from meal_planner.main."""

import pytest
from pydantic import ValidationError
from starlette.datastructures import FormData

from meal_planner.form_processing import (
    normalize_servings_values,
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
            "servings_min": None,
            "servings_max": None,
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
            "servings_min": None,
            "servings_max": None,
        }
        RecipeBase(**parsed_data)

    def test_parse_missing_fields(self):
        form_data = FormData([("name", "Only Name")])
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Only Name",
            "ingredients": [],
            "instructions": [],
            "servings_min": None,
            "servings_max": None,
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
            "servings_min": None,
            "servings_max": None,
        }
        RecipeBase(**parsed_data)

    def test_parse_empty_form(self):
        form_data = FormData([])
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "",
            "ingredients": [],
            "instructions": [],
            "servings_min": None,
            "servings_max": None,
        }
        with pytest.raises(ValidationError):
            RecipeBase(**parsed_data)

    def test_parse_servings_both_fields(self):
        form_data = FormData(
            [
                ("name", "Test Recipe"),
                ("ingredients", "Ing 1"),
                ("instructions", "Step 1"),
                ("servings_min", "4"),
                ("servings_max", "6"),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Test Recipe",
            "ingredients": ["Ing 1"],
            "instructions": ["Step 1"],
            "servings_min": 4,
            "servings_max": 6,
        }
        RecipeBase(**parsed_data)

    def test_parse_servings_min_only(self):
        form_data = FormData(
            [
                ("name", "Test Recipe"),
                ("ingredients", "Ing 1"),
                ("instructions", "Step 1"),
                ("servings_min", "4"),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Test Recipe",
            "ingredients": ["Ing 1"],
            "instructions": ["Step 1"],
            "servings_min": 4,
            "servings_max": None,  # Should stay None, not auto-populated
        }
        RecipeBase(**parsed_data)

    def test_parse_servings_max_only(self):
        form_data = FormData(
            [
                ("name", "Test Recipe"),
                ("ingredients", "Ing 1"),
                ("instructions", "Step 1"),
                ("servings_max", "6"),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Test Recipe",
            "ingredients": ["Ing 1"],
            "instructions": ["Step 1"],
            "servings_min": None,  # Should stay None, not auto-populated
            "servings_max": 6,
        }
        RecipeBase(**parsed_data)

    def test_parse_servings_invalid_values(self):
        form_data = FormData(
            [
                ("name", "Test Recipe"),
                ("ingredients", "Ing 1"),
                ("instructions", "Step 1"),
                ("servings_min", "invalid"),
                ("servings_max", "also_invalid"),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Test Recipe",
            "ingredients": ["Ing 1"],
            "instructions": ["Step 1"],
            "servings_min": None,
            "servings_max": None,
        }
        RecipeBase(**parsed_data)

    def test_parse_servings_empty_strings(self):
        form_data = FormData(
            [
                ("name", "Test Recipe"),
                ("ingredients", "Ing 1"),
                ("instructions", "Step 1"),
                ("servings_min", ""),
                ("servings_max", "  "),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Test Recipe",
            "ingredients": ["Ing 1"],
            "instructions": ["Step 1"],
            "servings_min": None,
            "servings_max": None,
        }
        RecipeBase(**parsed_data)


class TestNormalizeServingsValues:
    def test_both_values_provided(self):
        result = normalize_servings_values(4, 6)
        assert result == (4, 6)

    def test_only_min_provided(self):
        result = normalize_servings_values(4, None)
        assert result == (4, None)  # No auto-population

    def test_only_max_provided(self):
        result = normalize_servings_values(None, 6)
        assert result == (None, 6)  # No auto-population

    def test_both_none(self):
        result = normalize_servings_values(None, None)
        assert result == (None, None)

    def test_same_values(self):
        result = normalize_servings_values(4, 4)
        assert result == (4, 4)
