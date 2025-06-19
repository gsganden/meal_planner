"""Tests specifically for makes functionality in models."""

import pytest
from pydantic import ValidationError

from meal_planner.models import RecipeBase


class TestRecipeMakesValidation:
    """Test makes validation logic."""

    def test_makes_max_validation_error(self):
        """Test that makes_max < makes_min raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            RecipeBase(
                name="Test Recipe",
                ingredients=["ingredient 1"],
                instructions=["step 1"],
                makes_min=6,
                makes_max=4,  # Invalid: max < min
            )

        error_str = str(exc_info.value)
        assert "Maximum quantity (4) cannot be less than minimum quantity" in error_str

    def test_makes_markdown_generation(self):
        """Test all branches of makes markdown generation."""
        # Test equal makes (min == max)
        recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["ingredient 1"],
            instructions=["step 1"],
            makes_min=4,
            makes_max=4,
        )
        assert "**Makes:** 4 servings\n\n" in recipe.markdown

        # Test range makes (min != max)
        recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["ingredient 1"],
            instructions=["step 1"],
            makes_min=4,
            makes_max=6,
        )
        assert "**Makes:** 4-6 servings\n\n" in recipe.markdown

        # Test only min provided
        recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["ingredient 1"],
            instructions=["step 1"],
            makes_min=4,
            makes_max=None,
        )
        assert "**Makes:** 4+ servings\n\n" in recipe.markdown

        # Test only max provided
        recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["ingredient 1"],
            instructions=["step 1"],
            makes_min=None,
            makes_max=6,
        )
        assert "**Makes:** up to 6 servings\n\n" in recipe.markdown
