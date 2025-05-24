from unittest.mock import AsyncMock, MagicMock, patch

import html2text
import httpx
import pytest

from meal_planner.services.extract_webpage_text import (
    clean_html_text,
    fetch_and_clean_text_from_url,
    fetch_page_text,
)

TEST_URL = "http://test-recipe.com"


@pytest.mark.anyio
class TestFetchPageText:
    """Tests for the fetch_page_text utility function."""

    @pytest.fixture
    def mock_httpx_client_cm(self):
        """Fixture to mock httpx.AsyncClient context manager."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.text = "<html><body>Test Content</body></html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client) as mock_cm:
            yield mock_cm, mock_response, mock_client

    async def test_fetch_page_text_success(self, mock_httpx_client_cm):
        mock_cm, mock_response, mock_client = mock_httpx_client_cm
        result = await fetch_page_text(TEST_URL)
        expected_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
                "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        }
        mock_cm.assert_called_once_with(
            follow_redirects=True, timeout=15.0, headers=expected_headers
        )
        mock_client.get.assert_called_once_with(TEST_URL)
        mock_response.raise_for_status.assert_called_once()
        assert result == "<html><body>Test Content</body></html>"

    async def test_fetch_page_text_http_error(self, mock_httpx_client_cm):
        mock_cm, mock_response, mock_client = mock_httpx_client_cm
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Error", request=MagicMock(), response=MagicMock()
        )
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_page_text(TEST_URL)
        mock_response.raise_for_status.assert_called_once()

    async def test_fetch_page_text_request_error(self, mock_httpx_client_cm):
        mock_cm, mock_response, mock_client = mock_httpx_client_cm
        mock_client.get.side_effect = httpx.RequestError("Error", request=MagicMock())
        with pytest.raises(httpx.RequestError):
            await fetch_page_text(TEST_URL)


@pytest.mark.anyio
class TestFetchAndCleanTextFromUrl:
    """Tests for the fetch_and_clean_text_from_url utility function."""

    @pytest.fixture
    def mock_fetch_page_text(self):
        with patch(
            "meal_planner.services.extract_webpage_text.fetch_page_text",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = (
                "<html><body><a href='foo'>Link</a> Bar</body></html>"
            )
            yield mock_fetch

    @pytest.fixture
    def mock_clean_html_text(self):
        with patch(
            "meal_planner.services.extract_webpage_text.clean_html_text",
            return_value="Link Bar",
        ) as mock_clean:
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
                "Generic error fetching page text",
                id="generic_fetch_exception",
            ),
        ],
    )
    @patch("meal_planner.services.extract_webpage_text.logger.error")
    async def test_fetch_and_clean_errors_during_fetch(
        self,
        mock_logger_error,
        mock_fetch_page_text,
        mock_clean_html_text,
        raised_exception,
        expected_caught_exception,
        expected_log_fragment,
    ):
        mock_fetch_page_text.side_effect = raised_exception

        with pytest.raises(expected_caught_exception):
            await fetch_and_clean_text_from_url(TEST_URL)

        mock_fetch_page_text.assert_called_once_with(TEST_URL)
        assert not mock_clean_html_text.called
        mock_logger_error.assert_called_once()
        args, _ = mock_logger_error.call_args
        assert expected_log_fragment in args[0], (
            f"Log message '{args[0]}' did not contain '{expected_log_fragment}'"
        )

    @patch("meal_planner.services.extract_webpage_text.logger.error")
    async def test_fetch_and_clean_html_cleaner_error(
        self,
        mock_logger_error,
        mock_fetch_page_text,
        mock_clean_html_text,
    ):
        mock_clean_html_text.side_effect = Exception("Cleaning failed")

        with pytest.raises(RuntimeError) as exc_info:
            await fetch_and_clean_text_from_url(TEST_URL)

        assert "Failed to process URL content" in str(exc_info.value)
        mock_fetch_page_text.assert_called_once_with(TEST_URL)
        mock_clean_html_text.assert_called_once_with(
            "<html><body><a href='foo'>Link</a> Bar</body></html>"
        )
        mock_logger_error.assert_called_once()
        args, _ = mock_logger_error.call_args
        assert "Error cleaning HTML text" in args[0]

    async def test_fetch_and_clean_success(
        self, mock_fetch_page_text, mock_clean_html_text
    ):
        result = await fetch_and_clean_text_from_url(TEST_URL)
        assert result == "Link Bar"
        mock_fetch_page_text.assert_called_once_with(TEST_URL)
        mock_clean_html_text.assert_called_once_with(
            "<html><body><a href='foo'>Link</a> Bar</body></html>"
        )

    async def test_fetch_and_clean_success_with_real_cleaner(
        self,
        mock_fetch_page_text,
    ):
        """Test successful fetch and clean, ensuring create_html_cleaner is covered."""

        result = await fetch_and_clean_text_from_url(TEST_URL)

        assert result.strip() == "Link Bar"
        mock_fetch_page_text.assert_called_once_with(TEST_URL)


class TestCleanHtmlText:
    """Tests for the clean_html_text utility function."""

    def test_clean_simple_html(self):
        """Test cleaning simple HTML content."""
        html_input = "<html><body><p>Hello world</p></body></html>"
        result = clean_html_text(html_input)
        assert "Hello world" in result
        assert "<html>" not in result
        assert "<p>" not in result

    def test_clean_html_with_links(self):
        """Test that links are ignored as configured."""
        html_input = '<p>Visit <a href="http://example.com">our site</a> for more.</p>'
        result = clean_html_text(html_input)
        assert "Visit our site for more." in result
        assert "http://example.com" not in result
        assert "<a>" not in result

    def test_clean_html_with_images(self):
        """Test that images are ignored as configured."""
        html_input = '<p>See this <img src="image.jpg" alt="picture"> here.</p>'
        result = clean_html_text(html_input)
        assert "See this" in result and "here." in result
        assert "image.jpg" not in result
        assert "<img>" not in result

    def test_clean_empty_html(self):
        """Test cleaning empty HTML."""
        result = clean_html_text("")
        assert result.strip() == ""

    def test_clean_html_preserves_text_structure(self):
        """Test that basic text structure is preserved."""
        html_input = "<h1>Title</h1><p>Paragraph one.</p><p>Paragraph two.</p>"
        result = clean_html_text(html_input)
        assert "Title" in result
        assert "Paragraph one." in result
        assert "Paragraph two." in result
