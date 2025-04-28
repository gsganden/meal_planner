# meal_planner/api/recipes.py
import json
import logging
import uuid

from fastlite import NotFoundError, database
from pydantic import ValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Router

from meal_planner.models import Recipe, RecipeRead

logger = logging.getLogger(__name__)

# Initialize database connection
DB_PATH = "meal_planner.db"
db = database(DB_PATH)

# Define table reference
recipes_table = db.t.recipes

# Ensure table exists (adjust schema for UUID and JSON text)
recipes_table.create(
    id=uuid.UUID,
    name=str,
    ingredients=str,  # Store list as JSON string
    instructions=str,  # Store list as JSON string
    pk="id",
    replace=False,  # Don't replace if already exists
    if_not_exists=True,  # Create only if it doesn't exist
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


async def get_recipe(request: Request):
    recipe_id = request.path_params["recipe_id"]
    if not isinstance(recipe_id, uuid.UUID):
        raise HTTPException(status_code=400, detail="Invalid recipe ID format")

    try:
        row = recipes_table[recipe_id]
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Recipe not found") from None
    except Exception as e:
        logger.error(
            "Database error fetching recipe %s: %s", recipe_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=500, detail="Database error fetching recipe"
        ) from e

    try:
        ingredients_list = json.loads(row["ingredients"])
        instructions_list = json.loads(row["instructions"])
    except json.JSONDecodeError as e:
        logger.error(
            "Error decoding JSON for recipe %s: %s", recipe_id, e, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Error reading recipe data") from e

    recipe = RecipeRead(
        id=row["id"],
        name=row["name"],
        ingredients=ingredients_list,
        instructions=instructions_list,
    )

    return recipe


async def get_all_recipes(request: Request):
    try:
        all_rows = recipes_table()
    except Exception as e:
        logger.error("Database error fetching all recipes: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Database error fetching recipes"
        ) from e

    results = []
    for row in all_rows:
        try:
            ingredients_list = json.loads(row["ingredients"])
            instructions_list = json.loads(row["instructions"])
            results.append(
                RecipeRead(
                    id=row["id"],
                    name=row["name"],
                    ingredients=ingredients_list,
                    instructions=instructions_list,
                )
            )
        except json.JSONDecodeError as e:
            logger.error(
                "Error decoding JSON for recipe %s: %s", row.get("id"), e, exc_info=True
            )
            continue

    return results


api_router = Router(
    [
        Route("/recipes", endpoint=create_recipe, methods=["POST"]),
        Route(
            "/recipes", endpoint=get_all_recipes, methods=["GET"]
        ),  # Add route for GET all
        Route(
            "/recipes/{recipe_id:uuid}",
            endpoint=get_recipe,
            methods=["GET"],
            name="get_recipe",
        ),
    ]
)
