import json
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import httpx
import pytest
from fastlite import database
from httpx import ASGITransport, AsyncClient, Request, Response

import meal_planner.api.recipes as api_recipes_module
import meal_planner.main as main_module
from meal_planner.main import (
    CSS_ERROR_CLASS,
    app,
    fetch_and_clean_text_from_url,
    fetch_page_text,
    postprocess_recipe,
)
from meal_planner.models import Recipe

# Constants
TRANSPORT = ASGITransport(app=app)
TEST_URL = "http://test-recipe.com"

# URLs
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
        assert 'label="Recipe Text (Fetched or Manual)"' in response.text

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
                "Error fetching URL: Network connection failed. Check URL/connection.",
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
                "HTTP Error 404 fetching URL.",
            ),
            (
                RuntimeError,
                ("Processing failed",),
                "Failed to process URL: Processing failed",
            ),
            (
                Exception,
                ("Unexpected error",),
                "Unexpected error fetching text.",
            ),
        ],
    )
    @patch("meal_planner.main.logger.error")
    async def test_fetch_text_errors(
        self,
        mock_logger_error,
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
        mock_logger_error.assert_called_once()


@pytest.mark.anyio
class TestRecipeExtractRunEndpoint:
    @pytest.fixture
    def mock_call_llm(self):
        with patch("meal_planner.main.call_llm", new_callable=AsyncMock) as mock_llm:
            yield mock_llm

    async def test_success(self, client: AsyncClient, mock_call_llm):
        test_text = (
            "Recipe Name\nIngredients: ing1, ing2\nInstructions: 1. First "
            "step text\nStep 2: Second step text"
        )
        mock_call_llm.return_value = Recipe(
            name="Text Input Success Name",
            ingredients=["ingA", "ingB"],
            instructions=["1. Actual step A", "Step 2: Actual step B"],
        )

        response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: test_text}
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
        test_text = "Some recipe text that causes an LLM error."
        mock_call_llm.side_effect = Exception("LLM failed on text input")

        response = await client.post(
            RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: test_text}
        )
        assert response.status_code == 200
        expected_error_msg = (
            "Recipe extraction failed. An unexpected error occurred during processing."
        )
        assert expected_error_msg in response.text
        mock_call_llm.assert_called_once()

    async def test_no_text_input_provided(self, client: AsyncClient):
        response = await client.post(RECIPES_EXTRACT_RUN_URL, data={})

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
                Exception("Generic Error"),
                RuntimeError,
                "Error fetching page text",
                id="generic_exception",
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

        with pytest.raises(expected_caught_exception):
            await fetch_and_clean_text_from_url(self.TEST_URL)

        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        log_message = args[0]
        log_args = args[1:]
        assert expected_log_fragment in log_message
        assert log_args[0] == self.TEST_URL
        assert raised_exception == log_args[1]
        assert kwargs.get("exc_info") is True
        mock_html_cleaner.assert_not_called()


class TestPostprocessRecipeName:
    DUMMY_INGREDIENTS = ["dummy ingredient"]
    DUMMY_INSTRUCTIONS = ["dummy instruction"]

    @pytest.mark.parametrize(
        "input_name, expected_name",
        [
            ("  my awesome cake  ", "My Awesome Cake"),
            ("Another Example recipe ", "Another Example"),
            ("Another Example Recipe ", "Another Example"),
            ("", ""),
            ("Recipe (unclosed", "Recipe (Unclosed)"),
        ],
    )
    def test_postprocess_recipe_name(self, input_name: str, expected_name: str):
        input_recipe = Recipe(
            name=input_name,
            ingredients=self.DUMMY_INGREDIENTS,
            instructions=self.DUMMY_INSTRUCTIONS,
        )
        processed_recipe = postprocess_recipe(input_recipe)
        assert processed_recipe.name == expected_name


@pytest.fixture
def mock_recipe_data_fixture() -> Recipe:
    return Recipe(
        name="Mock Recipe",
        ingredients=["mock ingredient 1", "mock ingredient 2"],
        instructions=["mock instruction 1", "mock instruction 2"],
    )


