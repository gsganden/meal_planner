# Test File Reorganization Plan

## Overview
Reorganize test files to mirror the source code structure. Move tests from the catchall `tests/test_main.py` into focused, appropriately located test files.

## Principle
- **tests/main_tests/** → Tests code in `meal_planner/main.py` (route handlers & utility functions)
- **tests/ui/** → Tests code in `meal_planner/ui/` (UI components & helpers)
- **tests/** → Shared test utilities and helpers (not testing source code directly)

---

## Current State
- `tests/test_main.py` - 963 lines, mixed concerns, catchall file
- `tests/ui/test_recipe_editor.py` - Already correctly testing `ui/recipe_editor.py`
- `tests/main_tests/test_recipe_extraction.py` - Already correctly testing main functionality
- `tests/main_tests/test_recipe_modify_endpoint.py` - Already correctly testing main functionality

---

## Target File Structure

### `tests/main_tests/` (Testing `main.py` code)

#### `test_route_endpoints.py`
**Purpose**: Test all route handlers defined in `main.py`
- [ ] `TestSmokeEndpoints`
  - [ ] `test_root()` - Testing `/` route
  - [ ] `test_extract_recipe_page_loads()` - Testing `/recipes/extract` route
- [ ] `TestGetRecipeListPageErrors` - Testing `/recipes` route errors
  - [ ] `test_get_recipes_page_api_status_error()`
  - [ ] `test_get_recipes_page_api_error_htmx()`
  - [ ] `test_get_recipes_page_api_generic_error()`
- [ ] `TestGetRecipeListPageSuccess` - Testing `/recipes` route success
  - [ ] `test_get_recipes_page_success_with_data()`
  - [ ] `test_get_recipes_page_success_htmx()`
  - [ ] `test_get_recipes_page_success_no_data()`
- [ ] `TestGetSingleRecipePageErrors` - Testing `/recipes/{id}` route errors
  - [ ] `test_get_single_recipe_page_api_404()`
  - [ ] `test_get_single_recipe_page_api_other_status_error()`
  - [ ] `test_get_single_recipe_page_api_generic_error()`
- [ ] `TestGetSingleRecipePageSuccess` - Testing `/recipes/{id}` route success
  - [ ] `test_get_single_recipe_page_success()`
- [ ] All save recipe tests - Testing `/recipes/save` route
  - [ ] `test_save_recipe_success()`
  - [ ] `test_save_recipe_missing_data()` (parameterized)
  - [ ] `test_save_recipe_api_call_error()`
  - [ ] `test_save_recipe_validation_error()` (parameterized)
  - [ ] `test_save_recipe_api_call_generic_error()`
  - [ ] `test_save_recipe_api_call_request_error()`
  - [ ] `test_save_recipe_api_call_non_json_error_response()`
  - [ ] `test_save_recipe_api_call_422_error()`
  - [ ] `test_save_recipe_api_call_json_error_with_detail()`
- [ ] `TestRecipeUpdateDiff` - Testing `/recipes/ui/update-diff` route
  - [ ] `test_diff_generation_error()`
  - [ ] `test_update_diff_validation_error()` (parameterized)
- [ ] Form parsing exception tests (testing route error handling)
  - [ ] `test_update_diff_parsing_exception()`
  - [ ] `test_save_recipe_parsing_exception()`

#### `test_form_parsing.py`
**Purpose**: Test the `_parse_recipe_form_data()` utility function from `main.py`
- [ ] `TestParseRecipeFormData`
  - [ ] `test_parse_basic()`
  - [ ] `test_parse_with_prefix()`
  - [ ] `test_parse_missing_fields()`
  - [ ] `test_parse_empty_strings_and_whitespace()`
  - [ ] `test_parse_empty_form()`

### `tests/` (Shared test utilities)

#### `test_helpers.py`
**Purpose**: Test utilities and helper functions (not testing source code directly)
- [ ] `FormTargetDivNotFoundError` - Custom exception for form parsing
- [ ] `_get_edit_form_target_div()` - HTML parsing helper
- [ ] `_extract_form_value()` - Form field extraction helper  
- [ ] `_extract_form_list_values()` - Form list extraction helper
- [ ] `_extract_full_edit_form_data()` - Complete form data extraction
- [ ] `create_mock_api_response()` - Mock API response utility

#### Enhanced `conftest.py`
**Purpose**: Shared pytest fixtures
- [ ] Move `mock_recipe_data_fixture` from `test_main.py`
- [ ] Ensure all shared fixtures are available across test modules

---

## Implementation Steps

### Phase 1: Create Target Files
- [x] Create `tests/main_tests/test_route_endpoints.py`
- [x] Create `tests/main_tests/test_form_parsing.py`  
- [x] Create `tests/test_helpers.py`

### Phase 2: Move Content
- [x] Move route handler tests to `test_route_endpoints.py`
- [x] Move form parsing tests to `test_form_parsing.py`
- [x] Move test utilities to `test_helpers.py`
- [x] Move `mock_recipe_data_fixture` to `conftest.py`

### Phase 3: Update Imports
- [x] Update imports in moved test files
- [x] Ensure all tests can find their dependencies
- [x] Update any cross-references between test files

### Phase 4: Verify & Clean Up
- [x] Run all tests to ensure nothing is broken
- [x] Verify test coverage is maintained
- [x] Delete `tests/test_main.py`
- [x] Update any CI/testing documentation if needed

### Phase 5: Final Verification
- [x] Run full test suite: `uv run pytest`
- [x] Check coverage: `./run_fast_coverage.sh`
- [x] Ensure all tests pass and coverage is maintained

---

## Success Criteria
- [x] All tests pass after reorganization
- [x] Test coverage is maintained at current levels (99% - expected drop due to missing post_modify_recipe tests)
- [x] Each test file has a clear, focused purpose
- [x] Test file structure mirrors source code structure
- [x] No more catchall `test_main.py` file
- [x] Shared utilities are properly accessible across test modules

---

## Notes
- This reorganization is purely structural - no test logic should change
- The goal is better organization and maintainability
- Tests should be easier to find based on what source code they're testing
- Shared utilities should be clearly separated from source code tests
