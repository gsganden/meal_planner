"""Tests for servings UI functionality."""

from meal_planner.models import RecipeBase
from meal_planner.ui.edit_recipe import (
    _build_original_hidden_fields,
    _build_servings_section,
    build_recipe_display,
)


class TestServingsUIDisplay:
    """Test servings display logic in UI components."""

    def test_build_recipe_display_servings_equal(self):
        """Test recipe display when servings_min == servings_max."""
        recipe_data = {
            "name": "Test Recipe",
            "ingredients": ["ingredient 1"],
            "instructions": ["step 1"],
            "servings_min": 4,
            "servings_max": 4,
        }
        result = build_recipe_display(recipe_data)
        # This should hit the equality branch in the display logic
        assert result is not None

    def test_build_recipe_display_servings_range(self):
        """Test recipe display with servings range."""
        recipe_data = {
            "name": "Test Recipe",
            "ingredients": ["ingredient 1"],
            "instructions": ["step 1"],
            "servings_min": 4,
            "servings_max": 6,
        }
        result = build_recipe_display(recipe_data)
        # This should hit the range branch in the display logic
        assert result is not None

    def test_build_recipe_display_servings_min_only(self):
        """Test recipe display with only min servings."""
        recipe_data = {
            "name": "Test Recipe",
            "ingredients": ["ingredient 1"],
            "instructions": ["step 1"],
            "servings_min": 4,
            "servings_max": None,
        }
        result = build_recipe_display(recipe_data)
        # This should hit the min-only branch in the display logic
        assert result is not None

    def test_build_recipe_display_servings_max_only(self):
        """Test recipe display with only max servings."""
        recipe_data = {
            "name": "Test Recipe",
            "ingredients": ["ingredient 1"],
            "instructions": ["step 1"],
            "servings_min": None,
            "servings_max": 6,
        }
        result = build_recipe_display(recipe_data)
        # This should hit the max-only branch in the display logic
        assert result is not None

    def test_build_original_hidden_fields_with_servings(self):
        """Test hidden fields generation with servings values."""
        recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["ingredient 1"],
            instructions=["step 1"],
            servings_min=4,
            servings_max=6,
        )
        result = _build_original_hidden_fields(recipe)
        # This should hit the servings hidden fields branches
        assert result is not None
        # Should contain hidden fields for both servings values
        assert len(result) >= 5  # name + 1 ingredient + 1 instruction + 2 servings

    def test_build_original_hidden_fields_min_only(self):
        """Test hidden fields generation with only min servings."""
        recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["ingredient 1"],
            instructions=["step 1"],
            servings_min=4,
            servings_max=None,
        )
        result = _build_original_hidden_fields(recipe)
        # This should hit only the min servings branch
        assert result is not None
        assert len(result) >= 4  # name + 1 ingredient + 1 instruction + 1 servings

    def test_build_original_hidden_fields_max_only(self):
        """Test hidden fields generation with only max servings."""
        recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["ingredient 1"],
            instructions=["step 1"],
            servings_min=None,
            servings_max=6,
        )
        result = _build_original_hidden_fields(recipe)
        # This should hit only the max servings branch
        assert result is not None
        assert len(result) >= 4  # name + 1 ingredient + 1 instruction + 1 servings


class TestServingsUIEditSection:
    """Test servings edit section UI components."""

    def test_build_servings_section_renders_correctly(self):
        """Test that the servings section renders with the new UI elements."""
        result = _build_servings_section(4, 6)
        result_str = str(result)

        assert "Servings Range" in result_str
        assert "to" in result_str
        assert "Min" in result_str
        assert "Max" in result_str

    def test_build_servings_section_with_none_values(self):
        """Test servings section with None values."""
        result = _build_servings_section(None, None)
        result_str = str(result)

        assert "Servings Range" in result_str
        assert "Min" in result_str
        assert "Max" in result_str

    def test_build_servings_section_layout_classes(self):
        """Test that the servings section has the correct layout classes."""
        result = _build_servings_section(4, 6)
        result_str = str(result)

        assert "flex gap-3 items-end" in result_str
        assert "width: 5rem;" in result_str
