from unittest.mock import ANY, AsyncMock, patch, MagicMock

import httpx
import pytest
from httpx import ASGITransport, AsyncClient, Request, Response

from meal_planner.main import (
    Recipe,
    app,
    fetch_and_clean_text_from_url,
    fetch_page_text,
    postprocess_recipe,
)

TRANSPORT = ASGITransport(app=app)
CLIENT = AsyncClient(transport=TRANSPORT, base_url="http://test")
TEST_URL = "http://test-recipe.com"


@pytest.mark.anyio
class TestSmokeEndpoints:
    async def test_root(self, anyio_backend):
        response = await CLIENT.get("/")
        assert response.status_code == 200

    async def test_extract_recipe(self, anyio_backend):
        response = await CLIENT.get("/recipes/extract")
        assert response.status_code == 200

    async def test_get_extract_recipe_form_fragment_url(self):
        response = await CLIENT.get("/recipes/extract/form-fragment?input_type=url")
        assert response.status_code == 200

    async def test_get_extract_recipe_form_fragment_text(self):
        response = await CLIENT.get("/recipes/extract/form-fragment?input_type=text")
        assert response.status_code == 200


@pytest.mark.anyio
class TestRecipeExtractRunEndpoint:
    @pytest.fixture
    def mock_call_llm(self):
        with patch("meal_planner.main.call_llm", new_callable=AsyncMock) as mock_llm:
            yield mock_llm

    @pytest.fixture
    def mock_fetch_clean(self):
        with patch(
            "meal_planner.main.fetch_and_clean_text_from_url", new_callable=AsyncMock
        ) as mock_fetch:
            yield mock_fetch

    async def test_extraction_error_url_input(self, mock_fetch_clean, mock_call_llm):
        """Test POST /run handles exceptions from call_llm (via
        extract_recipe_from_text) for URL input."""
        test_url = "http://example.com/llm_fail"
        mock_fetch_clean.return_value = "Cleaned page text"
        mock_call_llm.side_effect = Exception("LLM processing failed")

        response = await CLIENT.post(
            "/recipes/extract/run", data={"recipe_url": test_url}
        )

        assert response.status_code == 200
        expected_error_msg = (
            "Recipe extraction failed. An unexpected error occurred during processing."
        )
        assert expected_error_msg in response.text
        mock_fetch_clean.assert_called_once_with(test_url)
        mock_call_llm.assert_called_once()

    @patch("meal_planner.main.logger.error")
    async def test_request_error(self, mock_logger_error, mock_fetch_clean):
        """Test POST /run handles httpx.RequestError from
        fetch_and_clean_text_from_url."""
        test_url = "http://example.com/network_error"
        error_message = "Network connection failed"
        mock_fetch_clean.side_effect = httpx.RequestError(error_message, request=None)

        response = await CLIENT.post(
            "/recipes/extract/run", data={"recipe_url": test_url}
        )

        assert response.status_code == 200
        expected_response_text = (
            f"Error fetching URL: {error_message}. Please check the URL and try again."
        )
        assert expected_response_text in response.text

        mock_logger_error.assert_called_once()
        call_args, call_kwargs = mock_logger_error.call_args
        log_format_string = call_args[0]
        log_args = call_args[1:]
        assert "HTTP Request Error processing URL %s: %s" in log_format_string
        assert log_args[0] == test_url
        assert isinstance(log_args[1], httpx.RequestError)
        assert str(log_args[1]) == error_message
        assert call_kwargs.get("exc_info") is False

    @patch("meal_planner.main.logger.error")
    async def test_status_error(self, mock_logger_error, mock_fetch_clean):
        """Test POST /run handles httpx.HTTPStatusError from
        fetch_and_clean_text_from_url."""
        test_url = "http://example.com/not_found"
        status_code = 404
        mock_request = Request("GET", test_url)
        mock_response = Response(status_code, request=mock_request)
        mock_fetch_clean.side_effect = httpx.HTTPStatusError(
            f"{status_code} Client Error", request=mock_request, response=mock_response
        )

        response = await CLIENT.post(
            "/recipes/extract/run", data={"recipe_url": test_url}
        )

        assert response.status_code == 200
        expected_response_text = (
            f"Error fetching URL: Received status {status_code}. Please check the URL."
        )
        assert expected_response_text in response.text

        mock_logger_error.assert_called_once()
        call_args, call_kwargs = mock_logger_error.call_args
        log_format_string = call_args[0]
        log_args = call_args[1:]
        assert "HTTP Status Error processing URL %s: %s" in log_format_string
        assert log_args[0] == test_url
        assert isinstance(log_args[1], httpx.HTTPStatusError)
        assert log_args[1].response.status_code == status_code
        assert call_kwargs.get("exc_info") is False

    @patch("meal_planner.main.logger.error")
    async def test_runtime_error_from_fetch(self, mock_logger_error, mock_fetch_clean):
        """Test POST /run handles RuntimeError from fetch_and_clean_text_from_url."""
        test_url = "http://example.com/runtime_error"
        error_message = "Something else went wrong during fetch/clean"
        mock_fetch_clean.side_effect = RuntimeError(
            f"Failed to process the provided URL. {error_message}"
        )

        response = await CLIENT.post(
            "/recipes/extract/run", data={"recipe_url": test_url}
        )

        assert response.status_code == 200
        expected_response_text = f"Failed to process the provided URL. {error_message}"
        assert expected_response_text in response.text

        mock_logger_error.assert_called_once()
        call_args, call_kwargs = mock_logger_error.call_args
        log_format_string = call_args[0]
        log_args = call_args[1:]
        assert "Runtime error processing URL %s: %s" in log_format_string
        assert log_args[0] == test_url
        assert isinstance(log_args[1], RuntimeError)
        assert (
            str(log_args[1]) == f"Failed to process the provided URL. {error_message}"
        )
        assert call_kwargs.get("exc_info") is True

    async def test_success_url_input(self, mock_fetch_clean, mock_call_llm):
        test_url = "http://example.com/success"
        mock_fetch_clean.return_value = "Cleaned text for LLM"
        mock_call_llm.return_value = Recipe(
            name="Mock Success Name",
            ingredients=["ing1", "ing2"],
            instructions=["1. Mix flour", "Step 2: Add eggs"],
        )

        response = await CLIENT.post(
            "/recipes/extract/run", data={"recipe_url": test_url}
        )

        assert response.status_code == 200
        mock_fetch_clean.assert_called_once_with(test_url)
        mock_call_llm.assert_called_once_with(
            prompt=ANY,
            response_model=Recipe,
        )
        assert "# Mock Success Name" in response.text
        assert "## Ingredients" in response.text
        assert "- ing1" in response.text
        assert "- ing2" in response.text
        assert "## Instructions" in response.text
        assert "Mix flour" in response.text
        assert "Add eggs" in response.text
        assert 'id="recipe_text_display"' in response.text
        assert 'id="recipe-display-form"' in response.text

    async def test_success_text_input(self, mock_call_llm):
        """Test successful recipe extraction using direct text input."""
        test_text = "Recipe Name\nIngredients: ing1, ing2\nInstructions: 1. First step "
        "text, Step 2: Second step text"
        mock_call_llm.return_value = Recipe(
            name="Text Input Success Name",
            ingredients=["ingA", "ingB"],
            instructions=["1. Actual step A", "Step 2: Actual step B"],
        )

        response = await CLIENT.post(
            "/recipes/extract/run", data={"recipe_text": test_text}
        )
        assert response.status_code == 200
        mock_call_llm.assert_called_once_with(
            prompt=ANY,
            response_model=Recipe,
        )
        assert "# Text Input Success Name" in response.text
        assert "## Ingredients" in response.text
        assert "- ingA" in response.text
        assert "- ingB" in response.text
        assert "## Instructions" in response.text
        assert "Actual step A" in response.text
        assert "Actual step B" in response.text
        assert 'id="recipe-display-form"' in response.text

    async def test_extraction_error_text_input(self, mock_call_llm):
        """Test POST /run handles exceptions from call_llm for text input."""
        test_text = "Some recipe text that causes an error."
        mock_call_llm.side_effect = Exception("LLM failed on text input")

        response = await CLIENT.post(
            "/recipes/extract/run", data={"recipe_text": test_text}
        )
        assert response.status_code == 200
        expected_error_msg = (
            "Recipe extraction failed. An unexpected error occurred during processing."
        )
        assert expected_error_msg in response.text
        mock_call_llm.assert_called_once()

    async def test_no_input_provided(self):
        """Test POST /run returns error if neither URL nor text is provided."""
        response = await CLIENT.post("/recipes/extract/run", data={})

        assert response.status_code == 200
        expected_error_msg = "Please provide either a Recipe URL or Recipe Text."
        assert expected_error_msg in response.text

    @patch("meal_planner.main.logger.error")
    async def test_empty_text_after_fetch(self, mock_logger_error, mock_fetch_clean):
        """Test POST /run handles case where fetched text is empty."""
        test_url = "http://example.com/empty_content"
        mock_fetch_clean.return_value = ""

        response = await CLIENT.post(
            "/recipes/extract/run", data={"recipe_url": test_url}
        )

        assert response.status_code == 200
        expected_error_msg = "Failed to obtain text content for extraction."
        assert expected_error_msg in response.text
        mock_fetch_clean.assert_called_once_with(test_url)
        mock_logger_error.assert_called_once_with(
            "No text content available for extraction after processing input."
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
        """Test fetch_page_text successfully returns page content."""
        mock_client_class, mock_client, mock_response = mock_httpx_client
        test_url = "http://example.com/success"

        result = await fetch_page_text(test_url)

        assert result == "Mock page content"
        mock_client_class.assert_called_once()
        mock_client.get.assert_called_once_with(test_url)
        mock_response.raise_for_status.assert_called_once()

    async def test_fetch_page_text_http_error(self, mock_httpx_client):
        """Test fetch_page_text raises HTTPStatusError correctly."""
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
        """Test fetch_page_text raises RequestError correctly."""
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

    @patch("meal_planner.main.logger.error")
    async def test_handles_request_error(
        self, mock_logger_error, mock_fetch_page_text, mock_html_cleaner
    ):
        test_url = "http://example.com/req_error"
        dummy_request = httpx.Request("GET", test_url)
        mock_fetch_page_text.side_effect = httpx.RequestError(
            "ReqErr", request=dummy_request
        )

        with pytest.raises(httpx.RequestError):
            await fetch_and_clean_text_from_url(test_url)

        mock_logger_error.assert_called_once()
        assert (
            "HTTP Request Error fetching page text" in mock_logger_error.call_args[0][0]
        )
        mock_html_cleaner.assert_not_called()

    @patch("meal_planner.main.logger.error")
    async def test_handles_status_error(
        self, mock_logger_error, mock_fetch_page_text, mock_html_cleaner
    ):
        test_url = "http://example.com/status_error"
        mock_response = httpx.Response(404, request=httpx.Request("GET", test_url))
        mock_fetch_page_text.side_effect = httpx.HTTPStatusError(
            "Not Found", request=None, response=mock_response
        )

        with pytest.raises(httpx.HTTPStatusError):
            await fetch_and_clean_text_from_url(test_url)

        mock_logger_error.assert_called_once()
        assert (
            "HTTP Status Error fetching page text" in mock_logger_error.call_args[0][0]
        )
        mock_html_cleaner.assert_not_called()

    @patch("meal_planner.main.logger.error")
    async def test_handles_generic_exception(
        self, mock_logger_error, mock_fetch_page_text, mock_html_cleaner
    ):
        test_url = "http://example.com/generic_error"
        mock_fetch_page_text.side_effect = Exception("Generic Error")

        with pytest.raises(RuntimeError, match=r"Failed to fetch or process URL"):
            await fetch_and_clean_text_from_url(test_url)

        mock_logger_error.assert_called_once()
        assert "Error fetching page text" in mock_logger_error.call_args[0][0]
        mock_html_cleaner.assert_not_called()


class TestPostprocessRecipeName:
    def test_strips_and_titlecases(self):
        """Test postprocess_recipe title-cases and strips whitespace."""
        input_recipe = Recipe(
            name="  my awesome cake  ", ingredients=[], instructions=[]
        )
        expected_name = "My Awesome Cake"
        processed_recipe = postprocess_recipe(input_recipe)
        assert processed_recipe.name == expected_name

    def test_removes_recipe_suffix_lowercase(self):
        """Test postprocess_recipe removes lowercase 'recipe' suffix."""
        input_recipe = Recipe(
            name="Another Example recipe ", ingredients=[], instructions=[]
        )
        expected_name = "Another Example"
        processed_recipe = postprocess_recipe(input_recipe)
        assert processed_recipe.name == expected_name

    def test_removes_recipe_suffix_titlecase(self):
        """Test postprocess_recipe removes title-case 'Recipe' suffix."""
        input_recipe = Recipe(
            name="Another Example Recipe ", ingredients=[], instructions=[]
        )
        expected_name = "Another Example"
        processed_recipe = postprocess_recipe(input_recipe)
        assert processed_recipe.name == expected_name

    def test_handles_empty_name(self):
        """Test postprocess_recipe handles an empty name string."""
        input_recipe = Recipe(name="", ingredients=[], instructions=[])
        processed_recipe = postprocess_recipe(input_recipe)
        assert processed_recipe.name == ""

    def test_closes_parenthesis(self):
        """Test postprocess_recipe adds a closing parenthesis if missing."""
        input_recipe = Recipe(name="Recipe (unclosed", ingredients=[], instructions=[])
        expected_name = "Recipe (Unclosed)"
        processed_recipe = postprocess_recipe(input_recipe)
        assert processed_recipe.name == expected_name
