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
        subgraph "UI & Presentation Layer"
            UI_Layer["FastHTML, MonsterUI, HTMX<br/>Serves HTML, UI Logic<br/>Orchestrates AI & API calls<br/>Handles Web Routes"]
        end

        subgraph "Business Logic / Services"
            direction TB
            Services_Layer["Internal Services<br/>e.g., Recipe Processing"]
        end

        subgraph "Backend API Layer"
            API_Layer["FastAPI<br/>RESTful Endpoints<br/>DB Interaction"]
        end

        UI_Layer -- "Uses" --> Services_Layer
        UI_Layer -- "Internal API Call" --> API_Layer
    end

    subgraph "External Data & AI" %% Renamed for clarity
        direction TB
        Database[("Database (SQLite)")]
        Gemini_AI["Google Gemini AI Service<br/>openai client, instructor"]
    end

    User --> Modal
    Modal --> UI_Layer

    UI_Layer -- "AI Tasks" --> Gemini_AI
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