@pytest.mark.anyio
async def test_extract_run_returns_save_form(
    client: AsyncClient, monkeypatch, mock_recipe_data_fixture: Recipe
):
    async def mock_extract(*args, **kwargs):
        return mock_recipe_data_fixture

    monkeypatch.setattr(main_module, "extract_recipe_from_text", mock_extract)

    response = await client.post(
        RECIPES_EXTRACT_RUN_URL, data={FIELD_RECIPE_TEXT: "some text"}
    )
    assert response.status_code == 200
    html_content = response.text

    assert (
        f'<input type="hidden" name="{FIELD_NAME}" '
        f'value="{mock_recipe_data_fixture.name}">' in html_content
    )
    for ing in mock_recipe_data_fixture.ingredients:
        assert (
            f'<input type="hidden" name="{FIELD_INGREDIENTS}" value="{ing}">'
            in html_content
        )
    for inst in mock_recipe_data_fixture.instructions:
        assert (
            f'<input type="hidden" name="{FIELD_INSTRUCTIONS}" value="{inst}">'
            in html_content
        )

    assert f'<button hx-post="{RECIPES_SAVE_URL}"' in html_content
    assert "Save Current Recipe" in html_content


@pytest.mark.anyio
async def test_save_recipe_success(client: AsyncClient, test_db_session):
    db_path = test_db_session

    form_data = {
        FIELD_NAME: "Saved Recipe Name",
        FIELD_INGREDIENTS: ["saved ing 1", "saved ing 2"],
        FIELD_INSTRUCTIONS: ["saved inst 1", "saved inst 2"],
    }

    response = await client.post(RECIPES_SAVE_URL, data=form_data)

    assert response.status_code == 200
    assert "Modified Recipe Saved!" in response.text

    verify_db = database(db_path)
    verify_table = verify_db.t.recipes
    all_recipes = verify_table()
    assert len(all_recipes) == 1
    saved_db_recipe = all_recipes[0]
    verify_db.conn.close()

    assert saved_db_recipe[FIELD_NAME] == form_data[FIELD_NAME]
    assert (
        json.loads(saved_db_recipe[FIELD_INGREDIENTS]) == form_data[FIELD_INGREDIENTS]
    )
    assert (
        json.loads(saved_db_recipe[FIELD_INSTRUCTIONS]) == form_data[FIELD_INSTRUCTIONS]
    )
    recipe_id = saved_db_recipe["id"]
    assert isinstance(recipe_id, int)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "form_data, expected_error",
    [
        ({FIELD_NAME: "Only Name"}, "Error: Missing recipe ingredients."),
        (
            {FIELD_NAME: "Name and Ing", FIELD_INGREDIENTS: ["ing1"]},
            "Error: Missing recipe instructions.",
        ),
        (
            {FIELD_INGREDIENTS: ["i"], FIELD_INSTRUCTIONS: ["s"]},
            "Error: Recipe name is required and must be text.",
        ),
    ],
)
async def test_save_recipe_missing_data(
    client: AsyncClient, form_data: dict, expected_error: str
):
    response = await client.post(RECIPES_SAVE_URL, data=form_data)
    assert response.status_code == 200
    assert expected_error in response.text


@pytest.mark.anyio
async def test_save_recipe_db_error(client: AsyncClient, monkeypatch):
    def mock_insert_fail(*args, **kwargs):
        raise Exception("Simulated DB Save Error")

    monkeypatch.setattr(api_recipes_module.recipes_table, "insert", mock_insert_fail)

    form_data = {
        FIELD_NAME: "DB Error Recipe",
        FIELD_INGREDIENTS: ["i1"],
        FIELD_INSTRUCTIONS: ["s1"],
    }
    response = await client.post(RECIPES_SAVE_URL, data=form_data)
    assert response.status_code == 200
    assert "Error saving recipe." in response.text


@pytest.fixture
def mock_original_recipe_fixture() -> Recipe:
    return Recipe(
        name="Original Recipe",
        ingredients=["orig ing 1", "orig ing 2"],
        instructions=["orig inst 1", "orig inst 2"],
    )


@pytest.fixture
def mock_current_recipe_before_modify_fixture() -> Recipe:
    return Recipe(
        name="Current Recipe",
        ingredients=["curr ing 1", "curr ing 2"],
        instructions=["curr inst 1", "curr inst 2"],
    )


@pytest.fixture
def mock_llm_modified_recipe_fixture() -> Recipe:
    return Recipe(
        name="Modified Recipe",
        ingredients=["mod ing 1", "mod ing 2"],
        instructions=["mod inst 1", "mod inst 2"],
    )


