# Iterative Plan for Phase 5: Route Handler Organization - Dev Loop 1

This document outlines the iterative development loop for refactoring the first piece of functionality: the Home Page Route (`get` at `/`).

## Dev Loop 1: Refactoring the Home Page Route (`get()` at `/`)

- [ ] **1. File & Directory Setup (To be done once at the beginning of Phase 5):**
    - [ ] Create the directory: `meal_planner/routers/`.
    - [ ] Create the file: `meal_planner/routers/__init__.py` (empty, to make `routers` a Python package).
    - [ ] Create the file: `meal_planner/routers/pages.py` (initially empty, will house page-rendering routes).
    - [ ] Create the file: `meal_planner/routers/actions.py` (initially empty, will house action-performing routes).
    - [ ] Create the file: `meal_planner/routers/ui_fragments.py` (initially empty, will house UI fragment routes).

- [ ] **2. Code Migration for the `/` Route:**
    - [ ] **In `meal_planner/routers/pages.py`:**
        - [ ] Add necessary initial imports:
            ```python
            import logging
            from meal_planner.ui.layout import with_layout
            ```
        - [ ] Initialize logger: `logger = logging.getLogger(__name__)`
        - [ ] Define `rt` by importing it from `meal_planner.main` (for now):
            ```python
            from meal_planner.main import rt
            ```
        - [ ] Copy the `get()` function (the one decorated with `@rt("/")`) from `meal_planner/main.py` to `meal_planner/routers/pages.py`.
    - [ ] **In `meal_planner/main.py`:**
        - [ ] Delete the `get()` function definition (lines defining the `/` route).
        - [ ] Add the import statement at the top of the routing section (or after app setup):
            ```python
            from meal_planner.routers import pages # noqa: F401, E402
            ```
        - [ ] Review if `from meal_planner.ui.layout import with_layout` can be removed from `main.py` if no other routes in `main.py` use it.

- [ ] **3. Update and Verify Existing Tests (within `tests/test_main.py` or its successor like `tests/main_tests/test_route_endpoints.py`):**
    - [ ] Identify the test for the `/` endpoint (e.g., `test_root()` or `test_get_home_page()`).
    - [ ] Run the test suite (e.g., `./run_fast_coverage.sh` or `uv run pytest`).
    - [ ] Verify the identified test passes (it uses `main.app` which now includes the route via imported `pages` module).
    - [ ] Confirm test coverage for the `/` route functionality (now in `meal_planner.routers.pages`) is maintained.

- [ ] **4. Move Tests to a New Test File:**
    - [ ] Create the file `tests/routers/test_pages.py` (if not already created based on `dev_plans/20250523_test_reorganization.md`).
    - [ ] **In `tests/routers/test_pages.py`:**
        - [ ] Add necessary imports.
        - [ ] Move the specific test function(s) for the `/` endpoint (e.g., `test_root()`) to this file.
    - [ ] **In the source test file (e.g., `tests/test_main.py` or `tests/main_tests/test_route_endpoints.py`):**
        - [ ] Delete the test function(s) that were moved.

- [ ] **5. Confirm Tests and Coverage Post-Test-Move:**
    - [ ] Run the test suite again (`./run_fast_coverage.sh`).
    - [ ] Verify all tests pass.
    - [ ] Verify test coverage is maintained, with `meal_planner/routers/pages.py` being tested by `tests/routers/test_pages.py`.

- [ ] **6. Code Quality Checks & User Confirmation:**
    - [ ] Run `uv run ruff format .`
    - [ ] Run `uv run ruff check --fix .`
    - [ ] Ask the user to confirm functionality and commit.

This completes the full development loop for the home page route. The next route will follow a similar pattern. 
