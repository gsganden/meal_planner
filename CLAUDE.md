# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Setup and Environment

```bash
# Install dependencies
uv sync --all-groups

# Install pre-commit hooks
pre-commit install --hook-type pre-push -f
```

### Run the Application

```bash
# Run the app locally
uv run modal serve deploy.py

# Deploy the app
uv run modal deploy deploy.app
```

## Run Database Migrations

```bash
uv run modal run deploy.py::migrate_db
```

### Testing

```bash
# Run all tests (including slow LLM calls)
uv run pytest --runslow

# Run tests without slow LLM calls
uv run pytest

# Run a specific test file
uv run pytest tests/services/test_llm_service.py

# Run a specific test
uv run pytest tests/services/test_llm_service.py::test_get_structured_llm_response_success

# Check test coverage with minimal LLM calls
./run_fast_coverage.sh
```

### Linting and Type Checking

```bash
# Run ruff linter
uv run ruff check .
```

### Git Worktree Management

```bash
# Create a new worktree using the naming convention
git worktree add ../wt-<branch-name> <branch-name>

# List all worktrees
git worktree list

# Remove a worktree when done
git worktree remove ../wt-<branch-name>
```

**Convention**: Use `wt-*` prefix for worktree directories. These are automatically ignored by `.gitignore`.

## Architecture

The Meal Planner is an AI-powered application that allows users to extract, modify, and save recipes. The application is built with FastAPI, FastHTML, and MonsterUI, and is deployed using Modal.

### Core Components

1. **UI Layer** (main.py): Handles HTTP requests and renders HTML responses using FastHTML and MonsterUI
   - Provides recipe extraction, viewing, and modification interface

2. **Services Layer** (services/):
   - `llm_service.py`: Interfaces with Google Gemini AI for recipe extraction and modification
   - `recipe_processing.py`: Post-processes LLM-generated recipes
   - `webpage_text_extractor.py`: Fetches and cleans text from recipe URLs

3. **API Layer** (api/):
   - `recipes.py`: CRUD operations for recipes via FastAPI endpoints

4. **Data Layer**:
   - SQLite database with SQLModel ORM
   - Alembic for migrations

### Data Flow

1. User submits a recipe URL or text
2. Application fetches and cleans the text
3. LLM service extracts structured recipe data
4. User can modify the recipe with natural language prompts
5. Modified recipes are saved to the database

### Key Files

- `meal_planner/main.py`: Entry point and UI orchestration
- `meal_planner/models.py`: Data models using SQLModel/Pydantic
- `meal_planner/services/llm_service.py`: AI service integration
- `prompt_templates/`: Contains prompts for LLM interactions

### Environment Configuration

Requires a `GOOGLE_API_KEY` for Gemini AI access, stored in a `.env` file or environment variable.

## Testing Strategy

- Unit tests for all services and API endpoints
- Mock-based testing for LLM service calls
- In-memory SQLite for database testing
- `--runslow` flag to include/exclude tests that make actual LLM calls
- Tests use pytest fixtures defined in `conftest.py`
