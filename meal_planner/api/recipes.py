import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from fastlite import database

from meal_planner.models import Recipe, RecipeRead

logger = logging.getLogger(__name__)

LOCAL_DB_PATH = Path("meal_planner_local.db")
DB_PATH = Path(os.environ.get("MEAL_PLANNER_DB_PATH", str(LOCAL_DB_PATH)))

logger.info(f"Absolute database path: {DB_PATH.resolve()}")

if DB_PATH == LOCAL_DB_PATH:
    LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

db = database(DB_PATH)


logger.info(f"Ensuring table exists in {DB_PATH.resolve()}")
# Use raw SQL to ensure AUTOINCREMENT is correctly specified
db.conn.execute(
    """CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        ingredients TEXT NOT NULL,
        instructions TEXT NOT NULL
    );"""
)
# Comment out or remove the fastlite table creation method
# recipes_table = db.t.recipes
# recipes_table.create(
#     id=int,
#     name=str,
#     ingredients=str,
#     instructions=str,
#     pk="id",
#     replace=False,
#     if_not_exists=True,
# )

# We still need the table object for other operations if used elsewhere
# Re-initialize it after ensuring the table exists via SQL
recipes_table = db.t.recipes

api_router = APIRouter()


@api_router.post(
    "/v0/recipes",
    status_code=status.HTTP_201_CREATED,
    response_model=RecipeRead,
)
async def create_recipe(recipe_data: Recipe):
    db_data = {
        "name": recipe_data.name,
        "ingredients": json.dumps(recipe_data.ingredients),
        "instructions": json.dumps(recipe_data.instructions),
    }

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

    location_path = f"/api/v0/recipes/{str(stored_recipe.id)}"

    return JSONResponse(
        content=stored_recipe.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
        headers={"Location": location_path},
    )


@api_router.get("/recipes", response_model=list[RecipeRead])
async def get_all_recipes():
    all_recipes = []
    try:
        # Select id as well and filter out rows with NULLs
        cursor = db.conn.execute(
            """SELECT id, name, ingredients, instructions 
               FROM recipes
               WHERE id IS NOT NULL 
                 AND name IS NOT NULL 
                 AND ingredients IS NOT NULL 
                 AND instructions IS NOT NULL;"""
        )
        for row in cursor:
            try:
                # Access tuple elements by index
                recipe_id = row[0]
                recipe_name = row[1]
                ingredients_json = row[2]
                instructions_json = row[3]

                # Basic check if required elements are present and not None
                if (
                    recipe_id is None  # Check id
                    or recipe_name is None
                    or ingredients_json is None
                    or instructions_json is None
                ):
                    raise ValueError("Missing required data in row")

                # Create RecipeRead object
                all_recipes.append(
                    RecipeRead(
                        id=recipe_id,
                        name=recipe_name,
                        ingredients=json.loads(ingredients_json),
                        instructions=json.loads(instructions_json),
                    )
                )
            except (json.JSONDecodeError, IndexError, TypeError, ValueError) as e:
                # Log error for the specific row and continue
                # Log limited info as we only have indices
                logger.error(
                    "Error processing recipe row from DB: %s",
                    e,
                    exc_info=False,
                )
                continue  # Skip this row
        cursor.close()
        return all_recipes
    except Exception as e:
        logger.error("Database error querying all recipes: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error retrieving recipes",
        ) from e


@api_router.get("/v0/recipes/{recipe_id}", response_model=RecipeRead)
async def get_recipe_by_id(recipe_id: int):
    try:
        # Use fastlite's get method which handles missing keys
        recipe_dict = recipes_table.get(recipe_id)
    except KeyError:
        # fastlite raises KeyError if the ID is not found
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
