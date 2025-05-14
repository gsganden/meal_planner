import logging
import os
from pathlib import Path
from typing import TypeVar

import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel

from meal_planner.models import RecipeBase

# Constants from main.py - these might need a more centralized home eventually
MODEL_NAME = "gemini-2.0-flash"
# Prompt-related constants moved from main.py
PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompt_templates"
ACTIVE_RECIPE_EXTRACTION_PROMPT_FILE = "20250505_213551__terminal_periods_wording.txt"
ACTIVE_RECIPE_MODIFICATION_PROMPT_FILE = "20250429_183353__initial.txt"

# Logger setup similar to main.py
logger = logging.getLogger(__name__)


# OpenAI client setup similar to main.py
# This assumes GOOGLE_API_KEY is set in the environment where this service is run.
# If this service is part of a larger app (e.g., Modal), the secret handling
# might need to be harmonized with the main app's approach.
openai_client = AsyncOpenAI(
    api_key=os.environ.get("GOOGLE_API_KEY"),  # Use .get for a bit more safety
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

aclient = instructor.from_openai(openai_client)

T = TypeVar("T", bound=BaseModel)


async def get_structured_llm_response(prompt: str, response_model: type[T]) -> T:
    """Queries the LLM with a prompt and returns a Pydantic model instance.

    Args:
        prompt: The prompt to send to the LLM.
        response_model: The Pydantic model to structure the LLM's response.

    Returns:
        An instance of the provided Pydantic model.

    Raises:
        Exception: If the LLM call fails or the response cannot be parsed.
    """
    try:
        logger.info(
            "LLM Call: model=%s, response_model=%s", MODEL_NAME, response_model.__name__
        )
        response = await aclient.chat.completions.create(
            model=MODEL_NAME,
            response_model=response_model,
            messages=[{"role": "user", "content": prompt}],
        )
        logger.debug("LLM Response: %s", response)
        return response
    except Exception as e:
        logger.error(
            "LLM Call Error: model=%s, response_model=%s, error=%s",
            MODEL_NAME,
            response_model.__name__,
            e,
            exc_info=True,
        )
        raise  # Re-raise the exception to be handled by the caller


def _get_llm_prompt_path(category: str, filename: str) -> Path:
    """Constructs the full path to a prompt file for LLM services."""
    return PROMPT_DIR / category / filename


async def generate_recipe_from_text(text: str) -> RecipeBase:
    """
    Formats a prompt to extract a recipe from text, calls the LLM,
    and returns the structured recipe.
    """
    logger.info("Starting recipe generation from text.")
    try:
        prompt_file_path = _get_llm_prompt_path(
            "recipe_extraction", ACTIVE_RECIPE_EXTRACTION_PROMPT_FILE
        )
        logger.info("Using extraction prompt file: %s", prompt_file_path.name)
        prompt_template = prompt_file_path.read_text()
        formatted_prompt = prompt_template.format(page_text=text)

        extracted_recipe: RecipeBase = await get_structured_llm_response(
            prompt=formatted_prompt,
            response_model=RecipeBase,
        )
        logger.info("LLM successfully generated recipe: %s", extracted_recipe.name)
        return extracted_recipe
    except FileNotFoundError as e:
        logger.error("Prompt file not found: %s", e, exc_info=True)
        # Consider a more specific exception type for the service layer
        raise RuntimeError(
            f"LLM service error: Prompt file missing - {e.filename}"
        ) from e
    except Exception as e:
        logger.error(
            "Error during LLM recipe generation from text: %s", e, exc_info=True
        )
        # Consider a more specific exception type
        raise RuntimeError(
            "LLM service error during recipe generation from text."
        ) from e


async def generate_modified_recipe(
    current_recipe: RecipeBase, modification_request: str
) -> RecipeBase:
    """
    Formats a prompt to modify an existing recipe based on a request,
    calls the LLM, and returns the structured modified recipe.
    """
    logger.info(
        "Starting recipe modification. Original: %s, Request: %s",
        current_recipe.name,
        modification_request,
    )
    try:
        prompt_file_path = _get_llm_prompt_path(
            "recipe_modification", ACTIVE_RECIPE_MODIFICATION_PROMPT_FILE
        )
        logger.info("Using modification prompt file: %s", prompt_file_path.name)
        modification_template = prompt_file_path.read_text()
        formatted_prompt = modification_template.format(
            current_recipe_markdown=current_recipe.markdown,
            modification_prompt=modification_request,
        )

        modified_recipe: RecipeBase = await get_structured_llm_response(
            prompt=formatted_prompt,
            response_model=RecipeBase,
        )
        logger.info(
            "LLM successfully generated modified recipe: %s", modified_recipe.name
        )
        # Note: postprocessing of this modified_recipe will happen in main.py
        return modified_recipe
    except FileNotFoundError as e:
        logger.error("Prompt file not found: %s", e, exc_info=True)
        raise RuntimeError(
            f"LLM service error: Prompt file missing - {e.filename}"
        ) from e
    except Exception as e:
        logger.error("Error during LLM recipe modification: %s", e, exc_info=True)
        raise RuntimeError("LLM service error during recipe modification.") from e
