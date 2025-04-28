# meal_planner/api/recipes.py
import logging
import uuid
import json
from typing import Annotated

import fasthtml.common as fh
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Router, Route
from starlette.exceptions import HTTPException
from pydantic import ValidationError
from fastlite import database, NotFoundError

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
        return JSONResponse(content={"detail": "Invalid JSON payload"}, status_code=400)

    new_id = uuid.uuid4()

    # Prepare data for DB (serialize lists to JSON)
    db_data = {
        "id": new_id,
        "name": recipe_data.name,
        "ingredients": json.dumps(recipe_data.ingredients),
        "instructions": json.dumps(recipe_data.instructions),
    }

    try:
        # Insert data using fastlite
        recipes_table.insert(db_data)
    except Exception as e:
        logger.error("Database error inserting recipe: %s", e, exc_info=True)
        # Use HTTPException for standard errors
        raise HTTPException(status_code=500, detail="Database error creating recipe")

    # Create the response model instance
    stored_recipe = RecipeRead(id=new_id, **recipe_data.model_dump())

    logger.info("Created recipe with ID: %s, Name: %s", new_id, stored_recipe.name)

    location_path = f"/api/v1/recipes/{str(new_id)}"

    return JSONResponse(
        content=stored_recipe.model_dump(mode="json"),
        status_code=201,
        headers={"Location": location_path},
    )


async def get_recipe(request: Request):
    recipe_id = request.path_params["recipe_id"]  # Already UUID from converter
    if not isinstance(recipe_id, uuid.UUID):
        # Should not happen if :uuid converter works, but good to check
        raise HTTPException(status_code=400, detail="Invalid recipe ID format")

    try:
        # Fetch using fastlite table indexing
        row = recipes_table[recipe_id]
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Recipe not found")
    except Exception as e:
        logger.error(
            "Database error fetching recipe %s: %s", recipe_id, e, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Database error fetching recipe")

    # Deserialize JSON strings back to lists
    try:
        ingredients_list = json.loads(row["ingredients"])
        instructions_list = json.loads(row["instructions"])
    except json.JSONDecodeError as e:
        logger.error(
            "Error decoding JSON for recipe %s: %s", recipe_id, e, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Error reading recipe data")

    # Create response model
    recipe = RecipeRead(
        id=row["id"],
        name=row["name"],
        ingredients=ingredients_list,
        instructions=instructions_list,
    )

    return recipe  # Return the Pydantic model directly


# Add GET all recipes endpoint
async def get_all_recipes(request: Request):
    try:
        # Fetch all rows using table as callable
        all_rows = recipes_table()
    except Exception as e:
        logger.error("Database error fetching all recipes: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Database error fetching recipes")

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
            # Skip corrupted rows or return an error? For now, skip.
            continue

    return results  # Return list of Pydantic models


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
