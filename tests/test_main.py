import json
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import httpx
import pytest
from fastlite import database
from httpx import ASGITransport, AsyncClient, Request, Response

import meal_planner.api.recipes as api_recipes_module
import meal_planner.main as main_module
from meal_planner.main import (
    Recipe,
    app,
    fetch_and_clean_text_from_url,
    fetch_page_text,
    postprocess_recipe,
)
from meal_planner.models import Recipe as ModelRecipe

TRANSPORT = ASGITransport(app=app)
TEST_URL = "http://test-recipe.com"


@pytest.mark.anyio
class TestSmokeEndpoints:
    async def test_root(self, client: AsyncClient):
        response = await client.get("/")
        assert response.status_code == 200
        assert "Meal Planner" in response.text

    async def test_extract_recipe_page_loads(self, client: AsyncClient):
        response = await client.get("/recipes/extract")
        assert response.status_code == 200
        assert 'id="recipe_url"' in response.text
        assert 'placeholder="Enter recipe URL (optional)' in response.text
        assert 'hx-post="/recipes/fetch-text"' in response.text
        assert "Fetch Text from URL" in response.text
        assert 'id="recipe_text"' in response.text
        assert 'placeholder="Paste recipe text here' in response.text
        assert 'hx-post="/recipes/extract/run"' in response.text
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
            "/recipes/fetch-text", data={"recipe_url": self.TEST_URL}
        )

        assert response.status_code == 200
        mock_fetch_clean.assert_called_once_with(self.TEST_URL)
        # Check that the response text contains the key parts of the textarea
        assert "<textarea" in response.text
        assert 'id="recipe_text"' in response.text
        assert 'name="recipe_text"' in response.text
        assert ">Fetched and cleaned recipe text.</textarea>" in response.text
        assert 'label="Recipe Text (Fetched or Manual)"' in response.text

    async def test_missing_url(self, client: AsyncClient):
        response = await client.post("/recipes/fetch-text", data={})
        assert response.status_code == 200
        assert "Please provide a Recipe URL to fetch." in response.text
        assert 'class="text-red-500 mb-4"' in response.text

    @patch("meal_planner.main.logger.error")
    async def test_request_error(
        self, mock_logger_error, client: AsyncClient, mock_fetch_clean
    ):
        error_message = "Network connection failed"
        mock_fetch_clean.side_effect = httpx.RequestError(error_message, request=None)

        response = await client.post(
            "/recipes/fetch-text", data={"recipe_url": self.TEST_URL}
        )

        assert response.status_code == 200
        expected_text = f"Error fetching URL: {error_message}. Check URL/connection."
        assert expected_text in response.text
        assert 'class="text-red-500 mb-4"' in response.text
        mock_logger_error.assert_called_once()

    @patch("meal_planner.main.logger.error")
    async def test_status_error(
        self, mock_logger_error, client: AsyncClient, mock_fetch_clean
    ):
        status_code = 404
        mock_request = Request("GET", self.TEST_URL)
        mock_response = Response(status_code, request=mock_request)
        mock_fetch_clean.side_effect = httpx.HTTPStatusError(
            f"{status_code} Client Error", request=mock_request, response=mock_response
        )

        response = await client.post(
            "/recipes/fetch-text", data={"recipe_url": self.TEST_URL}
        )

        assert response.status_code == 200
        expected_text = f"HTTP Error {status_code} fetching URL."
        assert expected_text in response.text
        assert 'class="text-red-500 mb-4"' in response.text
        mock_logger_error.assert_called_once()

    @patch("meal_planner.main.logger.error")
    async def test_runtime_error(
        self, mock_logger_error, client: AsyncClient, mock_fetch_clean
    ):
        error_message = "Processing failed"
        mock_fetch_clean.side_effect = RuntimeError(error_message)

        response = await client.post(
            "/recipes/fetch-text", data={"recipe_url": self.TEST_URL}
        )

        assert response.status_code == 200
        expected_text = f"Failed to process URL: {error_message}"
        assert expected_text in response.text
        assert 'class="text-red-500 mb-4"' in response.text
        mock_logger_error.assert_called_once()

    @patch("meal_planner.main.logger.error")
    async def test_generic_exception(
        self, mock_logger_error, client: AsyncClient, mock_fetch_clean
    ):
        mock_fetch_clean.side_effect = Exception("Unexpected error")

        response = await client.post(
            "/recipes/fetch-text", data={"recipe_url": self.TEST_URL}
        )

        assert response.status_code == 200
        assert "Unexpected error fetching text." in response.text
        assert 'class="text-red-500 mb-4"' in response.text
        mock_logger_error.assert_called_once()


