from typing import Any, cast
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import httpx
import monsterui.all as mu
import pytest
from bs4 import BeautifulSoup
from bs4.element import Tag
from fastcore.xml import FT  # Import FT for type checking
from httpx import ASGITransport, AsyncClient, Request, Response
from pydantic import ValidationError
from starlette.datastructures import FormData

import meal_planner.main as main_module
from meal_planner.main import (
    ACTIVE_RECIPE_MODIFICATION_PROMPT_FILE,
    CSS_ERROR_CLASS,
    MODEL_NAME,
    ModifyFormError,
    _parse_recipe_form_data,
    app,
    fetch_and_clean_text_from_url,
    fetch_page_text,
    get_structured_llm_response,
    postprocess_recipe,
)
from meal_planner.models import RecipeBase

# Constants
TRANSPORT = ASGITransport(app=app)
TEST_URL = "http://test-recipe.com"

# URLs
RECIPES_LIST_PATH = "/recipes"
RECIPES_EXTRACT_URL = "/recipes/extract"
RECIPES_FETCH_TEXT_URL = "/recipes/fetch-text"
RECIPES_EXTRACT_RUN_URL = "/recipes/extract/run"
RECIPES_SAVE_URL = "/recipes/save"
RECIPES_MODIFY_URL = "/recipes/modify"

# Form Field Names
FIELD_RECIPE_URL = "recipe_url"
FIELD_RECIPE_TEXT = "recipe_text"
FIELD_NAME = "name"
FIELD_INGREDIENTS = "ingredients"
FIELD_INSTRUCTIONS = "instructions"
FIELD_MODIFICATION_PROMPT = "modification_prompt"
FIELD_ORIGINAL_NAME = "original_name"
FIELD_ORIGINAL_INGREDIENTS = "original_ingredients"
FIELD_ORIGINAL_INSTRUCTIONS = "original_instructions"


def _build_ui_fragment_form_data(
    name="Test Recipe",
    ingredients=None,
    instructions=None,
    original_name=None,
    original_ingredients=None,
    original_instructions=None,
) -> dict:
    ingredients = ingredients if ingredients is not None else ["ing1"]
    instructions = instructions if instructions is not None else ["step1"]
    original_name = original_name if original_name is not None else name
    original_ingredients = (
        original_ingredients if original_ingredients is not None else ingredients
    )
    original_instructions = (
        original_instructions if original_instructions is not None else instructions
    )

    return {
        "name": name,
        "ingredients": ingredients,
        "instructions": instructions,
        "original_name": original_name,
        "original_ingredients": original_ingredients,
        "original_instructions": original_instructions,
    }


@pytest.mark.anyio
class TestSmokeEndpoints:
    async def test_root(self, client: AsyncClient):
        response = await client.get("/")
        assert response.status_code == 200
        assert "Meal Planner" in response.text

    async def test_extract_recipe_page_loads(self, client: AsyncClient):
        response = await client.get(RECIPES_EXTRACT_URL)
        assert response.status_code == 200
        assert 'id="recipe_url"' in response.text
        assert 'placeholder="https://example.com/recipe"' in response.text
        assert f'hx-post="{RECIPES_FETCH_TEXT_URL}"' in response.text
        assert "Fetch Text from URL" in response.text
        assert 'id="recipe_text"' in response.text
        assert (
            'placeholder="Paste full recipe text here, or fetch from URL above."'
            in response.text
        )
        assert f'hx-post="{RECIPES_EXTRACT_RUN_URL}"' in response.text
        assert "Extract Recipe" in response.text
        assert 'id="recipe-results"' in response.text


@pytest.mark.anyio
class TestRecipeFetchTextEndpoint:
    TEST_URL = "http://example.com/fetch-success"

    @pytest.fixture
    def mock_fetch_clean(self):
        with patch(
            "meal_planner.main.fetch_and_clean_text_from_url", new_callable=AsyncMock
        ) as mock_fetch:
            yield mock_fetch

    async def test_success(self, client: AsyncClient, mock_fetch_clean):
        mock_text = "Fetched and cleaned recipe text."
        mock_fetch_clean.return_value = mock_text

        response = await client.post(
            RECIPES_FETCH_TEXT_URL, data={FIELD_RECIPE_URL: self.TEST_URL}
        )

        assert response.status_code == 200
        mock_fetch_clean.assert_called_once_with(self.TEST_URL)
        assert "<textarea" in response.text
        assert f'id="{FIELD_RECIPE_TEXT}"' in response.text
        assert f'name="{FIELD_RECIPE_TEXT}"' in response.text
        assert ">Fetched and cleaned recipe text.</textarea>" in response.text

    async def test_missing_url(self, client: AsyncClient):
        response = await client.post(RECIPES_FETCH_TEXT_URL, data={})
        assert response.status_code == 200
        assert "Please provide a Recipe URL to fetch." in response.text
        assert f'class="{CSS_ERROR_CLASS}"' in response.text

    @pytest.mark.parametrize(
        "exception_type, exception_args, expected_message",
        [
            (
                httpx.RequestError,
                ("Network connection failed",),
                "Error fetching URL. Please check the URL and your connection.",
            ),
            (
                httpx.HTTPStatusError,
                (
                    "404 Client Error",
                    {
                        "request": Request("GET", TEST_URL),
                        "response": Response(404, request=Request("GET", TEST_URL)),
                    },
                ),
                "Error fetching URL: The server returned an error.",
            ),
            (
                RuntimeError,
                ("Processing failed",),
                "Failed to process the content from the URL.",
            ),
            (
                Exception,
                ("Unexpected error",),
                "Unexpected error fetching text.",
            ),
        ],
    )
    async def test_fetch_text_errors(
        self,
        client: AsyncClient,
        mock_fetch_clean,
        exception_type,
        exception_args,
        expected_message,
    ):
        if exception_type == httpx.HTTPStatusError:
            error_instance = exception_type(exception_args[0], **exception_args[1])
        elif exception_type == httpx.RequestError:
            error_instance = exception_type(exception_args[0], request=None)
        else:
            error_instance = exception_type(*exception_args)

        mock_fetch_clean.side_effect = error_instance

        response = await client.post(
            RECIPES_FETCH_TEXT_URL, data={FIELD_RECIPE_URL: self.TEST_URL}
        )

        assert response.status_code == 200
        assert expected_message in response.text
        assert f'class="{CSS_ERROR_CLASS}"' in response.text


@pytest.mark.anyio
class TestRecipeExtractRunEndpoint:
    @pytest.fixture
    def mock_structured_llm_response(self):
        with patch(
            "meal_planner.main.get_structured_llm_response", new_callable=AsyncMock
        ) as mock_llm:
            yield mock_llm

    async def test_success(self, client: AsyncClient, mock_structured_llm_response):
        test_text = (
            "Recipe Name\nIngredients: ing1, ing2\nInstructions: 1. First "
            "step text\nStep 2: Second step text"
        )
        mock_structured_llm_response.return_value = RecipeBase(
            name=" text input success name recipe ",
            ingredients=[" ingA ", "ingB, "],
            instructions=[
                "1. Actual step A",
                " Step 2: Actual step B ",
            ],
        )

        response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: test_text}
        )
        assert response.status_code == 200
        mock_structured_llm_response.assert_called_once_with(
            prompt=ANY,
            response_model=RecipeBase,
        )

        html_content = response.text
        assert (
            _extract_form_value(html_content, FIELD_NAME) == "Text Input Success Name"
        )
        assert _extract_form_list_values(html_content, FIELD_INGREDIENTS) == [
            "ingA",
            "ingB,",
        ]
        assert _extract_form_list_values(html_content, FIELD_INSTRUCTIONS) == [
            "Actual step A",
            "Actual step B",
        ]

    @patch("meal_planner.main.logger.error")
    async def test_extraction_error(
        self, mock_logger_error, client: AsyncClient, mock_structured_llm_response
    ):
        test_text = "Some recipe text that causes an LLM error."
        llm_exception = Exception("LLM failed on text input")
        mock_structured_llm_response.side_effect = llm_exception

        response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: test_text}
        )
        assert response.status_code == 200
        expected_error_msg = (
            "Recipe extraction failed. An unexpected error occurred during processing."
        )
        assert expected_error_msg in response.text
        mock_structured_llm_response.assert_called_once()
        mock_logger_error.assert_any_call(
            "Error during recipe extraction call: %s",
            MODEL_NAME,
            llm_exception,
            exc_info=True,
        )

    async def test_no_text_input_provided(self, client: AsyncClient):
        response = await client.post(RECIPES_EXTRACT_RUN_URL, data={})

        assert response.status_code == 200
        expected_error_msg = "No text content provided for extraction."
        assert expected_error_msg in response.text

    @patch("meal_planner.main.postprocess_recipe")
    @patch("meal_planner.main.get_structured_llm_response", new_callable=AsyncMock)
    async def test_extract_run_missing_instructions(
        self, mock_get_structured_llm_response, mock_postprocess, client: AsyncClient
    ):
        """Test recipe extraction placeholder logic for empty instructions."""
        test_text = "Recipe with ingredients only"

        mock_recipe = MagicMock(spec=RecipeBase)
        raw_name = "Needs Instructions Recipe"
        raw_ingredients = ["Ingredient A", " Ingredient B "]
        mock_recipe.name = raw_name
        mock_recipe.ingredients = raw_ingredients
        mock_recipe.instructions = []
        mock_get_structured_llm_response.return_value = mock_recipe

        mock_postprocess.side_effect = lambda recipe: recipe

        response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: test_text}
        )

        assert response.status_code == 200
        mock_get_structured_llm_response.assert_called_once()
        mock_postprocess.assert_called_once_with(mock_recipe)

        html_content = response.text
        assert _extract_form_value(html_content, FIELD_NAME) == raw_name
        assert (
            _extract_form_list_values(html_content, FIELD_INGREDIENTS)
            == raw_ingredients
        )
        assert _extract_form_list_values(html_content, FIELD_INSTRUCTIONS) == []

    @patch("meal_planner.main.postprocess_recipe")
    @patch("meal_planner.main.get_structured_llm_response", new_callable=AsyncMock)
    async def test_extract_run_missing_ingredients(
        self, mock_get_structured_llm_response, mock_postprocess, client: AsyncClient
    ):
        """Test recipe extraction placeholder logic for empty ingredients."""
        test_text = "Recipe with instructions only"

        mock_recipe = MagicMock(spec=RecipeBase)
        raw_name = "Needs Ingredients Recipe"
        raw_instructions = ["Instruction A", " 1. Instruction B"]
        mock_recipe.name = raw_name
        mock_recipe.ingredients = []
        mock_recipe.instructions = raw_instructions
        mock_get_structured_llm_response.return_value = mock_recipe

        mock_postprocess.side_effect = lambda recipe: recipe

        response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: test_text}
        )

        assert response.status_code == 200
        mock_get_structured_llm_response.assert_called_once()
        mock_postprocess.assert_called_once_with(mock_recipe)

        html_content = response.text
        assert _extract_form_value(html_content, FIELD_NAME) == raw_name
        assert _extract_form_list_values(html_content, FIELD_INGREDIENTS) == [
            "No ingredients found"
        ]
        assert (
            _extract_form_list_values(html_content, FIELD_INSTRUCTIONS)
            == raw_instructions
        )


