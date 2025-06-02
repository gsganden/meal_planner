"""Recipe post-processing and data cleaning service."""

import html
import re

from meal_planner.models import RecipeBase


def postprocess_recipe(recipe: RecipeBase) -> RecipeBase:
    """Clean and standardize all fields of an extracted recipe.

    Applies post-processing to recipe name, ingredients, and instructions
    to ensure consistent formatting and remove common extraction artifacts.

    Args:
        recipe: Raw recipe data extracted from a webpage.

    Returns:
        A new RecipeBase instance with all fields cleaned and standardized.

    Raises:
        ValueError: If the recipe has no valid ingredients after processing.
    """
    result = recipe.model_copy(deep=True)

    if result.name:
        result.name = _postprocess_recipe_name(result.name)

    result.ingredients = [
        processed_ing
        for ing_str in result.ingredients
        if (processed_ing := _postprocess_ingredient(ing_str))
    ]

    if not result.ingredients:
        raise ValueError(
            "Recipe must have at least one valid ingredient after processing."
        )

    result.instructions = [
        processed_inst
        for i in result.instructions
        if (processed_inst := _postprocess_instruction(i))
    ]

    return result


def _postprocess_recipe_name(name: str) -> str:
    """Clean and format a recipe name for display.

    Removes common suffixes like "recipe" or "Recipe", applies title case,
    and ensures balanced parentheses. Handles edge cases from various
    recipe websites.

    Args:
        name: Raw recipe name from extraction.

    Returns:
        Cleaned recipe name with proper capitalization and formatting.
    """
    return _close_parenthesis(
        name.strip().removesuffix("recipe").removesuffix("Recipe").title().strip()
    )


def _postprocess_ingredient(ingredient: str) -> str:
    """Normalize an ingredient string for consistent display.

    Removes extra whitespace, fixes comma spacing, and ensures balanced
    parentheses. Filters out empty or whitespace-only ingredients.

    Args:
        ingredient: Raw ingredient text from extraction.

    Returns:
        Cleaned ingredient string, or empty string if invalid.
    """
    return _close_parenthesis(" ".join(ingredient.split()).strip().replace(" ,", ","))


def _postprocess_instruction(instruction: str) -> str:
    """Clean and format a cooking instruction step.

    Removes step numbering, unescapes HTML entities, fixes punctuation
    spacing, and ensures proper ending punctuation. Maintains readability
    while standardizing format.

    Args:
        instruction: Raw instruction text from extraction.

    Returns:
        Cleaned instruction with proper formatting and punctuation.
    """
    return _ensure_ending_punctuation(
        _remove_leading_step_numbers(html.unescape(instruction))
        .replace(" ,", ",")
        .replace(" ;", ";")
        .strip()
    )


def _remove_leading_step_numbers(instruction: str) -> str:
    """Remove step numbering prefixes from instruction text.

    Handles various formats like "Step 1:", "1.", "1 " to create clean
    instruction text without redundant numbering.

    Args:
        instruction: Instruction text potentially with step numbers.

    Returns:
        Instruction text with leading step indicators removed.
    """
    instruction = instruction.strip()
    return re.sub(
        r"^\s*(?:Step\s*\d+|\d+)\s*[:.]?\s*", "", instruction, flags=re.IGNORECASE
    )


def _close_parenthesis(text: str) -> str:
    """Ensure balanced parentheses in text by adding closing parenthesis if needed.

    Some extraction processes leave unclosed parentheses. This ensures
    all opening parentheses have matching closing ones.

    Args:
        text: Text that may have unbalanced parentheses.

    Returns:
        Text with balanced parentheses.
    """
    if "(" in text and ")" not in text:
        return text + ")"
    return text


def _ensure_ending_punctuation(text: str) -> str:
    """Add appropriate ending punctuation to text if missing.

    Ensures instructions end with proper punctuation for readability.
    Special handling for text ending with parentheses to place periods
    correctly.

    Args:
        text: Text that may lack ending punctuation.

    Returns:
        Text with appropriate ending punctuation (period if none exists).
    """
    if not text:
        return text

    ending_punctuation = [".", "!", "?", ":", ";"]

    if text[-1] in ending_punctuation:
        return text

    if text.endswith(")"):
        if len(text) > 1 and text[-2] not in ending_punctuation:
            return text[:-1] + "." + text[-1]
        return text

    return text + "."
