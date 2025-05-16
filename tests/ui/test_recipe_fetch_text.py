from unittest.mock import AsyncMock, patch

import httpx
import pytest
from bs4 import BeautifulSoup
from bs4.element import Tag  # Added for type hint
from httpx import AsyncClient, Request, Response

from meal_planner.ui.common import CSS_ERROR_CLASS
from tests import constants

# Copied from tests/test_main.py - consider moving to a shared constants module
# URLs
# RECIPES_FETCH_TEXT_URL = "/recipes/fetch-text" # Moved

# Form Field Names
# FIELD_RECIPE_URL = "input_url" # Moved
# FIELD_RECIPE_TEXT = "recipe_text" # Moved

# Other constants potentially used by the class or its methods
# CSS_ERROR_CLASS = "uk-text-danger uk-text-small" # REMOVE THIS - Use imported one
# TEST_URL = "http://test-recipe.com" # Moved to constants


@pytest.mark.anyio
class TestRecipeFetchTextEndpoint:
    CLASS_TEST_URL = "http://example.com/fetch-success"  # Specific to this class, renamed to avoid conflict

    async def test_success(self, client: AsyncClient):
        mock_text = "Fetched and cleaned recipe text."

        with patch(
            "meal_planner.main.fetch_and_clean_text_from_url",
            new_callable=AsyncMock,
        ) as local_mock_fetch_clean:
            local_mock_fetch_clean.return_value = mock_text

            response = await client.post(
                constants.RECIPES_FETCH_TEXT_URL,
                data={constants.FIELD_RECIPE_URL: self.CLASS_TEST_URL},
            )

        assert response.status_code == 200
        local_mock_fetch_clean.assert_called_once_with(self.CLASS_TEST_URL)
        assert "<textarea" in response.text
        assert f'id="{constants.FIELD_RECIPE_TEXT}"' in response.text
        assert f'name="{constants.FIELD_RECIPE_TEXT}"' in response.text
        assert f">{mock_text}</textarea>" in response.text

    async def test_missing_url(self, client: AsyncClient):
        response = await client.post(constants.RECIPES_FETCH_TEXT_URL, data={})
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
                        "request": Request(
                            "GET", constants.TEST_URL
                        ),  # Uses global TEST_URL
                        "response": Response(
                            404, request=Request("GET", constants.TEST_URL)
                        ),
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
                "An unexpected error occurred while fetching text.",
            ),
        ],
    )
    async def test_fetch_text_errors(
        self,
        client: AsyncClient,
        exception_type,
        exception_args,
        expected_message,
    ):
        """Test that various exceptions from the service are handled correctly."""
        # Uses self.CLASS_TEST_URL from the class for the actual call
        with patch(
            "meal_planner.main.fetch_and_clean_text_from_url", new_callable=AsyncMock
        ) as local_mock_fetch_clean:
            if exception_type == httpx.HTTPStatusError:
                message, details = exception_args
                local_mock_fetch_clean.side_effect = exception_type(
                    message, request=details["request"], response=details["response"]
                )
            else:
                local_mock_fetch_clean.side_effect = exception_type(*exception_args)

            response = await client.post(
                constants.RECIPES_FETCH_TEXT_URL,
                data={
                    constants.FIELD_RECIPE_URL: self.CLASS_TEST_URL
                },  # Call uses self.CLASS_TEST_URL
            )

            local_mock_fetch_clean.assert_called_once_with(
                self.CLASS_TEST_URL
            )  # Assert call with self.CLASS_TEST_URL

            assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")

        text_area_container = soup.find("div", id="recipe_text_container")
        assert text_area_container is not None
        text_area = text_area_container.find("textarea", id="recipe_text")
        assert text_area is not None
        assert text_area.get_text(strip=True) == ""

        error_div = soup.find("div", id="fetch-url-error-display")
        assert error_div is not None
        assert error_div.text.strip() == expected_message
        expected_classes = set(CSS_ERROR_CLASS.split())
        actual_classes = set(error_div.get("class", []))
        assert expected_classes.issubset(actual_classes)

        parent_of_error_div = error_div.parent
        assert parent_of_error_div is not None, "Parent of error_div not found"
        assert isinstance(parent_of_error_div, Tag), "Parent of error_div is not a Tag"
        assert (
            parent_of_error_div.get("hx-swap-oob")
            == "outerHTML:#fetch-url-error-display"
        ), (
            f"hx-swap-oob attribute incorrect or missing on parent of error_div. "
            f"Got: {parent_of_error_div.get('hx-swap-oob')}"
        )
