# Plan for Adding Timestamps to Recipes (Issue #83)

This plan outlines the steps to add `created_at` and `updated_at` timestamp fields to the `Recipe` model and database table, as detailed in GitHub issue #83. The database in use is SQLite.

## 1. Update `Recipe` Data Model (`meal_planner/models.py`)

-   [ ] **Add Imports:** Add `from datetime import datetime, timezone` and `from typing import Optional` (if not already present for `id`) to `meal_planner/models.py`. Ensure `from sqlalchemy import func` is also present.
-   [ ] **Add `created_at` field to `Recipe` model:**
    -   Type in Python model: `Optional[datetime]`
    -   Default value in Python model: `None`
    -   SQLAlchemy column arguments: `nullable=False`, `server_default=func.now()`
    -   Field definition example: `created_at: Optional[datetime] = Field(default=None, sa_column_kwargs={"nullable": False, "server_default": func.now()})`
-   [ ] **Add `updated_at` field to `Recipe` model:**
    -   Type in Python model: `Optional[datetime]`
    -   Default value in Python model: `None`
    -   SQLAlchemy column arguments: `nullable=False`, `server_default=func.now()`, `onupdate=func.now()`
    -   Field definition example: `updated_at: Optional[datetime] = Field(default=None, sa_column_kwargs={"nullable": False, "server_default": func.now(), "onupdate": func.now()})`
-   [ ] **Update `Recipe` Docstrings:** Add descriptions for `created_at` and `updated_at` fields. Clarify that these are database-managed timestamps, will be `None` in Python before an object is persisted or if not loaded from the DB, but will always be populated for records retrieved from the database.

## 2. Create and Implement Database Migration (Alembic)

-   [ ] **Generate Alembic Migration:**
    -   Run `uv run alembic revision -m "add_timestamps_to_recipes_table"`.
-   [ ] **Edit Migration Script (`upgrade` function in `alembic/versions/`):**
    -   Add `created_at` column to `recipes` table:
        -   `op.add_column('recipes', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))`
    -   Add `updated_at` column to `recipes` table:
        -   `op.add_column('recipes', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False))`
    -   **Populate timestamps for existing rows (SQLite):**
        -   Add an explicit update as a safeguard: `op.execute('UPDATE recipes SET created_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE created_at IS NULL')` (Note: `CURRENT_TIMESTAMP` and `func.now()` are appropriate for SQLite).
-   [ ] **Edit Migration Script (`downgrade` function):**
    -   Implement logic to remove the columns:
        -   `op.drop_column('recipes', 'updated_at')`
        -   `op.drop_column('recipes', 'created_at')`
-   [ ] **Test Migration (Locally):**
    -   Apply: `uv run alembic upgrade head`
    -   Verify schema and data.
    -   Downgrade: `uv run alembic downgrade -1`
    -   Re-apply: `uv run alembic upgrade head`

## 3. API Adjustments and Verification

-   [ ] **Review `Recipe` Pydantic Schemas (likely in `meal_planner/api/recipes.py`):**
    -   Check `RecipeRead`, `RecipeCreate`, etc.
    -   Ensure `created_at` and `updated_at` are present in schemas used for API responses (e.g., `RecipeRead` should define them as non-optional `datetime`). This should be automatic if they are part of the SQLModel `Recipe`.
-   [ ] **Verify API Responses:**
    -   `POST /v0/recipes`: Ensure `created_at` and `updated_at` are in the response.
    -   `GET /v0/recipes`: Ensure `created_at` and `updated_at` are in the list.
    -   `GET /v0/recipes/{recipe_id}`: Ensure `created_at` and `updated_at` are in the single recipe response.
-   [ ] **Verify Creation Logic:** Confirm `created_at` and `updated_at` are correctly populated in the database upon new recipe creation.

## 4. Write Automated Tests

-   [ ] **Target Test Files:** API tests in `tests/test_api/test_recipes.py`. Consider `tests/test_services/test_process_recipe.py` for service-level tests or create a new service test file if needed.
-   [ ] **Test Recipe Creation:**
    -   Assert `created_at` and `updated_at` in API response and database, and that they are approximately equal post-creation.
-   [ ] **Test Recipe Retrieval (Single & List):**
    -   Assert `created_at` and `updated_at` are present and correct.
-   [ ] **(Placeholder for Issue #53) Test Recipe Update:**
    -   Note to test that `updated_at` changes and `created_at` does not upon update.
-   [ ] **Test Migration Data Population (Optional but Recommended):**
    -   Verify that migration populates timestamps for existing rows.

## 5. Documentation Updates

-   [ ] **OpenAPI/Swagger Documentation:**
    -   Check `/docs` to verify `Recipe` schema includes `created_at` and `updated_at` (as non-optional `datetime`).
-   [ ] **Model Docstrings:** Add descriptions for new fields (covered in Step 1).

## 6. Code Quality and Final Checks

-   [ ] **Remove added code comments** (not docstrings).
-   [ ] **Format:** `uv run ruff format .`
-   [ ] **Lint:** `uv run ruff check --fix .`
-   [ ] **Test & Coverage:** `./run_fast_coverage.sh`. Ensure 100% coverage for new/modified code.
-   [ ] **Final Review:** Read through all changes.

This plan provides a structured approach to implementing the required timestamp functionality.
