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
uv run prompt-test run --prompt v1_baseline --compare current

# Analyze all previous results
uv run prompt-test analyze
```

## Directory Structure

```
prompt_testing/
├── test_cases/           # Test case definitions (JSON files)
│   ├── basic_optimizations.json
│   ├── complex_transformations.json
│   └── edge_cases.json
├── prompts/              # Prompt versions (text files)
│   ├── v1_baseline.txt
│   ├── current.txt
│   └── v2_improved.txt
├── results/              # Test results and analysis
│   └── [timestamp]_[prompt_version].json
└── evaluation/           # Scoring and review tools
    ├── scorer.py
    └── reviewer.py
```

## Test Case Format

Test cases are defined in JSON files with the following structure:

```json
{
  "description": "Test case category description",
  "cases": [
    {
      "id": "unique_case_id",
      "category": "optimization_type",
      "quality": "good_example|bad_example|challenging_example",
      "description": "Human readable description",
      "input": {
        "language": "C++",
        "compiler": "gcc 13.1",
        "compilationOptions": ["-O2"],
        "instructionSet": "x86_64",
        "code": "source code here",
        "asm": [
          {"text": "mov eax, edi", "address": 1, "source": {"line": 2}}
        ]
      },
      "expected_topics": ["vectorization", "loop_optimization"],
      "difficulty": "beginner|intermediate|advanced"
    }
  ]
}
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

### Human Review

Human reviewers can provide:
- Numerical scores (1-5 scale) for different dimensions
- Qualitative feedback (strengths, weaknesses, suggestions)
- Comparative preferences between prompt versions

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
   cp prompt_testing/prompts/current.txt prompt_testing/prompts/v3_experiment.txt
   # Edit the new prompt
   ```

2. Test the new prompt:
   ```bash
   uv run prompt-test run --prompt v3_experiment --compare current
   ```

3. If it performs better, update current:
   ```bash
   cp prompt_testing/prompts/v3_experiment.txt prompt_testing/prompts/current.txt
   ```

### Adding Test Cases

1. Add new cases to existing JSON files or create new category files
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

## Extending the Framework

### Adding New Evaluation Metrics

1. Extend `EvaluationMetrics` class in `evaluation/scorer.py`
2. Add scoring logic to `AutomaticScorer.evaluate_response()`
3. Update CLI to display new metrics

### Adding New Test Case Categories

1. Create new JSON file in `test_cases/`
2. Define category-specific expected topics in scorer
3. Add any category-specific evaluation logic

### Custom Scoring

You can create custom scoring functions:

```python
from prompt_testing.evaluation.scorer import AutomaticScorer

class CustomScorer(AutomaticScorer):
    def score_custom_metric(self, response: str) -> float:
        # Your custom scoring logic
        return score

scorer = CustomScorer()
metrics = scorer.evaluate_response(response, expected_topics, difficulty, token_count)
```

## Troubleshooting

### Common Issues

1. **API Key Issues**: Ensure `ANTHROPIC_API_KEY` environment variable is set
2. **Missing Test Cases**: Run `python -m prompt_testing.cli list` to see available cases
3. **Import Errors**: Make sure you're running from the project root directory
4. **Permission Errors**: Check that results directory is writable

### Performance Considerations

- **Rate Limits**: The framework respects Anthropic API rate limits
- **Parallel Testing**: Currently runs sequentially (could be parallelized)
- **Token Usage**: Monitor costs when running large test suites
- **Caching**: Consider adding response caching for repeated tests

For more help, check the example commands in the CLI help:
```bash
uv run prompt-test --help
uv run prompt-test run --help
```
