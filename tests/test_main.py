from unittest.mock import patch

import httpx
import pytest
from bs4 import BeautifulSoup
from httpx import ASGITransport, AsyncClient
from pytest_httpx import HTTPXMock

from meal_planner.main import (
    Recipe,
    _check_api_key,
    app,
    clean_html,
    fetch_page_text,
)

TRANSPORT = ASGITransport(app=app)
CLIENT = AsyncClient(transport=TRANSPORT, base_url="http://test")
TEST_URL = "http://test-recipe.com"


@pytest.mark.anyio
async def test_smoke_root(anyio_backend):
    response = await CLIENT.get("/")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_smoke_extract_recipe(anyio_backend):
    response = await CLIENT.get("/recipes/extract")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_smoke_post_extract_recipe_run(anyio_backend):
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
async def test_fetch_page_text_success(httpx_mock: HTTPXMock):
    expected_text = "<html><body>Recipe Content</body></html>"
    httpx_mock.add_response(url=TEST_URL, text=expected_text, status_code=200)

    result = await fetch_page_text(TEST_URL)
    assert result == expected_text


@pytest.mark.anyio
async def test_fetch_page_text_http_error(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=TEST_URL, status_code=404)

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_page_text(TEST_URL)


@pytest.mark.anyio
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

    mock_llm.return_value = Recipe(name="Mock Name")

    response = await CLIENT.post(
        "/recipes/extract/run",
        data={"recipe_url": "http://example.com"},
    )

    assert response.status_code == 200
    mock_fetch.assert_called_once_with("http://example.com")

    assert """<div>name=\'Mock Name\'</div>""" in response.text


def test_clean_html_with_main_tag():
    """
    Test clean_html when a <main> tag is present.
    It should return the HTML string with specified tags removed, keeping <header>.
    """
    html_input = """
    <html>
    <head><title>Test Page</title><style>body { color: red; }</style></head>
    <body>
        <header>Site Header</header>
        <nav>Navigation</nav>
        <main>
            <h1>Main Title</h1>
            <p>This is the main content.</p>
            <script>alert('hello');</script>
        </main>
        <aside>Sidebar</aside>
        <footer>Site Footer</footer>
    </body>
    </html>
    """

    expected_html_structure = """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <header>Site Header</header>
        <main>
            <h1>Main Title</h1>
            <p>This is the main content.</p>
        </main>
    </body>
    </html>
    """
    expected_soup = BeautifulSoup(expected_html_structure, "html.parser")

    actual_output_str = clean_html(html_input)
    actual_soup = BeautifulSoup(actual_output_str, "html.parser")

    assert actual_soup == expected_soup


def test_clean_html_no_main_no_body():
    """
    Test clean_html when neither <main> nor <body> tags are found.
    It should return the string representation of the parsed HTML after cleaning
    (which might involve BeautifulSoup adding <html>/<body> tags).
    """
    html_input = "<head><title>Just a head</title></head>"
    expected_output_soup = BeautifulSoup(html_input, "html.parser")
    expected_output = str(expected_output_soup)

    actual_output = clean_html(html_input)
    assert actual_output == expected_output

    html_input_plain = "Just some plain text."

    expected_output_plain_soup = BeautifulSoup(html_input_plain, "html.parser")
    expected_output_plain = str(expected_output_plain_soup)
    actual_output_plain = clean_html(html_input_plain)
    assert actual_output_plain == expected_output_plain