@pytest.mark.anyio
class TestFetchPageText:
    @pytest.fixture
    def mock_httpx_client(self):
        with patch("meal_planner.main.httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock(spec=httpx.Response)
            mock_response.text = "Mock page content"
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)

            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_client_instance
            yield mock_client_class, mock_client, mock_response

    async def test_fetch_page_text_success(self, mock_httpx_client):
        mock_client_class, mock_client, mock_response = mock_httpx_client
        test_url = "http://example.com/success"

        result = await fetch_page_text(test_url)

        assert result == "Mock page content"
        mock_client_class.assert_called_once()
        mock_client.get.assert_called_once_with(test_url)
        mock_response.raise_for_status.assert_called_once()

    async def test_fetch_page_text_http_error(self, mock_httpx_client):
        mock_client_class, mock_client, mock_response = mock_httpx_client
        test_url = "http://example.com/notfound"
        dummy_request = httpx.Request("GET", test_url)
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=dummy_request, response=mock_response
        )

        with pytest.raises(httpx.HTTPStatusError):
            await fetch_page_text(test_url)

        mock_client_class.assert_called_once()
        mock_client.get.assert_called_once_with(test_url)
        mock_response.raise_for_status.assert_called_once()

    async def test_fetch_page_text_request_error(self, mock_httpx_client):
        mock_client_class, mock_client, mock_response = mock_httpx_client
        test_url = "http://example.com/networkfail"
        dummy_request = httpx.Request("GET", test_url)
        mock_client.get.side_effect = httpx.RequestError(
            "Network error", request=dummy_request
        )

        with pytest.raises(httpx.RequestError):
            await fetch_page_text(test_url)

        mock_client_class.assert_called_once()
        mock_client.get.assert_called_once_with(test_url)
        mock_response.raise_for_status.assert_not_called()


@pytest.mark.anyio
class TestFetchAndCleanTextFromUrl:
    TEST_URL = "http://example.com/error-test"

    @pytest.fixture
    def mock_fetch_page_text(self):
        with patch(
            "meal_planner.main.fetch_page_text", new_callable=AsyncMock
        ) as mock_fetch:
            yield mock_fetch

    @pytest.fixture
    def mock_html_cleaner(self):
        with patch("meal_planner.main.HTML_CLEANER.handle") as mock_clean:
            yield mock_clean

    @pytest.mark.parametrize(
        "raised_exception, expected_caught_exception, expected_log_fragment",
        [
            pytest.param(
                httpx.RequestError("ReqErr", request=httpx.Request("GET", TEST_URL)),
                httpx.RequestError,
                "HTTP Request Error",
                id="request_error",
            ),
            pytest.param(
                httpx.HTTPStatusError(
                    "Not Found",
                    request=httpx.Request("GET", TEST_URL),
                    response=httpx.Response(
                        404, request=httpx.Request("GET", TEST_URL)
                    ),
                ),
                httpx.HTTPStatusError,
                "HTTP Status Error",
                id="status_error",
            ),
            pytest.param(
                Exception("Generic fetch error"),
                RuntimeError,
                "Error fetching page text",
                id="generic_fetch_exception",
            ),
        ],
    )
    @patch("meal_planner.main.logger.error")
    async def test_fetch_and_clean_errors(
        self,
        mock_logger_error,
        mock_fetch_page_text,
        mock_html_cleaner,
        raised_exception,
        expected_caught_exception,
        expected_log_fragment,
    ):
        mock_fetch_page_text.side_effect = raised_exception

        with pytest.raises(expected_caught_exception) as excinfo:
            await fetch_and_clean_text_from_url(self.TEST_URL)

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        log_message = args[0]
        log_args = args[1:]
        assert expected_log_fragment in log_message
        assert log_args[0] == self.TEST_URL
        assert raised_exception == log_args[1]
        assert kwargs.get("exc_info") is True

        if not isinstance(
            raised_exception, (httpx.RequestError, httpx.HTTPStatusError)
        ):
            mock_html_cleaner.assert_not_called()
        if expected_log_fragment == "Error fetching page text":
            assert f"Failed to fetch or process URL: {self.TEST_URL}" in str(
                excinfo.value
            )

    @patch("meal_planner.main.logger.error")
    async def test_fetch_and_clean_html_cleaner_error(
        self,
        mock_logger_error,
        mock_fetch_page_text,
        mock_html_cleaner,
    ):
        """Test that a generic exception during HTML cleaning is caught and raises
        RuntimeError."""
        mock_fetch_page_text.return_value = "<html></html>"
        cleaning_exception = Exception("HTML cleaning failed!")
        mock_html_cleaner.side_effect = cleaning_exception

        with pytest.raises(RuntimeError) as excinfo:
            await fetch_and_clean_text_from_url(self.TEST_URL)

        assert excinfo.value.__cause__ is cleaning_exception
        assert f"Failed to process URL content: {self.TEST_URL}" in str(excinfo.value)

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        assert "Error cleaning HTML text" in args[0]
        assert args[1] == self.TEST_URL
        assert args[2] is cleaning_exception
        assert kwargs.get("exc_info") is True

        mock_fetch_page_text.assert_called_once_with(self.TEST_URL)
        mock_html_cleaner.assert_called_once_with("<html></html>")


@pytest.mark.anyio
@patch("meal_planner.main.aclient.chat.completions.create", new_callable=AsyncMock)
@patch("meal_planner.main.logger.error")
async def test_get_structured_llm_response_api_error(mock_logger_error, mock_create):
    """Test that get_structured_llm_response catches and logs errors during the API
    call."""
    api_exception = Exception("Simulated API failure")
    mock_create.side_effect = api_exception
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


@pytest.fixture
def mock_recipe_data_fixture() -> RecipeBase:
    return RecipeBase(
        name="Mock Recipe",
        ingredients=["mock ingredient 1"],
        instructions=["mock instruction 1"],
    )


@pytest.mark.anyio
async def test_extract_run_returns_save_form(
    client: AsyncClient, monkeypatch, mock_recipe_data_fixture: RecipeBase
):
    async def mock_extract(*args, **kwargs):
        return mock_recipe_data_fixture

    monkeypatch.setattr(main_module, "extract_recipe_from_text", mock_extract)

    response = await client.post(
        RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: "some text"}
    )
    assert response.status_code == 200
    html_content = response.text

    assert 'id="edit-review-form"' in html_content
    assert 'id="name"' in html_content
    assert f'value="{mock_recipe_data_fixture.name}"' in html_content
    assert "<input" in html_content
    assert f'button hx-post="{RECIPES_SAVE_URL}"' in html_content
    assert ">Save Recipe</button>" in html_content


@pytest.mark.anyio
async def test_save_recipe_success(client: AsyncClient):
    form_data = {
        FIELD_NAME: "Saved Recipe Name",
        FIELD_INGREDIENTS: ["saved ing 1", "saved ing 2"],
        FIELD_INSTRUCTIONS: ["saved inst 1", "saved inst 2"],
    }

    save_response = await client.post(RECIPES_SAVE_URL, data=form_data)
    assert save_response.status_code == 200
    assert "Current Recipe Saved!" in save_response.text

    get_all_response = await client.get("/api/v0/recipes")
    assert get_all_response.status_code == 200
    all_recipes_data = get_all_response.json()

    saved_recipe_api_data = None
    for recipe in all_recipes_data:
        if recipe["name"] == form_data[FIELD_NAME]:
            saved_recipe_api_data = recipe
            break

    assert saved_recipe_api_data is not None, (
        f"Recipe named '{form_data[FIELD_NAME]}' not found in API response"
    )
    saved_recipe_id = saved_recipe_api_data["id"]
    assert isinstance(saved_recipe_id, int)

    get_one_response = await client.get(f"/api/v0/recipes/{saved_recipe_id}")
    assert get_one_response.status_code == 200
    fetched_recipe = get_one_response.json()

    assert fetched_recipe["name"] == form_data[FIELD_NAME]
    assert fetched_recipe["ingredients"] == form_data[FIELD_INGREDIENTS]
    assert fetched_recipe["instructions"] == form_data[FIELD_INSTRUCTIONS]
    assert fetched_recipe["id"] == saved_recipe_id


