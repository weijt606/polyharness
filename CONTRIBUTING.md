# Contributing to PolyHarness

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/weijt606/polyharness.git
cd polyharness
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -q
```

## Linting

```bash
ruff check src/ tests/
```

## Code Style

- Python 3.12+, type hints encouraged.
- Line length: 120 characters.
- All code, comments, and identifiers in **English**.
- Documentation (`docs/`, `README.md`) is bilingual (Chinese + English).

## Pull Requests

1. Fork the repo and create a feature branch from `main`.
2. Write tests for new functionality.
3. Ensure `ruff check` and `pytest` pass before submitting.
4. Keep PRs focused — one feature or fix per PR.

## Third-party code & attribution

PolyHarness ships **no vendored third-party source**. When you borrow an idea
from another project:

- Re-implement it in our own code; do **not** copy source from a licensed
  project without preserving its license and copyright notice.
- Attribute the source in an inline comment, and add substantial mechanisms to
  the **Acknowledgments** section of the README.
- Borrowing *ideas* from open/MIT works is welcome; vendoring their *code* is not.

## Reporting Issues

Use [GitHub Issues](https://github.com/weijt606/polyharness/issues). Include:
- Steps to reproduce
- Expected vs actual behavior
- Python version and OS

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
