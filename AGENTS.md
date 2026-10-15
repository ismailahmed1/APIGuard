# AGENTS.md

## Project Context

Before making changes, read `docs/PROJECT_CONTEXT.md` to understand APIGuard’s goals, requirements, current design decisions and open questions.

If a requirement or design decision is unclear, do not make a major assumption. Ask for clarification or record the question in the project-context document.

## Development Guidelines

- Work on one GitHub issue at a time.
- Create a separate branch for each issue.
- Keep changes small and limited to the issue’s scope.
- Prefer simple implementations that the team can understand and maintain.
- Explain any important design choices or new dependencies.
- Do not introduce major architectural changes without team approval.
- Add or update tests when changing system behaviour.
- Run the relevant tests before opening a pull request.
- Never commit API keys, passwords, tokens, `.env` files or other secrets.

## Project Rules

- Generated test suites must be saved and executable without calling the AI model again.
- FastAPI applications and their tests should run in isolated Docker environments.
- Schemathesis will be used as the baseline for comparison.
- Both direct Pytest generation and structured test-definition generation will initially be evaluated.
- Important decisions and their reasoning should be recorded in `docs/PROJECT_CONTEXT.md`.

## Git Workflow

- Create branches from `main`.
- Use descriptive branch names such as `feature/openapi-parser`, `docs/project-context` or `fix/test-runner`.
- Write clear commit messages.
- Connect pull requests to their related GitHub issues.
- Do not push unfinished work directly to `main`.

## Commands

Project setup, testing and formatting commands will be added here once the initial Python project is created.
