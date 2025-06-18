"""Tests for the Recipe models with source field functionality."""

import pytest
from pydantic import ValidationError

from meal_planner.models import RecipeBase


class TestRecipeBaseWithSource:
    """Test RecipeBase model with the new source field."""

    def test_recipe_base_with_source_url(self):
        """Test RecipeBase can be created with a source URL."""
        recipe = RecipeBase(
            name="Test Recipe",
            source="https://example.com/recipe",
            ingredients=["Ingredient 1", "Ingredient 2"],
            instructions=["Step 1", "Step 2"],
        )
        assert recipe.name == "Test Recipe"
        assert recipe.source == "https://example.com/recipe"
        assert recipe.ingredients == ["Ingredient 1", "Ingredient 2"]
        assert recipe.instructions == ["Step 1", "Step 2"]

    def test_recipe_base_without_source(self):
        """Test RecipeBase can be created without a source (None)."""
        recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["Ingredient 1"],
            instructions=["Step 1"],
        )
        assert recipe.name == "Test Recipe"
        assert recipe.source is None
        assert recipe.ingredients == ["Ingredient 1"]
        assert recipe.instructions == ["Step 1"]

    def test_recipe_base_with_empty_source(self):
        """Test RecipeBase can be created with empty source."""
        recipe = RecipeBase(
            name="Test Recipe",
            source=None,
            ingredients=["Ingredient 1"],
            instructions=["Step 1"],
        )
        assert recipe.name == "Test Recipe"
        assert recipe.source is None

    def test_recipe_base_markdown_with_source(self):
        """Test markdown property includes source when present."""
        recipe = RecipeBase(
            name="Test Recipe",
            source="https://example.com/recipe",
            ingredients=["Ingredient 1", "Ingredient 2"],
            instructions=["Step 1", "Step 2"],
        )
        markdown = recipe.markdown
        assert "# Test Recipe" in markdown
        assert "**Source:** https://example.com/recipe" in markdown
        assert "## Ingredients" in markdown
        assert "- Ingredient 1" in markdown
        assert "- Ingredient 2" in markdown
        assert "## Instructions" in markdown
        assert "- Step 1" in markdown
        assert "- Step 2" in markdown

    def test_recipe_base_markdown_without_source(self):
        """Test markdown property excludes source when not present."""
        recipe = RecipeBase(
            name="Test Recipe",
            ingredients=["Ingredient 1"],
            instructions=["Step 1"],
        )
        markdown = recipe.markdown
        assert "# Test Recipe" in markdown
        assert "**Source:**" not in markdown
        assert "## Ingredients" in markdown
        assert "- Ingredient 1" in markdown
        assert "## Instructions" in markdown
        assert "- Step 1" in markdown

    def test_recipe_base_validation_still_works(self):
        """Test that existing validation still works with source field."""
        # Test missing name
        with pytest.raises(ValidationError):
            RecipeBase(
                name="",
                ingredients=["Ingredient 1"],
                instructions=["Step 1"],
            )

        # Test missing ingredients
        with pytest.raises(ValidationError):
            RecipeBase(
                name="Test Recipe",
                ingredients=[],
                instructions=["Step 1"],
            )

        # Test missing instructions
        with pytest.raises(ValidationError):
            RecipeBase(
                name="Test Recipe",
                ingredients=["Ingredient 1"],
                instructions=[],
            )
