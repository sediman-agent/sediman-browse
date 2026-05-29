# Contributing to Sediman

Thank you for your interest in contributing to Sediman! We appreciate every bug
report, feature idea, and pull request.

## Development Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/sediman-ai/sediman-browse.git
   cd sediman-browse
   ```

2. Install dependencies with [uv](https://docs.astral.sh/uv/):

   ```bash
   uv sync
   ```

3. Run the test suite to verify everything works:

   ```bash
   pytest
   ```

## Code Style

We use [Ruff](https://docs.astral.sh/ruff/) for both formatting and linting.

Format your code before committing:

```bash
ruff format src/
```

Check for lint issues:

```bash
ruff check src/
```

Fix auto-fixable lint issues:

```bash
ruff check --fix src/
```

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`.

Examples:

- `feat(browser): add proxy support`
- `fix(agent): handle timeout on navigation`
- `docs: update README installation steps`

## Pull Request Process

1. Fork the repository.
2. Create a feature branch from `main`:

   ```bash
   git checkout -b feat/my-new-feature
   ```

3. Make your changes. Keep one feature or fix per PR.
4. Ensure tests pass:

   ```bash
   pytest tests/ -q
   ```

5. Ensure linting passes:

   ```bash
   ruff check src/ && ruff format --check src/
   ```

6. Push your branch and open a pull request against `main`.
7. Address any review feedback.

## Testing

Run the full test suite:

```bash
pytest tests/ -q
```

Run a specific test file:

```bash
pytest tests/test_agent.py -q
```

Please add tests for any new functionality or bug fixes.

## License

By contributing to Sediman, you agree that your contributions will be licensed
under the Business Source License 1.1 (BSL-1.1) that covers this project.