@pytest.mark.anyio
@pytest.mark.parametrize(
    "form_data, expected_error_message, test_id",
    [
        pytest.param(
            {FIELD_NAME: "Only Name"},
            "Invalid recipe data. Please check the fields.",
            "missing_ingredients",
            id="missing_ingredients",
        ),
        pytest.param(
            {FIELD_INGREDIENTS: ["i"], FIELD_INSTRUCTIONS: ["s"]},
            "Invalid recipe data. Please check the fields.",
            "missing_name",
            id="missing_name",
        ),
    ],
)
async def test_save_recipe_missing_data(
    client: AsyncClient, form_data: dict, expected_error_message: str, test_id: str
):
    response = await client.post(RECIPES_SAVE_URL, data=form_data)
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    error_span = soup.find("span", id="save-button-container")
    assert error_span is not None
    assert error_span.get_text(strip=True) == expected_error_message


@pytest.mark.anyio
async def test_save_recipe_api_call_error(client: AsyncClient, monkeypatch):
    """Test error handling when the internal API call fails."""
    mock_post = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "API Error",
            request=httpx.Request("POST", "/api/v0/recipes"),
            response=httpx.Response(500, content=b"Internal Server Error"),
        )
    )
    monkeypatch.setattr("meal_planner.main.internal_client.post", mock_post)

    form_data = {
        FIELD_NAME: "API Error Test",
        FIELD_INGREDIENTS: ["ingredient"],
        FIELD_INSTRUCTIONS: ["instruction"],
    }
    response = await client.post(RECIPES_SAVE_URL, data=form_data)
    assert response.status_code == 200
    assert "Could not save recipe. Please check input and try again." in response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalid_form_data, expected_error_message, test_id",
    [
        pytest.param(
            {FIELD_NAME: "", FIELD_INGREDIENTS: ["i1"], FIELD_INSTRUCTIONS: ["s1"]},
            "Invalid recipe data. Please check the fields.",
            "empty_name",
            id="empty_name",
        ),
        pytest.param(
            {FIELD_NAME: "Valid", FIELD_INGREDIENTS: [""], FIELD_INSTRUCTIONS: ["s1"]},
            "Invalid recipe data. Please check the fields.",
            "empty_ingredient",
            id="empty_ingredient",
        ),
    ],
)
async def test_save_recipe_validation_error(
    client: AsyncClient,
    invalid_form_data: dict,
    expected_error_message: str,
    test_id: str,
):
    """Test saving recipe with data that causes Pydantic validation errors."""
    response = await client.post(RECIPES_SAVE_URL, data=invalid_form_data)
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    error_span = soup.find("span", id="save-button-container")
    assert error_span is not None
    assert error_span.get_text(strip=True) == expected_error_message


@pytest.fixture
def mock_original_recipe_fixture() -> RecipeBase:
    return RecipeBase(
        name="Original Recipe",
        ingredients=["orig ing 1"],
        instructions=["orig inst 1"],
    )


@pytest.fixture
def mock_current_recipe_before_modify_fixture() -> RecipeBase:
    return RecipeBase(
        name="Current Recipe",
        ingredients=["curr ing 1"],
        instructions=["curr inst 1"],
    )


@pytest.fixture
def mock_llm_modified_recipe_fixture() -> RecipeBase:
    return RecipeBase(
        name="Modified",
        ingredients=["mod ing 1"],
        instructions=["mod inst 1"],
    )


@pytest.mark.anyio
class TestRecipeModifyEndpoint:
    @pytest.fixture
    def mock_get_structured_llm_response(self):
        with patch(
            "meal_planner.main.get_structured_llm_response", new_callable=AsyncMock
        ) as mock_llm:
            yield mock_llm

    def _build_modify_form_data(
        self,
        current_recipe: RecipeBase,
        original_recipe: RecipeBase,
        modification_prompt: str | None = None,
    ) -> dict:
        data = {
            FIELD_NAME: current_recipe.name,
            FIELD_INGREDIENTS: current_recipe.ingredients,
            FIELD_INSTRUCTIONS: current_recipe.instructions,
            FIELD_ORIGINAL_NAME: original_recipe.name,
            FIELD_ORIGINAL_INGREDIENTS: original_recipe.ingredients,
            FIELD_ORIGINAL_INSTRUCTIONS: original_recipe.instructions,
        }
        if modification_prompt is not None:
            data[FIELD_MODIFICATION_PROMPT] = modification_prompt
        return data

    @patch("meal_planner.main.logger.info")
    async def test_modify_success(
        self,
        mock_logger_info,
        client: AsyncClient,
        mock_get_structured_llm_response,
        mock_current_recipe_before_modify_fixture: RecipeBase,
        mock_original_recipe_fixture: RecipeBase,
        mock_llm_modified_recipe_fixture: RecipeBase,
    ):
        mock_get_structured_llm_response.return_value = mock_llm_modified_recipe_fixture
        test_prompt = "Make it spicier"
        form_data = self._build_modify_form_data(
            mock_current_recipe_before_modify_fixture,
            mock_original_recipe_fixture,
            test_prompt,
        )

        response = await client.post(RECIPES_MODIFY_URL, data=form_data)

        assert response.status_code == 200
        mock_get_structured_llm_response.assert_called_once_with(
            prompt=ANY, response_model=RecipeBase
        )
        call_args, call_kwargs = mock_get_structured_llm_response.call_args
        prompt_arg = call_kwargs.get("prompt", call_args[0] if call_args else None)
        assert mock_current_recipe_before_modify_fixture.markdown in prompt_arg
        assert test_prompt in prompt_arg

        assert f'value="{mock_llm_modified_recipe_fixture.name}"' in response.text
        assert 'id="name"' in response.text
        assert (
            f'<input type="hidden" name="{FIELD_ORIGINAL_NAME}"'
            f' value="{mock_original_recipe_fixture.name}"' in response.text
        )

        found_log = False
        for call in mock_logger_info.call_args_list:
            if ACTIVE_RECIPE_MODIFICATION_PROMPT_FILE in call.args:
                found_log = True
                break
        assert found_log, (
            f"Log message with prompt filename "
            f"'{ACTIVE_RECIPE_MODIFICATION_PROMPT_FILE}' not found."
        )

    async def test_modify_no_prompt(
        self,
        client: AsyncClient,
        mock_get_structured_llm_response,
        mock_current_recipe_before_modify_fixture: RecipeBase,
        mock_original_recipe_fixture: RecipeBase,
    ):
        form_data = self._build_modify_form_data(
            mock_current_recipe_before_modify_fixture, mock_original_recipe_fixture, ""
        )

        response = await client.post(RECIPES_MODIFY_URL, data=form_data)

        assert response.status_code == 200
        assert "Please enter modification instructions." in response.text
        assert f'class="{CSS_ERROR_CLASS} mt-2"' in response.text
        assert 'id="name"' in response.text
        assert (
            f'<input type="hidden" name="{FIELD_ORIGINAL_NAME}"'
            f' value="{mock_original_recipe_fixture.name}"' in response.text
        )
        mock_get_structured_llm_response.assert_not_called()

    async def test_modify_llm_error(
        self,
        client: AsyncClient,
        mock_get_structured_llm_response,
        mock_current_recipe_before_modify_fixture: RecipeBase,
        mock_original_recipe_fixture: RecipeBase,
    ):
        mock_get_structured_llm_response.side_effect = Exception(
            "LLM modification error"
        )
        test_prompt = "Cause an error"
        form_data = self._build_modify_form_data(
            mock_current_recipe_before_modify_fixture,
            mock_original_recipe_fixture,
            test_prompt,
        )

        response = await client.post(RECIPES_MODIFY_URL, data=form_data)

        assert response.status_code == 200
        assert (
            "Recipe modification failed. An unexpected error occurred." in response.text
        )
        assert f'class="{CSS_ERROR_CLASS} mt-2"' in response.text
        assert 'id="name"' in response.text
        assert (
            f'<input type="hidden" name="{FIELD_ORIGINAL_NAME}"'
            f' value="{mock_original_recipe_fixture.name}"' in response.text
        )
        mock_get_structured_llm_response.assert_called_once()

    async def test_modify_validation_error(
        self,
        client: AsyncClient,
        mock_current_recipe_before_modify_fixture: RecipeBase,
        mock_original_recipe_fixture: RecipeBase,
    ):
        """Test that a validation error during form parsing returns the correct
        HTML error."""
        form_data = self._build_modify_form_data(
            mock_current_recipe_before_modify_fixture,
            mock_original_recipe_fixture,
            "A valid prompt",
        )
        form_data[FIELD_NAME] = ""

        response = await client.post(RECIPES_MODIFY_URL, data=form_data)

        assert response.status_code == 200
        assert "Invalid recipe data. Please check the fields." in response.text
        assert CSS_ERROR_CLASS in response.text
        with patch(
            "meal_planner.main.get_structured_llm_response", new_callable=AsyncMock
        ) as local_mock_llm:
            local_mock_llm.assert_not_called()


