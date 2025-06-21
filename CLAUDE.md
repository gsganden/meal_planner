# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Refer to:
- `README.md` for the app architecture and typical commands
- `pre-commit-config.yaml` for standard checks.
- `.cursor` for code style guidance.

Do **not** comment the code except where necessary to explain the rationale for an initially puzzling choice. Do NOT leave comments that simply restate what the code does. If the code is at a lower level of abstraction than its surroundings, place it in a helper function with a descriptive name rather than leaving a comment.

## Style Guidance

`fasthtml` and `monsterui` are designed to work with `import *`, so we want that pattern even though it is not recommended generally.

## Environment Configuration

Requires a `GOOGLE_API_KEY` for Gemini AI access, stored in a `.env` file or environment variable.

## Git Worktree Management

Use worktrees so we can easily work on multiple issues in parallel on a single machine:

```bash
# Create branch
git checkout -b <branch-name>

# Create a new worktree for the branch using the naming convention and copy .env file into it
git worktree add ../meal_planner__wt-<branch-name> <branch-name> \
    && cp .env ../meal_planner__wt-<branch-name>

# List all worktrees
git worktree list

# Remove a worktree when done
git worktree remove ../meal_planner__wt-<branch-name>
```

## Pull Requests

Include `.github/PULL_REQUEST_TEMPLATE.md` in pull request descriptions.

## Testing Strategy

- Unit tests for all services and API endpoints
- Mock-based testing for LLM service calls
- In-memory SQLite for database testing
- `--runslow` flag to include/exclude tests that make actual LLM calls
- Tests use pytest fixtures defined in `conftest.py`
