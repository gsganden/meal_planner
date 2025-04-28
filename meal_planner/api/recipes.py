import json
import logging
import uuid

from fastlite import database
from pydantic import ValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Router

from meal_planner.models import Recipe, RecipeRead

logger = logging.getLogger(__name__)

DB_PATH = "meal_planner.db"
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

    new_id = uuid.uuid4()

    db_data = {
        "id": new_id,
        "name": recipe_data.name,
        "ingredients": json.dumps(recipe_data.ingredients),
        "instructions": json.dumps(recipe_data.instructions),
    }

    try:
        recipes_table.insert(db_data)
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