@pytest.mark.anyio
@patch("meal_planner.main._parse_recipe_form_data")
async def test_modify_parsing_exception(mock_parse, client: AsyncClient):
    "Test generic exception during form parsing in post_modify_recipe."
    mock_parse.side_effect = Exception("Simulated parsing error")
    dummy_form_data = {FIELD_NAME: "Test", "original_name": "Orig"}

    response = await client.post(RECIPES_MODIFY_URL, data=dummy_form_data)

    assert response.status_code == 200
    assert "Critical error processing form." in response.text
    assert CSS_ERROR_CLASS in response.text
    assert mock_parse.call_count == 2


@pytest.mark.anyio
async def test_modify_critical_failure(client: AsyncClient):
    """Test critical failure during form parsing in post_modify_recipe."""
    with patch("meal_planner.main._parse_and_validate_modify_form") as mock_validate:
        mock_validate.side_effect = ModifyFormError("Form validation error")

        with patch("meal_planner.main._parse_recipe_form_data") as mock_parse:
            mock_parse.side_effect = Exception("Critical parsing error")

            response = await client.post(RECIPES_MODIFY_URL, data={"name": "Test"})

            assert response.status_code == 200
            assert "Critical error processing form." in response.text
            assert CSS_ERROR_CLASS in response.text

            # Verify the functions were called
            mock_validate.assert_called_once()
            mock_parse.assert_called_once()


class TestGenerateDiffHtml:
    def _to_comparable(self, items: list[Any]) -> list[tuple[str, str]]:
        """Converts items (strings/FT objects) to a list of (type_name_str, content_str)
        tuples for comparison."""
        result = []
        for item in items:
            if isinstance(item, str):
                result.append(("str", item))
            elif isinstance(item, FT):
                result.append((item.tag, item.children[0]))
            else:
                result.append((type(item).__name__, str(item)))
        return result

    def test_diff_insert(self):
        before = "line1\nline3"
        after = "line1\nline2\nline3"
        before_items, after_items = main_module.generate_diff_html(before, after)
        assert self._to_comparable(before_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("str", "line3"),
        ]
        assert self._to_comparable(after_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("ins", "line2"),
            ("str", "\n"),
            ("str", "line3"),
        ]

    def test_diff_delete(self):
        before = "line1\nline2\nline3"
        after = "line1\nline3"
        before_items, after_items = main_module.generate_diff_html(before, after)
        assert self._to_comparable(before_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("del", "line2"),
            ("str", "\n"),
            ("str", "line3"),
        ]
        assert self._to_comparable(after_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("str", "line3"),
        ]

    def test_diff_replace(self):
        before = "line1\nline TWO\nline3"
        after = "line1\nline 2\nline3"
        before_items, after_items = main_module.generate_diff_html(before, after)
        assert self._to_comparable(before_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("del", "line TWO"),
            ("str", "\n"),
            ("str", "line3"),
        ]
        assert self._to_comparable(after_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("ins", "line 2"),
            ("str", "\n"),
            ("str", "line3"),
        ]

    def test_diff_equal(self):
        before = "line1\nline2"
        after = "line1\nline2"
        before_items, after_items = main_module.generate_diff_html(before, after)
        assert self._to_comparable(before_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("str", "line2"),
        ]
        assert self._to_comparable(after_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("str", "line2"),
        ]

    def test_diff_combined(self):
        before = "line1\nline to delete\nline3\nline4"
        after = "line1\nline3\nline inserted\nline4"
        before_items, after_items = main_module.generate_diff_html(before, after)
        assert self._to_comparable(before_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("del", "line to delete"),
            ("str", "\n"),
            ("str", "line3"),
            ("str", "\n"),
            ("str", "line4"),
        ]
        assert self._to_comparable(after_items) == [
            ("str", "line1"),
            ("str", "\n"),
            ("str", "line3"),
            ("str", "\n"),
            ("ins", "line inserted"),
            ("str", "\n"),
            ("str", "line4"),
        ]


