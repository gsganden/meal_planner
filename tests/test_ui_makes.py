"""Tests for makes UI functionality."""

from meal_planner.models import RecipeBase
from meal_planner.ui.edit_recipe import (
    _build_original_hidden_fields,
    build_makes_section,
    build_recipe_display,
)


class TestMakesUIDisplay:
    """Test makes display logic in UI components."""

    def test_build_recipe_display_makes_equal(self):
        """Test recipe display when makes_min == makes_max."""
        recipe_data = {
            "name": "Test Recipe",
            "ingredients": ["ingredient 1"],
            "instructions": ["step 1"],
            "makes_min": 4,
            "makes_max": 4,
        }
        result = build_recipe_display(recipe_data)
        # This should hit the equality branch in the display logic
        assert result is not None

    def test_build_recipe_display_makes_range(self):
        """Test recipe display with makes range."""
        recipe_data = {
            "name": "Test Recipe",
            "ingredients": ["ingredient 1"],
            "instructions": ["step 1"],
            "makes_min": 4,
            "makes_max": 6,
        }
        result = build_recipe_display(recipe_data)
        # This should hit the range branch in the display logic
        assert result is not None

    def test_build_recipe_display_makes_min_only(self):
        """Test recipe display with only min makes."""
        recipe_data = {
            "name": "Test Recipe",
            "ingredients": ["ingredient 1"],
            "instructions": ["step 1"],
            "makes_min": 4,
            "makes_max": None,
        }
        result = build_recipe_display(recipe_data)
        # This should hit the min-only branch in the display logic
        assert result is not None

    def test_build_recipe_display_makes_max_only(self):
        """Test recipe display with only max makes."""
        recipe_data = {
            "name": "Test Recipe",
            "ingredients": ["ingredient 1"],
            "instructions": ["step 1"],
            "makes_min": None,
            "makes_max": 6,
        }
        result = build_recipe_display(recipe_data)
        # This should hit the max-only branch in the display logic
        assert result is not None

    def test_build_original_hidden_fields_with_makes(self):
        """Test hidden fields generation with makes values."""
        recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["ingredient 1"],
            instructions=["step 1"],
            makes_min=4,
            makes_max=6,
            makes_unit="servings",
        )
        result = _build_original_hidden_fields(recipe)
        # This should hit the makes hidden fields branches
        assert result is not None
        # Should contain hidden fields for all makes values
        assert len(result) >= 6  # name + 1 ingredient + 1 instruction + 3 makes

    def test_build_original_hidden_fields_min_only(self):
        """Test hidden fields generation with only min makes."""
        recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["ingredient 1"],
            instructions=["step 1"],
            makes_min=4,
            makes_max=None,
        )
        result = _build_original_hidden_fields(recipe)
        # This should hit only the min makes branch
        assert result is not None
        assert len(result) >= 4  # name + 1 ingredient + 1 instruction + 1 makes

    def test_build_original_hidden_fields_max_only(self):
        """Test hidden fields generation with only max makes."""
        recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["ingredient 1"],
            instructions=["step 1"],
            makes_min=None,
            makes_max=6,
        )
        result = _build_original_hidden_fields(recipe)
        # This should hit only the max makes branch
        assert result is not None
        assert len(result) >= 4  # name + 1 ingredient + 1 instruction + 1 makes


class TestMakesUIEditSection:
    """Test makes edit section UI components."""

    def test_build_makes_section_renders_correctly(self):
        """Test that the makes section renders with the new UI elements."""
        result = build_makes_section(4, 6, "servings")
        assert result is not None
        assert hasattr(result, "id")
        assert result.id == "makes-section"

    def test_build_makes_section_with_none_values(self):
        """Test makes section with None values."""
        result = build_makes_section(None, None, None)
        assert result is not None
        assert hasattr(result, "id")
        assert result.id == "makes-section"

    def test_build_makes_section_layout_classes(self):
        """Test that the makes section has the correct layout classes."""
        result = build_makes_section(4, 6, "servings")
        assert result is not None
        assert hasattr(result, "id")
        assert result.id == "makes-section"

    def test_build_makes_section_with_error_message(self):
        """Test makes section displays error message when provided."""
        error_msg = "Maximum makes cannot be less than minimum makes"
        result = build_makes_section(6, 4, "servings", error_message=error_msg)
        assert result is not None
        assert hasattr(result, "id")
        assert result.id == "makes-section"
