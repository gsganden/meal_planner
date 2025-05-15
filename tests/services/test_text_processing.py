from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from meal_planner.services.text_processing import (
    HTML_CLEANER,  # Assuming HTML_CLEANER might be needed for some tests, or its mock
    fetch_and_clean_text_from_url,
    fetch_page_text,
)

TEST_URL = "http://test-recipe.com"  # Define if not imported from elsewhere


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
        mock_cm.assert_called_once_with(
            follow_redirects=True, timeout=15.0, headers=pytest.approx(dict)
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
            "meal_planner.services.text_processing.fetch_page_text",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = (
                "<html><body><a href='foo'>Link</a> Bar</body></html>"
            )
            yield mock_fetch

    @pytest.fixture
    def mock_html_cleaner(self):
        mock_cleaner_instance = MagicMock(spec=HTML_CLEANER)
        mock_cleaner_instance.handle.return_value = "Link Bar"
        # Patch where HTML_CLEANER is defined and used
        with patch(
            "meal_planner.services.text_processing.HTML_CLEANER", mock_cleaner_instance
        ) as _:
            yield mock_cleaner_instance  # yield the instance for assertions if needed

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
                # The service wraps generic exceptions from fetch_page_text
                RuntimeError,
                "Generic error fetching page text",
                id="generic_fetch_exception",
            ),
        ],
    )
    @patch("meal_planner.services.text_processing.logger.error")
    async def test_fetch_and_clean_errors_during_fetch(
        self,
        mock_logger_error,
        mock_fetch_page_text,
        mock_html_cleaner,  # This will be the instance from the fixture
        raised_exception,
        expected_caught_exception,
        expected_log_fragment,
    ):
        mock_fetch_page_text.side_effect = raised_exception

        with pytest.raises(expected_caught_exception):
            await fetch_and_clean_text_from_url(TEST_URL)

        mock_fetch_page_text.assert_called_once_with(TEST_URL)
        assert not mock_html_cleaner.handle.called
        mock_logger_error.assert_called_once()
        # Check that the log message contains the expected fragment
        args, _ = mock_logger_error.call_args
        assert expected_log_fragment in args[0], (
            f"Log message '{args[0]}' did not contain '{expected_log_fragment}'"
        )

    @patch("meal_planner.services.text_processing.logger.error")
    async def test_fetch_and_clean_html_cleaner_error(
        self,
        mock_logger_error,
        mock_fetch_page_text,  # Patched fetch_page_text
        mock_html_cleaner,  # Patched HTML_CLEANER instance
    ):
        mock_html_cleaner.handle.side_effect = Exception("Cleaning failed")

        with pytest.raises(RuntimeError) as exc_info:
            await fetch_and_clean_text_from_url(TEST_URL)

        assert "Failed to process URL content" in str(exc_info.value)
        mock_fetch_page_text.assert_called_once_with(TEST_URL)
        mock_html_cleaner.handle.assert_called_once_with(
            "<html><body><a href='foo'>Link</a> Bar</body></html>"
        )
        mock_logger_error.assert_called_once()
        args, _ = mock_logger_error.call_args
        assert "Error cleaning HTML text" in args[0]

    async def test_fetch_and_clean_success(
        self, mock_fetch_page_text, mock_html_cleaner
    ):
        result = await fetch_and_clean_text_from_url(TEST_URL)
        assert result == "Link Bar"
        mock_fetch_page_text.assert_called_once_with(TEST_URL)
        mock_html_cleaner.handle.assert_called_once_with(
            "<html><body><a href='foo'>Link</a> Bar</body></html>"
        )