@pytest.mark.anyio
class TestRecipeExtractRunEndpoint:
    @pytest.fixture
    def mock_call_llm(self):
        with patch("meal_planner.main.call_llm", new_callable=AsyncMock) as mock_llm:
            yield mock_llm

    async def test_success(self, client: AsyncClient, mock_call_llm):
        """Test successful recipe extraction using direct text input."""
        test_text = "Recipe Name\nIngredients: ing1, ing2\nInstructions: 1. First step "
        "text, Step 2: Second step text"
        mock_call_llm.return_value = Recipe(
            name="Text Input Success Name",
            ingredients=["ingA", "ingB"],
            instructions=["1. Actual step A", "Step 2: Actual step B"],
        )

        response = await client.post(
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

    async def test_extraction_error(self, client: AsyncClient, mock_call_llm):
        """Test POST /run handles exceptions from call_llm (via
        extract_recipe_from_text)."""
        test_text = "Some recipe text that causes an LLM error."
        mock_call_llm.side_effect = Exception("LLM failed on text input")

        response = await client.post(
            "/recipes/extract/run", data={"recipe_text": test_text}
        )
        assert response.status_code == 200
        expected_error_msg = (
            "Recipe extraction failed. An unexpected error occurred during processing."
        )
        assert expected_error_msg in response.text
        mock_call_llm.assert_called_once()

    async def test_no_text_input_provided(self, client: AsyncClient):
        """Test POST /run returns error if recipe_text is not provided."""
        response = await client.post("/recipes/extract/run", data={})

        assert response.status_code == 200
        expected_error_msg = "No text content provided for extraction."
        assert expected_error_msg in response.text


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
        dummy_request = httpx.Request("GET", test_url)
        mock_response = httpx.Response(404, request=dummy_request)
        mock_fetch_page_text.side_effect = httpx.HTTPStatusError(
            "Not Found", request=dummy_request, response=mock_response
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


# Example Mock Recipe Data
mock_recipe_data = ModelRecipe(
    name="Mock Recipe",
    ingredients=["mock ingredient 1", "mock ingredient 2"],
    instructions=["mock instruction 1", "mock instruction 2"],
)


@pytest.mark.anyio
async def test_extract_run_returns_save_form(client: AsyncClient, monkeypatch):
    async def mock_extract(*args, **kwargs):
        return mock_recipe_data

    monkeypatch.setattr(main_module, "extract_recipe_from_text", mock_extract)

    response = await client.post(
        "/recipes/extract/run", data={"recipe_text": "some text"}
    )
    assert response.status_code == 200
    html_content = response.text

    # Check for hidden fields
    assert (
        f'<input type="hidden" name="name" value="{mock_recipe_data.name}">'
        in html_content
    )
    for ing in mock_recipe_data.ingredients:
        assert f'<input type="hidden" name="ingredients" value="{ing}">' in html_content
    for inst in mock_recipe_data.instructions:
        assert (
            f'<input type="hidden" name="instructions" value="{inst}">' in html_content
        )

    # Check for save button
    assert '<button hx-post="/recipes/save"' in html_content
    assert ">Save Recipe</button>" in html_content


@pytest.mark.anyio
async def test_save_recipe_success(client: AsyncClient, test_db_session):
    db_path = test_db_session  # Get the path from the fixture

    form_data = {
        "name": "Saved Recipe Name",
        "ingredients": ["saved ing 1", "saved ing 2"],
        "instructions": ["saved inst 1", "saved inst 2"],
    }

    response = await client.post("/recipes/save", data=form_data)

    assert response.status_code == 200
    assert "Recipe Saved Successfully!" in response.text

    # Verify data in DB using the yielded path
    verify_db = database(db_path)
    verify_table = verify_db.t.recipes
    all_recipes = verify_table()
    assert len(all_recipes) == 1
    saved_db_recipe = all_recipes[0]
    verify_db.conn.close()  # Close the verification connection

    assert saved_db_recipe["name"] == form_data["name"]
    assert json.loads(saved_db_recipe["ingredients"]) == form_data["ingredients"]
    assert json.loads(saved_db_recipe["instructions"]) == form_data["instructions"]
    # Verify ID is an integer
    recipe_id = saved_db_recipe["id"]
    assert isinstance(recipe_id, int)


@pytest.mark.anyio
async def test_save_recipe_missing_ingredients_instructions(client: AsyncClient):
    # Test case: Missing ingredients and instructions
    response = await client.post("/recipes/save", data={"name": "Only Name"})
    assert response.status_code == 200
    assert "Error: Missing recipe ingredients." in response.text


@pytest.mark.anyio
async def test_save_recipe_missing_instructions(client: AsyncClient):
    response = await client.post(
        "/recipes/save", data={"name": "Name and Ing", "ingredients": ["ing1"]}
    )
    assert response.status_code == 200
    assert "Error: Missing recipe instructions." in response.text


@pytest.mark.anyio
async def test_save_recipe_missing_name(client: AsyncClient):
    # Test case: Missing name
    response = await client.post(
        "/recipes/save", data={"ingredients": ["i"], "instructions": ["s"]}
    )
    assert response.status_code == 200
    assert "Error: Recipe name is required and must be text." in response.text


@pytest.mark.anyio
async def test_save_recipe_db_error(client: AsyncClient, monkeypatch):
    def mock_insert_fail(*args, **kwargs):
        raise Exception("Simulated DB Save Error")

    monkeypatch.setattr(api_recipes_module.recipes_table, "insert", mock_insert_fail)

    form_data = {
        "name": "DB Error Recipe",
        "ingredients": ["i1"],
        "instructions": ["s1"],
    }
    response = await client.post("/recipes/save", data=form_data)
    assert response.status_code == 200
    assert "Error saving recipe to database." in response.text
