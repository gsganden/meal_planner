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
        Main_Routes["Route Handlers<br/>(main.py)<br/>FastHTML"]
        
        UI_Components["UI Components<br/>(ui/)<br/>MonsterUI"]

        subgraph "Business Logic (services/)"
            direction TB
            Webpage_Text_Extractor_Service["Webpage text extraction<br/>(extract_webpage_text.py)<br/>URL fetching, HTML cleaning"]
            Recipe_Processing_Service["Recipe processing<br/>(process_recipe.py)<br/>Data cleaning & standardization"]
            LLM_Service["LLM interactions<br/>(call_llm.py)<br/>OpenAI client, Instructor"]
        end

        API_Layer["Recipe CRUD operations<br/>(recipes.py)<br/>FastAPI"]

        Main_Routes -- "Renders" --> UI_Components
        
        Main_Routes -- "Calls" --> Webpage_Text_Extractor_Service
        Main_Routes -- "Calls" --> Recipe_Processing_Service
        Main_Routes -- "Calls" --> LLM_Service
        Main_Routes -- "Internal API Call" --> API_Layer
    end

    subgraph "External Resources"
        direction TB
        Database[("Database (SQLite)")]
        External_Web_Pages["External Web Pages/URLs"]
        Gemini_AI["Google Gemini"]
    end

    User --> Modal
    Modal --> Main_Routes

    Webpage_Text_Extractor_Service -- "Fetches content" --> External_Web_Pages
    LLM_Service -- "AI Tasks" --> Gemini_AI
    API_Layer --> Database
```

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
## Run Tests

To run all the tests:

```bash
uv run pytest --runslow
```

To skip tests that make slow LLM calls:

```bash
uv run pytest
```

To check test coverage with minimal LLM calls:

```bash
./run_fast_coverage.sh
```