class TestParseRecipeFormData:
    def test_parse_basic(self):
        form_data = FormData(
            [
                ("name", "Test Recipe"),
                ("ingredients", "Ing 1"),
                ("ingredients", "Ing 2"),
                ("instructions", "Step 1"),
                ("instructions", "Step 2"),
            ]
        )
        parsed_data = _parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Test Recipe",
            "ingredients": ["Ing 1", "Ing 2"],
            "instructions": ["Step 1", "Step 2"],
        }
        RecipeBase(**parsed_data)

    def test_parse_with_prefix(self):
        form_data = FormData(
            [
                ("original_name", "Original Name"),
                ("original_ingredients", "Orig Ing 1"),
                ("original_instructions", "Orig Step 1"),
                ("name", "Current Name"),
            ]
        )
        parsed_data = _parse_recipe_form_data(form_data, prefix="original_")
        assert parsed_data == {
            "name": "Original Name",
            "ingredients": ["Orig Ing 1"],
            "instructions": ["Orig Step 1"],
        }
        RecipeBase(**parsed_data)

    def test_parse_missing_fields(self):
        form_data = FormData([("name", "Only Name")])
        parsed_data = _parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "Only Name",
            "ingredients": [],
            "instructions": [],
        }

    def test_parse_empty_strings_and_whitespace(self):
        form_data = FormData(
            [
                ("name", "  Spaced Name  "),
                ("ingredients", "Real Ing"),
                ("ingredients", "  "),
                ("ingredients", ""),
                ("instructions", "Real Step"),
                ("instructions", "  "),
                ("instructions", ""),
            ]
        )
        parsed_data = _parse_recipe_form_data(form_data)
        assert parsed_data == {
            "name": "  Spaced Name  ",
            "ingredients": ["Real Ing"],
            "instructions": ["Real Step"],
        }
        RecipeBase(**parsed_data)

    def test_parse_empty_form(self):
        form_data = FormData([])
        parsed_data = _parse_recipe_form_data(form_data)
        assert parsed_data == {"name": "", "ingredients": [], "instructions": []}
        with pytest.raises(ValidationError):
            RecipeBase(**parsed_data)


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

    def test_postprocess_instructions(self):
        recipe = RecipeBase(
            name="Test Name",
            ingredients=["Ing 1"],
            instructions=[
                " Step 1: Basic step. ",
                "2. Step with number.",
                "  Step 3 Another step.",
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
            "Has comma, in middle",
        ]


@pytest.mark.anyio
class TestRecipeUIFragments:
    ADD_INGREDIENT_URL = "/recipes/ui/add-ingredient"
    ADD_INSTRUCTION_URL = "/recipes/ui/add-instruction"
    DELETE_INGREDIENT_BASE_URL = "/recipes/ui/delete-ingredient"
    DELETE_INSTRUCTION_BASE_URL = "/recipes/ui/delete-instruction"
    # TOUCH_NAME_URL = "/recipes/ui/touch-name" # Commented out as per previous steps

    async def test_add_ingredient(self, client: AsyncClient):
        form_data = _build_ui_fragment_form_data(
            ingredients=["existing ing"], instructions=["step1"]
        )
        response = await client.post(self.ADD_INGREDIENT_URL, data=form_data)
        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")

        ingredients_list_div = soup.find("div", id="ingredients-list")
        assert ingredients_list_div, "Ingredients list div not found"
        assert isinstance(ingredients_list_div, Tag)
        ingredient_inputs = ingredients_list_div.find_all(
            "input", {"name": "ingredients"}
        )
        assert len(ingredient_inputs) == 2, (
            f"Expected 2 ingredient inputs, got {len(ingredient_inputs)}"
        )

        new_ingredient_input = ingredient_inputs[-1]
        assert isinstance(new_ingredient_input, Tag)
        assert new_ingredient_input.get("value", "") == ""
        assert new_ingredient_input["placeholder"] == "Ingredient"

        new_item_div = new_ingredient_input.find_parent("div", class_="flex")
        assert new_item_div, "Parent div for new ingredient not found"
        assert isinstance(new_item_div, Tag)
        delete_button = new_item_div.find(
            "button",
            {
                "hx-post": lambda x: bool(
                    x and x.startswith(f"{self.DELETE_INGREDIENT_BASE_URL}/")
                )
            },
        )
        assert delete_button, "Delete button for new ingredient not found"
        assert isinstance(delete_button, Tag)

        # Restore and correct assertions
        icon_element = delete_button.find("uk-icon", attrs={"icon": "minus-circle"})
        assert icon_element, (
            "UkIcon 'minus-circle' not found in ingredient delete button"
        )
        assert isinstance(icon_element, Tag)
        class_list = icon_element.get("class")
        if class_list is None:
            class_list = []
        assert str(mu.TextT.error) in class_list

        oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#diff-content-wrapper"})
        assert oob_div, "OOB diff wrapper not found"
        assert isinstance(oob_div, Tag)
        assert oob_div.find("pre", id="diff-before-pre"), "Diff before pre not found"
        assert oob_div.find("pre", id="diff-after-pre"), "Diff after pre not found"

    async def test_add_instruction(self, client: AsyncClient):
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["existing step"]
        )
        response = await client.post(self.ADD_INSTRUCTION_URL, data=form_data)
        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")

        instructions_list_div = soup.find("div", id="instructions-list")
        assert instructions_list_div, "Instructions list div not found"
        assert isinstance(instructions_list_div, Tag)
        instruction_textareas = instructions_list_div.find_all(
            "textarea", {"name": "instructions"}
        )
        assert len(instruction_textareas) == 2, (
            f"Expected 2 instruction textareas, got {len(instruction_textareas)}"
        )

        new_instruction_textarea = instruction_textareas[-1]
        assert isinstance(new_instruction_textarea, Tag)
        assert new_instruction_textarea.text == ""
        assert new_instruction_textarea["placeholder"] == "Instruction Step"

        new_item_div = new_instruction_textarea.find_parent("div", class_="flex")
        assert new_item_div, "Parent div for new instruction not found"
        assert isinstance(new_item_div, Tag)
        delete_button = new_item_div.find(
            "button",
            {
                "hx-post": lambda x: bool(
                    x and x.startswith(f"{self.DELETE_INSTRUCTION_BASE_URL}/")
                )
            },
        )
        assert delete_button, "Delete button for new instruction not found"
        assert isinstance(delete_button, Tag)
        icon_element = delete_button.find("uk-icon", attrs={"icon": "minus-circle"})
        assert icon_element, (
            "UkIcon 'minus-circle' not found in instruction delete button"
        )
        assert isinstance(icon_element, Tag)
        class_list = icon_element.get("class")
        if class_list is None:
            class_list = []
        assert str(mu.TextT.error) in class_list

        oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#diff-content-wrapper"})
        assert oob_div, "OOB diff wrapper not found"
        assert isinstance(oob_div, Tag)
        assert oob_div.find("pre", id="diff-before-pre"), "Diff before pre not found"
        assert oob_div.find("pre", id="diff-after-pre"), "Diff after pre not found"

    async def test_delete_ingredient(self, client: AsyncClient):
        initial_ingredients = ["ing_to_keep1", "ing_to_delete", "ing_to_keep2"]
        form_data = _build_ui_fragment_form_data(
            ingredients=initial_ingredients, instructions=["step1"]
        )
        index_to_delete = 1  # "ing_to_delete"

        response = await client.post(
            f"{self.DELETE_INGREDIENT_BASE_URL}/{index_to_delete}", data=form_data
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")

        ingredients_list_div = soup.find("div", id="ingredients-list")
        assert ingredients_list_div, "Ingredients list div for delete not found"
        assert isinstance(ingredients_list_div, Tag)
        ingredient_inputs = ingredients_list_div.find_all(
            "input", {"name": "ingredients"}
        )
        assert len(ingredient_inputs) == 2, (
            f"Expected 2 ingredients after delete, got {len(ingredient_inputs)}"
        )

        rendered_ingredient_values = [
            cast(Tag, inp)["value"] for inp in ingredient_inputs
        ]
        assert "ing_to_keep1" in rendered_ingredient_values
        assert "ing_to_keep2" in rendered_ingredient_values
        assert "ing_to_delete" not in rendered_ingredient_values

        oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#diff-content-wrapper"})
        assert oob_div, "OOB diff wrapper for delete not found"
        assert isinstance(oob_div, Tag)
        assert oob_div.find("pre", id="diff-before-pre"), (
            "Diff before pre for delete not found"
        )
        assert oob_div.find("pre", id="diff-after-pre"), (
            "Diff after pre for delete not found"
        )

    async def test_delete_instruction(self, client: AsyncClient):
        initial_instructions = ["step_to_keep1", "step_to_delete", "step_to_keep2"]
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=initial_instructions
        )
        index_to_delete = 1  # "step_to_delete"

        response = await client.post(
            f"{self.DELETE_INSTRUCTION_BASE_URL}/{index_to_delete}", data=form_data
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")

        instructions_list_div = soup.find("div", id="instructions-list")
        assert instructions_list_div, "Instructions list div for delete not found"
        assert isinstance(instructions_list_div, Tag)
        instruction_textareas = instructions_list_div.find_all(
            "textarea", {"name": "instructions"}
        )
        assert len(instruction_textareas) == 2, (
            f"Expected 2 instructions after delete, got {len(instruction_textareas)}"
        )

        rendered_instruction_values = [ta.text for ta in instruction_textareas]
        assert "step_to_keep1" in rendered_instruction_values
        assert "step_to_keep2" in rendered_instruction_values
        assert "step_to_delete" not in rendered_instruction_values

        oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#diff-content-wrapper"})
        assert oob_div, "OOB diff wrapper for delete not found"
        assert isinstance(oob_div, Tag)
        assert oob_div.find("pre", id="diff-before-pre"), (
            "Diff before pre for delete not found"
        )
        assert oob_div.find("pre", id="diff-after-pre"), (
            "Diff after pre for delete not found"
        )

    @pytest.mark.parametrize("invalid_index", [5])
    @patch("meal_planner.main.logger.warning")
    async def test_delete_ingredient_invalid_index(
        self, mock_logger_warning, client: AsyncClient, invalid_index: int
    ):
        initial_ingredients = ["ing1", "ing2"]
        form_data = _build_ui_fragment_form_data(
            ingredients=initial_ingredients, instructions=["step1"]
        )

        response = await client.post(
            f"{self.DELETE_INGREDIENT_BASE_URL}/{invalid_index}", data=form_data
        )
        assert (
            response.status_code == 200
        )  # Route still returns successfully with current items
        soup = BeautifulSoup(response.text, "html.parser")
        ingredient_inputs = soup.find_all("input", {"name": "ingredients"})
        assert len(ingredient_inputs) == len(initial_ingredients)  # No change
        mock_logger_warning.assert_called_once_with(
            f"Attempted to delete ingredient at invalid index {invalid_index}"
        )

    @pytest.mark.parametrize("invalid_index", [5])
    @patch("meal_planner.main.logger.warning")
    async def test_delete_instruction_invalid_index(
        self, mock_logger_warning, client: AsyncClient, invalid_index: int
    ):
        initial_instructions = ["inst1", "inst2"]
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=initial_instructions
        )

        response = await client.post(
            f"{self.DELETE_INSTRUCTION_BASE_URL}/{invalid_index}", data=form_data
        )
        assert (
            response.status_code == 200
        )  # Route still returns successfully with current items
        soup = BeautifulSoup(response.text, "html.parser")
        instruction_textareas = soup.find_all("textarea", {"name": "instructions"})
        assert len(instruction_textareas) == len(initial_instructions)  # No change
        mock_logger_warning.assert_called_once_with(
            f"Attempted to delete instruction at invalid index {invalid_index}"
        )

    @patch("meal_planner.main._parse_recipe_form_data")
    @patch("meal_planner.main.logger.error")
    async def test_delete_ingredient_validation_error(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        validation_exc = ValidationError.from_exception_data(
            title="TestVE_del_ing", line_errors=[]
        )
        # Initial form data for the test
        initial_ingredients = ["ing1_to_delete", "ing2_remains"]
        form_data_dict = _build_ui_fragment_form_data(
            ingredients=initial_ingredients, instructions=["s1"]
        )

        # Mock _parse_recipe_form_data:
        # 1st call (in try block of main.py): raises ValidationError
        # 2nd call (in except ValidationError block): returns the original form data
        mock_parse.side_effect = [
            validation_exc,
            form_data_dict.copy(),
        ]
        index_to_delete = 0

        response = await client.post(
            f"{self.DELETE_INGREDIENT_BASE_URL}/{index_to_delete}", data=form_data_dict
        )
        assert response.status_code == 200
        assert "Error updating list after delete. Validation failed." in response.text
        assert CSS_ERROR_CLASS in response.text

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        expected_log_msg_fragment = "Validation error processing ingredient deletion"
        assert expected_log_msg_fragment in args[0]
        assert str(validation_exc) in args[0]
        assert kwargs.get("exc_info") is True

        soup = BeautifulSoup(response.text, "html.parser")
        # Check that the list is re-rendered with original items
        ingredients_list_div = soup.find("div", id="ingredients-list")
        assert ingredients_list_div, "Ingredients list div for error case not found"
        assert isinstance(ingredients_list_div, Tag)
        ingredient_inputs = ingredients_list_div.find_all(
            "input", {"name": "ingredients"}
        )
        assert len(ingredient_inputs) == len(initial_ingredients)  # Original count

        # Check NO OOB diff content
        oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#diff-content-wrapper"})
        assert not oob_div, "OOB diff wrapper should NOT be present on validation error"

    @patch("meal_planner.main._parse_recipe_form_data")
    @patch("meal_planner.main.logger.error")
    async def test_delete_ingredient_generic_exception(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        generic_exc = Exception("Generic parse error for del_ing")
        mock_parse.side_effect = (
            generic_exc  # Only called once in the try block for this case
        )
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["s1"]
        )
        index_to_delete = 0

        response = await client.post(
            f"{self.DELETE_INGREDIENT_BASE_URL}/{index_to_delete}", data=form_data
        )
        assert response.status_code == 200
        assert "Error processing delete request." in response.text
        assert CSS_ERROR_CLASS in response.text

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        expected_log_msg = (
            f"Error deleting ingredient at index {index_to_delete}: {generic_exc}"
        )
        assert args[0] == expected_log_msg
        assert kwargs.get("exc_info") is True

    @patch("meal_planner.main._parse_recipe_form_data")
    @patch("meal_planner.main.logger.error")
    async def test_delete_instruction_validation_error(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        validation_exc = ValidationError.from_exception_data(
            title="TestVE_del_inst", line_errors=[]
        )
        # Initial form data for the test
        initial_instructions = ["s1_to_delete", "s2_remains"]
        form_data_dict = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=initial_instructions
        )

        # Mock _parse_recipe_form_data:
        # 1st call (in try block of main.py): raises ValidationError
        # 2nd call (in except ValidationError block): returns the original form data
        mock_parse.side_effect = [
            validation_exc,
            form_data_dict.copy(),
        ]
        index_to_delete = 0

        response = await client.post(
            f"{self.DELETE_INSTRUCTION_BASE_URL}/{index_to_delete}", data=form_data_dict
        )
        assert response.status_code == 200
        assert "Error updating list after delete. Validation failed." in response.text
        assert CSS_ERROR_CLASS in response.text

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        expected_log_msg_fragment = "Validation error processing instruction deletion"
        assert expected_log_msg_fragment in args[0]
        assert str(validation_exc) in args[0]
        assert kwargs.get("exc_info") is True

        soup = BeautifulSoup(response.text, "html.parser")
        # Check that the list is re-rendered with original items
        instructions_list_div = soup.find("div", id="instructions-list")
        assert instructions_list_div, "Instructions list div for error case not found"
        assert isinstance(instructions_list_div, Tag)
        instruction_textareas = instructions_list_div.find_all(
            "textarea", {"name": "instructions"}
        )
        assert len(instruction_textareas) == len(initial_instructions)  # Original count

        # Check NO OOB diff content
        oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#diff-content-wrapper"})
        assert not oob_div, "OOB diff wrapper should NOT be present on validation error"

    @patch("meal_planner.main._parse_recipe_form_data")
    @patch("meal_planner.main.logger.error")
    async def test_delete_instruction_generic_exception(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        generic_exc = Exception("Generic parse error for del_inst")
        mock_parse.side_effect = generic_exc  # Only called once in the try block
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["s1"]
        )
        index_to_delete = 0

        response = await client.post(
            f"{self.DELETE_INSTRUCTION_BASE_URL}/{index_to_delete}", data=form_data
        )
        assert response.status_code == 200
        assert "Error processing delete request." in response.text
        assert CSS_ERROR_CLASS in response.text

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        expected_log_msg = (
            f"Error deleting instruction at index {index_to_delete}: {generic_exc}"
        )
        assert args[0] == expected_log_msg
        assert kwargs.get("exc_info") is True

    @patch("meal_planner.main._parse_recipe_form_data")
    @patch("meal_planner.main.logger.error")
    async def test_add_ingredient_validation_error(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        validation_exc = ValidationError.from_exception_data(
            title="TestVE_add_ing", line_errors=[]
        )
        mock_parse.side_effect = [
            validation_exc,
            _build_ui_fragment_form_data(ingredients=["fallback_ing"]),
        ]
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["s1"]
        )

        response = await client.post(self.ADD_INGREDIENT_URL, data=form_data)
        assert response.status_code == 200
        assert "Error updating list after add." in response.text
        assert CSS_ERROR_CLASS in response.text

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        expected_log_msg = (
            f"Validation error processing ingredient addition: {validation_exc}"
        )
        assert args[0] == expected_log_msg
        assert kwargs.get("exc_info") is True

    @patch("meal_planner.main._parse_recipe_form_data")
    @patch("meal_planner.main.logger.error")
    async def test_add_ingredient_generic_exception(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        generic_exc = Exception("Generic parse error for add_ing")
        mock_parse.side_effect = generic_exc  # Only called once
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["s1"]
        )

        response = await client.post(self.ADD_INGREDIENT_URL, data=form_data)
        assert response.status_code == 200
        assert "Error processing add request." in response.text
        assert CSS_ERROR_CLASS in response.text

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        expected_log_msg = f"Error adding ingredient: {generic_exc}"
        assert args[0] == expected_log_msg
        assert kwargs.get("exc_info") is True

    @patch("meal_planner.main._parse_recipe_form_data")
    @patch("meal_planner.main.logger.error")
    async def test_add_instruction_validation_error(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        validation_exc = ValidationError.from_exception_data(
            title="TestVE_add_inst", line_errors=[]
        )
        mock_parse.side_effect = [
            validation_exc,
            _build_ui_fragment_form_data(instructions=["fallback_inst"]),
        ]
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["s1"]
        )

        response = await client.post(self.ADD_INSTRUCTION_URL, data=form_data)
        assert response.status_code == 200
        assert "Error updating list after add." in response.text
        assert CSS_ERROR_CLASS in response.text

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        expected_log_msg = (
            f"Validation error processing instruction addition: {validation_exc}"
        )
        assert args[0] == expected_log_msg
        assert kwargs.get("exc_info") is True

    @patch("meal_planner.main._parse_recipe_form_data")
    @patch("meal_planner.main.logger.error")
    async def test_add_instruction_generic_exception(
        self, mock_logger_error, mock_parse, client: AsyncClient
    ):
        generic_exc = Exception("Generic parse error for add_inst")
        mock_parse.side_effect = generic_exc  # Only called once
        form_data = _build_ui_fragment_form_data(
            ingredients=["ing1"], instructions=["s1"]
        )

        response = await client.post(self.ADD_INSTRUCTION_URL, data=form_data)
        assert response.status_code == 200
        assert "Error processing add request." in response.text
        assert CSS_ERROR_CLASS in response.text

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        expected_log_msg = f"Error adding instruction: {generic_exc}"
        assert args[0] == expected_log_msg
        assert kwargs.get("exc_info") is True

    async def test_delete_instruction_missing_ingredients_in_form(
        self, client: AsyncClient
    ):
        """Test successful instruction deletion when form data initially lacks
        ingredients fields."""
        initial_instructions = ["step_to_keep1", "step_to_delete", "step_to_keep2"]
        index_to_delete = 1  # This index is for the `try` block's attempt.

        form_data_dict = {
            "name": "Test Recipe Name",
            "instructions": initial_instructions,
            "original_name": "Test Recipe Name",
            "original_instructions": initial_instructions,
        }

        response = await client.post(
            f"{self.DELETE_INSTRUCTION_BASE_URL}/{index_to_delete}", data=form_data_dict
        )
        assert response.status_code == 200  # The route itself succeeds
        soup = BeautifulSoup(response.text, "html.parser")

        # This scenario now falls into the ValidationError in main.py because
        # RecipeData(name="...", ingredients=[], instructions=["s1","s2"]) will fail.
        # The `except ValidationError` block in `main.py` now re-renders the
        # list based on the original form data (before delete attempt).
        assert "Error updating list after delete. Validation failed." in response.text

        instructions_list_div = soup.find("div", id="instructions-list")
        assert instructions_list_div, "Instructions list div for delete error not found"
        assert isinstance(instructions_list_div, Tag)
        instruction_textareas = instructions_list_div.find_all(
            "textarea", {"name": "instructions"}
        )
        assert len(instruction_textareas) == len(initial_instructions)

        # Check NO OOB diff content
        oob_div = soup.find("div", {"hx-swap-oob": "innerHTML:#diff-content-wrapper"})
        assert not oob_div, (
            "OOB diff wrapper should NOT be present on validation error path"
        )


@pytest.mark.anyio
class TestRecipeUpdateDiff:
    UPDATE_DIFF_URL = "/recipes/ui/update-diff"

    def _build_diff_form_data(
        self, current: RecipeBase, original: RecipeBase | None = None
    ) -> dict:
        if original is None:
            original = current
        form_data = {
            "name": current.name,
            "ingredients": current.ingredients,
            "instructions": current.instructions,
            "original_name": original.name,
            "original_ingredients": original.ingredients,
            "original_instructions": original.instructions,
        }
        return form_data

    async def test_diff_no_changes(self, client: AsyncClient):
        recipe = RecipeBase(name="Same", ingredients=["i1"], instructions=["s1"])
        form_data = self._build_diff_form_data(recipe, recipe)

        response = await client.post(self.UPDATE_DIFF_URL, data=form_data)
        assert response.status_code == 200
        html = response.text  # Change back from response_text
        assert '<pre id="diff-before-pre"' in html
        assert '<pre id="diff-after-pre"' in html
        assert "<del>" not in html
        assert "<ins>" not in html
        assert "# Same" in html
        assert "- i1" in html
        assert "- s1" in html

    async def test_diff_addition(self, client: AsyncClient):
        original = RecipeBase(name="Orig", ingredients=["i1"], instructions=["s1"])
        current = RecipeBase(
            name="Current", ingredients=["i1", "i2"], instructions=["s1", "s2"]
        )
        form_data = self._build_diff_form_data(current, original)

        response = await client.post(self.UPDATE_DIFF_URL, data=form_data)
        assert response.status_code == 200
        html = response.text  # Change back
        assert '<pre id="diff-before-pre"' in html
        assert '<pre id="diff-after-pre"' in html
        assert "<del># Orig</del>" in html
        assert "<ins># Current</ins>" in html
        assert "- i1" in html
        assert "<ins>- i2</ins>" in html
        assert "- s1" in html
        assert "<ins>- s2</ins>" in html

    async def test_diff_deletion(self, client: AsyncClient):
        original = RecipeBase(
            name="Orig", ingredients=["i1", "i2"], instructions=["s1", "s2"]
        )
        current = RecipeBase(name="Current", ingredients=["i1"], instructions=["s1"])
        form_data = self._build_diff_form_data(current, original)

        response = await client.post(self.UPDATE_DIFF_URL, data=form_data)
        assert response.status_code == 200
        html = response.text  # Change back
        assert '<pre id="diff-before-pre"' in html
        assert '<pre id="diff-after-pre"' in html
        assert "<del># Orig</del>" in html
        assert "<ins># Current</ins>" in html
        assert "- i1" in html
        assert "<del>- i2</del>" in html
        assert "- s1" in html
        assert "<del>- s2</del>" in html

    async def test_diff_modification(self, client: AsyncClient):
        original = RecipeBase(name="Orig", ingredients=["i1"], instructions=["s1"])
        current = RecipeBase(
            name="Current", ingredients=["i1_mod"], instructions=["s1_mod"]
        )
        form_data = self._build_diff_form_data(current, original)

        response = await client.post(self.UPDATE_DIFF_URL, data=form_data)
        assert response.status_code == 200
        html = response.text  # Change back
        assert '<pre id="diff-before-pre"' in html
        assert '<pre id="diff-after-pre"' in html
        assert "<del># Orig</del>" in html
        assert "<ins># Current</ins>" in html
        assert "<del>- i1</del>" in html
        assert "<ins>- i1_mod</ins>" in html
        assert "<del>- s1</del>" in html
        assert "<ins>- s1_mod</ins>" in html

    @patch("meal_planner.main._build_diff_content_children")
    @patch("meal_planner.main.logger.error")
    async def test_diff_generation_error(
        self, mock_logger_error, mock_build_diff, client: AsyncClient
    ):
        diff_exception = Exception("Simulated diff error")
        mock_build_diff.side_effect = diff_exception
        recipe = RecipeBase(name="Error Recipe", ingredients=["i"], instructions=["s"])
        form_data = self._build_diff_form_data(recipe, recipe)

        response = await client.post(self.UPDATE_DIFF_URL, data=form_data)
        assert response.status_code == 200
        html = response.text
        assert f'class="{CSS_ERROR_CLASS}"' in html
        assert "Error updating diff view" in html

        mock_build_diff.assert_called_once()
        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        assert args[0] == "Error updating diff: %s"
        assert args[1] is diff_exception
        assert kwargs.get("exc_info") is True

    @pytest.mark.parametrize(
        "invalid_field, invalid_value, error_title_suffix",
        [
            pytest.param(FIELD_NAME, "", "curr_name", id="current_empty_name"),
            pytest.param(
                FIELD_INGREDIENTS, [""], "curr_ing", id="current_empty_ingredient"
            ),
            pytest.param(
                FIELD_ORIGINAL_NAME, "", "orig_name", id="original_empty_name"
            ),
            pytest.param(
                FIELD_ORIGINAL_INGREDIENTS,
                [""],
                "orig_ing",
                id="original_empty_ingredient",
            ),
        ],
    )
    @patch("meal_planner.main.logger.warning")
    async def test_update_diff_validation_error(
        self,
        mock_logger_warning,
        client: AsyncClient,
        invalid_field: str,
        invalid_value: str | list[str],
        error_title_suffix: str,
    ):
        """Test that update diff returns 200 OK even with empty list inputs,
        as validation might happen later."""
        valid_recipe = RecipeBase(name="Valid", ingredients=["i"], instructions=["s"])
        form_data = self._build_diff_form_data(valid_recipe, valid_recipe)
        form_data[invalid_field] = invalid_value

        response = await client.post(self.UPDATE_DIFF_URL, data=form_data)

        assert response.status_code == 200
        html = response.text
        assert "Recipe state invalid for diff. Please check all fields." in html
        assert "diff-content-wrapper" not in html

        mock_logger_warning.assert_called_once()
        args, kwargs = mock_logger_warning.call_args
        assert args[0] == "Validation error during diff update: %s"
        assert isinstance(args[1], ValidationError)
        assert kwargs.get("exc_info") is False


@pytest.mark.anyio
@patch("meal_planner.main._parse_recipe_form_data")
async def test_update_diff_parsing_exception(mock_parse, client: AsyncClient):
    "Test generic exception during form parsing in post_update_diff."
    mock_parse.side_effect = Exception("Simulated parsing error")
    dummy_form_data = {FIELD_NAME: "Test", "original_name": "Orig"}

    response = await client.post(
        TestRecipeUpdateDiff.UPDATE_DIFF_URL, data=dummy_form_data
    )

    assert response.status_code == 200
    assert "Error updating diff view." in response.text
    assert CSS_ERROR_CLASS in response.text
    assert mock_parse.call_count == 1


@pytest.mark.anyio
@patch("meal_planner.main._parse_recipe_form_data")
async def test_save_recipe_parsing_exception(mock_parse, client: AsyncClient):
    "Test generic exception during form parsing in post_save_recipe."
    mock_parse.side_effect = Exception("Simulated parsing error")
    dummy_form_data = {
        FIELD_NAME: "Test",
        FIELD_INGREDIENTS: ["i"],
        FIELD_INSTRUCTIONS: ["s"],
    }

    response = await client.post(RECIPES_SAVE_URL, data=dummy_form_data)

    assert response.status_code == 200
    assert "Error processing form data." in response.text
    assert CSS_ERROR_CLASS in response.text
    mock_parse.assert_called_once()


def test_build_edit_review_form_no_original():
    "Test hitting the `original_recipe = current_recipe` line."
    current = RecipeBase(name="Test", ingredients=["i"], instructions=["s"])
    result = main_module._build_edit_review_form(current)
    assert result is not None


def test_build_edit_review_form_with_original():
    """Test hitting the logic where original_recipe is provided."""
    current = RecipeBase(
        name="Updated Name", ingredients=["i1", "i2"], instructions=["s1"]
    )
    original = RecipeBase(
        name="Original Name", ingredients=["i1"], instructions=["s1", "s2"]
    )
    result = main_module._build_edit_review_form(current, original)
    assert result is not None


@pytest.mark.anyio
class TestGetRecipesPageErrors:
    @patch("meal_planner.main.internal_client.get")
    async def test_get_recipes_page_api_status_error(
        self, mock_api_get, client: AsyncClient
    ):
        "Test error handling when the API call returns a status error."
        mock_api_get.side_effect = httpx.HTTPStatusError(
            "API Error",
            request=httpx.Request("GET", "/api/v0/recipes"),
            response=httpx.Response(500),
        )
        response = await client.get(RECIPES_LIST_PATH)
        assert response.status_code == 200
        assert "Error fetching recipes from API." in response.text
        assert CSS_ERROR_CLASS in response.text
        mock_api_get.assert_awaited_once_with("/api/v0/recipes")

    @patch("meal_planner.main.internal_client.get")
    async def test_get_recipes_page_api_generic_error(
        self, mock_api_get, client: AsyncClient
    ):
        "Test error handling when the API call raises a generic exception."
        mock_api_get.side_effect = Exception("Unexpected API failure")
        response = await client.get(RECIPES_LIST_PATH)
        assert response.status_code == 200
        assert "An unexpected error occurred while fetching recipes." in response.text
        assert CSS_ERROR_CLASS in response.text
        mock_api_get.assert_awaited_once_with("/api/v0/recipes")


@pytest.mark.anyio
class TestGetSingleRecipePageErrors:
    RECIPE_ID = 123
    API_URL = f"/api/v0/recipes/{RECIPE_ID}"
    PAGE_URL = f"/recipes/{RECIPE_ID}"

    @patch("meal_planner.main.internal_client.get")
    async def test_get_single_recipe_page_api_404(
        self, mock_api_get, client: AsyncClient
    ):
        """Test handling when the API returns 404 for the recipe ID."""
        mock_api_get.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=httpx.Request("GET", self.API_URL),
            response=httpx.Response(404),
        )
        response = await client.get(self.PAGE_URL)
        assert response.status_code == 200
        assert "Recipe Not Found" in response.text
        mock_api_get.assert_awaited_once_with(self.API_URL)

    @patch("meal_planner.main.internal_client.get")
    async def test_get_single_recipe_page_api_other_status_error(
        self, mock_api_get, client: AsyncClient
    ):
        """Test handling when the API returns a non-404 status error."""
        mock_api_get.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=httpx.Request("GET", self.API_URL),
            response=httpx.Response(500),
        )
        response = await client.get(self.PAGE_URL)
        assert response.status_code == 200
        assert "Error fetching recipe from API." in response.text
        assert "Error" in response.text
        mock_api_get.assert_awaited_once_with(self.API_URL)

    @patch("meal_planner.main.internal_client.get")
    async def test_get_single_recipe_page_api_generic_error(
        self, mock_api_get, client: AsyncClient
    ):
        """Test handling when the API call raises a generic exception."""
        mock_api_get.side_effect = Exception("Unexpected API failure")
        response = await client.get(self.PAGE_URL)
        assert response.status_code == 200
        assert "An unexpected error occurred." in response.text
        mock_api_get.assert_awaited_once_with(self.API_URL)


