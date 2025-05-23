import pytest

from meal_planner.models import RecipeBase
from meal_planner.services.recipe_processing import (
    _ensure_ending_punctuation,
    postprocess_recipe,
)


class TestPostprocessRecipeName:
    DUMMY_INGREDIENTS = ["dummy ingredient"]
    DUMMY_INSTRUCTIONS = ["dummy instruction"]

    @pytest.mark.parametrize(
        "input_name, expected_name",
        [
            ("  my awesome cake  ", "My Awesome Cake"),
            ("Another Example recipe ", "Another Example"),
            ("Another Example Recipe ", "Another Example"),
            ("Recipe (unclosed", "Recipe (Unclosed)"),
        ],
    )
    def test_postprocess_recipe_name(self, input_name: str, expected_name: str):
        input_recipe = RecipeBase(
            name=input_name,
            ingredients=self.DUMMY_INGREDIENTS,
            instructions=self.DUMMY_INSTRUCTIONS,
        )
        processed_recipe = postprocess_recipe(input_recipe)
        assert processed_recipe.name == expected_name


class TestPostprocessRecipe:
    def test_postprocess_ingredients(self):
        recipe = RecipeBase(
            name="Test Name",
            ingredients=[
                "  Ingredient 1 ",
                "Ingredient 2 (with parens)",
                " Ingredient 3, needs trim",
                "  ",
                "Multiple   spaces",
                " Ends with comma ,",
            ],
            instructions=["Step 1"],
        )
        processed = postprocess_recipe(recipe)
        assert processed.ingredients == [
            "Ingredient 1",
            "Ingredient 2 (with parens)",
            "Ingredient 3, needs trim",
            "Multiple spaces",
            "Ends with comma,",
        ]

    def test_postprocess_ingredients_empty_result(self):
        recipe = RecipeBase(
            name="Test Name For Empty Ingredients",
            ingredients=[
                "  ",  # Just whitespace
                "\t",  # Just a tab
                "",  # Empty string
            ],
            instructions=["Step 1"],
        )
        with pytest.raises(ValueError) as excinfo:
            postprocess_recipe(recipe)
        assert (
            "Recipe must have at least one valid ingredient after processing."
            in str(excinfo.value)
        )

    def test_postprocess_instructions(self):
        recipe = RecipeBase(
            name="Test Name",
            ingredients=["Ing 1"],
            instructions=[
                " Step 1: Basic step. ",
                "2. Step with number.",
                "  Step 3 Another step",  # No ending punctuation
                "No number.",
                "  ",
                " Ends with semicolon ;",
                " Has comma , in middle",
            ],
        )
        processed = postprocess_recipe(recipe)
        assert processed.instructions == [
            "Basic step.",
            "Step with number.",
            "Another step.",
            "No number.",
            "Ends with semicolon;",
            "Has comma, in middle.",
        ]


class TestEnsureEndingPunctuation:
    @pytest.mark.parametrize(
        "input_text",
        [
            "This needs a period",
            "This already has a period.",
            "Does this need a period?",
            "Exclamation point!",
            "With colon:",
            "With semicolon;",
            "",
            "   ",
            "Ending with parenthesis)",
            "Already has punctuation.)",
            "Question mark?)",
            "Nested (parenthetical statement)",
            "Multiple nested (statements (here))",
            "Already has period inside.)",
        ],
    )
    def test_ensure_ending_punctuation(self, input_text):
        result = _ensure_ending_punctuation(input_text)

        if not result:
            return

        ending_punctuation = [".", "!", "?", ":", ";", ")"]

        if result.endswith(")"):
            assert result[-2] in ending_punctuation, (
                f"No punctuation before closing parenthesis in: '{result}'"
            )
        else:
            assert result[-1] in ending_punctuation, (
                f"No ending punctuation in: '{result}'"
            )

        if "(" in result:
            assert ")" in result, f"Unbalanced parentheses in: '{result}'"
