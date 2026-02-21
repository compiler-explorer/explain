# Prompt Testing

Simple framework for testing prompt changes against curated test cases.

## Quick Start

```bash
# Run all test cases with the current production prompt
uv run prompt-test run

# Run with Opus correctness review (catches factual errors)
uv run prompt-test run --review

# Run specific cases or categories
uv run prompt-test run --cases basic_loop_001 --cases basic_inline_001
uv run prompt-test run --categories loop_optimization

# Review existing results with Opus
uv run prompt-test review results/20250221_120000_current.json

# Compare two result files
uv run prompt-test compare results_a.json results_b.json

# List available test cases
uv run prompt-test list
```

## How It Works

1. **Test cases** live in `test_cases/*.yaml` — each has source code, compiler flags, and real assembly output
2. `prompt-test run` sends each case to the Claude API using the current prompt and saves all outputs
3. `--review` flag runs each output through Opus for **correctness checking** — it identifies specific factual errors rather than giving abstract scores
4. You read the outputs (and any flagged issues) and decide if they're good
5. To compare prompt changes: run once before, once after, then `prompt-test compare`

### Correctness Review

The `--review` flag uses Claude Opus to check explanations for factual errors. Unlike generic scoring, it looks for specific issues:

- **Instruction semantics**: Is `lea` correctly described as address computation, not memory access?
- **Complexity claims**: Does it claim O(n) when it's actually O(2^n)?
- **Optimisation characterisation**: Does it correctly identify unoptimised code?
- **Register usage**: Are calling conventions right?

Each issue is flagged as an **error** (would mislead a student) or **warning** (imprecise but not wrong).

## Test Case Format

```yaml
cases:
  - id: unique_id
    category: loop_optimization
    description: "What this tests"
    audience: beginner          # or experienced
    explanation_type: assembly  # or haiku
    input:
      language: C++
      compiler: "x86-64 gcc 13.1"
      compilationOptions: ["-O2"]
      instructionSet: x86_64
      code: |
        int foo() { return 42; }
      asm:
        - text: "foo():"
        - text: "        mov     eax, 42"
          source: { line: 1 }
        - text: "        ret"
          source: { line: 1 }
```

## Enriching Test Cases

If you have test cases without assembly, the `enrich` command fetches real output from the Compiler Explorer API:

```bash
uv run prompt-test enrich -i test_cases/new_tests.yaml
```

## Directory Structure

```
prompt_testing/
├── test_cases/       # Curated test cases (YAML)
├── results/          # Saved test run outputs (JSON, gitignored)
├── ce_api/           # Compiler Explorer API client
├── runner.py         # Test runner
├── reviewer.py       # Opus correctness checker
├── cli.py            # CLI commands
├── enricher.py       # CE API enrichment
├── file_utils.py     # File I/O helpers
└── yaml_utils.py     # YAML helpers
```
