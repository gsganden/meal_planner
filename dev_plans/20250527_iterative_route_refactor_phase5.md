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
    - [x] Verify test coverage is maintained, with the new functionality in `meal_planner/routers/pages.py` being tested by `tests/routers/test_pages.py`. (N/A for specific test move, overall coverage maintained)

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
    - [x] Ask the user to confirm functionality and commit.

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
    - [x] Ask the user to confirm functionality and commit.

## Dev Loop 5: Refactoring the Save Recipe Action Route (`post_save_recipe` at `/recipes/save`)

- [ ] **1. Code Migration for the `/recipes/save` Route:**
    - [ ] **In `meal_planner/routers/actions.py`:**
        - [ ] Add necessary imports:
            ```python
            import logging
            from fastapi import Request
            from fasthtml.common import *
            from pydantic import ValidationError
            from starlette import status
            from starlette.datastructures import FormData
            
            from meal_planner.main import rt, internal_client
            from meal_planner.models import RecipeBase
            from meal_planner.ui.common import CSS_ERROR_CLASS, CSS_SUCCESS_CLASS
            ```
        - [ ] Copy the `post_save_recipe()` function from `meal_planner/main.py` to `meal_planner/routers/actions.py`.
        - [ ] Copy the `_parse_recipe_form_data()` helper function from `meal_planner/main.py` to `meal_planner/routers/actions.py` (since it's used by the save route).
    - [ ] **In `meal_planner/main.py`:**
        - [ ] Delete the `post_save_recipe()` function definition.
        - [ ] Review if `_parse_recipe_form_data()` can be removed (check if other routes in main.py still use it).
        - [ ] Review if imports like `ValidationError`, `status`, `FormData`, `CSS_SUCCESS_CLASS` can be removed from `main.py` if no other functions use them.

- [ ] **2. Update and Verify Existing Tests (likely in `tests/test_main/test_route_endpoints.py`):**
    - [ ] Identify the test(s) for the `/recipes/save` endpoint (e.g., `TestSaveRecipeEndpoint` class and its methods).
    - [ ] Run the test suite (e.g., `./run_fast_coverage.sh`).
    - [ ] Verify the identified test(s) pass.
    - [ ] Confirm test coverage for the save recipe route functionality (now in `meal_planner.routers.actions`) is maintained.

- [ ] **3. Move Tests to `tests/routers/test_actions.py`:**
    - [ ] Create the file `tests/routers/test_actions.py` if it doesn't exist.
    - [ ] **In `tests/routers/test_actions.py`:**
        - [ ] Add necessary imports for the moved tests.
        - [ ] Move the specific test class/functions for the `/recipes/save` endpoint (e.g., `TestSaveRecipeEndpoint`) to this file.
        - [ ] Update patch targets from `meal_planner.main.*` to `meal_planner.routers.actions.*` where applicable.
    - [ ] **In the source test file (e.g., `tests/test_main/test_route_endpoints.py`):**
        - [ ] Delete the test class/functions that were moved.

- [ ] **4. Confirm Tests and Coverage Post-Test-Move:**
    - [ ] Run the test suite again (`./run_fast_coverage.sh`).
    - [ ] Verify all tests pass.
    - [ ] Verify test coverage is maintained, with the functionality in `meal_planner/routers/actions.py` being tested by `tests/routers/test_actions.py`.

- [ ] **5. Code Quality Checks & User Confirmation:**
    - [ ] Run `uv run ruff format .`
    - [ ] Run `uv run ruff check --fix .`
    - [ ] Confirm that the net diff size is ~0-10 lines.
    - [ ] Ask the user to confirm functionality and commit.
