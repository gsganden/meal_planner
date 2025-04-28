import json
import logging
import os
from pathlib import Path

from fastlite import database
from pydantic import ValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Router

from meal_planner.models import Recipe, RecipeRead

logger = logging.getLogger(__name__)

LOCAL_DB_PATH = Path("meal_planner_local.db")
VOLUME_MOUNT_PATH = Path("/data")
DB_PATH_STR = os.environ.get("MEAL_PLANNER_DB_PATH", str(LOCAL_DB_PATH))
DB_PATH = Path(DB_PATH_STR)

logger.info(f"Using database path: {DB_PATH}")

if DB_PATH == LOCAL_DB_PATH:
    LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

db = database(DB_PATH)
recipes_table = db.t.recipes

if DB_PATH == LOCAL_DB_PATH:
    logger.info("Ensuring table exists for local DB")
    recipes_table.create(
        id=int,
        name=str,
        ingredients=str,
        instructions=str,
        pk="id",
        replace=False,
        if_not_exists=True,
    )


async def create_recipe(request: Request):
    try:
        payload = await request.json()
        recipe_data = Recipe.model_validate(payload)
    except ValidationError as e:
        logger.warning("Validation failed for create recipe: %s", e.errors())
        return JSONResponse(content={"detail": e.errors()}, status_code=422)
    except Exception as e:
        logger.error("Error parsing request JSON: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from e

    # ID is now auto-generated
    # new_id = uuid.uuid4()

    db_data = {
        # Remove "id": new_id,
        "name": recipe_data.name,
        "ingredients": json.dumps(recipe_data.ingredients),
        "instructions": json.dumps(recipe_data.instructions),
    }

    try:
        # Use insert for auto-incrementing PKs
        inserted_record = recipes_table.insert(db_data)
    except Exception as e:
        logger.error("Database error inserting recipe: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Database error creating recipe"
        ) from e

    # Construct the response model using the ID from the inserted record
    stored_recipe = RecipeRead(id=inserted_record["id"], **recipe_data.model_dump())

    logger.info(
        "Created recipe with ID: %s, Name: %s",
        stored_recipe.id,
        stored_recipe.name,
    )

    location_path = f"/api/v1/recipes/{str(stored_recipe.id)}"

    return JSONResponse(
        content=stored_recipe.model_dump(mode="json"),
        status_code=201,
        headers={"Location": location_path},
    )


api_router = Router(
    [
        Route("/recipes", endpoint=create_recipe, methods=["POST"]),
    ]
)
