# Meal Planner Refactoring Plan

This document outlines our plan for refactoring the Meal Planner codebase to improve maintainability and organization.

## Overall Structure

We plan to break down `meal_planner/main.py` and `tests/test_main.py` into smaller, more focused modules with the following structure:

### Application Code Structure

1. **`meal_planner/app_setup.py`**:
   - [ ] Centralize application instance creation and global configurations
   - [ ] Move FastAPI app instance (`api_app`) and FastHTMLWithLiveReload instance (`app`)
   - [ ] Move httpx.AsyncClient instances (`internal_client`, `internal_api_client`)
   - [ ] Move logging configuration
   - [ ] Move global constants like `MODEL_NAME`, `STATIC_DIR`, etc.

2. **`meal_planner/services/`** (Business Logic):
   - [x] **`services/recipe_processing.py`**: Functions for cleaning and standardizing recipe data
   - [x] **`services/text_processing.py`**: Functions for fetching and cleaning text from URLs
   - [ ] **`services/llm_service.py`**: Functions for LLM interactions

3. **`meal_planner/ui/`** (UI Components):
   - [ ] **`ui/layout.py`**: Main page layout and shared UI elements
   - [ ] **`ui/recipe_display.py`**: Recipe display components
   - [ ] **`ui/recipe_form.py`**: Recipe form handling components

4. **`meal_planner/routers/`** (Route Handlers):
   - [ ] **`routers/pages.py`**: Routes that render full pages
   - [ ] **`routers/actions.py`**: Routes that perform actions (fetch, extract, save, modify)
   - [ ] **`routers/ui_fragments.py`**: Routes that return HTMX UI fragments

5. **`meal_planner/main.py`** (Refactored):
   - [ ] Simplify to be an entry point that wires everything together

### Test Code Structure

1. **`tests/conftest.py`**:
   - [ ] Store shared fixtures and test helper functions

2. **`tests/constants.py`** (Optional):
   - [ ] Shared test constants

3. **Test files mirroring the application structure**:
   - [x] **`tests/services/test_recipe_processing.py`**
   - [x] **`tests/services/test_text_processing.py`**
   - [ ] **`tests/services/test_llm_service.py`**
   - [ ] **`tests/ui/test_layout.py`**
   - [ ] **`tests/ui/test_recipe_display.py`**
   - [ ] **`tests/ui/test_recipe_form.py`**
   - [ ] **`tests/routers/test_pages.py`**
   - [ ] **`tests/routers/test_actions.py`**
   - [ ] **`tests/routers/test_ui_fragments.py`**

## Completed Refactorings

### Phase 1: Text Processing Service Extraction

**Goal:** Separate text fetching and HTML cleaning logic from `main.py` into a dedicated service module.

**Changes Made:**
- [x] Created new service module `meal_planner/services/text_processing.py`
- [x] Moved `fetch_page_text` and `fetch_and_clean_text_from_url` functions from `main.py` to the new module
- [x] Moved `create_html_cleaner` and `HTML_CLEANER` to the new module
- [x] Updated imports in `main.py` to use the new service
- [x] Renamed form field from `recipe_url` to `input_url` for consistency
- [x] Fixed logging levels in `post_fetch_text` function (changed `warning` to `error` for network and HTTP errors)
- [x] Updated tests to reflect these changes
- [x] Added new tests for the text processing service
- [x] Updated README.md Mermaid diagram to reflect the new architecture

### Phase 2: Recipe Processing Service Extraction

**Goal:** Separate recipe post-processing logic from `main.py` into a dedicated service module.

**Changes Made:**
- [x] Created new service module `meal_planner/services/recipe_processing.py`
- [x] Moved recipe processing functions from `main.py` to the new module:
  - [x] `postprocess_recipe`
  - [x] `_postprocess_recipe_name`
  - [x] `_postprocess_ingredient`
  - [x] `_postprocess_instruction`
  - [x] `_remove_leading_step_numbers`
  - [x] `_close_parenthesis`
- [x] Updated imports in `main.py` to use the new service
- [x] Created `tests/services/test_recipe_processing.py` with tests for the moved functions
- [x] Moved relevant tests from `tests/test_main.py` to the new test file
- [x] Updated imports in tests to point to the new module location
- [x] Fixed regex in `_remove_leading_step_numbers` to properly handle step numbers

## Planned Future Refactorings

### Phase 3: LLM Service Extraction

**Goal:** Separate LLM interaction logic from `main.py` into a dedicated service module.

**Proposed Changes:**
- [ ] Create `meal_planner/services/llm_service.py`
- [ ] Move LLM-related functions from `main.py` to the new module:
  - [ ] `get_structured_llm_response`
  - [ ] `extract_recipe_from_text`
  - [ ] `_request_recipe_modification`
  - [ ] `_get_prompt_path`
- [ ] Update imports in `main.py` to use the new service
- [ ] Create `tests/services/test_llm_service.py` with tests for the moved functions
- [ ] Move relevant tests from `tests/test_main.py` to the new test file
- [ ] Update imports in tests to point to the new module location

### Phase 4: UI Component Extraction

**Goal:** Extract reusable UI components from `main.py` to reduce its size and improve maintainability.

**Proposed Changes:**
- [ ] Create a `meal_planner/ui/` directory for UI components
- [ ] Extract common layout components (sidebar, layout wrapper, etc.)
- [ ] Extract recipe form components
- [ ] Extract error handling and display components

### Phase 5: Route Handler Organization

**Goal:** Organize route handlers by feature area to improve code navigation and maintainability.

**Proposed Changes:**
- [ ] Create a `meal_planner/routers/` directory
- [ ] Group route handlers by feature (recipes, user, etc.)
- [ ] Move route handler functions from `main.py` to appropriate modules

## Refactoring Guidelines

When implementing these refactorings, follow these guidelines:

1. **One change at a time:** Focus on a single refactoring goal per PR to keep changes manageable and reviewable.
2. **Maintain test coverage:** Ensure tests are updated or added for all refactored code.
3. **Backward compatibility:** Ensure refactorings don't break existing functionality.
4. **Documentation:** Update diagrams and documentation to reflect architectural changes.
5. **Code style:** Follow the project's code style guidelines (ruff formatting, 88 character line length, etc.). 
