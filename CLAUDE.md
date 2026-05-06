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

## Anthropic API gotchas

- **`max_tokens` includes thinking tokens.** When a prompt YAML sets `model.thinking: {type: adaptive}` (or
  `{type: enabled, budget_tokens: N}`), thinking counts against `max_tokens`. The production value `1536` silently
  starves the visible text output on complex cases when thinking is on. `Prompt.__init__` now refuses to load a
  thinking-enabled config with `max_tokens < 4096`; ≥4096 (8192 worked in past experiments) is the floor.
- **The reviewer model rejects `temperature`.** Opus 4.7 deprecated the parameter, so `prompt_testing/reviewer.py`
  omits it. The Sonnet explainer still accepts `temperature`. If you swap the reviewer to a model that requires
  it, restore the param.
- **Reviewer thinking is on by default.** `prompt-test run --review` and `prompt-test review` default to
  `--reviewer-thinking adaptive` / `--thinking adaptive`. It catches factual errors the no-think reviewer misses
  but adds ~70% to review cost. Pass `off` to compare runs or save money on large batches.
- **Production explainer thinking is intentionally off.** Adaptive thinking on Sonnet 4.6 measurably improves
  factual accuracy (e.g. eliminates the recurring `imul eax, edi, edi` invention) but adds ~11s end-to-end
  latency, which is too much for the interactive endpoint. Don't enable it in `app/prompt.yaml` without an
  explicit latency/quality decision.
- **Multi-block responses.** When thinking is enabled the API returns thinking blocks before the text block.
  `app/explain.py` and `prompt_testing/runner.py` both pick the last text block via `getattr(c, "type", None) ==
  "text"`. Preserve that pattern for any new code that consumes responses. The API may also return
  `redacted_thinking` blocks (encrypted reasoning when safety filters trip); the same filter excludes them
  correctly, but be aware "no text block" can mean either max_tokens starvation *or* a redacted-thinking-only
  response — the error message is the same.
- **Empty responses are not 500s.** When the model returns no text block, `app/explain.py` returns
  `ExplainResponse(status="error")` with `usage` populated and emits `ClaudeExplainEmptyResponse`. The cache
  layer skips storing error responses so retries hit the API. Don't change this to raise — the structured error
  is what the CE frontend can render.

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
