from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meal_planner.models import RecipeBase
from meal_planner.services.llm_service import (
    ACTIVE_RECIPE_EXTRACTION_PROMPT_FILE,
    ACTIVE_RECIPE_MODIFICATION_PROMPT_FILE,
    MODEL_NAME,
    generate_modified_recipe,
    generate_recipe_from_text,
    get_structured_llm_response,
)
from meal_planner.services.llm_service import logger as llm_service_logger


@pytest.mark.anyio
@patch(
    "meal_planner.services.llm_service.aclient.chat.completions.create",
    new_callable=AsyncMock,
)
@patch.object(llm_service_logger, "error")
async def test_get_structured_llm_response_api_error(
    mock_logger_error, mock_create_completion
):
    """Test get_structured_llm_response catches and logs API call errors."""
    api_exception = Exception("Simulated API failure")
    mock_create_completion.side_effect = api_exception
    test_prompt = "Test prompt"
    test_model = RecipeBase

    with pytest.raises(Exception) as excinfo:
        await get_structured_llm_response(prompt=test_prompt, response_model=test_model)

    assert excinfo.value is api_exception

    mock_logger_error.assert_called_once_with(
        "LLM Call Error: model=%s, response_model=%s, error=%s",
        MODEL_NAME,
        test_model.__name__,
        api_exception,
        exc_info=True,
    )


@pytest.mark.anyio
@patch(
    "meal_planner.services.llm_service.aclient.chat.completions.create",
    new_callable=AsyncMock,
)
@patch.object(llm_service_logger, "error")
async def test_get_structured_llm_response_generic_exception_explicitly(
    mock_logger_error_specific, mock_create_completion_specific
):
    """Test get_structured_llm_response re-raises generic exceptions after logging."""
    generic_exception = ValueError("Simulated generic failure")
    mock_create_completion_specific.side_effect = generic_exception
    test_prompt = "Another test prompt"
    test_model = RecipeBase

    with pytest.raises(ValueError) as excinfo:
        await get_structured_llm_response(prompt=test_prompt, response_model=test_model)

    assert excinfo.value is generic_exception

    mock_logger_error_specific.assert_called_once_with(
        "LLM Call Error: model=%s, response_model=%s, error=%s",
        MODEL_NAME,
        test_model.__name__,
        generic_exception,
        exc_info=True,
    )


@pytest.mark.anyio
@patch("meal_planner.services.llm_service._get_llm_prompt_path")
@patch(
    "meal_planner.services.llm_service.get_structured_llm_response",
    new_callable=AsyncMock,
)
@patch.object(llm_service_logger, "info")
async def test_generate_recipe_from_text_success(
    mock_logger_info, mock_get_structured_response, mock_get_prompt_path
):
    """Test successful recipe generation from text."""
    test_text = "Some recipe text"
    from unittest.mock import MagicMock

    mock_prompt_file = MagicMock(spec=Path)
    mock_prompt_file.read_text.return_value = "Prompt template: {page_text}"
    mock_prompt_file.name = "test_prompt.txt"
    mock_get_prompt_path.return_value = mock_prompt_file

    expected_recipe = RecipeBase(
        name="Generated Recipe", ingredients=["ing1"], instructions=["step1"]
    )
    mock_get_structured_response.return_value = expected_recipe

    result = await generate_recipe_from_text(text=test_text)

    assert result == expected_recipe
    mock_get_prompt_path.assert_called_once_with(
        "recipe_extraction", ACTIVE_RECIPE_EXTRACTION_PROMPT_FILE
    )
    mock_prompt_file.read_text.assert_called_once()
    mock_get_structured_response.assert_called_once_with(
        prompt="Prompt template: Some recipe text",
        response_model=RecipeBase,
    )
    mock_logger_info.assert_any_call("Starting recipe generation from text.")
    mock_logger_info.assert_any_call(
        "Using extraction prompt file: %s", "test_prompt.txt"
    )
    mock_logger_info.assert_any_call(
        "LLM successfully generated recipe: %s", "Generated Recipe"
    )


@pytest.mark.anyio
@patch("meal_planner.services.llm_service._get_llm_prompt_path")
@patch.object(llm_service_logger, "error")
async def test_generate_recipe_from_text_prompt_file_not_found(
    mock_logger_error, mock_get_prompt_path
):
    """Test FileNotFoundError when prompt file is missing for recipe generation."""
    test_text = "Some recipe text"
    mock_get_prompt_path.return_value.read_text.side_effect = FileNotFoundError(
        2, "No such file or directory", "non_existent_prompt.txt"
    )
    mock_get_prompt_path.return_value.name = "non_existent_prompt.txt"

    with pytest.raises(RuntimeError) as excinfo:
        await generate_recipe_from_text(text=test_text)

    assert "LLM service error: Prompt file missing - non_existent_prompt.txt" in str(
        excinfo.value
    )
    args, kwargs = mock_logger_error.call_args
    assert args[0] == "Prompt file not found: %s"
    assert isinstance(args[1], FileNotFoundError)
    assert args[1].filename == "non_existent_prompt.txt"
    assert kwargs.get("exc_info") is True


