from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import AsyncClient, Request, Response

from tests import constants

# Constants
# TRANSPORT = ASGITransport(app=app)
# TEST_URL = "http://test-recipe.com"

# URLs
# RECIPES_LIST_PATH = "/recipes"
# RECIPES_EXTRACT_URL = "/recipes/extract"
# RECIPES_FETCH_TEXT_URL = "/recipes/fetch-text"
# RECIPES_EXTRACT_RUN_URL = "/recipes/extract/run"
# RECIPES_MODIFY_URL = "/recipes/modify"
# RECIPES_SAVE_URL = "/recipes/save"

# Form Field Names
# FIELD_RECIPE_URL = "input_url"
# FIELD_RECIPE_TEXT = "recipe_text"
# FIELD_NAME = "name"
# FIELD_INGREDIENTS = "ingredients"
# FIELD_INSTRUCTIONS = "instructions"
# FIELD_MODIFICATION_PROMPT = "modification_prompt"
# FIELD_ORIGINAL_NAME = "original_name"
# FIELD_ORIGINAL_INGREDIENTS = "original_ingredients"
# FIELD_ORIGINAL_INSTRUCTIONS = "original_instructions"

# All test classes (TestSmokeEndpoints, TestGetRecipesPageErrors, TestGetSingleRecipePageErrors)
# have been moved to tests/routers/test_pages.py

# Constants, URLs, Form Field Names - All moved or removed earlier
