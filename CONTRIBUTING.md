# Contributing

Thanks for your interest in contributing to Growth Creative Factory.

## Development setup

1. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   pip install pre-commit ruff black detect-secrets
   ```

3. Install git hooks:

   ```bash
   pre-commit install
   ```

4. Run checks locally before opening a PR:

   ```bash
   black --check .
   ruff check .
   pytest -v
   ```

## Coding style

- Use `black` formatting defaults.
- Use `ruff` for linting.
- Add or update tests with `pytest` for behavior changes.
- Avoid adding network-coupled tests; use fixtures/mocks.

## Adding connectors/providers/prompts

### Connectors (`gcf/connectors/`)

- Implement pull/push logic with clear, typed function signatures.
- Raise connector-specific exceptions (see existing connectors).
- Keep provider credentials in environment variables or local config files ignored by git.
- Add tests under `tests/` for parsing/transformation behavior.

### Providers (`gcf/providers/`)

- Implement the provider contract from `gcf/providers/base.py`.
- Keep retries/budget logic in config; do not hardcode secrets or model IDs.
- Add unit tests for provider behavior with mocks.

### Prompts (`gcf/prompts/`)

- Keep prompts plain-text and focused on one task.
- If prompt schema changes, update validation/tests accordingly.

## Commit message convention

Use a short conventional prefix:

- `feat:` new feature
- `fix:` bug fix
- `chore:` maintenance
- `refactor:` internal change without behavior change
- `docs:` documentation only

Examples:

- `feat: add google sheets push command`
- `fix: handle missing revenue column in validator`
- `docs: improve quickstart and connector docs links`

## Pull requests

- Use the PR template checklist.
- Keep changes focused and small when possible.
- Update docs/tests when behavior changes.
- Confirm no credentials or private data are included.
