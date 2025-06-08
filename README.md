[![Build Status](https://github.com/gsganden/meal_planner/actions/workflows/ci_cd.yml/badge.svg)](https://github.com/gsganden/meal_planner/actions/workflows/ci_cd.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Checked with Pyright](https://img.shields.io/badge/type_checked-pyright-blue)](https://github.com/microsoft/pyright)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)

# Meal Planner

AI-powered meal planning app. Under development. Running at https://gsganden--meal-planner-web.modal.run/.


```mermaid
graph LR
    User(("User"))

    Modal["Modal (Hosting)"]

    subgraph "Meal Planner Application"
        direction LR

        direction TB
        Web_Routing_Layer["Web Request Routing<br/>(routers/)<br/>FastHTML"]
        
        UI_Components["UI Components<br/>(ui/)<br/>MonsterUI"]

        subgraph "Business Logic (services/)"
            direction TB
            Webpage_Text_Extractor_Service["Webpage text extraction<br/>(extract_webpage_text.py)<br/>URL fetching, HTML cleaning"]
            Recipe_Processing_Service["Recipe processing<br/>(process_recipe.py)<br/>Data cleaning & standardization"]
            LLM_Service["LLM interactions<br/>(call_llm.py)<br/>Google Gemini, Instructor"]
        end

        API_Layer["Recipe CRUD API<br/>(api/recipes.py)<br/>FastAPI"]

        Web_Routing_Layer -- "Renders" --> UI_Components
        
        Web_Routing_Layer -- "Calls" --> Webpage_Text_Extractor_Service
        Web_Routing_Layer -- "Calls" --> Recipe_Processing_Service
        Web_Routing_Layer -- "Calls" --> LLM_Service
        Web_Routing_Layer -- "Internal API Call" --> API_Layer
    end

    subgraph "External Resources"
        direction TB
        Database[("Database (SQLite)")]
        External_Web_Pages["External Web Pages/URLs"]
        Google_Gemini_Cloud["Google Gemini Cloud API"]
    end

    User --> Modal
    Modal --> Web_Routing_Layer

    Webpage_Text_Extractor_Service -- "Fetches content" --> External_Web_Pages
    LLM_Service -- "AI Tasks" --> Google_Gemini_Cloud
    API_Layer --> Database
```

## Setup

```bash
uv sync --all-extras
```

[Get a Gemini API key](https://aistudio.google.com/apikey) and assign its value to a `GOOGLE_API_KEY` environment variable inside a dotenv file.

Install pre-commit hooks:

```bash
pre-commit install --hook-type pre-push -f
```

## Run App Locally

```bash
uv run modal serve deploy.py
```

## Run Database Migrations

```bash
uv run modal run deploy.py::migrate_db
```

## Run Tests

Skip tests that make slow LLM calls:

```bash
uv run pytest
```

Run the tests that make slow LLM calls with a chance to retry once as a way to handle atypical nondeterministic failures:

```bash
source .env && uv run pytest tests/test_ml_evals.py --runslow --reruns=1
```

Check test coverage with minimal LLM calls:

```bash
./run_fast_coverage.sh
```
