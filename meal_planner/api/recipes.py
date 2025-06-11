"""REST API endpoints for recipe CRUD operations."""

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from meal_planner.database import get_session
from meal_planner.models import (
    Recipe,
    RecipeBase,
)

logger = logging.getLogger(__name__)

API_ROUTER = APIRouter()


@API_ROUTER.post(
    "/v0/recipes",
    status_code=status.HTTP_201_CREATED,
    response_model=Recipe,
)
async def create_recipe(
    recipe_data: RecipeBase,
    session: Annotated[Session, Depends(get_session)],
):
    """Create a new recipe in the database.

    Validates the recipe data and persists it to the database. Returns
    the created recipe with its assigned ID and sets the Location header
    for the new resource.

    Args:
        recipe_data: Recipe information to create (name, ingredients, instructions,
            servings).
        session: Database session from dependency injection.

    Returns:
        The created recipe with database-assigned ID.

    Raises:
        HTTPException: 500 if database operation fails.

    Response Headers:
        Location: URL path to the newly created recipe resource.
    """
    db_recipe = Recipe.model_validate(recipe_data)

    now = datetime.now(timezone.utc)
    db_recipe.created_at = now
    db_recipe.updated_at = now

    try:
        session.add(db_recipe)
        session.commit()
        session.refresh(db_recipe)
    except Exception as e:
        session.rollback()
        logger.error("Database error inserting recipe: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error creating recipe",
        ) from e

    logger.info(
        "Created recipe with ID: %s, Name: %s",
        db_recipe.id,
        db_recipe.name,
    )

    location_path = f"/api/v0/recipes/{str(db_recipe.id)}"

    return JSONResponse(
        content=db_recipe.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
        headers={"Location": location_path},
    )


@API_ROUTER.get("/v0/recipes", response_model=list[Recipe])
async def get_all_recipes(session: Annotated[Session, Depends(get_session)]):
    """Retrieve all recipes from the database.

    Fetches the complete list of recipes without pagination. For production
    use with large datasets, pagination should be implemented.

    Args:
        session: Database session from dependency injection.

    Returns:
        List of all recipes in the database, empty list if none exist.

    Raises:
        HTTPException: 500 if database query fails.
    """
    try:
        statement = select(Recipe)
        all_recipes = session.exec(statement).all()
        return all_recipes
    except Exception as e:
        logger.error("Database error querying all recipes: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error retrieving recipes",
        ) from e


@API_ROUTER.get("/v0/recipes/{recipe_id}", response_model=Recipe)
async def get_recipe_by_id(
    recipe_id: int, session: Annotated[Session, Depends(get_session)]
):
    """Retrieve a specific recipe by its ID.

    Fetches a single recipe from the database using its primary key.
    Returns 404 if the recipe doesn't exist.

    Args:
        recipe_id: Unique identifier of the recipe to retrieve.
        session: Database session from dependency injection.

    Returns:
        The requested recipe if found.

    Raises:
        HTTPException: 404 if recipe not found, 500 if database error.
    """
    try:
        recipe = session.get(Recipe, recipe_id)
    except Exception as e:
        logger.error(
            "Database error fetching recipe ID %s: %s", recipe_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error retrieving recipe",
        ) from e

    if recipe is None:
        logger.warning("Recipe with ID %s not found.", recipe_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found"
        )

    return recipe


@API_ROUTER.put("/v0/recipes/{recipe_id}", response_model=Recipe)
async def update_recipe(
    recipe_id: int,
    recipe_data: RecipeBase,
    session: Annotated[Session, Depends(get_session)],
):
    """Update an existing recipe in the database.

    Replaces all recipe fields with the provided data. Returns the updated recipe with a
    Last-Modified header for caching support.

    Args:
        recipe_id: Unique identifier of the recipe to update.
        recipe_data: Recipe data to update (name, ingredients, instructions,
            servings).
        session: Database session from dependency injection.

    Returns:
        The updated recipe with preserved created_at and new updated_at timestamp.

    Raises:
        HTTPException: 404 if recipe not found, 500 if database error.

    Response Headers:
        Last-Modified: Timestamp of when the recipe was last updated.
    """
    try:
        recipe = session.get(Recipe, recipe_id)
    except Exception as e:
        logger.error(
            "Database error fetching recipe ID %s for update: %s",
            recipe_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error retrieving recipe",
        ) from e

    if recipe is None:
        logger.warning("Recipe with ID %s not found for update.", recipe_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found"
        )

    recipe.name = recipe_data.name
    recipe.ingredients = recipe_data.ingredients
    recipe.instructions = recipe_data.instructions
    recipe.servings_min = recipe_data.servings_min
    recipe.servings_max = recipe_data.servings_max

    recipe.updated_at = datetime.now(timezone.utc)

    try:
        session.add(recipe)
        session.commit()
        session.refresh(recipe)
    except Exception as e:
        session.rollback()
        logger.error(
            "Database error updating recipe ID %s: %s", recipe_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error updating recipe",
        ) from e

    logger.info(
        "Updated recipe with ID: %s, Name: %s",
        recipe.id,
        recipe.name,
    )

    last_modified = recipe.updated_at.strftime("%a, %d %b %Y %H:%M:%S GMT")

    return JSONResponse(
        content=recipe.model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
        headers={"Last-Modified": last_modified},
    )


@API_ROUTER.delete("/v0/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipe(
    recipe_id: int, session: Annotated[Session, Depends(get_session)]
):
    """Delete a recipe from the database.

    Permanently removes a recipe. Returns 204 No Content on success.
    Includes HX-Trigger header to notify HTMX clients of the change.

    Args:
        recipe_id: Unique identifier of the recipe to delete.
        session: Database session from dependency injection.

    Returns:
        Empty response with 204 status on success.

    Raises:
        HTTPException: 404 if recipe not found, 500 if database error.

    Response Headers:
        HX-Trigger: "recipeListChanged" event for HTMX updates.
    """
    try:
        recipe = session.get(Recipe, recipe_id)
    except Exception as e:
        logger.error(
            "Database error fetching recipe ID %s for deletion: %s",
            recipe_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error fetching recipe for deletion",
        ) from e

    if recipe is None:
        logger.warning("Recipe with ID %s not found for deletion.", recipe_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found"
        )

    try:
        session.delete(recipe)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(
            "Database error deleting recipe ID %s: %s", recipe_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error deleting recipe",
        ) from e

    logger.info("Deleted recipe with ID: %s", recipe_id)
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={"HX-Trigger": "recipeListChanged"},
    )
