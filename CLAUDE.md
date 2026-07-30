# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A FastAPI service that provides AI-powered explanations of compiler assembly output for the Compiler Explorer
website, using Anthropic's Claude API. Runs locally for development or as an AWS Lambda function (Mangum adapter)
behind an API Gateway HTTP API. The production explainer model is Sonnet 5 (see `app/prompt.yaml`); the
prompt-testing framework's correctness reviewer is Opus 5.

Request pipeline: input validation, then smart assembly filtering plus hard character caps, then the Claude API
call, then a response with usage/cost metrics. See `claude_explain.md` for detailed architecture documentation.

There is a prompt-testing framework (`prompt_testing/`, CLI `prompt-test`) for evaluating prompt and model
changes against curated test cases, with an Opus-based correctness review. Use it before changing
`app/prompt.yaml`: run the suite with `--review` before and after, and compare accuracy, latency, and tokens.

## Development Commands

```bash
# Setup: .env file containing ANTHROPIC_API_KEY=<your-key-here>, then:
uv sync --group dev

# Run locally
uv run fastapi dev
./test-explain.sh            # exercise the local server (--pretty for readable output)

# Tests and linting
uv run pytest                # run all tests (matches CI)
uv run pytest app/test_explain.py::TestProcessRequest::test_process_request_success  # one test
uv run pre-commit run --all-files   # ruff lint/format, shellcheck etc (matches CI)

# Prompt evaluation
uv run prompt-test run --prompt current --review   # full suite + Opus correctness review
uv run prompt-test list                            # available test cases
```

**Always run `uv run pytest` and `uv run pre-commit run --all-files` before pushing.** CI runs exactly these.
Pre-commit hooks may modify files (e.g. ruff format); re-`git add` if a hook reports fixes.

## Anthropic API gotchas

- **`max_tokens` includes thinking tokens.** When thinking is enabled it counts against `max_tokens`, and can
  starve the visible text on complex cases. `Prompt.__init__` refuses to load a thinking-enabled config with
  `max_tokens < 4096` (production uses 4096).
- **Neither production model accepts `temperature`.** Opus 5 (reviewer) and Sonnet 5 (explainer) reject
  non-default sampling parameters with a 400, so neither sets one. Only pre-5 Sonnet models accept
  `temperature`; restore it in the YAML if you ever pin one of those.
- **Sonnet 5 runs adaptive thinking by default when `thinking` is omitted.** `app/prompt.yaml` therefore sets
  `thinking: {type: disabled}` explicitly; dropping that line silently turns thinking on and eats the
  `max_tokens` budget. The same trap applies to the reviewer, which always sends an explicit thinking config so
  `--reviewer-thinking off` really means off.
- **Sonnet 5's tokenizer produces ~30% more tokens than 4.6 for the same text.** Don't reuse token counts or
  cost baselines measured on 4.6-era models.
- **`model.effort` is plumbed but a no-op with thinking disabled.** The 2026-07 sweep (low/medium/high, 21
  cases) showed identical latency and cost across levels with thinking off: effort mostly modulates thinking
  depth, so there is nothing to modulate. Production leaves it unset (API default `high`). It becomes meaningful
  on the `useThinking` path or if adaptive thinking is ever made the default.
- **Production explainer thinking is opt-in per request** (`useThinking: true`; default off). The 2026-07 eval
  showed adaptive thinking bought no accuracy on our test set while adding output tokens, and thinking can push
  large queries past the **30s Lambda + API Gateway v2 timeout** (a hard ceiling; not raisable on HTTP APIs).
  Cache keys split on the flag. Default-on would need a smaller thinking budget or an async response
  architecture (Lambda response streaming, SQS poll, etc.).
- **Reviewer thinking is on by default** (`--reviewer-thinking adaptive`). It catches factual errors the
  no-think reviewer misses but adds ~70% to review cost; pass `off` for cheap comparative runs.
- **Cheaper/faster models: evaluated and rejected for the default path.** Haiku 4.5 was the original explainer,
  replaced for factual errors on complex optimisations (commit `d188a44`, 2025-12). A 2026-07 multi-model
  bake-off (gpt-oss-120b on Cerebras/Groq, gemini-3.5-flash, deepseek-v4-flash, via OpenRouter) found the only
  fast option 10x quicker but similarly error-prone; full data, a parked "fast draft tier" idea, and the privacy
  implications of any multi-provider routing are in issue #31. Don't propose down-tiering the default model
  without rerunning that eval.
- **Prompt caching: evaluated 2026-07 and rejected at current traffic.** ~104 fresh Claude calls/day
  (CloudWatch, 14-day window), only ~35 hours/fortnight above 12 calls/hour, against a 5-minute cache TTL and a
  prefix fragmented by language/arch/audience/type. Generous math: ~$0.40 saved per fortnight of ~$22 spend,
  before counting the restructuring needed to clear Sonnet 5's 1024-token minimum cacheable prefix (the system
  prompt is only ~620 tokens; the per-audience guidance lives in the user prompt). Revisit if traffic grows
  ~50x, or if sustained >3 same-combo requests/hour makes the 1-hour TTL viable. Rerun the analysis with
  `aws cloudwatch get-metric-statistics` on `CompilerExplorer/ClaudeExplainFreshResponse`.
- **Safety refusals are handled before the empty-response path.** Claude 5-family classifiers can decline a
  request (HTTP 200 with `stop_reason: "refusal"`, empty or partial content), plausible here since CE users
  compile arbitrary, sometimes exploit-adjacent code. `app/explain.py` returns a distinct user-facing message,
  discards any partial output, and emits `ClaudeExplainRefusal`.
- **Multi-block responses.** With thinking enabled the API returns thinking blocks before the text block; both
  `app/explain.py` and `prompt_testing/runner.py` pick the last text block via
  `getattr(c, "type", None) == "text"`. Preserve that pattern in new response-consuming code. "No text block"
  can mean max_tokens starvation or a redacted-thinking-only response; the error message is the same.
- **Empty responses are not 500s.** When the model returns no text block, `app/explain.py` returns
  `ExplainResponse(status="error")` with usage populated and emits `ClaudeExplainEmptyResponse`. The cache layer
  skips storing error responses so retries hit the API. Don't change this to raise; the structured error is what
  the CE frontend can render.
- **`build_api_payload` is the single source of truth for API kwargs.** Production (`app/explain.py`) and the
  prompt-test runner both call it; don't reconstruct thinking/temperature/output_config logic elsewhere.

## Code Style Guidelines

- Modern Python 3.13+ type syntax: `a: list[str] | None`, not `Optional[List[str]]`
- ruff for linting and formatting, line length 120
- Prefer `pathlib.Path` over naked `open`/`glob`; always supply an encoding
- Import at the top of the file only
- Strive for simplicity and clarity; avoid unnecessary complexity
- Don't assume backwards compatibility is required unless explicitly stated; ask if unsure