@pytest.mark.anyio
async def test_save_recipe_api_call_generic_error(client: AsyncClient, monkeypatch):
    """Test error handling when the internal API call raises a generic exception."""
    mock_post = AsyncMock(side_effect=Exception("Unexpected network issue"))
    monkeypatch.setattr("meal_planner.main.internal_client.post", mock_post)

    form_data = {
        FIELD_NAME: "Generic API Error Test",
        FIELD_INGREDIENTS: ["ingredient"],
        FIELD_INSTRUCTIONS: ["instruction"],
    }
    response = await client.post(RECIPES_SAVE_URL, data=form_data)
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    error_span = soup.find("span", id="save-button-container")

    assert error_span is not None, "Error message container span not found."
    assert "An unexpected error occurred" in error_span.get_text(strip=True)

    mock_post.assert_awaited_once()


@pytest.mark.anyio
async def test_save_recipe_api_call_request_error(client: AsyncClient, monkeypatch):
    """Test handling when the internal API call raises httpx.RequestError."""
    mock_post = AsyncMock(
        side_effect=httpx.RequestError(
            "Network error", request=httpx.Request("POST", "/api/v0/recipes")
        )
    )
    monkeypatch.setattr("meal_planner.main.internal_client.post", mock_post)

    form_data = {
        FIELD_NAME: "RequestError Test",
        FIELD_INGREDIENTS: ["ingredient"],
        FIELD_INSTRUCTIONS: ["instruction"],
    }
    response = await client.post(RECIPES_SAVE_URL, data=form_data)
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    error_span = soup.find("span", id="save-button-container")

    assert error_span is not None, "Error message container span not found."
    assert "due to a network issue" in error_span.get_text(strip=True)

    mock_post.assert_awaited_once()


