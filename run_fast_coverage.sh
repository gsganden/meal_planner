#!/usr/bin/env bash
set -e

echo "Sourcing environment variables..."
source .env

echo "Running fast coverage check (main, api, 1 eval test)..."
uv run pytest \
    --cov=meal_planner \
    --cov-report term-missing \
    tests/test_main.py \
    tests/test_api.py \
    'tests/test_main_evals.py::test_extract_recipe_name[tests/data/recipes/raw/good-old-fashioned-pancakes.html]' \
    --runslow

echo "Done." 