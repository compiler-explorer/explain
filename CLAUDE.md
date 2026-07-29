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
  `{type: enabled, budget_tokens: N}`), thinking counts against `max_tokens`. The old production value `1536`
  silently starved the visible text output on complex cases when thinking was on (production is now `4096`). `Prompt.__init__` now refuses to load a
  thinking-enabled config with `max_tokens < 4096`; ≥4096 (8192 worked in past experiments) is the floor.
- **Neither production model accepts `temperature`.** Opus 5 (reviewer) and Sonnet 5 (explainer) both reject
  non-default sampling parameters with a 400, so `prompt_testing/reviewer.py` omits it and `app/prompt.yaml` sets
  none. Only pre-5 Sonnet models accept `temperature`; restore it in the YAML if you ever pin one of those.
- **Sonnet 5 runs adaptive thinking by default when `thinking` is omitted** (unlike 4.6, where omitted meant off).
  `app/prompt.yaml` therefore sets `thinking: {type: disabled}` explicitly; dropping that line silently turns
  thinking on and eats the `max_tokens` budget. Sonnet 5 also uses a new tokenizer (~30% more tokens for the same
  text than 4.6) — don't reuse token counts or cost baselines measured on 4.6.
- **`model.effort` is plumbed but a no-op with thinking disabled.** The 2026-07 sweep (low/medium/high, 21 cases)
  showed identical latency and cost across levels with `thinking: disabled` — effort mostly modulates thinking
  depth, so there's nothing to modulate. Production leaves it unset (API default `high`). It becomes meaningful
  on the `useThinking` path or if adaptive thinking is ever made the default.
- **Reviewer thinking is on by default.** `prompt-test run --review` and `prompt-test review` default to
  `--reviewer-thinking adaptive` / `--thinking adaptive`. It catches factual errors the no-think reviewer misses
  but adds ~70% to review cost. Pass `off` to compare runs or save money on large batches.
- **Production explainer thinking is opt-in per request.** On Sonnet 5 the 2026-07 eval showed adaptive thinking
  bought no accuracy on our test set (15/21 vs 17/21 reviewer-correct) while adding output tokens; thinking-off is
  the default. Latency risk is the enduring reason: thinking can push large queries past the **30s Lambda + API
  Gateway v2 timeout** (no raising that — HTTP API has a 30s ceiling). Callers opt in by sending
  `useThinking: true` on the request; the default (no field, or `false`) preserves current latency. Cache keys split on the flag, so on/off requests
  cache independently. If we ever want default-on, we need either a smaller fixed thinking budget *or* an async
  response architecture (Lambda Function URL with response streaming, SQS poll, etc.).
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