@pytest.mark.anyio
class TestGetRecipesPageSuccess:
    async def test_get_recipes_page_success_with_data(self, client: AsyncClient):
        recipe1_payload = {
            "name": "Recipe One For Page Test",
            "ingredients": ["i1"],
            "instructions": ["s1"],
        }
        recipe2_payload = {
            "name": "Recipe Two For Page Test",
            "ingredients": ["i2"],
            "instructions": ["s2"],
        }
        create_resp1 = await client.post("/api/v0/recipes", json=recipe1_payload)
        assert create_resp1.status_code == 201
        recipe1_id = create_resp1.json()["id"]

        create_resp2 = await client.post("/api/v0/recipes", json=recipe2_payload)
        assert create_resp2.status_code == 201
        recipe2_id = create_resp2.json()["id"]

        page_url = RECIPES_LIST_PATH
        response = await client.get(page_url)
        assert response.status_code == 200
        html_content = response.text

        assert recipe1_payload["name"] in html_content
        assert f'href="/recipes/{recipe1_id}"' in html_content
        assert recipe2_payload["name"] in html_content
        assert f'href="/recipes/{recipe2_id}"' in html_content
        assert "No recipes found." not in html_content

    async def test_get_recipes_page_success_no_data(self, client: AsyncClient):
        page_url = RECIPES_LIST_PATH
        response = await client.get(page_url)
        assert response.status_code == 200
        html_content = response.text

        assert "No recipes found." in html_content


