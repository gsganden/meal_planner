# Recipe Update Operation Implementation Plan - June 9, 2025

**Issue:** [#53 - Add Update (PUT/PATCH) Operation for Recipes](https://github.com/gsganden/meal_planner/issues/53)

**Goal:** Implement a PUT endpoint for updating existing recipes in the CRUD API, completing the missing update operation.

## Overview

Currently, the recipes API supports Create (POST), Read (GET), and Delete (DELETE) operations, but is missing the Update operation. This plan implements a `PUT /api/v0/recipes/{recipe_id}` endpoint following REST conventions and the existing codebase patterns.

## Analysis of Existing Implementation

- **API Pattern:** All endpoints in `meal_planner/api/recipes.py` follow consistent patterns:
  - Type hints with `Annotated[Session, Depends(get_session)]`
  - Comprehensive error handling with appropriate HTTP status codes
  - Detailed logging for operations and errors
  - Validation using Pydantic models (`RecipeBase`)
  - Timestamp management for SQLite compatibility
- **Models:** `RecipeBase` for input validation, `Recipe` for database operations
- **Testing:** Comprehensive test coverage in `tests/test_api/test_recipes.py` with success/error scenarios

## Implementation Details

### **PUT Semantics Decision**
**Approach:** Partial update - preserve existing fields that aren't included in the request body. This provides a more user-friendly experience and reduces risk of accidental data loss.

### **Response Headers**
Include `Last-Modified` header in successful responses to support HTTP caching and optimistic concurrency control.

### **Validation Order**
Validate request body structure and content **before** checking if recipe exists - provides better user experience by surfacing validation errors first.

## Implementation Checklist

### 1. API Endpoint Implementation
- [x] **Add PUT endpoint to `meal_planner/api/recipes.py`**
  - [x] Define `@API_ROUTER.put("/v0/recipes/{recipe_id}", response_model=Recipe)`
  - [x] Accept `recipe_id: int` as path parameter
  - [x] Accept `recipe_data: RecipeBase` as request body
  - [x] Use `session: Annotated[Session, Depends(get_session)]` dependency
  - [x] **Validate request body BEFORE checking recipe existence**
  - [x] **Include `Last-Modified` header in successful responses**
  - [x] Follow existing docstring pattern with detailed Args/Returns/Raises sections

### 2. Core Logic Implementation
- [x] **Database Operation Logic**
  - [x] Fetch existing recipe using `session.get(Recipe, recipe_id)`
  - [x] Return 404 if recipe not found
  - [x] **Implement partial update semantics - only update provided fields**
  - [x] Update recipe fields from `recipe_data` (preserve missing fields)
  - [x] Preserve `created_at` timestamp
  - [x] Set `updated_at` to `datetime.now(timezone.utc)`
  - [x] Commit changes to database
  - [x] Return updated recipe object

### 3. Error Handling
- [x] **HTTP Status Codes**
  - [x] 200 OK for successful updates with updated recipe in response
  - [x] 404 Not Found if `recipe_id` doesn't exist
  - [x] 422 Unprocessable Entity for validation errors (handled by FastAPI)
  - [x] 500 Internal Server Error for database errors
- [x] **Exception Handling**
  - [x] Wrap database fetch in try/catch for 500 errors
  - [x] Wrap database commit in try/catch with rollback for 500 errors
  - [x] Add appropriate logging for all error scenarios

### 4. Comprehensive Testing
- [x] **Create new test class `TestUpdateRecipe` in `tests/test_api/test_recipes.py`**
  - [x] Add fixture for creating test recipe to update
  - [x] Test successful update with 200 response
  - [x] Test response contains updated data
  - [x] Test that `created_at` remains unchanged
  - [x] Test that `updated_at` is updated to current time
  - [x] Test 404 for non-existent recipe_id
  - [x] Test 422 for invalid request data (empty ingredients/instructions, etc.)
  - [x] Test database error handling (fetch and commit errors)
- [x] **Add timestamp verification tests**
  - [x] Verify `updated_at` changes after update
  - [x] Verify `created_at` remains unchanged
  - [x] Verify `updated_at` reflects the time of update operation

### 5. Integration Testing
- [x] **Add integration test to verify end-to-end functionality**
  - [x] Create recipe via POST
  - [x] Update via PUT 
  - [x] Verify changes via GET
  - [x] Verify timestamps are properly managed

### 6. Code Quality & Standards
- [x] **Follow existing patterns**
  - [x] Match error handling patterns from other endpoints
  - [x] Use same logging format and levels
  - [x] Follow existing type hints and documentation style
  - [x] Use same transaction management (rollback on errors)
- [x] **Code formatting**
  - [x] Run `uv run ruff format`
  - [x] Run `uv run ruff check --fix`
  - [x] Ensure 88 character line length limit

### 7. Testing & Coverage
- [x] **Run test suite**
  - [x] Execute `./run_fast_coverage.sh` for quick coverage check
  - [x] Ensure 100% test coverage maintained
  - [x] Fix any failing tests
  - [x] Verify all new code paths are covered

## Implementation Notes

### Endpoint Signature
```python
@API_ROUTER.put("/v0/recipes/{recipe_id}", response_model=Recipe)
async def update_recipe(
    recipe_id: int,
    recipe_data: RecipeBase,
    session: Annotated[Session, Depends(get_session)],
):
```

### Timestamp Management
Following the existing pattern in `create_recipe`:
- Preserve original `created_at` value
- Set `updated_at = datetime.now(timezone.utc)` before commit
- Manual timestamp management required for SQLite compatibility

### Error Response Patterns
Follow existing patterns:
- 404: `{"detail": "Recipe not found"}`
- 500: `{"detail": "Database error updating recipe"}`
- 422: Handled automatically by FastAPI with validation details

### Database Transaction Pattern
```python
try:
    # Update operations
    session.add(recipe)
    session.commit()
    session.refresh(recipe)
except Exception as e:
    session.rollback()
    logger.error("Database error updating recipe: %s", e, exc_info=True)
    raise HTTPException(status_code=500, detail="Database error updating recipe")
```

## Testing Strategy

### Test Categories
1. **Success Cases:** Valid updates with various data combinations
2. **Validation Errors:** Invalid input data (empty lists, wrong types)
3. **Not Found Errors:** Non-existent recipe IDs
4. **Database Errors:** Simulated database failures
5. **Timestamp Verification:** Proper timestamp management

### Key Test Scenarios
- Update all fields of an existing recipe
- Verify response contains updated data
- Verify database persistence
- Verify timestamp behavior (`created_at` unchanged, `updated_at` updated)
- Error handling for all failure modes

## Dependencies & Prerequisites

- [x] Issue #83 (Add timestamps to recipes) - **COMPLETED**
- [x] Existing CRUD operations (Create, Read, Delete) are working
- [x] Test infrastructure is in place

## Definition of Done

- [x] PUT endpoint implemented following existing patterns
- [x] All acceptance criteria from GitHub issue satisfied
- [x] Comprehensive test coverage (100%)
- [x] Error handling for all specified scenarios
- [x] Proper timestamp management
- [x] Code passes formatting and linting checks
- [x] Integration tests pass
- [x] Documentation updated (docstrings)

## ✅ IMPLEMENTATION COMPLETED - June 9, 2025

**Status: COMPLETE** - All checklist items finished successfully.

**Key Deliverables:**
- ✅ PUT `/api/v0/recipes/{recipe_id}` endpoint implemented in `meal_planner/api/recipes.py:151`
- ✅ 16 comprehensive test cases added (15 unit tests + 1 integration test)
- ✅ 100% test coverage maintained across entire codebase
- ✅ All linting and type checking passes
- ✅ Proper timestamp management (preserves `created_at`, updates `updated_at`)
- ✅ Last-Modified header support for HTTP caching
- ✅ Complete error handling (404, 422, 500) with appropriate logging

**Implementation Summary:**
The PUT endpoint successfully implements partial update semantics, following all existing codebase patterns. The comprehensive test suite verifies success scenarios, validation errors, not-found cases, database error handling, and proper timestamp management. The implementation is production-ready and maintains backward compatibility.

## Future Considerations

After this implementation:
- Consider PATCH endpoint for partial updates
- Add authentication/authorization when auth system is implemented
- Consider optimistic locking for high concurrency scenarios
- Add audit logging for recipe changes 
 