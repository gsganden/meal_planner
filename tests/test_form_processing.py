"""Tests for form processing utilities."""

import pytest
from pydantic import ValidationError
from starlette.datastructures import FormData

from meal_planner.form_processing import parse_recipe_form_data
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
            "makes_min": None,
            "makes_max": None,
            "makes_unit": None,
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
            "makes_min": None,
            "makes_max": None,
            "makes_unit": None,
        }
        RecipeBase(**parsed_data)

    def test_parse_missing_fields(self):
        form_data = FormData([("name", "Only Name")])
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Only Name",
            "ingredients": [],
            "instructions": [],
            "makes_min": None,
            "makes_max": None,
            "makes_unit": None,
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
            "makes_min": None,
            "makes_max": None,
            "makes_unit": None,
        }
        RecipeBase(**parsed_data)

    def test_parse_empty_form(self):
        form_data = FormData([])
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "",
            "ingredients": [],
            "instructions": [],
            "makes_min": None,
            "makes_max": None,
            "makes_unit": None,
        }
        with pytest.raises(ValidationError):
            RecipeBase(**parsed_data)

    def test_parse_makes_both_fields(self):
        form_data = FormData(
            [
                ("name", "Test Recipe"),
                ("ingredients", "Ing 1"),
                ("instructions", "Step 1"),
                ("makes_min", "4"),
                ("makes_max", "6"),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Test Recipe",
            "ingredients": ["Ing 1"],
            "instructions": ["Step 1"],
            "makes_min": 4,
            "makes_max": 6,
            "makes_unit": None,
        }
        RecipeBase(**parsed_data)

    def test_parse_makes_min_only(self):
        form_data = FormData(
            [
                ("name", "Test Recipe"),
                ("ingredients", "Ing 1"),
                ("instructions", "Step 1"),
                ("makes_min", "4"),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Test Recipe",
            "ingredients": ["Ing 1"],
            "instructions": ["Step 1"],
            "makes_min": 4,
            "makes_max": None,  # Should stay None, not auto-populated
            "makes_unit": None,
        }
        RecipeBase(**parsed_data)

    def test_parse_makes_max_only(self):
        form_data = FormData(
            [
                ("name", "Test Recipe"),
                ("ingredients", "Ing 1"),
                ("instructions", "Step 1"),
                ("makes_max", "6"),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Test Recipe",
            "ingredients": ["Ing 1"],
            "instructions": ["Step 1"],
            "makes_min": None,  # Should stay None, not auto-populated
            "makes_max": 6,
            "makes_unit": None,
        }
        RecipeBase(**parsed_data)

    def test_parse_makes_invalid_values(self):
        form_data = FormData(
            [
                ("name", "Test Recipe"),
                ("ingredients", "Ing 1"),
                ("instructions", "Step 1"),
                ("makes_min", "invalid"),
                ("makes_max", "also_invalid"),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Test Recipe",
            "ingredients": ["Ing 1"],
            "instructions": ["Step 1"],
            "makes_min": None,
            "makes_max": None,
            "makes_unit": None,
        }
        RecipeBase(**parsed_data)

    def test_parse_makes_empty_strings(self):
        form_data = FormData(
            [
                ("name", "Test Recipe"),
                ("ingredients", "Ing 1"),
                ("instructions", "Step 1"),
                ("makes_min", ""),
                ("makes_max", "  "),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Test Recipe",
            "ingredients": ["Ing 1"],
            "instructions": ["Step 1"],
            "makes_min": None,
            "makes_max": None,
            "makes_unit": None,
        }
        RecipeBase(**parsed_data)

    def test_parse_makes_with_unit(self):
        form_data = FormData(
            [
                ("name", "Test Recipe"),
                ("ingredients", "Ing 1"),
                ("instructions", "Step 1"),
                ("makes_min", "4"),
                ("makes_max", "6"),
                ("makes_unit", "servings"),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Test Recipe",
            "ingredients": ["Ing 1"],
            "instructions": ["Step 1"],
            "makes_min": 4,
            "makes_max": 6,
            "makes_unit": "servings",
        }
        RecipeBase(**parsed_data)

    def test_parse_makes_unit_only(self):
        form_data = FormData(
            [
                ("name", "Test Recipe"),
                ("ingredients", "Ing 1"),
                ("instructions", "Step 1"),
                ("makes_unit", "portions"),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Test Recipe",
            "ingredients": ["Ing 1"],
            "instructions": ["Step 1"],
            "makes_min": None,
            "makes_max": None,
            "makes_unit": "portions",
        }
        RecipeBase(**parsed_data)

    def test_parse_makes_unit_empty_string(self):
        form_data = FormData(
            [
                ("name", "Test Recipe"),
                ("ingredients", "Ing 1"),
                ("instructions", "Step 1"),
                ("makes_unit", "  "),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Test Recipe",
            "ingredients": ["Ing 1"],
            "instructions": ["Step 1"],
            "makes_min": None,
            "makes_max": None,
            "makes_unit": None,
        }
        RecipeBase(**parsed_data)
