"""Tests for the _parse_recipe_form_data() utility function from meal_planner.main."""

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
            "source": None,
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
            "source": None,
            "ingredients": ["Orig Ing 1"],
            "instructions": ["Orig Step 1"],
        }
        RecipeBase(**parsed_data)

    def test_parse_missing_fields(self):
        form_data = FormData([("name", "Only Name")])
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Only Name",
            "source": None,
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
            "source": None,
            "ingredients": ["Real Ing"],
            "instructions": ["Real Step"],
        }
        RecipeBase(**parsed_data)

    def test_parse_empty_form(self):
        form_data = FormData([])
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "",
            "source": None,
            "ingredients": [],
            "instructions": [],
        }
        with pytest.raises(ValidationError):
            RecipeBase(**parsed_data)

    def test_parse_with_source_url(self):
        form_data = FormData(
            [
                ("name", "Test Recipe"),
                ("source", "https://example.com/recipe"),
                ("ingredients", "Ing 1"),
                ("instructions", "Step 1"),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Test Recipe",
            "source": "https://example.com/recipe",
            "ingredients": ["Ing 1"],
            "instructions": ["Step 1"],
        }
        RecipeBase(**parsed_data)

    def test_parse_with_empty_source(self):
        form_data = FormData(
            [
                ("name", "Test Recipe"),
                ("source", ""),
                ("ingredients", "Ing 1"),
                ("instructions", "Step 1"),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Test Recipe",
            "source": None,
            "ingredients": ["Ing 1"],
            "instructions": ["Step 1"],
        }
        RecipeBase(**parsed_data)

    def test_parse_with_whitespace_source(self):
        form_data = FormData(
            [
                ("name", "Test Recipe"),
                ("source", "   "),
                ("ingredients", "Ing 1"),
                ("instructions", "Step 1"),
            ]
        )
        parsed_data = parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Test Recipe",
            "source": None,
            "ingredients": ["Ing 1"],
            "instructions": ["Step 1"],
        }
        RecipeBase(**parsed_data)
