# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a FastAPI-based service that provides AI-powered explanations of compiler assembly output for the Compiler Explorer website. The service uses Anthropic's Claude API to analyze source code and its compiled assembly, providing educational explanations of compiler transformations and optimizations.

## Project Structure

- `app/main.py` - FastAPI application entry point with `/explain` endpoint
- `app/explain.py` - Core logic for processing assembly explanation requests
- `app/config.py` - Configuration management using Pydantic settings
- `test-explain.sh` - Integration test script for the explain endpoint

The application is designed to run both locally for development and as an AWS Lambda function via Mangum adapter.

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
uv run pytest app/explain_test.py::test_should_succeed
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

### Request Processing Flow
1. FastAPI receives POST to `/explain` with compiler output data
2. `process_request()` validates input and prepares structured data
3. Assembly output is intelligently truncated if too large via `select_important_assembly()`
4. Claude API is called with system prompt and structured JSON data
5. Response includes explanation, token usage, and cost metrics

### Assembly Intelligence
The service implements smart assembly filtering to handle large compiler outputs:
- Preserves function boundaries (labels, entry/exit points)
- Keeps instructions with source code mappings
- Maintains contextual instructions around important code
- Adds omission markers for skipped sections

### Metrics & Monitoring
Uses AWS Embedded Metrics for CloudWatch integration when deployed, with a no-op provider for local development. Tracks token usage, costs, and request patterns.

### Environment Configuration
- Local development: Uses `.env` file for API key
- AWS deployment: Expects environment variables for API key and optional root path

## Important Constants

- `MAX_ASSEMBLY_LINES = 300` - Maximum assembly lines processed
- `MODEL = "claude-3-5-haiku-20241022"` - Claude model used
- `MAX_TOKENS = 1024` - Response length limit
- Token costs are tracked for billing/monitoring

## Code Style Guidelines

- Prefer using modern Python 3.9+ type syntax. Good: `a: list[str] | None`. Bad: `a: Optional[List[str]]`

## Development Workflow Notes

- The pre commit hooks may modify the code and so: always run them before `git add`, and if a commit hook fails then it's probably you'll need to `git add` again if it indicated if fixed issues (e.g. `ruff`)