@pytest.mark.anyio
class TestGetSingleRecipePageSuccess:
    RECIPE_ID = 456
    API_URL = f"/api/v0/recipes/{RECIPE_ID}"
    PAGE_URL = f"/recipes/{RECIPE_ID}"

    async def test_get_single_recipe_page_success(self, client: AsyncClient):
        recipe_payload = {
            "name": "Specific Recipe Page Test",
            "ingredients": ["Specific Ing 1", "Specific Ing 2"],
            "instructions": ["Specific Step 1.", "Specific Step 2."],
        }
        create_resp = await client.post("/api/v0/recipes", json=recipe_payload)
        assert create_resp.status_code == 201
        created_recipe_id = create_resp.json()["id"]

        page_url = f"/recipes/{created_recipe_id}"
        response = await client.get(page_url)
        assert response.status_code == 200
        html_content = response.text

        assert recipe_payload["name"] in html_content
        assert recipe_payload["ingredients"][0] in html_content
        assert recipe_payload["ingredients"][1] in html_content
        assert recipe_payload["instructions"][0] in html_content
        assert recipe_payload["instructions"][1] in html_content


class FormTargetDivNotFoundError(Exception):
    """Custom exception raised when the target div for form parsing is not found."""

    pass


def _get_edit_form_target_div(html_text: str) -> Tag:
    """Parses HTML and finds the specific div target for form edits.

    Raises:
        FormTargetDivNotFoundError: If the target div is not found.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    found_element = soup.find(
        "div", attrs={"hx-swap-oob": "innerHTML:#edit-form-target"}
    )
    if isinstance(found_element, Tag):
        return found_element
    raise FormTargetDivNotFoundError(
        "Could not find div with hx-swap-oob='innerHTML:#edit-form-target'"
    )


def _extract_form_value(html_text: str, name: str) -> str | None:
    """Extracts a single value from an input or textarea in the HTML form section.

    Can propagate FormTargetDivNotFoundError if the main form container is missing.
    Returns None if the specific field is not found within the container.
    """
    form_div = _get_edit_form_target_div(html_text)

    input_tag_candidate = form_div.find("input", attrs={"name": name})
    if isinstance(input_tag_candidate, Tag) and input_tag_candidate.has_attr("value"):
        value = input_tag_candidate["value"]
        if isinstance(value, str):
            return value
        elif isinstance(value, list) and value and isinstance(value[0], str):
            return value[0]

    textarea_tag_candidate = form_div.find("textarea", attrs={"name": name})
    if isinstance(textarea_tag_candidate, Tag):
        return (
            str(textarea_tag_candidate.string)
            if textarea_tag_candidate.string is not None
            else None
        )

    return None


def _extract_form_list_values(html_text: str, name: str) -> list[str]:
    """Extracts all values from inputs/textareas with the same name.

    Can propagate FormTargetDivNotFoundError if the main form container is missing.
    Returns an empty list if no specific fields are found within the container.
    """
    form_div = _get_edit_form_target_div(html_text)

    values: list[str] = []
    elements = form_div.find_all(
        lambda tag: isinstance(tag, Tag)
        and tag.name in ["input", "textarea"]
        and tag.get("name") == name
    )

    for element in elements:
        if isinstance(element, Tag):
            if element.name == "input" and element.has_attr("value"):
                value_attr = element["value"]
                if isinstance(value_attr, str):
                    values.append(value_attr)
                elif (
                    isinstance(value_attr, list)
                    and value_attr
                    and isinstance(value_attr[0], str)
                ):
                    values.append(value_attr[0])
            elif element.name == "textarea":
                values.append(str(element.string) if element.string is not None else "")

    return values


@pytest.mark.anyio
async def test_save_recipe_api_call_non_json_error_response(
    client: AsyncClient, monkeypatch
):
    """Test handling when API returns non-201 status with non-JSON content."""
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 500
    mock_response.text = "Server Error Text, Not JSON"
    mock_response.json = MagicMock(side_effect=Exception("Invalid JSON"))

    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "Server Error",
            request=Request("POST", "/api/v0/recipes"),
            response=mock_response,
        )
    )

    mock_post = AsyncMock(return_value=mock_response)
    monkeypatch.setattr("meal_planner.main.internal_client.post", mock_post)

    form_data = {
        FIELD_NAME: "Non JSON Error Test",
        FIELD_INGREDIENTS: ["ingredient"],
        FIELD_INSTRUCTIONS: ["instruction"],
    }
    response = await client.post(RECIPES_SAVE_URL, data=form_data)
    assert response.status_code == 200

    soup = BeautifulSoup(response.text, "html.parser")
    error_span = soup.find("span", id="save-button-container")

    assert error_span is not None, "Error message container span not found."
    assert "Could not save recipe. Please check input" in error_span.get_text(
        strip=True
    )

    mock_post.assert_awaited_once()


@pytest.mark.anyio
async def test_save_recipe_api_call_422_error(client: AsyncClient, monkeypatch):
    """Test error handling for HTTP 422 error from the internal API."""
    mock_response_422 = AsyncMock(spec=httpx.Response)
    mock_response_422.status_code = 422
    mock_response_422.text = "Unprocessable Entity"
    mock_response_422.json = MagicMock(return_value={"detail": "API validation error"})

    mock_post = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "API 422 Error",
            request=httpx.Request("POST", "/api/v0/recipes"),
            response=mock_response_422,
        )
    )
    monkeypatch.setattr("meal_planner.main.internal_client.post", mock_post)

    form_data = {
        FIELD_NAME: "Test 422 Error",
        FIELD_INGREDIENTS: ["ingredient"],
        FIELD_INSTRUCTIONS: ["instruction"],
    }
    response = await client.post(RECIPES_SAVE_URL, data=form_data)
    assert response.status_code == 200
    expected_msg = "Could not save recipe: Invalid data for some fields."
    soup = BeautifulSoup(response.text, "html.parser")
    error_span = soup.find("span", id="save-button-container")
    assert error_span is not None
    assert error_span.get_text(strip=True) == expected_msg
    mock_post.assert_awaited_once()


@pytest.mark.anyio
@patch("meal_planner.main.logger.debug")
async def test_save_recipe_api_call_json_error_with_detail(
    mock_logger_debug: MagicMock, client: AsyncClient, monkeypatch
):
    """Test error handling when internal API returns HTTPStatusError with JSON
    detail."""
    error_detail_text = "Specific error detail from JSON"

    mock_api_response = AsyncMock(spec=httpx.Response)
    mock_api_response.status_code = 400
    mock_api_response.text = f'{{"detail": "{error_detail_text}"}}'
    mock_api_response.json = MagicMock(return_value={"detail": error_detail_text})

    mock_post = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "API JSON Error",
            request=httpx.Request("POST", "/api/v0/recipes"),
            response=mock_api_response,
        )
    )
    monkeypatch.setattr("meal_planner.main.internal_client.post", mock_post)

    form_data = {
        FIELD_NAME: "API JSON Error Test",
        FIELD_INGREDIENTS: ["ingredient"],
        FIELD_INSTRUCTIONS: ["instruction"],
    }
    response = await client.post(RECIPES_SAVE_URL, data=form_data)
    assert response.status_code == 200

    expected_user_msg = "Could not save recipe. Please check input and try again."
    soup = BeautifulSoup(response.text, "html.parser")
    error_span = soup.find("span", id="save-button-container")
    assert error_span is not None
    assert error_span.get_text(strip=True) == expected_user_msg

    mock_post.assert_awaited_once()
    mock_logger_debug.assert_any_call("API error detail: %s", error_detail_text)
