# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A FastAPI service that provides AI-powered explanations of compiler assembly output for the Compiler Explorer
website, using Anthropic's Claude API. Runs locally for development or as an AWS Lambda function (Mangum adapter)
behind an API Gateway HTTP API. The production explainer model is Sonnet 5.5 (see `app/prompt.yaml`); the
prompt-testing framework's correctness reviewer is Opus 5.

Request pipeline: input validation, then smart assembly filtering plus hard character caps, then the Claude API
call, then a response with usage/cost metrics. See `claude_explain.md` for detailed architecture documentation.

There is a prompt-testing framework (`prompt_testing/`, CLI `prompt-test`) for evaluating prompt and model
changes against curated test cases, with an Opus-based correctness review. Use it before changing
`app/prompt.yaml`: run the suite with `--review` before and after, and compare accuracy, latency, and tokens.
The original cases are near ceiling for Sonnet 5.5; the 32 `hard_*` cases are where models and prompts separate, and
reviewer noise is about +/-5 points, so pool configs and run 3+ times before trusting a small gap
(see `prompt_testing/README.md`). Fixture `labelDefinitions` must be Compiler Explorer's map (label to 1-based line
of its definition); `prompt_testing/test_fixtures.py` enforces it.

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
- **Neither production model accepts `temperature`.** Opus 5 (reviewer) and Sonnet 5.5 (explainer) reject
  non-default sampling parameters with a 400, so neither sets one. Only pre-5 Sonnet models accept
  `temperature`; restore it in the YAML if you ever pin one of those. anthropic SDK 1.x has no `temperature`
  kwarg, so `build_api_payload` sends a configured one via `extra_body`.
- **Sonnet 5.5 runs adaptive thinking by default when `thinking` is omitted, and 400s on `disabled`.**
  `app/prompt.yaml` therefore sets `thinking: {type: between_tools}`, the lowest setting (no thinking when no
  tools are sent; only valid at effort `high` or below). Dropping that line silently turns thinking on and eats
  the `max_tokens` budget. Sonnet 5 and Opus 5 still take `disabled`; the reviewer (Opus 5) always sends an
  explicit thinking config so `--reviewer-thinking off` really means off.
- **Sonnet 5/5.5's tokenizer produces ~30% more tokens than 4.6 for the same text.** Don't reuse token counts or
  cost baselines measured on 4.6-era models.
- **`model.effort` is plumbed but a no-op with thinking disabled.** The 2026-07 sweep (low/medium/high, 21
  cases) showed identical latency and cost across levels with thinking off, and the 2026-09 Sonnet 5.5 eval
  found medium and high indistinguishable under `between_tools`: effort mostly modulates thinking
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
- **Haiku 5.5, Opus 5.5, Fable 5.1: evaluated 2026-10-10, Sonnet 5.5 stays.** Production prompt, 21 cases,
  Opus 5 adaptive reviewer, assembly cases only, 3 runs per config unless noted. Sonnet 5.5: 43/48 correct (3
  were reviewer failures, not wrong answers), 2 errors, mean 5.2s, p95 9.4s, $0.011/call.
  - *Haiku 5.5 with `thinking: disabled`* (accepted, unlike Sonnet 5.5): 36/48, 14 errors; mean 3.1s, p95 5.2s,
    $0.0005/call (20x cheaper). The errors are failures to trace: misreading control flow (a straight-line
    `.L4` called a loop), wrong register arithmetic, a hallucinated `imul eax, edi, edi`, "-O0 doesn't
    constant-fold". It also missed a `je` targeting its own fall-through in about 5 of 12 samples; Sonnet,
    Opus 5.5 and Fable 5.1 caught it every time.
  - *Haiku 5.5 adaptive (the API default)*: 41/48, 8 errors, but no faster than Sonnet (mean 5.0s at low,
    5.8s at medium, max 17-18s). At `high` effort thinking exhausted `max_tokens=4096` and returned an empty
    response on `loop_experienced_assembly` in 2 of 3 runs.
  - *Opus 5.5* (thinking cannot be disabled): low 16/16, medium 30/31 reviewed, which is within noise of
    Sonnet, at 2-2.5x the cost and 6.6s / 9.6s mean. *Fable 5.1*: 15/16 at $0.059/call, with a 37s max that
    breaks the 30s ceiling.
