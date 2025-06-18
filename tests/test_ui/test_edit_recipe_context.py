"""Tests for recipe editing UI context-aware functionality."""

import pytest

from meal_planner.ui.edit_recipe import _build_recipe_id_field, _build_save_buttons


class TestRecipeIdField:
    def test_build_recipe_id_field_with_id(self):
        """Test hidden recipe ID field is created when ID is provided."""
        result = _build_recipe_id_field(123)
        # Check the result is an Input component with correct attributes
        assert hasattr(result, 'attrs')
        assert result.attrs["type"] == "hidden"
        assert result.attrs["name"] == "recipe_id"
        assert result.attrs["value"] == "123"

    def test_build_recipe_id_field_without_id(self):
        """Test empty string is returned when no ID provided."""
        result = _build_recipe_id_field(None)
        assert result == ""


class TestSaveButtons:
    def test_build_save_buttons_new_recipe(self):
        """Test single save button for new recipes."""
        result = _build_save_buttons(None)
        # The result should be a Div with a single Button for new recipes
        # Let's check for presence of button-related attributes
        assert hasattr(result, 'children')
        # Look for the save recipe behavior
        html_repr = repr(result)
        assert "Save Recipe" in html_repr

    def test_build_save_buttons_existing_recipe(self):
        """Test dual buttons for existing recipes."""
        result = _build_save_buttons(123)
        # The result should be a Div with both save buttons for existing recipes
        assert hasattr(result, 'children')
        html_repr = repr(result)
        assert "Save Changes" in html_repr
        assert "Save as New Recipe" in html_repr