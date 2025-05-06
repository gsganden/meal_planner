#!/usr/bin/env bash
set -e

source .env

uv run pytest \
    --cov=meal_planner \
    --cov-report term-missing \
    --cov-fail-under=100 \
    tests/test_main.py \
    tests/test_api.py \
    'tests/test_main_evals.py::test_extract_recipe_name[tests/data/recipes/raw/good-old-fashioned-pancakes.html]' \
    --runslow
