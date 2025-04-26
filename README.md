[![Build Status](https://github.com/gsganden/meal_planner/actions/workflows/ci.yml/badge.svg)](https://github.com/gsganden/meal_planner/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Checked with Pyright](https://img.shields.io/badge/type_checked-pyright-blue)](https://github.com/microsoft/pyright)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)

# Meal Planner

## Setup

```bash
uv sync
```

[Get a Gemini API key](https://aistudio.google.com/apikey) and assign its value to a `GOOGLE_API_KEY` environment variable.

```bash
pre-commit install --hook-type pre-push -f
```

## Commands

```bash
uv run python meal_planner/main.py
```
