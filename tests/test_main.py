from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pytest_httpx import HTTPXMock

from meal_planner.main import (
    MODEL_NAME,
    Recipe,
    _check_api_key,
    app,
    extract_recipe_from_url,
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

    async def test_post_extract_recipe_run(self, anyio_backend):
        response = await CLIENT.post(
            "/recipes/extract/run",
            data={"recipe_url": "http://example.com"},
        )
        assert response.status_code == 200


@patch("meal_planner.main.os.environ", {})
def test_configure_genai_exits_if_no_api_key():
    """
    Test that _check_api_key() raises SystemExit if GOOGLE_API_KEY is not set,
    using unittest.mock.patch.
    """
    with pytest.raises(SystemExit) as excinfo:
        _check_api_key()

    assert "GOOGLE_API_KEY environment variable not set" in str(excinfo.value)


@pytest.mark.anyio
class TestFetchPageText:
    async def test_success(self, httpx_mock: HTTPXMock, anyio_backend):
        expected_text = "<html><body>Recipe Content</body></html>"
        httpx_mock.add_response(url=TEST_URL, text=expected_text, status_code=200)

        result = await fetch_page_text(TEST_URL)
        assert result == expected_text

    async def test_http_error(self, httpx_mock: HTTPXMock, anyio_backend):
        httpx_mock.add_response(url=TEST_URL, status_code=404)

        with pytest.raises(httpx.HTTPStatusError):
            await fetch_page_text(TEST_URL)


@pytest.mark.anyio
@patch("meal_planner.main.call_llm")
@patch("meal_planner.main.fetch_page_text")
async def test_post_extract_recipe_run_generic_exception(mock_fetch, anyio_backend):
    mock_fetch.side_effect = Exception("Something went wrong!")

    response = await CLIENT.post(
        "/recipes/extract/run",
        data={"recipe_url": "http://example.com/fails"},
    )

    assert response.status_code == 200
    expected_error_msg = "Recipe extraction failed. An unexpected error occurred."
    assert expected_error_msg in response.text
    mock_fetch.assert_called_once_with("http://example.com/fails")


@pytest.mark.anyio
@patch("meal_planner.main.call_llm")
@patch("meal_planner.main.fetch_page_text")
async def test_post_extract_response_contains_only_result(
    mock_fetch,
    mock_llm,
    anyio_backend,
):
    fetched_page_content = (
        "<html><body><h1>Mock Recipe Name</h1><p>Ingredients...</p></body></html>"
    )
    mock_fetch.return_value = fetched_page_content

    mock_llm.return_value = Recipe(name="Mock Name", ingredients=[], instructions=[])

    response = await CLIENT.post(
        "/recipes/extract/run",
        data={"recipe_url": "http://example.com"},
    )

    assert response.status_code == 200
    mock_fetch.assert_called_once_with("http://example.com")

    assert "# Mock Name" in response.text


@pytest.mark.anyio
@patch("meal_planner.main.fetch_page_text")
@patch("meal_planner.main.call_llm")
@patch("meal_planner.main.logger.error")
async def test_extract_recipe_from_url_llm_exception(
    mock_logger_error,
    mock_call_llm,
    mock_fetch_page_text,
    anyio_backend,
):
    """Test extract_recipe_from_url handles exceptions from call_llm."""
    test_url = "http://example.com/llm_fail"
    dummy_html = "<html><body>Some content</body></html>"
    expected_error_message = "LLM processing failed"

    mock_fetch_page_text.return_value = dummy_html
    mock_call_llm.side_effect = Exception(expected_error_message)

    with pytest.raises(Exception) as excinfo:
        await extract_recipe_from_url(test_url)

    # Check if the raised exception is the one we expect
    assert str(excinfo.value) == expected_error_message

    # Verify logger.error was called correctly
    mock_logger_error.assert_called_once()
    call_args, call_kwargs = mock_logger_error.call_args
    log_format_string = call_args[0]
    log_args = call_args[1:]
    assert (
        f"Error calling model {MODEL_NAME} for URL {test_url}: %s" in log_format_string
    )
    assert isinstance(log_args[0], Exception)
    assert str(log_args[0]) == expected_error_message
    assert call_kwargs.get("exc_info") is True


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


@pytest.mark.anyio
@patch("meal_planner.main.extract_recipe_from_url")
@patch("meal_planner.main.logger.error")
async def test_post_extract_recipe_run_request_error(
    mock_logger_error,
    mock_extract,
    anyio_backend,
):
    """Test the POST /recipes/extract/run endpoint handles httpx.RequestError."""
    test_url = "http://example.com/network_error"
    error_message = "Network connection failed"
    mock_extract.side_effect = httpx.RequestError(error_message, request=None)

    response = await CLIENT.post("/recipes/extract/run", data={"recipe_url": test_url})

    assert response.status_code == 200
    # Check that the specific error message for RequestError is in the response
    expected_response_text = (
        f"Error fetching URL: {error_message}. Please check the URL and try again."
    )
    assert expected_response_text in response.text

    # Verify logger call
    mock_logger_error.assert_called_once()
    call_args, call_kwargs = mock_logger_error.call_args
    log_format_string = call_args[0]
    log_args = call_args[1:]
    assert "HTTP Request Error extracting recipe from %s: %s" in log_format_string
    assert log_args[0] == test_url
    assert isinstance(log_args[1], httpx.RequestError)
    assert str(log_args[1]) == error_message
    assert call_kwargs.get("exc_info") is True


@pytest.mark.anyio
@patch("meal_planner.main.extract_recipe_from_url")
@patch("meal_planner.main.logger.error")
async def test_post_extract_recipe_run_status_error(
    mock_logger_error,
    mock_extract,
    anyio_backend,
):
    """Test the POST /recipes/extract/run endpoint handles httpx.HTTPStatusError."""
    test_url = "http://example.com/not_found"
    status_code = 404
    # Create a mock response and request needed for HTTPStatusError
    mock_request = httpx.Request("GET", test_url)
    mock_response = httpx.Response(status_code, request=mock_request)
    mock_extract.side_effect = httpx.HTTPStatusError(
        f"{status_code} Client Error", request=mock_request, response=mock_response
    )

    response = await CLIENT.post("/recipes/extract/run", data={"recipe_url": test_url})

    assert response.status_code == 200
    # Check that the specific error message for HTTPStatusError is in the response
    expected_response_text = (
        f"Error fetching URL: Received status {status_code}. Please check the URL."
    )
    assert expected_response_text in response.text

    # Verify logger call
    mock_logger_error.assert_called_once()
    call_args, call_kwargs = mock_logger_error.call_args
    log_format_string = call_args[0]
    log_args = call_args[1:]
    assert "HTTP Status Error extracting recipe from %s: %s" in log_format_string
    assert log_args[0] == test_url
    assert isinstance(log_args[1], httpx.HTTPStatusError)
    assert log_args[1].response.status_code == status_code
    assert call_kwargs.get("exc_info") is True


@pytest.mark.anyio
class TestRecipeExtractRunEndpoint:
    @patch("meal_planner.main.fetch_page_text")
    async def test_generic_exception(self, mock_fetch, anyio_backend):
        mock_fetch.side_effect = Exception("Something went wrong!")

        response = await CLIENT.post(
            "/recipes/extract/run",
            data={"recipe_url": "http://example.com/fails"},
        )

        assert response.status_code == 200
        expected_error_msg = "Recipe extraction failed. An unexpected error occurred."
        assert expected_error_msg in response.text
        mock_fetch.assert_called_once_with("http://example.com/fails")

    @patch("meal_planner.main.call_llm")
    @patch("meal_planner.main.fetch_page_text")
    async def test_contains_only_result(self, mock_fetch, mock_llm, anyio_backend):
        fetched_page_content = (
            "<html><body><h1>Mock Recipe Name</h1><p>Ingredients...</p></body></html>"
        )
        mock_fetch.return_value = fetched_page_content

        mock_llm.return_value = Recipe(
            name="Mock Name", ingredients=[], instructions=[]
        )

        response = await CLIENT.post(
            "/recipes/extract/run",
            data={"recipe_url": "http://example.com"},
        )

        assert response.status_code == 200
        mock_fetch.assert_called_once_with("http://example.com")

        # Check for the start of the Markdown content
        assert "# Mock Name" in response.text

    @patch("meal_planner.main.extract_recipe_from_url")
    @patch("meal_planner.main.logger.error")
    async def test_request_error(self, mock_logger_error, mock_extract, anyio_backend):
        """Test the POST /recipes/extract/run endpoint handles httpx.RequestError."""
        test_url = "http://example.com/network_error"
        error_message = "Network connection failed"
        mock_extract.side_effect = httpx.RequestError(error_message, request=None)

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
        assert "HTTP Request Error extracting recipe from %s: %s" in log_format_string
        assert log_args[0] == test_url
        assert isinstance(log_args[1], httpx.RequestError)
        assert str(log_args[1]) == error_message
        assert call_kwargs.get("exc_info") is True

    @patch("meal_planner.main.extract_recipe_from_url")
    @patch("meal_planner.main.logger.error")
    async def test_status_error(self, mock_logger_error, mock_extract, anyio_backend):
        """Test the POST /recipes/extract/run endpoint handles httpx.HTTPStatusError."""
        test_url = "http://example.com/not_found"
        status_code = 404
        mock_request = httpx.Request("GET", test_url)
        mock_response = httpx.Response(status_code, request=mock_request)
        mock_extract.side_effect = httpx.HTTPStatusError(
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
        assert "HTTP Status Error extracting recipe from %s: %s" in log_format_string
        assert log_args[0] == test_url
        assert isinstance(log_args[1], httpx.HTTPStatusError)
        assert log_args[1].response.status_code == status_code
        assert call_kwargs.get("exc_info") is True
