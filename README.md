[![Build Status](https://github.com/gsganden/meal_planner/actions/workflows/ci.yml/badge.svg)](https://github.com/gsganden/meal_planner/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Checked with Pyright](https://img.shields.io/badge/type_checked-pyright-blue)](https://github.com/microsoft/pyright)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)

# Meal Planner

AI-powered meal planning app. Under development. Running at https://gsganden--meal-planner-web.modal.run/.

## Setup

```bash
uv sync
```

[Get a Gemini API key](https://aistudio.google.com/apikey) and assign its value to a `GOOGLE_API_KEY` environment variable inside a dotenv file.

Install pre-commit hooks:

```bash
pre-commit install --hook-type pre-push -f
```

## Run App Locally

```bash
uv run modal serve meal_planner/main.py
```

## Deploy App

```bash
uv run modal deploy deploy.app
```

## Running Tests

To run all the tests:

```bash
uv run pytest --runslow
```

To skip tests that make slow LLM calls:

```bash
uv run pytest --runslow
```

To check test coverage with minimal LLM calls:

```bash
./run_fast_coverage.sh
```