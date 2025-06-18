# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Refer to:
- `README.md` for the app architecture and typical commands
- `pre-commit-config.yaml` for standard checks.
- `.cursor` for code style guidance.

### Environment Configuration

Requires a `GOOGLE_API_KEY` for Gemini AI access, stored in a `.env` file or environment variable.

### Git Worktree Management

It is helpful to use worktrees to manage multiple tasks in parallel:

```bash
# Create a new worktree using the naming convention and copy .env file into it
git worktree add ../meal_planner__wt-<branch-name> <branch-name> \
    && cp .env ../meal_planner__wt-<branch-name>

# List all worktrees
git worktree list

# Remove a worktree when done
git worktree remove ../meal_planner__wt-<branch-name>
```

## Testing Strategy

- Unit tests for all services and API endpoints
- Mock-based testing for LLM service calls
- In-memory SQLite for database testing
- `--runslow` flag to include/exclude tests that make actual LLM calls
- Tests use pytest fixtures defined in `conftest.py`
