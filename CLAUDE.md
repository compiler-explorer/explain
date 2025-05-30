# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a FastAPI-based service that provides AI-powered explanations of compiler assembly output for the Compiler
Explorer website. The service uses Anthropic's Claude API to analyze source code and its compiled assembly, providing
educational explanations of compiler transformations and optimizations.

There's a prompt testing framework that allows for us to explore and improve the prompts used to generate explanations.
This framework is designed to be extensible and allows for easy addition of new tests and prompt variations.

## Project Structure

This is a FastAPI-based service that can run locally for development or as an AWS Lambda function via Mangum adapter.
See the source code for current project structure.

## Development Commands

### Setup

```bash
# Set up environment with .env file containing:
# ANTHROPIC_API_KEY=<your-key-here>

# Install dependencies
uv sync --group dev
```

### Running Locally

```bash
# Start development server
uv run fastapi dev

# Test the service
./test-explain.sh
# Or with pretty output:
./test-explain.sh --pretty
```

### Testing

```bash
# Run tests
uv run pytest

# Run specific test
uv run pytest app/explain_test.py::test_process_request_success
```

### Code Quality

```bash
# Run pre-commit hooks (ruff linting/formatting, shellcheck)
uv run pre-commit run --all-files

# Manual linting
uv run ruff check
uv run ruff format
```

## Key Architecture Details

The service processes compiler output through a pipeline: input validation → smart assembly filtering → Claude API
call → response with metrics. See `claude_explain.md` for detailed architecture documentation.

## Code Style Guidelines

- Prefer using modern Python 3.13+ type syntax. Good: `a: list[str] | None`. Bad: `a: Optional[List[str]]`
- Use ruff for linting and formatting with line length of 120 characters
- Prefer pathlib.Path over old-fashioned io like naked `open` and `glob` calls. Always supply an encoding
- Always import at the top of the file, don't litter imports throughout the file
- Strive for simplicity and clarity in code. Avoid unnecessary complexity.
- Don't assume backwards compatibility is required unless explicitly stated. Ask if unsure.

## Development Workflow Notes

### Before Pushing Code
**ALWAYS run the full test suite before pushing any code changes:**

```bash
# Required before every push
uv run pytest              # Run all tests (matches CI)
uv run pre-commit run --all-files  # Run all linting/formatting
```

This prevents CI failures and ensures code quality. The CI runs exactly these commands, so running them locally will catch any issues.

### General Notes
- The pre-commit hooks may modify the code and so: always run them before `git add`, and if a commit hook fails then
  it's probably you'll need to `git add` again if it indicated it fixed issues (e.g. `ruff`)
- Ruff is configured for Python 3.13+ with 120 character line length
