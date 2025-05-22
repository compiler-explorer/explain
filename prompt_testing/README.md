# Prompt Testing Framework

A comprehensive framework for testing and iterating on prompts for the Claude explain service.

## Overview

This framework allows you to:
- Test prompts against a curated set of assembly/source code examples
- Compare different prompt versions automatically
- Score responses using both automatic metrics and human review
- Track performance over time and identify regressions

## Quick Start

```bash
# List available test cases and prompts
uv run prompt-test list

# Run current prompt against basic optimization cases
uv run prompt-test run --prompt current --categories basic_optimizations

# Compare two prompt versions
uv run prompt-test run --prompt current --compare v1_baseline

# Analyze all previous results
uv run prompt-test analyze
```

## Directory Structure

```
prompt_testing/
├── test_cases/           # Test case definitions (YAML files)
│   ├── basic_optimizations.yaml
│   ├── complex_transformations.yaml
│   └── edge_cases.yaml
├── prompts/              # Prompt versions (YAML files)
│   ├── v1_baseline.yaml
│   ├── current.yaml
│   └── v2_improved.yaml
├── results/              # Test results and analysis
│   └── [timestamp]_[prompt_version].json
└── evaluation/           # Scoring and review tools
    ├── scorer.py
    └── reviewer.py
```

## Test Case Format

Test cases are defined in YAML files with the following structure:

```yaml
description: "Test case category description"

cases:
  - id: unique_case_id
    category: optimization_type
    quality: good_example  # good_example|bad_example|challenging_example
    description: "Human readable description"
    input:
      language: C++
      compiler: "gcc 13.1"
      compilationOptions: ["-O2"]
      instructionSet: x86_64
      code: |
        source code here
      asm:
        - text: "mov eax, edi"
          address: 1
          source:
            line: 2
    expected_topics: [vectorization, loop_optimization]
    difficulty: beginner  # beginner|intermediate|advanced
```

## Prompt Format

Prompts are defined in YAML files with separate system and user prompts:

```yaml
system_prompt: |
  You are an expert in {arch} assembly code and {language}, helping users of the
  Compiler Explorer website understand how their code compiles to assembly.

user_prompt: "Explain the {arch} assembly output."

assistant_prefill: "I have analysed the assembly code and my analysis is:"

model_config:
  model: claude-3-5-sonnet-20241022
  max_tokens: 4000
```

## Evaluation Metrics

### Automatic Scoring

The framework automatically scores responses on:

- **Accuracy** (0-1): How well it covers expected topics
- **Technical Accuracy** (0-1): Absence of technical inaccuracies
- **Clarity** (0-1): Readability and educational value
- **Completeness** (0-1): Covers all relevant aspects
- **Length Appropriateness** (0-1): Not too verbose or brief
- **Overall Score**: Weighted combination of above metrics

## Usage Examples

### Running Tests

```bash
# Test current prompt on all cases
uv run prompt-test run --prompt current

# Test specific cases
uv run prompt-test run --prompt current --cases basic_loop_001 edge_empty_001

# Test by category
uv run prompt-test run --prompt current --categories loop_optimization vectorization

# Compare two versions
uv run prompt-test run --prompt v1_baseline --compare current --categories basic_optimizations
```

### Managing Prompts

1. Create a new prompt version:
   ```bash
   cp prompt_testing/prompts/current.yaml prompt_testing/prompts/v3_experiment.yaml
   # Edit the new prompt
   ```

2. Test the new prompt:
   ```bash
   uv run prompt-test run --prompt v3_experiment --compare current
   ```

3. If it performs better, update current:
   ```bash
   cp prompt_testing/prompts/v3_experiment.yaml prompt_testing/prompts/current.yaml
   ```

### Adding Test Cases

1. Add new cases to existing YAML files or create new category files
2. Include realistic assembly output (you can use Compiler Explorer to generate examples)
3. Specify expected topics that a good explanation should cover
4. Test your new cases to ensure they work as expected

### Human Review Workflow

1. Run tests to generate results:
   ```bash
   uv run prompt-test run --prompt current --output my_test_results.json
   ```

2. Review results interactively:
   ```bash
   uv run prompt-test review --results-file prompt_testing/results/my_test_results.json
   ```

3. Analyze review data:
   ```bash
   uv run prompt-test analyze
   ```

## Best Practices

### Test Case Creation

- **Use real examples**: Generate assembly from actual code using Compiler Explorer
- **Cover edge cases**: Include empty functions, undefined behavior, truncated assembly
- **Vary difficulty**: Mix beginner, intermediate, and advanced examples
- **Quality labels**: Mark cases as good/bad examples to test robustness

### Prompt Development

- **Start small**: Test on a subset before running full suite
- **Iterate quickly**: Make small changes and measure impact
- **Use version control**: Keep track of what works and what doesn't
- **Document changes**: Note the reasoning behind prompt modifications

### Evaluation Strategy

- **Combine metrics**: Use both automatic and human evaluation
- **Regular testing**: Run tests after any prompt changes
- **Baseline comparison**: Always compare against previous best version
- **Long-term tracking**: Monitor performance trends over time

## Integration with Main Service

The testing framework uses the same core logic as the main explain service:
- Same request/response format (`ExplainRequest`/`ExplainResponse`)
- Same data preparation (`prepare_structured_data`)
- Same Claude API calls
- Same token counting and cost calculation

This ensures that test results accurately reflect production performance.

## Troubleshooting

### Common Issues

1. **API Key Issues**: Ensure `ANTHROPIC_API_KEY` environment variable is set
2. **Missing Test Cases**: Run `uv run prompt-test list` to see available cases
3. **Import Errors**: Make sure you're running from the project root directory
4. **Permission Errors**: Check that results directory is writable

### Performance Considerations

- **Rate Limits**: The framework respects Anthropic API rate limits
- **Parallel Testing**: Currently runs sequentially (could be parallelized)
- **Token Usage**: Monitor costs when running large test suites

For more help, check the CLI help:
```bash
uv run prompt-test --help
uv run prompt-test run --help
```
