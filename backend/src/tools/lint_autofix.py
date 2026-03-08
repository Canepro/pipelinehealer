"""Shared deterministic lint autofix commands."""


def lint_autofix_command(linter: str) -> str:
    """Return the approved autofix command for a known linter."""
    commands = {
        "eslint": "npx eslint --fix .",
        "prettier": "npx prettier --write .",
        "black": "black .",
        "ruff": "ruff check --fix . && ruff format .",
        "isort": "isort .",
    }
    return commands.get(str(linter).strip().lower(), "")
