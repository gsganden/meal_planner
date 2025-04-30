import pytest

from meal_planner.models import Recipe


@pytest.fixture
def sample_recipe() -> Recipe:
    """Provides a sample Recipe instance for testing."""
    return Recipe(
        name="Test Salad",
        ingredients=["Lettuce", "Tomato", "1/2 cup Dressing"],
        instructions=[
            "Wash lettuce.",
            "Chop tomato.",
            "Combine ingredients and add dressing.",
        ],
    )


# Removed tests for .html property
