# Plan: Replace Servings with Generalized "Makes" System

## Model Changes
- [x] Update `RecipeBase` model to replace `servings_min` and `servings_max` with `makes_min`, `makes_max`, and `makes_unit`
- [x] Update model validation to ensure `makes_max >= makes_min` when both are present
- [x] Update `markdown` property to display makes information appropriately

## Database Schema Changes
- [x] Create Alembic migration to add new `makes_min`, `makes_max`, `makes_unit` columns
- [x] Drop old `servings_min` and `servings_max` columns in same migration
- [x] Update `Recipe` SQLModel class to use new column definitions

## Form Processing Changes
- [x] Update `parse_recipe_form_data()` to extract makes fields instead of servings
- [x] Update `normalize_servings_values()` to `normalize_makes_values()`
- [x] Update form field names in HTML forms

## UI Component Changes
- [x] Update `build_servings_section()` to `build_makes_section()` in `edit_recipe.py`
- [x] Change "Servings Range" header to "Makes"
- [x] Update input field names and IDs from `servings_*` to `makes_*`
- [x] Add unit field/display (could start simple with text input or select)
- [x] Update error messages to reference "makes" instead of "servings"

## Backend Route Changes
- [x] Update `/recipes/ui/adjust-servings` to `/recipes/ui/adjust-makes`
- [x] Update route handler logic to work with makes fields
- [x] Update validation error handling for makes range validation
- [x] Update OOB swap targets to use makes section IDs

## LLM Prompt Changes
- [x] Update prompt to extract makes information with units
- [x] Add guidelines for common units (servings, pieces, cookies, etc.)
- [x] Update examples in prompt to show various makes units

## Test Data Updates
- [x] Update all ML test JSON files to use `expected_makes_*` fields
- [x] Add `expected_makes_unit` to test files with appropriate units
- [x] Update falafel recipe to `makes_unit: "pieces"` or `"falafel"`

## Test Code Updates
- [x] Update ML test assertions to check makes fields instead of servings
- [x] Update unit tests for form processing, UI components, and routes
- [x] Update test fixtures and mock data
- [x] Add tests for various makes units

## Pre-Review Quality Checks
- [x] Run all tests and ensure they pass (`uv run pytest`)
- [x] Run ML evaluation tests with new makes fields (`uv run pytest tests/test_ml_evals.py --runslow`)
- [x] Run linting and formatting checks (`uv run ruff check`, `uv run ruff format`)
- [x] Check test coverage meets requirements (`./run_fast_coverage.sh`)
- [x] Verify database migration runs successfully
- [ ] Manual smoke test of makes UI functionality
- [ ] Verify existing recipes still display correctly (backwards compatibility)
- [ ] Test recipe creation with various makes units
- [ ] Test recipe editing with makes fields

## Future Enhancements (Optional)
- [ ] Add unit validation (whitelist of acceptable units)
- [ ] Smart unit conversion/normalization
- [ ] Enhanced UI for unit selection (dropdown with common options)
- [ ] Search/filter by makes information