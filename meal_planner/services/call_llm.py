import logging
import os
import string
from pathlib import Path
from typing import TypeVar

import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel

from meal_planner.models import RecipeBase

MODEL_NAME = "gemini-2.0-flash"
PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompt_templates"
ACTIVE_RECIPE_EXTRACTION_PROMPT_FILE = "20250525_174436__string_template_syntax.txt"
ACTIVE_RECIPE_MODIFICATION_PROMPT_FILE = "20250525_174436__string_template_syntax.txt"

logger = logging.getLogger(__name__)

_openai_client = None
_aclient = None

T = TypeVar("T", bound=BaseModel)


def _get_aclient():
    """Lazy initialization of the instructor client."""
    global _openai_client, _aclient
    if _aclient is None:
        _openai_client = AsyncOpenAI(
            api_key=os.environ["GOOGLE_API_KEY"],
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        _aclient = instructor.from_openai(_openai_client)
    return _aclient


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
        aclient = _get_aclient()
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
        raise


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
        prompt_template = prompt_file_path.read_text(encoding="utf-8")
        formatted_prompt = string.Template(prompt_template).safe_substitute(
            page_text=text
        )

        extracted_recipe: RecipeBase = await get_structured_llm_response(
            prompt=formatted_prompt,
            response_model=RecipeBase,
        )
        logger.info("LLM successfully generated recipe: %s", extracted_recipe.name)
        return extracted_recipe
    except FileNotFoundError as e:
        logger.error("Prompt file not found: %s", e, exc_info=True)
        raise
    except Exception as e:
        logger.error(
            "Error during LLM recipe generation from text: %s", e, exc_info=True
        )
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
        formatted_prompt = string.Template(modification_template).safe_substitute(
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
        return modified_recipe
    except FileNotFoundError as e:
        logger.error("Prompt file not found: %s", e, exc_info=True)
        raise
    except Exception as e:
        logger.error("Error during LLM recipe modification: %s", e, exc_info=True)
        raise RuntimeError("LLM service error during recipe modification.") from e
