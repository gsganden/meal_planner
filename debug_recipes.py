#!/usr/bin/env python3
"""Debug script to test recipe API with production data."""

import asyncio
from meal_planner.api.recipes import get_recipes
from meal_planner.database import get_session

async def test_recipes():
    session_gen = get_session()
    session = next(session_gen)
    try:
        recipes = await get_recipes(session)
        print(f'Found {len(recipes)} recipes')
        
        # Check for any None values in critical fields
        for i, recipe in enumerate(recipes):
            if recipe.id is None:
                print(f'Recipe {i}: ID is None')
            if recipe.created_at is None:
                print(f'Recipe {i}: created_at is None - {recipe.name}')
            if recipe.updated_at is None:
                print(f'Recipe {i}: updated_at is None - {recipe.name}')
                
        print('Recipe validation complete')
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    asyncio.run(test_recipes())