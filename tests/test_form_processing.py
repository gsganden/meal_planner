"""Tests for the _parse_recipe_form_data() utility function from meal_planner.main."""

import pytest
from pydantic import ValidationError
from starlette.datastructures import FormData

from meal_planner.form_processing import parse_recipe_form_data, process_recipe_form
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


class TestProcessRecipeForm:
    def test_process_basic_strings(self):
        form_dict = {
            "name": "String Test Recipe",
            "ingredients": "Ingredient A, Ingredient B ,  Ingredient C",
            "instructions": "Step 1\nStep 2\n  Step 3  ",
        }
        recipe = process_recipe_form(form_dict)
        assert recipe.name == "String Test Recipe"
        assert recipe.ingredients == ["Ingredient A", "Ingredient B", "Ingredient C"]
        assert recipe.instructions == ["Step 1", "Step 2", "Step 3"]

    def test_process_empty_fields(self):
        form_dict = {"name": "Empty Fields", "ingredients": "", "instructions": ""}
        with pytest.raises(ValueError) as excinfo:
            process_recipe_form(form_dict)
        assert "Ingredients list cannot be empty after processing." in str(
            excinfo.value
        )

    def test_process_only_whitespace_fields(self):
        form_dict = {
            "name": "Whitespace Fields",
            "ingredients": " ,,  ",
            "instructions": " \n \n  ",
        }
        with pytest.raises(ValueError) as excinfo:
            process_recipe_form(form_dict)
        assert "Ingredients list cannot be empty after processing." in str(
            excinfo.value
        )

    def test_process_instructions_can_be_empty(self):
        form_dict = {
            "name": "Test Recipe Instructions Empty",
            "ingredients": "Ingredient A, Ingredient B",
            "instructions": "",
        }
        recipe = process_recipe_form(form_dict)
        assert recipe.name == "Test Recipe Instructions Empty"
        assert recipe.ingredients == ["Ingredient A", "Ingredient B"]
        assert recipe.instructions == []

    def test_process_missing_name_raises_keyerror(self):
        form_dict = {"ingredients": "i1,i2", "instructions": "s1\ns2"}
        with pytest.raises(KeyError):
            process_recipe_form(form_dict)

    def test_process_missing_ingredients_raises_keyerror(self):
        form_dict = {"name": "No Ingredients", "instructions": "s1\ns2"}
        with pytest.raises(KeyError):
            process_recipe_form(form_dict)

    def test_process_missing_instructions_raises_keyerror(self):
        form_dict = {"name": "No Instructions", "ingredients": "i1,i2"}
        with pytest.raises(KeyError):
            process_recipe_form(form_dict)
