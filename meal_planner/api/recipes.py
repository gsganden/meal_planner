import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
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
    db_recipe = Recipe.model_validate(recipe_data)

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
    try:
        recipe = session.get(Recipe, recipe_id)
    except Exception as e:
        # Catch potential database errors during fetch
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
