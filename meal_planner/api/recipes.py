import json
import logging
from pathlib import Path
from typing import Annotated

import apswutils.db
import fastlite as fl
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from meal_planner.db import get_initialized_db
from meal_planner.models import Recipe, RecipeId, RecipeRead

logger = logging.getLogger(__name__)

API_ROUTER = APIRouter()

API_VERSION = "v0"
RECIPES_PATH = f"/{API_VERSION}/recipes"
RECIPE_ITEM_PATH = RECIPES_PATH + "/{recipe_id}"


@API_ROUTER.post(
    RECIPES_PATH,
    status_code=status.HTTP_201_CREATED,
    response_model=RecipeRead,
)
async def create_recipe(
    recipe_data: Recipe, db: Annotated[fl.Database, Depends(get_initialized_db)]
):
    db_data = {
        "name": recipe_data.name,
        "ingredients": json.dumps(recipe_data.ingredients),
        "instructions": json.dumps(recipe_data.instructions),
    }
    recipes_table = db.t.recipes  # type: ignore

    try:
        inserted_record = recipes_table.insert(db_data)
    except Exception as e:
        logger.error("Database error inserting recipe: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error creating recipe",
        ) from e

    stored_recipe = RecipeRead(id=inserted_record["id"], **recipe_data.model_dump())

    logger.info(
        "Created recipe with ID: %s, Name: %s",
        stored_recipe.id,
        stored_recipe.name,
    )

    location_path = f"/api{RECIPES_PATH}/{str(stored_recipe.id)}"

    return JSONResponse(
        content=stored_recipe.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
        headers={"Location": location_path},
    )


@API_ROUTER.get(RECIPES_PATH, response_model=list[RecipeRead])
async def get_all_recipes(db: Annotated[fl.Database, Depends(get_initialized_db)]):
    all_recipes = []
    try:
        recipes_table = db.t.recipes  # type: ignore
        for recipe_dict in recipes_table():
            try:
                all_recipes.append(
                    RecipeRead(
                        id=recipe_dict["id"],
                        name=recipe_dict["name"],
                        ingredients=json.loads(recipe_dict["ingredients"]),
                        instructions=json.loads(recipe_dict["instructions"]),
                    )
                )
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                logger.error(
                    f"Error processing recipe row from DB: {e} - Data: {recipe_dict}",
                    exc_info=False,
                )
                continue
        return all_recipes
    except Exception as e:
        logger.error("Database error querying all recipes: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error retrieving recipes",
        ) from e


@API_ROUTER.get(RECIPE_ITEM_PATH, response_model=RecipeRead)
async def get_recipe_by_id(
    recipe_id: RecipeId, db: Annotated[fl.Database, Depends(get_initialized_db)]
):
    recipes_table = db.t.recipes  # type: ignore
    try:
        recipe_dict = recipes_table.get(recipe_id)
    except apswutils.db.NotFoundError:
        logger.warning("Recipe with ID %s not found.", recipe_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found"
        ) from None
    except Exception as e:
        logger.error(
            "Database error fetching recipe ID %s: %s", recipe_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error retrieving recipe",
        ) from e

    try:
        return RecipeRead(
            id=recipe_dict["id"],
            name=recipe_dict["name"],
            ingredients=json.loads(recipe_dict["ingredients"]),
            instructions=json.loads(recipe_dict["instructions"]),
        )
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error(
            "Error processing recipe data for ID %s: %s. Data: %s",
            recipe_id,
            e,
            recipe_dict,
            exc_info=False,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing recipe data",
        ) from e