@pytest.mark.anyio
@patch("meal_planner.services.llm_service._get_llm_prompt_path")
@patch(
    "meal_planner.services.llm_service.get_structured_llm_response",
    new_callable=AsyncMock,
)
@patch.object(llm_service_logger, "error")
async def test_generate_recipe_from_text_generic_exception(
    mock_logger_error, mock_get_structured_response, mock_get_prompt_path
):
    """Test generic Exception during recipe generation from text."""
    test_text = "Some recipe text"
    mock_prompt_file = MagicMock(spec=Path)
    mock_prompt_file.read_text.return_value = "Prompt: {page_text}"
    mock_prompt_file.name = "test_prompt.txt"
    mock_get_prompt_path.return_value = mock_prompt_file

    generic_exception = ValueError("LLM call failed unexpectedly")
    mock_get_structured_response.side_effect = generic_exception

    with pytest.raises(RuntimeError) as excinfo:
        await generate_recipe_from_text(text=test_text)

    assert "LLM service error during recipe generation from text." in str(excinfo.value)
    assert excinfo.value.__cause__ is generic_exception

    mock_logger_error.assert_called_once_with(
        "Error during LLM recipe generation from text: %s",
        generic_exception,
        exc_info=True,
    )


@pytest.mark.anyio
@patch("meal_planner.services.llm_service._get_llm_prompt_path")
@patch(
    "meal_planner.services.llm_service.get_structured_llm_response",
    new_callable=AsyncMock,
)
@patch.object(llm_service_logger, "info")
async def test_generate_modified_recipe_success(
    mock_logger_info, mock_get_structured_response, mock_get_prompt_path
):
    """Test successful recipe modification."""
    current_recipe = RecipeBase(
        name="Original Recipe", ingredients=["orig_ing"], instructions=["orig_step"]
    )
    modification_request = "Make it vegan"

    mock_prompt_file = MagicMock(spec=Path)
    mock_prompt_file.read_text.return_value = (
        "Mod Prompt: {current_recipe_markdown} {modification_prompt}"
    )
    mock_prompt_file.name = "mod_prompt.txt"
    mock_get_prompt_path.return_value = mock_prompt_file

    expected_modified_recipe = RecipeBase(
        name="Vegan Recipe", ingredients=["vegan_ing"], instructions=["vegan_step"]
    )
    mock_get_structured_response.return_value = expected_modified_recipe

    result = await generate_modified_recipe(current_recipe, modification_request)

    assert result == expected_modified_recipe
    mock_get_prompt_path.assert_called_once_with(
        "recipe_modification", ACTIVE_RECIPE_MODIFICATION_PROMPT_FILE
    )
    mock_prompt_file.read_text.assert_called_once()
    expected_formatted_prompt = (
        f"Mod Prompt: {current_recipe.markdown} {modification_request}"
    )
    mock_get_structured_response.assert_called_once_with(
        prompt=expected_formatted_prompt, response_model=RecipeBase
    )
    mock_logger_info.assert_any_call(
        "Starting recipe modification. Original: %s, Request: %s",
        "Original Recipe",
        modification_request,
    )
    mock_logger_info.assert_any_call(
        "Using modification prompt file: %s", "mod_prompt.txt"
    )
    mock_logger_info.assert_any_call(
        "LLM successfully generated modified recipe: %s", "Vegan Recipe"
    )


@pytest.mark.anyio
@patch("meal_planner.services.llm_service._get_llm_prompt_path")
@patch.object(llm_service_logger, "error")
async def test_generate_modified_recipe_prompt_file_not_found(
    mock_logger_error, mock_get_prompt_path
):
    """Test FileNotFoundError when prompt file is missing for recipe modification."""
    current_recipe = RecipeBase(
        name="Original Recipe", ingredients=["ing"], instructions=["step"]
    )
    modification_request = "Make it spicier"

    mock_get_prompt_path.return_value.read_text.side_effect = FileNotFoundError(
        2, "No such file for mod", "non_existent_mod_prompt.txt"
    )
    mock_get_prompt_path.return_value.name = "non_existent_mod_prompt.txt"

    with pytest.raises(RuntimeError) as excinfo:
        await generate_modified_recipe(current_recipe, modification_request)

    assert (
        "LLM service error: Prompt file missing - non_existent_mod_prompt.txt"
        in str(excinfo.value)
    )
    args, kwargs = mock_logger_error.call_args
    assert args[0] == "Prompt file not found: %s"
    assert isinstance(args[1], FileNotFoundError)
    assert args[1].filename == "non_existent_mod_prompt.txt"
    assert kwargs.get("exc_info") is True


@pytest.mark.anyio
@patch("meal_planner.services.llm_service._get_llm_prompt_path")
@patch(
    "meal_planner.services.llm_service.get_structured_llm_response",
    new_callable=AsyncMock,
)
@patch.object(llm_service_logger, "error")
async def test_generate_modified_recipe_generic_exception(
    mock_logger_error, mock_get_structured_response, mock_get_prompt_path
):
    """Test generic Exception during recipe modification."""
    current_recipe = RecipeBase(
        name="Original Recipe", ingredients=["ing"], instructions=["step"]
    )
    modification_request = "Another mod request"

    mock_prompt_file = MagicMock(spec=Path)
    mock_prompt_file.read_text.return_value = "Mod Prompt: ..."
    mock_prompt_file.name = "mod_prompt.txt"
    mock_get_prompt_path.return_value = mock_prompt_file

    generic_exception = TypeError("LLM modification failed unexpectedly")
    mock_get_structured_response.side_effect = generic_exception

    with pytest.raises(RuntimeError) as excinfo:
        await generate_modified_recipe(current_recipe, modification_request)

    assert "LLM service error during recipe modification." in str(excinfo.value)
    assert excinfo.value.__cause__ is generic_exception

    mock_logger_error.assert_called_once_with(
        "Error during LLM recipe modification: %s",
        generic_exception,
        exc_info=True,
    )
