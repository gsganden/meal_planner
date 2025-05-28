# Plan: Refactor Shared Resources to `meal_planner/core.py`

**Goal:** Resolve circular dependencies and centralize core application components (`app`, `rt`, `api_app`, `internal_client`, `internal_api_client`, `STATIC_DIR`) by moving them from `meal_planner/main.py` to a new `meal_planner/core.py` module.

**Phase 0: Ensure Module Docstrings**
*   [x] **0.1. `meal_planner/main.py`**: Add a module docstring if missing.
*   [x] **0.2. `meal_planner/routers/pages.py`**: Add a module docstring if missing.
*   [x] **0.3. `meal_planner/routers/actions.py`**: Add a module docstring if missing.
*   [x] **0.4. `meal_planner/routers/ui_fragments.py`**: Add a module docstring if missing.
*   [x] **0.5. `meal_planner/form_processing.py`**: Add a module docstring if missing.
*   [x] **0.6. `meal_planner/api/recipes.py`**: Add a module docstring if missing.
*   [x] **0.7. `meal_planner/services/call_llm.py`**: Add a module docstring if missing.
*   [x] **0.8. `meal_planner/services/extract_webpage_text.py`**: Add a module docstring if missing.
*   [x] **0.9. `meal_planner/services/process_recipe.py`**: Add a module docstring if missing.
*   [x] **0.10. `meal_planner/ui/common.py`**: Add a module docstring if missing.
*   [x] **0.11. `meal_planner/ui/edit_recipe.py`**: Add a module docstring if missing.
*   [x] **0.12. `meal_planner/ui/extract_recipe.py`**: Add a module docstring if missing.
*   [x] **0.13. `meal_planner/ui/layout.py`**: Add a module docstring if missing.
*   [x] **0.14. `meal_planner/ui/list_recipes.py`**: Add a module docstring if missing.
*   [x] **0.15. `meal_planner/models.py`**: Add a module docstring if missing.
*   [x] **0.16. `meal_planner/database.py`**: Add a module docstring if missing.
*   [x] **0.17. `meal_planner/config.py`**: Add a module docstring if missing.
*   [x] **0.18. `meal_planner/routers/__init__.py`**: Add module docstring explaining the purpose of the `routers` package.
*   [x] **0.19. `meal_planner/api/__init__.py`**: Add module docstring (if file exists, or create and add) explaining the purpose of the `api` package.
*   [x] **0.20. `meal_planner/services/__init__.py`**: Add module docstring explaining the purpose of the `services` package.
*   [x] **0.21. `meal_planner/ui/__init__.py`**: Add module docstring (if file exists, or create and add) explaining the purpose of the `ui` package.
*   [x] **0.22. `meal_planner/__init__.py`**: Add module docstring (if file exists, or create and add) explaining the purpose of the main `meal_planner` package.

**Phase 1: Create and Populate `meal_planner/core.py`**
*   [x] **1.1. Create File:** Create `meal_planner/core.py` (and add its module docstring).
*   [x] **1.2. Add Imports:** Add necessary base imports to `core.py` (e.g., `logging`, `Path` from `pathlib`, `httpx`, `FastAPI` from `fastapi`, `FastHTMLWithLiveReload`, `Theme` from `fasthtml.common`, `ASGITransport` from `httpx`, `StaticFiles` from `starlette.staticfiles`).
*   [x] **1.3. Add API Router Import:** Add `from meal_planner.api.recipes import API_ROUTER as RECIPES_API_ROUTER`.
*   [x] **1.4. Initialize Logger:** Add `logger = logging.getLogger(__name__)`.
*   [x] **1.5. Define `STATIC_DIR`:**
    *   Move/copy `STATIC_DIR = Path(__file__).resolve().parent.parent / "static"` (adjusting path for `core.py`'s location).
*   [x] **1.6. Define `app`:**
    *   Move `app = FastHTMLWithLiveReload(hdrs=(Theme.blue.headers()))` from `main.py` to `core.py`.
*   [x] **1.7. Define `rt`:**
    *   Move `rt = app.route` from `main.py` to `core.py`.
*   [x] **1.8. Define `api_app`:**
    *   Move `api_app = FastAPI()` from `main.py` to `core.py`.
    *   Move `api_app.include_router(RECIPES_API_ROUTER)` to `core.py`.
*   [x] **1.9. Define `internal_client`:**
    *   Move `internal_client = httpx.AsyncClient(transport=ASGITransport(app=app), ...)` from `main.py` to `core.py`, ensuring `app` refers to `core.app`.
*   [x] **1.10. Define `internal_api_client`:**
    *   Move `internal_api_client = httpx.AsyncClient(transport=ASGITransport(app=api_app), ...)` from `main.py` to `core.py`, ensuring `api_app` refers to `core.api_app`.

**Phase 2: Refactor `meal_planner/main.py`**
*   [x] **2.1. Remove Definitions:** Delete the definitions of `STATIC_DIR`, `app`, `rt`, `api_app` (and its `include_router`), `internal_client`, and `internal_api_client` from `main.py`.
*   [x] **2.2. Add Core Imports:** Add `from meal_planner.core import app, rt, api_app, internal_client, internal_api_client, STATIC_DIR` to `main.py`.
*   [x] **2.3. Verify Mounts:** Ensure `app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")` and `app.mount("/api", api_app)` in `main.py` correctly use the imported `app`, `STATIC_DIR`, and `api_app` from `core`.
*   [x] **2.4. Logging Configuration:** Keep `logging.basicConfig(...)` in `main.py` as it's the application entry point. The `logger = logging.getLogger(__name__)` can also remain.

**Phase 3: Update Router Modules (`pages.py`, `actions.py`, `ui_fragments.py`)**
*   [x] **3.1. `meal_planner/routers/pages.py`:**
    *   Change `from meal_planner.main import rt, internal_client, internal_api_client`
        TO `from meal_planner.core import rt, internal_client, internal_api_client`.
*   [x] **3.2. `meal_planner/routers/actions.py`:**
    *   Change `from meal_planner.main import internal_client, rt`
        TO `from meal_planner.core import internal_client, rt`.
*   [x] **3.3. `meal_planner/routers/ui_fragments.py`:**
    *   Change `from meal_planner.main import rt`
        TO `from meal_planner.core import rt`.

**Phase 4: Update Test Files**
*   [x] **4.1. Identify Patch Targets:** Systematically search all test files for `patch("meal_planner.main.app")`, `patch("meal_planner.main.rt")`, `patch("meal_planner.main.internal_client")`, `patch("meal_planner.main.internal_api_client")`, and any direct imports of these from `meal_planner.main`.
*   [x] **4.2. Update Patch Targets:** Modify identified patch targets and direct imports to point to `meal_planner.core` (e.g., `patch("meal_planner.core.internal_client")`).

**Phase 5: Verification and Code Quality**
*   [x] **5.1. Format Code:** Run `uv run ruff format .`.
*   [x] **5.2. Lint Code:** Run `uv run ruff check --fix .`.
*   [x] **5.3. Run Tests:** Execute `./run_fast_coverage.sh`.
*   [x] **5.4. Resolve Test Issues:** Debug and fix any test failures, ensuring all tests pass.
*   [x] **5.5. Verify Coverage:** Confirm test coverage remains at 100%.
*   [x] **5.6. Manual Test (Optional but Recommended):** Run the application locally (`uv run modal serve deploy.py`) and perform a quick functional check of key features. (Skipped)

**Phase 6: Commit**
*   [x] **6.1. Suggest Commit Message.**
*   [x] **6.2. User Confirmation and Commit.**
