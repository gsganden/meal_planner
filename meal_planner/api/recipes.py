import json
import logging
from pathlib import Path
from typing import Annotated, Any

import apswutils.db
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
import fastlite as fl
from pydantic import Field

from meal_planner.models import Recipe, RecipeRead

logger = logging.getLogger(__name__)

DB_NAME = "meal_planner.db"
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / DB_NAME


def get_initialized_db(db_path_override: Path | None = None) -> fl.Database:
    """Get a database connection.

    Ensures that the database has been initialized with `recipes` table.

    Args:
        db_path_override: If provided, use this path instead of the default.
    """
    target_db_path = db_path_override if db_path_override else DB_PATH

    db_conn = fl.database(target_db_path)

    db_conn.conn.execute(
        """CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            ingredients TEXT NOT NULL,
            instructions TEXT NOT NULL
        );"""
    )

    return db_conn


api_router = APIRouter()


@api_router.post(
    "/v0/recipes",
    status_code=status.HTTP_201_CREATED,
    response_model=RecipeRead,
)
async def create_recipe(
    recipe_data: Recipe, db: Annotated[Any, Depends(get_initialized_db)]
):
    db_data = {
        "name": recipe_data.name,
        "ingredients": json.dumps(recipe_data.ingredients),
        "instructions": json.dumps(recipe_data.instructions),
    }
    recipes_table = db.t.recipes  # Get table object from the connection

    try:
        # Use the specific connection for this request
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

    location_path = f"/api/v0/recipes/{str(stored_recipe.id)}"

    return JSONResponse(
        content=stored_recipe.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
        headers={"Location": location_path},
    )


@api_router.get("/recipes", response_model=list[RecipeRead])
async def get_all_recipes(db: Annotated[Any, Depends(get_initialized_db)]):
    all_recipes = []
    try:
        # Try using fastlite's table select method instead of raw SQL
        recipes_table = db.t.recipes
        for recipe_dict in recipes_table():  # Selects all rows
            try:
                # Removed check for nulls/missing keys, relying on NOT NULL
                # constraints
                # and subsequent KeyError handling if needed.

                # Create RecipeRead object
                all_recipes.append(
                    RecipeRead(
                        id=recipe_dict["id"],
                        name=recipe_dict["name"],
                        ingredients=json.loads(recipe_dict["ingredients"]),
                        instructions=json.loads(recipe_dict["instructions"]),
                    )
                )
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                # Log error for the specific row and continue
                logger.error(
                    f"Error processing recipe row from DB: {e} - Data: {recipe_dict}",
                    exc_info=False,
                )
                continue  # Skip this row
        return all_recipes
    except Exception as e:
        logger.error("Database error querying all recipes: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error retrieving recipes",
        ) from e


@api_router.get("/v0/recipes/{recipe_id}", response_model=RecipeRead)
async def get_recipe_by_id(
    recipe_id: int, db: Annotated[Any, Depends(get_initialized_db)]
):
    recipes_table = db.t.recipes  # Get table object from the connection
    try:
        # Use fastlite's get method which handles missing keys
        # Use the specific connection for this request
        recipe_dict = recipes_table.get(recipe_id)
    except apswutils.db.NotFoundError:  # Catch the correct exception
        # fastlite raises NotFoundError if the ID is not found
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
        # Deserialize JSON fields
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


RecipeId = Annotated[int, Field(..., description="Unique identifier for the recipe")]
RecipeIngredients = Annotated[list[str], Field(..., description="List of ingredients")]
RecipeInstructions = Annotated[
    list[str], Field(..., description="List of instructions")
]
RecipeName = Annotated[str, Field(..., description="The name of the recipe")]
