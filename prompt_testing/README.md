# Prompt Testing

Simple framework for testing prompt changes against curated test cases.

## Quick Start

```bash
# Run all test cases with the current production prompt
uv run prompt-test run

# Run specific cases or categories
uv run prompt-test run --cases basic_loop_001 basic_inline_001
uv run prompt-test run --categories loop_optimization

# Compare two result files
uv run prompt-test compare results_a.json results_b.json

# List available test cases
uv run prompt-test list
```

## How It Works

1. **Test cases** live in `test_cases/*.yaml` — each has source code, compiler flags, and real assembly output
2. `prompt-test run` sends each case to the Claude API using the current prompt and saves all outputs
3. You read the outputs and decide if they're good
4. To compare prompt changes: run once before, once after, then `prompt-test compare`

No automated scoring, no Claude-as-judge, no web UI. The human is the judge.

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
├── cli.py            # CLI commands
├── enricher.py       # CE API enrichment
├── file_utils.py     # File I/O helpers
└── yaml_utils.py     # YAML helpers
```