@pytest.mark.anyio
class TestRecipeModifyEndpoint:
    @pytest.fixture
    def mock_call_llm(self):
        with patch("meal_planner.main.call_llm", new_callable=AsyncMock) as mock_llm:
            yield mock_llm

    def _build_modify_form_data(
        self,
        current_recipe: Recipe,
        original_recipe: Recipe,
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

    async def test_modify_success(
        self,
        client: AsyncClient,
        mock_call_llm,
        mock_current_recipe_before_modify_fixture: Recipe,
        mock_original_recipe_fixture: Recipe,
        mock_llm_modified_recipe_fixture: Recipe,
    ):
        mock_call_llm.return_value = mock_llm_modified_recipe_fixture
        test_prompt = "Make it spicier"
        form_data = self._build_modify_form_data(
            mock_current_recipe_before_modify_fixture,
            mock_original_recipe_fixture,
            test_prompt,
        )

        response = await client.post(RECIPES_MODIFY_URL, data=form_data)

        assert response.status_code == 200
        mock_call_llm.assert_called_once_with(prompt=ANY, response_model=Recipe)
        call_args, call_kwargs = mock_call_llm.call_args
        prompt_arg = call_kwargs.get("prompt", call_args[0] if call_args else None)
        assert mock_current_recipe_before_modify_fixture.markdown in prompt_arg
        assert test_prompt in prompt_arg

        assert (
            f'<input type="hidden" name="{FIELD_NAME}"'
            f' value="{mock_llm_modified_recipe_fixture.name}">' in response.text
        )
        for ing in mock_llm_modified_recipe_fixture.ingredients:
            assert (
                f'<input type="hidden" name="{FIELD_INGREDIENTS}" value="{ing}">'
                in response.text
            )
        for inst in mock_llm_modified_recipe_fixture.instructions:
            assert (
                f'<input type="hidden" name="{FIELD_INSTRUCTIONS}" value="{inst}">'
                in response.text
            )
        assert (
            f'<input type="hidden" name="{FIELD_ORIGINAL_NAME}"'
            f' value="{mock_original_recipe_fixture.name}">' in response.text
        )

    async def test_modify_no_prompt(
        self,
        client: AsyncClient,
        mock_call_llm,
        mock_current_recipe_before_modify_fixture: Recipe,
        mock_original_recipe_fixture: Recipe,
    ):
        form_data = self._build_modify_form_data(
            mock_current_recipe_before_modify_fixture, mock_original_recipe_fixture, ""
        )

        response = await client.post(RECIPES_MODIFY_URL, data=form_data)

        assert response.status_code == 200
        assert "Please enter modification instructions." in response.text
        assert f'class="{CSS_ERROR_CLASS} mt-2"' in response.text
        assert (
            f'<input type="hidden" name="{FIELD_NAME}"'
            f' value="{mock_current_recipe_before_modify_fixture.name}">'
            in response.text
        )
        assert (
            f'<input type="hidden" name="{FIELD_ORIGINAL_NAME}"'
            f' value="{mock_original_recipe_fixture.name}">' in response.text
        )
        mock_call_llm.assert_not_called()

    async def test_modify_llm_error(
        self,
        client: AsyncClient,
        mock_call_llm,
        mock_current_recipe_before_modify_fixture: Recipe,
        mock_original_recipe_fixture: Recipe,
    ):
        mock_call_llm.side_effect = Exception("LLM modification error")
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
        assert (
            f'<input type="hidden" name="{FIELD_NAME}"'
            f' value="{mock_current_recipe_before_modify_fixture.name}">'
            in response.text
        )
        assert (
            f'<input type="hidden" name="{FIELD_ORIGINAL_NAME}"'
            f' value="{mock_original_recipe_fixture.name}">' in response.text
        )
        mock_call_llm.assert_called_once()


class TestGenerateDiffHtml:
    def test_diff_insert(self):
        before = "line1\nline3"
        after = "line1\nline2\nline3"
        before_html, after_html = main_module.generate_diff_html(before, after)
        assert before_html == "line1\nline3"
        assert after_html == "line1\n<ins>line2</ins>\nline3"

    def test_diff_delete(self):
        before = "line1\nline2\nline3"
        after = "line1\nline3"
        before_html, after_html = main_module.generate_diff_html(before, after)
        assert before_html == "line1\n<del>line2</del>\nline3"
        assert after_html == "line1\nline3"

    def test_diff_replace(self):
        before = "line1\nline TWO\nline3"
        after = "line1\nline 2\nline3"
        before_html, after_html = main_module.generate_diff_html(before, after)
        assert before_html == "line1\n<del>line TWO</del>\nline3"
        assert after_html == "line1\n<ins>line 2</ins>\nline3"

    def test_diff_equal(self):
        before = "line1\nline2"
        after = "line1\nline2"
        before_html, after_html = main_module.generate_diff_html(before, after)
        assert before_html == "line1\nline2"
        assert after_html == "line1\nline2"
