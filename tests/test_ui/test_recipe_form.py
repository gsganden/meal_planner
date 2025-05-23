import pytest
from httpx import ASGITransport, AsyncClient

from meal_planner.main import app
from tests.constants import (
    RECIPES_EXTRACT_RUN_URL,
    RECIPES_EXTRACT_URL,
    RECIPES_FETCH_TEXT_URL,
)

TRANSPORT = ASGITransport(app=app)


@pytest.mark.anyio
async def test_extract_recipe_page_loads(
    client: AsyncClient,
):
    response = await client.get(RECIPES_EXTRACT_URL)
    assert response.status_code == 200
    assert 'id="input_url"' in response.text
    assert 'name="input_url"' in response.text
    assert 'placeholder="https://example.com/recipe"' in response.text
    assert f'hx-post="{RECIPES_FETCH_TEXT_URL}"' in response.text
    assert "hx-include=\"[name='input_url']\"" in response.text
    assert "Fetch Text from URL" in response.text
    assert 'id="recipe_text"' in response.text
    assert (
        'placeholder="Paste full recipe text here, or fetch from URL above."'
        in response.text
    )
    assert f'hx-post="{RECIPES_EXTRACT_RUN_URL}"' in response.text
    assert "Extract Recipe" in response.text
    assert 'id="recipe-results"' in response.text
