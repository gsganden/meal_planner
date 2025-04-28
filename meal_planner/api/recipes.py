import json
import logging
import uuid
from pathlib import Path

from fastlite import database
from pydantic import ValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Router

from meal_planner.models import Recipe, RecipeRead

logger = logging.getLogger(__name__)

VOLUME_MOUNT_PATH = Path("/data")
DB_PATH = VOLUME_MOUNT_PATH / "meal_planner.db"

# Global variables for database and table, initialized lazily
db = None
recipes_table = None


def initialize_db():
    global db, recipes_table
    if db is None:
        logger.info(f"Initializing database connection to: {DB_PATH}")
        # Assuming /data exists due to deploy.py
        db = database(DB_PATH)
        recipes_table = db.t.recipes
        recipes_table.create(
            id=uuid.UUID,
            name=str,
            ingredients=str,
            instructions=str,
            pk="id",
            replace=False,
            if_not_exists=True,
        )
        logger.info(f"Database initialized and table ensured: {recipes_table}")
    return recipes_table


async def create_recipe(request: Request):
    table = initialize_db()  # Get table, ensuring DB is initialized
    try:
        payload = await request.json()
        recipe_data = Recipe.model_validate(payload)
    except ValidationError as e:
        logger.warning("Validation failed for create recipe: %s", e.errors())
        return JSONResponse(content={"detail": e.errors()}, status_code=422)
    except Exception as e:
        logger.error("Error parsing request JSON: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from e

    new_id = uuid.uuid4()

    db_data = {
        "id": new_id,
        "name": recipe_data.name,
        "ingredients": json.dumps(recipe_data.ingredients),
        "instructions": json.dumps(recipe_data.instructions),
    }

    try:
        table.insert(db_data)  # Use the local 'table' variable
    except Exception as e:
        logger.error("Database error inserting recipe: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Database error creating recipe"
        ) from e

    stored_recipe = RecipeRead(id=new_id, **recipe_data.model_dump())

    logger.info("Created recipe with ID: %s, Name: %s", new_id, stored_recipe.name)

    location_path = f"/api/v1/recipes/{str(new_id)}"

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
