# Save vs Save-As Functionality Implementation Plan

**Issue**: [#104](https://github.com/gsganden/meal_planner/issues/104)  
**Date**: 2025-06-18  
**Dependencies**: Should be implemented before Issue #29 (Enable editing on recipe page)

## Overview
Add context-aware saving to distinguish between updating existing recipes vs creating new ones, starting with the recipe creation flow.

## Requirements Summary
- [ ] No recipe ownership/permissions validation (handled later)
- [ ] No confirmation dialogs (keep UX streamlined)
- [ ] Auto-populate copy names: "Recipe Name (Copy)" for save-as functionality
- [ ] Use standard MonsterUI styling (no custom button layouts)

## Phase 1: Backend Infrastructure

### 1. Add Recipe Context Tracking
- [ ] Add optional `recipe_id` field to edit forms to track whether editing existing recipe
- [ ] Modify `parse_recipe_form_data()` in `form_processing.py` to extract `recipe_id`
- [ ] Update form validation to handle recipe ID context

### 2. Create New Save Handler
- [ ] Add new route `/recipes/save-as` in `actions.py` for "Save as New Recipe" functionality
- [ ] Keep existing `/recipes/save` route but modify it to detect context:
  - [ ] If `recipe_id` present → call `PUT /api/v0/recipes/{id}` (update existing)
  - [ ] If no `recipe_id` → call `POST /api/v0/recipes` (create new)

### 3. Update API Response Handling
- [ ] Modify save success messages to be context-aware:
  - [ ] "Recipe Updated!" for existing recipe updates
  - [ ] "New Recipe Saved!" for new recipe creation
- [ ] Ensure proper error handling for both PUT and POST scenarios

### 4. Implement Save-As Logic
- [ ] Auto-generate copy names: append " (Copy)" to recipe name when saving as new
- [ ] Handle duplicate copy names (e.g., "Recipe (Copy 2)", "Recipe (Copy 3)")

## Phase 2: UI Updates

### 5. Modify Save Button Component
- [ ] Update `_build_save_button()` in `edit_recipe.py` to accept recipe context
- [ ] Show different button text based on context:
  - [ ] New recipe: "Save Recipe"
  - [ ] Existing recipe: "Save Changes"

### 6. Add Save-As Button (Conditional)
- [ ] Add "Save as New Recipe" button when editing existing recipes
- [ ] Position next to main save button using existing MonsterUI styling
- [ ] Route to `/recipes/save-as` endpoint
- [ ] Only show when `recipe_id` is present in form context

### 7. Update Form Structure
- [ ] Add hidden `recipe_id` input field to edit forms when editing existing recipes
- [ ] Modify `build_edit_review_form()` to accept optional `recipe_id` parameter
- [ ] Update all form builders to pass recipe context through

## Phase 3: Integration Points

### 8. Recipe Creation Flow (No Changes)
- [ ] Verify current `/recipes/extract` → edit → save workflow unchanged
- [ ] Confirm no `recipe_id` present → single "Save Recipe" button → creates new recipe

### 9. Future Recipe Editing Flow (Preparation)
- [ ] Ensure recipe display page can pass `recipe_id` to edit form
- [ ] Verify edit form shows "Save Changes" + "Save as New Recipe" buttons
- [ ] Test proper routing based on user choice

## Phase 4: Testing Strategy

### 10. Unit Tests
- [ ] Test `parse_recipe_form_data()` with and without `recipe_id`
- [ ] Test save handler routing logic (PUT vs POST)
- [ ] Test form validation with recipe context
- [ ] Test copy name generation logic

### 11. Integration Tests
- [ ] Test complete save workflow for new recipes
- [ ] Test complete save workflow for existing recipes (simulated)
- [ ] Test save-as workflow creating recipe copies with proper names
- [ ] Test error scenarios (recipe not found, validation errors)

## Implementation Order

1. **Backend First**: Recipe context tracking, form parsing, save handler logic
2. **UI Updates**: Button components, form modifications  
3. **Integration**: Wire everything together, test end-to-end
4. **Validation**: Comprehensive testing of all scenarios

## Key Files to Modify

- `meal_planner/routers/actions.py` - Save handlers and routing logic
- `meal_planner/form_processing.py` - Recipe ID extraction and copy name generation
- `meal_planner/ui/edit_recipe.py` - Button components and form structure
- Tests for all modified components

## Risk Mitigation

- **Backward Compatibility**: Current creation flow remains unchanged
- **Graceful Degradation**: Missing recipe ID defaults to creation behavior
- **Clear Error Messages**: Distinct errors for update vs create failures
- **Incremental Testing**: Each phase can be tested independently

## Success Criteria

- [ ] New recipe creation flow unchanged and working
- [ ] Context-aware save behavior (PUT vs POST) working correctly
- [ ] Save-as functionality creates copies with "(Copy)" naming
- [ ] UI shows appropriate buttons based on recipe context
- [ ] All tests passing
- [ ] Ready for integration with Issue #29 (recipe page editing)