"""Tests specifically for servings functionality in models."""

import pytest
from pydantic import ValidationError

from meal_planner.models import RecipeBase


class TestRecipeServingsValidation:
    """Test servings validation logic."""

    def test_servings_max_validation_error(self):
        """Test that servings_max < servings_min raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            RecipeBase(
                name="Test Recipe",
                ingredients=["ingredient 1"],
                instructions=["step 1"],
                servings_min=6,
                servings_max=4,  # Invalid: max < min
            )

        error_str = str(exc_info.value)
        assert "Maximum servings (4) cannot be less than minimum" in error_str

    def test_servings_markdown_generation(self):
        """Test all branches of servings markdown generation."""
        # Test equal servings (min == max)
        recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["ingredient 1"],
            instructions=["step 1"],
            servings_min=4,
            servings_max=4,
        )
        assert "**Serves:** 4\n\n" in recipe.markdown

        # Test range servings (min != max)
        recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["ingredient 1"],
            instructions=["step 1"],
            servings_min=4,
            servings_max=6,
        )
        assert "**Serves:** 4-6\n\n" in recipe.markdown

        # Test only min provided
        recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["ingredient 1"],
            instructions=["step 1"],
            servings_min=4,
            servings_max=None,
        )
        assert "**Serves:** 4+\n\n" in recipe.markdown

        # Test only max provided
        recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["ingredient 1"],
            instructions=["step 1"],
            servings_min=None,
            servings_max=6,
        )
        assert "**Serves:** up to 6\n\n" in recipe.markdown