- **Hard-corpus follow-up, 2026-10-11: Sonnet 5.5 with the bullet-cap prompt stays.** Scored on the 31 reviewable
  `hard_*` cases (Opus 5 adaptive reviewer; it safety-refuses the 32nd, `hard_wasm_sum_loop`). Reviews dominate
  cost at about $2 per 31-case run; the full 53-case suite is about $3 on Sonnet and $7.6 on Fable. Treat gaps
  under ~8 points as noise: configs differing only in input compaction, which should not matter, scored 81% vs
  90% and 85% vs 94%.
  - *Sonnet 5.5*: 159/186 (85%) pooled over the pre-cap prompt and compaction variants, 116/124 (94%) for the
    exact merged prompt; mean 7.2s, p95 9.4s, max 9.9s, $0.017/call.
  - *Opus 5.5 low* is the only plausible upgrade: 346/372 (93%) pooled over 12 runs, mean 10.7s, p95 14.9s,
    $0.032/call (2x). Not adopted: at most a few points better, about 3s slower, and one call in 512 took 33s for
    only 747 output tokens (slow API response or SDK retry, not length), past the 30s ceiling. Its errors differ
    in kind: confident hypotheticals about other flags (claiming `-march=rv64gc_zbb` turns a shift-and-mask
    popcount loop into `cpop`, which GCC's popcount recognition does not do) versus Sonnet's arithmetic and fact
    slips (calling `0x92492493` the magic number for ⌈2³⁵/7⌉ instead of ⌈2³⁴/7⌉).
  - *Fable 5.1* on the merged prompt, full suite, one run: 45/47 correct (29/31 on hard cases, the same rate as
    Sonnet), but mean 17.4s, p95 32.6s, max 39.3s, 5 of 53 calls over 30s, $0.098/call. Adaptive thinking adds
    1,700-2,800 output tokens per call; unusable under the 30s ceiling.
  - *Others*: Haiku 5.5 without thinking 87/124 (70%); Opus 5 without thinking 50/62 (81%) and slow (max 25.9s);
    Sonnet 5.5 with adaptive thinking at low or medium effort 112/124 (90%) at no latency cost, which is not
    significantly better than the 85% baseline, so unproven.
  - *No effect, don't retry without new evidence*: dropping the "compare with what other optimisation levels or
    architectures might produce" focus bullet (Sonnet 27/31 vs 116/124 control, Opus 30/31 vs 57/62; opposite
    directions, and speculation about other flags persisted); a mechanically computed control-flow digest
    (natural loops from dominators, handed over as ground truth for "is this a loop" and "does this jump target
    the next instruction"), Sonnet 85% vs 85%, Opus 93% vs 91%; and compacting the assembly JSON, which cuts input
    tokens but changed neither accuracy nor latency. The digest and compaction code was not merged.
  - *Fast mode* (`speed: "fast"` with beta `fast-mode-2026-02-01`; Opus 5.5, 5 and 4.8 only; $8/$40 per MTok;
    up to 2.5x output tokens/s) returns a 429 for this org (limit 0), so access would have to be requested. It
    was judged too expensive anyway.
- **Prompt caching: evaluated 2026-07 and rejected at current traffic.** ~104 fresh Claude calls/day
  (CloudWatch, 14-day window), only ~35 hours/fortnight above 12 calls/hour, against a 5-minute cache TTL and a
  prefix fragmented by language/arch/audience/type. Generous math: ~$0.40 saved per fortnight of ~$22 spend.
  (That analysis also counted restructuring to clear Sonnet 5's 1024-token minimum; Sonnet 5.5's is 512, which
  the ~620-token system prompt already clears, but the savings math still doesn't pay.) Revisit if traffic grows
  ~50x, or if sustained >3 same-combo requests/hour makes the 1-hour TTL viable. Rerun the analysis with
  `aws cloudwatch get-metric-statistics` on `CompilerExplorer/ClaudeExplainFreshResponse`.
- **Safety refusals are handled before the empty-response path.** Claude 5-family classifiers can decline a
  request (HTTP 200 with `stop_reason: "refusal"`, empty or partial content), plausible here since CE users
  compile arbitrary, sometimes exploit-adjacent code. Sonnet 5.5 declines in more categories than Sonnet 5
  (adds `bio`, `reasoning_extraction`, `general_harms`); watch the metric after model bumps. `app/explain.py` returns a distinct user-facing message,
  discards any partial output, and emits `ClaudeExplainRefusal`.
- **A spent workspace limit is a 400, not a 429.** Anthropic returns `invalid_request_error` ("You have reached
  your specified workspace API usage limits...") until the limit resets or is raised in the Console (a
  per-workspace limit, separate from the org one). `app/explain.py` matches the message and emits
  `ClaudeExplainUsageLimit`; any other unhandled API error emits `ClaudeExplainApiError` before re-raising.
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
- **Latency is output length.** A Sonnet 5.5 call takes about 0.4s plus 7.7ms per output token (~130 tok/s), so
  shorter answers are the main speed lever; input size barely matters (cutting input tokens 35% did not move
  latency). The old "under roughly 250 words" limit was ignored (mean 423 words on the hard corpus). A
  sentence/bullet cap ("at most 6 bullets or short paragraphs, none longer than two sentences, no headings") cut
  mean latency 8.2s to 6.5s (p95 12.2s to 9.0s, max 17.7s to 9.9s) with no detectable change in accuracy (87.8%
  vs 88.3% correct over 188 reviews each, across both corpora). Anthropic's latency guide says the same: word
  limits work worse than sentence or paragraph limits.

## Code Style Guidelines

- Modern Python 3.13+ type syntax: `a: list[str] | None`, not `Optional[List[str]]`
- ruff for linting and formatting, line length 120
- Prefer `pathlib.Path` over naked `open`/`glob`; always supply an encoding
- Import at the top of the file only
- Strive for simplicity and clarity; avoid unnecessary complexity
- Don't assume backwards compatibility is required unless explicitly stated; ask if unsure
