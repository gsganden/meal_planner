# Iterative Plan for Phase 5: Route Handler Organization - Dev Loop 1

This document outlines the iterative development loop for refactoring the first piece of functionality: the Home Page Route (`get` at `/`).

## Dev Loop 1: Refactoring the Home Page Route (`get()` at `/`)

- [x] **1. File & Directory Setup (To be done once at the beginning of Phase 5):**
    - [x] Create the directory: `meal_planner/routers/`.
    - [x] Create the file: `meal_planner/routers/__init__.py` (empty, to make `routers` a Python package).
    - [x] Create the file: `meal_planner/routers/pages.py` (initially empty, will house page-rendering routes).
    - [x] Create the file: `meal_planner/routers/actions.py` (initially empty, will house action-performing routes).
    - [x] Create the file: `meal_planner/routers/ui_fragments.py` (initially empty, will house UI fragment routes).

- [x] **2. Code Migration for the `/` Route:**
    - [x] **In `meal_planner/routers/pages.py`:**
        - [x] Add necessary initial imports:
            ```python
            import logging
            from meal_planner.ui.layout import with_layout
            ```
        - [x] Initialize logger: `logger = logging.getLogger(__name__)`
        - [x] Define `rt` by importing it from `meal_planner.main` (for now):
            ```python
            from meal_planner.main import rt
            ```
        - [x] Copy the `get()` function (the one decorated with `@rt("/")`) from `meal_planner/main.py` to `meal_planner/routers/pages.py`.
    - [x] **In `meal_planner/main.py`:**
        - [x] Delete the `get()` function definition (lines defining the `/` route).
        - [x] Add the import statement at the top of the routing section (or after app setup):
            ```python
            from meal_planner.routers import pages # noqa: F401, E402
            ```
        - [x] Review if `from meal_planner.ui.layout import with_layout` can be removed from `main.py` if no other routes in `main.py` use it. (Outcome: Import kept as it's still used)

- [x] **3. Update and Verify Existing Tests (within `tests/test_main.py` or its successor like `tests/main_tests/test_route_endpoints.py`):**
    - [x] Identify the test for the `/` endpoint (e.g., `test_root()` or `test_get_home_page()`).
    - [x] Run the test suite (e.g., `./run_fast_coverage.sh` or `uv run pytest`).
    - [x] Verify the identified test passes (it uses `main.app` which now includes the route via imported `pages` module).
    - [x] Confirm test coverage for the `/` route functionality (now in `meal_planner.routers.pages`) is maintained.

- [x] **4. Move Tests to a New Test File:**
    - [x] Create the file `tests/routers/test_pages.py` (if not already created based on `dev_plans/20250523_test_reorganization.md`).
    - [x] **In `tests/routers/test_pages.py`:**
        - [x] Add necessary imports.
        - [x] Move the specific test function(s) for the `/` endpoint (e.g., `test_root()`) to this file.
    - [x] **In the source test file (e.g., `tests/test_main.py` or `tests/main_tests/test_route_endpoints.py`):**
        - [x] Delete the test function(s) that were moved.

- [x] **5. Confirm Tests and Coverage Post-Test-Move:**
    - [x] Run the test suite again (`./run_fast_coverage.sh`).
    - [x] Verify all tests pass.
    - [x] Verify test coverage is maintained, with `meal_planner/routers/pages.py` being tested by `tests/routers/test_pages.py`.

- [x] **6. Code Quality Checks & User Confirmation:**
    - [x] Run `uv run ruff format .`
    - [x] Run `uv run ruff check --fix .`
    - [x] Ask the user to confirm functionality and commit.

This completes the full development loop for the home page route. The next route will follow a similar pattern.

## Dev Loop 2: Refactoring the Recipe Extraction Page Route (`get_recipe_extraction_page` at `/recipes/extract`)

- [x] **1. Code Migration for the `/recipes/extract` Route:**
    - [x] **In `meal_planner/routers/pages.py`:**
        - [x] Add necessary imports (if not already present). Based on the function in `main.py`, this will likely include `Div` from `fasthtml.common` and `create_extraction_form` from `meal_planner.ui.extract_recipe`. (We already have `with_layout` and `rt`).
        - [x] Copy the `get_recipe_extraction_page()` function from `meal_planner/main.py` to `meal_planner/routers/pages.py`.
    - [x] **In `meal_planner/main.py`:**
        - [x] Delete the `get_recipe_extraction_page()` function definition.
        - [x] Review if imports like `create_extraction_form` from `meal_planner.ui.extract_recipe` or `Div` from `fasthtml.common.*` can be removed from `main.py` if no other routes in `main.py` use them. (Outcome: `create_extraction_form` removed, `Div` via `fasthtml.common.*` kept)

- [x] **2. Update and Verify Existing Tests (likely in `tests/test_main/test_route_endpoints.py`):**
    - [x] Identify the test(s) for the `/recipes/extract` endpoint (e.g., `test_get_recipe_extraction_page()`). (Outcome: No specific, isolated unit test found in the primary test file for this GET page route)
    - [x] Run the test suite (e.g., `./run_fast_coverage.sh`).
    - [x] Verify the identified test(s) pass.
    - [x] Confirm test coverage for the `/recipes/extract` route functionality (now in `meal_planner.routers.pages`) is maintained.

- [x] **3. Move Tests to `tests/routers/test_pages.py`:**
    - [x] **In `tests/routers/test_pages.py`:**
        - [x] Add necessary imports (if not already present).
        - [x] Move the specific test function(s) for the `/recipes/extract` endpoint to this file. (N/A for this route as no specific test was moved)
    - [x] **In the source test file (e.g., `tests/test_main/test_route_endpoints.py`):**
        - [x] Delete the test function(s) that were moved. (N/A for this route)

- [x] **4. Confirm Tests and Coverage Post-Test-Move:**
    - [x] Run the test suite again (`./run_fast_coverage.sh`).
    - [x] Verify all tests pass.
    - [x] Verify test coverage is maintained, with the new functionality in `meal_planner/routers/pages.py` being tested by `tests/routers/test_pages.py`.

- [x] **5. Code Quality Checks & User Confirmation:**
    - [x] Run `uv run ruff format .`
    - [x] Run `uv run ruff check --fix .`
    - [x] Ask the user to confirm functionality and commit.

## Dev Loop 3: Refactoring the Recipe List Page Route (`get_recipe_list_page` at `/recipes`)

- [x] **1. Code Migration for the `/recipes` Route:**
    - [x] **In `meal_planner/routers/pages.py`:**
        - [x] Add necessary new imports:
            ```python
            from fastapi import Request
            import httpx
            from monsterui.all import TextT
            from meal_planner.main import internal_api_client
            from meal_planner.ui.list_recipes import format_recipe_list
            from meal_planner.ui.layout import is_htmx
            ```
        - [x] Copy the `get_recipe_list_page()` function from `meal_planner/main.py` to `meal_planner/routers/pages.py`.
    - [x] **In `meal_planner/main.py`:**
        - [x] Delete the `get_recipe_list_page()` function definition.
        - [x] Review if imports like `Request` (fastapi), `httpx`, `TextT` (monsterui), `format_recipe_list`, `is_htmx` can be removed from `main.py` if no other functions in `main.py` use them. `internal_api_client` will still be defined in `main.py`. (Outcome: Removed `format_recipe_list` and `is_htmx`, kept others as they're still used)

- [x] **2. Update and Verify Existing Tests (likely in `tests/test_main/test_route_endpoints.py`):**
    - [x] Identify the test(s) for the `/recipes` GET endpoint (e.g., `TestGetRecipeListPage` class and its methods).
    - [x] Run the test suite (e.g., `./run_fast_coverage.sh`).
    - [x] Verify the identified test(s) pass.
    - [x] Confirm test coverage for the `/recipes` GET route functionality (now in `meal_planner.routers.pages`) is maintained.

- [x] **3. Move Tests to `tests/routers/test_pages.py`:**
    - [x] **In `tests/routers/test_pages.py`:**
        - [x] Add necessary imports for the moved tests (e.g., `Request`, `AsyncClient`, `patch`, mocks, `format_recipe_list` related helpers/constants if any).
        - [x] Move the specific test class/functions for the `/recipes` GET endpoint (e.g., `TestGetRecipeListPage`) to this file.
        - [x] Update patch targets from `meal_planner.main.internal_api_client` to `meal_planner.routers.pages.internal_api_client`.
    - [x] **In the source test file (e.g., `tests/test_main/test_route_endpoints.py`):**
        - [x] Delete the test class/functions that were moved.

- [x] **4. Confirm Tests and Coverage Post-Test-Move:**
    - [x] Run the test suite again (`./run_fast_coverage.sh`).
    - [x] Verify all tests pass.
    - [x] Verify test coverage is maintained, with the functionality in `meal_planner/routers/pages.py` being tested by `tests/routers/test_pages.py`.

- [x] **5. Code Quality Checks & User Confirmation:**
    - [x] Run `uv run ruff format .`
    - [x] Run `uv run ruff check --fix .`
    - [x] Suggested a one-line commit message.
    - [x] User confirmed functionality and will commit.

## Dev Loop 4: Refactoring the Single Recipe Page Route (`get_single_recipe_page` at `/recipes/{recipe_id:int}`)

- [x] **1. Code Migration for the `/recipes/{recipe_id:int}` Route:**
    - [x] **In `meal_planner/routers/pages.py`:**
        - [x] Add necessary new imports:
            ```python
            from meal_planner.main import internal_client
            from meal_planner.ui.common import CSS_ERROR_CLASS
            from meal_planner.ui.edit_recipe import build_recipe_display
            ```
        - [x] Copy the `get_single_recipe_page()` function from `meal_planner/main.py` to `meal_planner/routers/pages.py`.
    - [x] **In `meal_planner/main.py`:**
        - [x] Delete the `get_single_recipe_page()` function definition.
        - [x] Review if imports like `CSS_ERROR_CLASS`, `build_recipe_display` can be removed from `main.py` if no other functions in `main.py` use them. `internal_client` will still be defined in `main.py`. (Outcome: Both imports kept as they're still heavily used in main.py)

- [x] **2. Update and Verify Existing Tests (likely in `tests/test_main/test_route_endpoints.py`):**
    - [x] Identify the test(s) for the `/recipes/{recipe_id:int}` endpoint (e.g., `TestGetSingleRecipePage` class and its methods).
    - [x] Run the test suite (e.g., `./run_fast_coverage.sh`).
    - [x] Verify the identified test(s) pass.
    - [x] Confirm test coverage for the single recipe page route functionality (now in `meal_planner.routers.pages`) is maintained.

- [x] **3. Move Tests to `tests/routers/test_pages.py`:**
    - [x] **In `tests/routers/test_pages.py`:**
        - [x] Add necessary imports for the moved tests (if not already present).
        - [x] Move the specific test class/functions for the `/recipes/{recipe_id:int}` endpoint (e.g., `TestGetSingleRecipePage`) to this file.
        - [x] Update patch targets from `meal_planner.main.internal_client` to `meal_planner.routers.pages.internal_client`.
    - [x] **In the source test file (e.g., `tests/test_main/test_route_endpoints.py`):**
        - [x] Delete the test class/functions that were moved.

- [x] **4. Confirm Tests and Coverage Post-Test-Move:**
    - [x] Run the test suite again (`./run_fast_coverage.sh`).
    - [x] Verify all tests pass.
    - [x] Verify test coverage is maintained, with the functionality in `meal_planner/routers/pages.py` being tested by `tests/routers/test_pages.py`.

- [x] **5. Code Quality Checks & User Confirmation:**
    - [x] Run `uv run ruff format .`
    - [x] Run `uv run ruff check --fix .`
    - [x] Run `./scripts/check_refactor_diff.sh` and reviewed its output; net change is minimal.
    - [x] Suggested a one-line commit message.
    - [x] User confirmed functionality and will commit.

## Dev Loop 5: Refactoring the Save Recipe Action Route (`post_save_recipe` at `/recipes/save`)

- [x] **1. Code Migration for the `/recipes/save` Route:**
    - [x] **In `meal_planner/routers/actions.py`:**
        - [x] Add necessary imports (including `httpx`, `rt`, `internal_client` from main, `RecipeBase`, `CSS_ERROR_CLASS`, `CSS_SUCCESS_CLASS`, `_parse_recipe_form_data` from `form_processing`).
        - [x] Copy the `post_save_recipe()` function from `meal_planner/main.py` to `meal_planner/routers/actions.py`.
    - [x] **In `meal_planner/form_processing.py` (New file created):**
        - [x] Move `_parse_recipe_form_data()` here from `main.py`.
    - [x] **In `meal_planner/main.py`:**
        - [x] Delete the `post_save_recipe()` function definition.
        - [x] Delete `_parse_recipe_form_data()` function definition (moved to `form_processing.py`).
        - [x] Import `_parse_recipe_form_data` from `form_processing.py`.
        - [x] Remove unused imports: `starlette.status`, `CSS_SUCCESS_CLASS`. (`ValidationError`, `FormData` kept as they are still used).

- [x] **2. Update and Verify Existing Tests (in `tests/test_main/test_route_endpoints.py` and `tests/routers/test_actions.py`):**
    - [x] Identified `TestSaveRecipeEndpoint` (already in `tests/routers/test_actions.py`).
    - [x] Updated patch targets in `tests/test_main/test_route_endpoints.py` for `_parse_recipe_form_data` in `test_save_recipe_parsing_exception` (to `meal_planner.routers.actions._parse_recipe_form_data`) and `test_update_diff_parsing_exception` (to `meal_planner.main._parse_recipe_form_data`).
    - [x] Run the test suite (`./run_fast_coverage.sh`).
    - [x] Verified all tests pass.
    - [x] Confirmed test coverage for the save recipe route functionality is maintained at 100%.

- [x] **3. Move Tests to `tests/routers/test_actions.py`:**
    - [x] `tests/routers/test_actions.py` already existed and contained `TestSaveRecipeEndpoint`.
    - [x] **In `tests/routers/test_actions.py`:**
        - [x] Necessary imports were already present.
        - [x] `TestSaveRecipeEndpoint` was confirmed to be correctly located.
        - [x] Patch targets within `TestSaveRecipeEndpoint` (e.g., for `internal_client.post`, `_parse_recipe_form_data`) were confirmed to point to `meal_planner.routers.actions.*`.
    - [x] **In the source test file (`tests/test_main/test_route_endpoints.py`):**
        - [x] Deleted the (original/duplicate) `TestSaveRecipeEndpoint` class.

- [x] **4. Confirm Tests and Coverage Post-Test-Move:**
    - [x] Run the test suite again (`./run_fast_coverage.sh`).
    - [x] Verified all tests pass (163 passed).
    - [x] Verified test coverage is maintained at 100%.

- [x] **5. Code Quality Checks & User Confirmation:**
    - [x] Run `uv run ruff format .`
    - [x] Run `uv run ruff check --fix .`
    - [x] Suggested a one-line commit message.
    - [x] User confirmed functionality and will commit.

## Dev Loop 6: Refactoring the Recipe Modification Route (`post_modify_recipe` at `/recipes/modify`)

- [x] **1. Code Migration for the `/recipes/modify` Route:**
    - [x] **In `meal_planner/routers/actions.py`:**
        - [x] Add necessary new imports:
            ```python
            # from meal_planner.models import RecipeBase (already there)
            from meal_planner.services.call_llm import generate_modified_recipe
            from meal_planner.services.process_recipe import postprocess_recipe
            from meal_planner.ui.edit_recipe import build_modify_form_response
            # Already has: Request, FormData, rt, logger, CSS_ERROR_CLASS
            # Already imports _parse_recipe_form_data via form_processing
            ```
        - [x] Copy the `post_modify_recipe()` function from `meal_planner/main.py` to `meal_planner/routers/actions.py`.
    - [x] **In `meal_planner/main.py`:**
        - [x] Delete the `post_modify_recipe()` function definition.
        - [x] Review if imports like `generate_modified_recipe`, `postprocess_recipe`, `build_modify_form_response` can now be removed from `main.py` if no other functions in `main.py` use them.

- [x] **2. Update and Verify Existing Tests (likely in `tests/test_main/test_modify_recipe_endpoint.py`):**
    - [x] Identify the test class/functions for the `/recipes/modify` endpoint (e.g., `TestModifyRecipeEndpoint` in `tests/test_main/test_modify_recipe_endpoint.py`).
    - [x] Run the test suite (e.g., `./run_fast_coverage.sh`).
    - [x] Verify the identified test(s) pass. The target URL `/recipes/modify` remains the same.
    - [x] Examine and update patch targets within these tests. For example:
        - `meal_planner.main.generate_modified_recipe` -> `meal_planner.routers.actions.generate_modified_recipe` (if imported directly into actions) or `meal_planner.services.call_llm.generate_modified_recipe` (if patching at source). Prefer patching where it's looked up in the module under test.
        - `meal_planner.main._parse_recipe_form_data` (if used by `post_modify_recipe` directly, which it is) -> `meal_planner.routers.actions._parse_recipe_form_data` (as it's imported from `form_processing` into `actions.py`).
        - `meal_planner.main.build_modify_form_response` -> `meal_planner.routers.actions.build_modify_form_response` or source.
    - [x] Confirm test coverage for the `/recipes/modify` route functionality (now in `meal_planner.routers.actions`) is maintained after patch target adjustments.

- [x] **3. Move Tests to `tests/routers/test_actions.py`:**
    - [x] **In `tests/routers/test_actions.py`:**
        - [x] Add necessary new imports for the moved tests.
        - [x] Move the specific test class/functions for the `/recipes/modify` endpoint (e.g., `TestModifyRecipeEndpoint`) to this file.
    - [x] **In the source test file (e.g., `tests/test_main/test_modify_recipe_endpoint.py`):**
        - [x] Delete the test class/functions that were moved. (If `test_modify_recipe_endpoint.py` becomes empty, consider deleting it or its import if it's a separate file).

- [x] **4. Confirm Tests and Coverage Post-Test-Move:**
    - [x] Run the test suite again (`./run_fast_coverage.sh`).
    - [x] Verify all tests pass.
    - [x] Verify test coverage is maintained.

- [x] **5. Code Quality Checks & User Confirmation:**
    - [x] Run `uv run ruff format .`
    - [x] Run `uv run ruff check --fix .`
    - [x] Run `./scripts/check_refactor_diff.sh` and review its output to confirm minimal net change in application code.
    - [x] Suggest a one-line commit message.
    - [x] Ask the user to confirm functionality and commit.

## Dev Loop 7: Refactoring Recipe Editor UI Fragment Routes

- [x] **1. Code Migration for UI Fragment Routes:**
    - [x] **In `meal_planner/routers/ui_fragments.py`:**
        - [x] Add necessary initial imports:
            ```python
            import logging
            from fastapi import Request
            from fasthtml.common import * # type: ignore
            from pydantic import ValidationError

            from meal_planner.form_processing import _parse_recipe_form_data
            from meal_planner.main import rt # Assuming rt is needed
            from meal_planner.models import RecipeBase
            from meal_planner.ui.common import CSS_ERROR_CLASS
            from meal_planner.ui.edit_recipe import (
                build_diff_content_children,
                render_ingredient_list_items,
                render_instruction_list_items,
            )
            # FT from fasthtml.common may be needed for type hints if not covered by *
            ```
        - [x] Initialize logger: `logger = logging.getLogger(__name__)`
        - [x] Copy the following functions from `meal_planner/main.py` to `meal_planner/routers/ui_fragments.py`:
            - `post_delete_ingredient_row()`
            - `post_delete_instruction_row()`
            - `post_add_ingredient_row()`
            - `post_add_instruction_row()`
            - `update_diff()`
            - `_build_sortable_list_with_oob_diff()`
    - [x] **In `meal_planner/main.py`:**
        - [x] Delete the definitions of the six functions listed above.
        - [x] Add the import statement:
            ```python
            from meal_planner.routers import ui_fragments # noqa: F401, E402
            ```
        - [x] Review if imports exclusively used by these moved functions can be removed from `main.py`. Potential candidates: `render_ingredient_list_items`, `render_instruction_list_items`, `build_diff_content_children`. `FormData` might still be used by other routes.

- [x] **2. Update and Verify Existing Tests:**
    - [x] Identify the test(s) for these UI fragment endpoints. These are likely in `tests/test_ui/test_recipe_editor.py` and potentially `tests/test_main/test_route_endpoints.py` (for `update_diff` if it had its own test class there).
    - [x] Run the test suite (e.g., `./run_fast_coverage.sh`).
    - [x] Verify the identified test(s) pass. The target URLs remain the same.
    - [x] Examine and update patch targets within these tests. For example:
        - `meal_planner.main._parse_recipe_form_data` -> `meal_planner.routers.ui_fragments._parse_recipe_form_data` (as it's imported from `form_processing` into `ui_fragments.py`).
        - Any other direct mocks of functions now within `ui_fragments.py` need to be updated.

- [x] **3. Move Tests to `tests/routers/test_ui_fragments.py`:**
    - [x] Create the file `tests/routers/test_ui_fragments.py` (if not already present from a previous refactoring phase).
    - [x] **In `tests/routers/test_ui_fragments.py`:**
        - [x] Add necessary new imports for the moved tests.
        - [x] Move the specific test classes/functions for these UI fragment endpoints to this file.
    - [x] **In the source test file(s):**
        - [x] Delete the test classes/functions that were moved.

- [x] **4. Confirm Tests and Coverage Post-Test-Move:**
    - [x] Run the test suite again (`./run_fast_coverage.sh`).
    - [x] Verify all tests pass.
    - [x] Verify test coverage is maintained for the moved routes and helper.

- [x] **5. Code Quality Checks & User Confirmation:**
    - [x] Run `uv run ruff format .`
    - [x] Run `uv run ruff check --fix .`
    - [x] Make sure we haven't added code comments, except docstrings that add information beyond the item name and type hints.
    - [x] Suggested a one-line commit message.
    - [x] User confirmed functionality and committed.

## Dev Loop 8: Refactoring the Fetch Text UI Fragment Route (`post_fetch_text` at `/recipes/fetch-text`)

- [x] **1. Code Migration for the `/recipes/fetch-text` Route:**
    - [x] **In `meal_planner/routers/ui_fragments.py`:**
        - [x] Add necessary new imports (e.g., `httpx`, `TextArea`, `Group` from `monsterui.all` if not already covered by `fasthtml.common.*`).
        - [x] Copy the `post_fetch_text()` function from `meal_planner/main.py` to `meal_planner/routers/ui_fragments.py`.
    - [x] **In `meal_planner/main.py`:**
        - [x] Delete the `post_fetch_text()` function definition.
        - [x] Review if imports exclusively used by this function can be removed from `main.py` (e.g., `fetch_and_clean_text_from_url` if no other main route uses it).

- [x] **2. Update and Verify Existing Tests:**
    - [x] Identify the test(s) for the `/recipes/fetch-text` endpoint. These are likely in `tests/test_main/test_route_endpoints.py` (e.g., a class like `TestPostFetchText` or similar).
    - [x] Run the test suite (e.g., `./run_fast_coverage.sh`).
    - [x] Verify the identified test(s) pass. The target URL `/recipes/fetch-text` remains the same.
    - [x] Examine and update patch targets within these tests if necessary (e.g., if `fetch_and_clean_text_from_url` was mocked relative to `main`, it might now need to be mocked relative to `ui_fragments`).

- [x] **3. Move Tests to `tests/routers/test_ui_fragments.py`:**
    - [x] **In `tests/routers/test_ui_fragments.py`:**
        - [x] Add necessary new imports for the moved tests.
        - [x] Move the specific test class/functions for the `/recipes/fetch-text` endpoint to this file.
    - [x] **In the source test file (e.g., `tests/test_main/test_route_endpoints.py`):**
        - [x] Delete the test class/functions that were moved.

- [x] **4. Confirm Tests and Coverage Post-Test-Move:**
    - [x] Run the test suite again (`./run_fast_coverage.sh`).
    - [x] Verify all tests pass.
    - [x] Verify test coverage is maintained for the moved route.

- [x] **5. Code Quality Checks & User Confirmation:**
    - [x] Run `uv run ruff format .`
    - [x] Run `uv run ruff check --fix .`
    - [x] Ensure no non-docstring comments were added.
    - [x] Manually check `git diff --stat HEAD` to confirm minimal net change in application code.
    - [x] Suggested a one-line commit message.
    - [x] User confirmed functionality and will commit.

## Dev Loop 9: Refactoring the Recipe Extraction Action Route (`post` at `/recipes/extract/run`)

- [x] **1. Code Migration for the `/recipes/extract/run` Route and Helper:**
    - [x] **In `meal_planner/routers/actions.py`:**
        - [x] Add necessary new imports (e.g., `RecipeBase` from `meal_planner.models`, `generate_recipe_from_text` from `meal_planner.services.call_llm`, `postprocess_recipe` from `meal_planner.services.process_recipe`, `build_edit_review_form`, `build_recipe_display` from `meal_planner.ui.edit_recipe`, `H2`, `Group` if not already covered).
        - [x] Copy the `extract_recipe_from_text()` helper function from `meal_planner/main.py` to `meal_planner/routers/actions.py`.
        - [x] Copy the `post()` function (the one decorated with `@rt("/recipes/extract/run")`) from `meal_planner/main.py` to `meal_planner/routers/actions.py`.
    - [x] **In `meal_planner/main.py`:**
        - [x] Delete the `extract_recipe_from_text()` function definition.
        - [x] Delete the `post()` function definition (for `/recipes/extract/run`).
        - [x] Review if imports exclusively used by these moved functions can be removed from `main.py` (e.g., `generate_recipe_from_text`, `postprocess_recipe`, `build_edit_review_form`, `build_recipe_display`).

- [x] **2. Update and Verify Existing Tests:**
    - [x] Identify the test(s) for the `/recipes/extract/run` endpoint. These are likely in `tests/test_main/test_extract_recipe_endpoints.py` (e.g., `TestExtractRecipeEndpoint` class).
    - [x] Run the test suite (e.g., `./run_fast_coverage.sh`).
    - [x] Verify the identified test(s) pass. The target URL `/recipes/extract/run` remains the same.
    - [x] Examine and update patch targets within these tests. For example:
        - `meal_planner.main.generate_recipe_from_text` -> `meal_planner.routers.actions.generate_recipe_from_text`
        - `meal_planner.main.postprocess_recipe` -> `meal_planner.routers.actions.postprocess_recipe` (or to their original service locations if that's preferred, but patching where it's looked up in `actions.py` is consistent).
        - `meal_planner.main.logger.error` (if used in the context of these moved functions' tests) -> `meal_planner.routers.actions.logger.error`.

- [x] **3. Move Tests to `tests/routers/test_actions.py`:**
    - [x] **In `tests/routers/test_actions.py`:**
        - [x] Add necessary new imports for the moved tests (e.g., `RecipeBase`, any specific constants like `FIELD_RECIPE_TEXT`, `RECIPES_EXTRACT_RUN_URL`, `CSS_ERROR_CLASS`).
        - [x] Move the specific test class/functions (e.g., `TestExtractRecipeEndpoint` and any related fixtures like `mock_recipe_data_fixture`) to this file.
    - [x] **In the source test file (e.g., `tests/test_main/test_extract_recipe_endpoints.py`):**
        - [x] Delete the test class/functions and fixtures that were moved. If the file becomes empty or only contains unused imports, consider deleting it.

- [x] **4. Confirm Tests and Coverage Post-Test-Move:**
    - [x] Run the test suite again (`./run_fast_coverage.sh`).
    - [x] Verify all tests pass.
    - [x] Verify test coverage is maintained for the moved route and helper.

- [x] **5. Code Quality Checks & User Confirmation:**
    - [x] Run `uv run ruff format .`
    - [x] Run `uv run ruff check --fix .`
    - [x] Ensure no non-docstring comments were added.
    - [x] Manually check `git diff --stat HEAD` to confirm minimal net change in application code.
    - [x] Suggest a one-line commit message.
    - [x] Ask the user to confirm functionality and commit.
