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

# Use Claude-based AI scoring instead of regex patterns
uv run prompt-test run --prompt current --scorer claude

# Use hybrid scoring (20% of cases evaluated by Claude)
uv run prompt-test run --prompt current --scorer hybrid --claude-sample-rate 0.2

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

The framework supports three scoring methods:

### 1. Automatic Scoring (Default)

Fast regex-based pattern matching that scores responses on:

- **Accuracy** (0-1): How well it covers expected topics using keyword patterns
- **Technical Accuracy** (0-1): Absence of known inaccuracy patterns
- **Clarity** (0-1): Heuristic-based readability analysis
- **Completeness** (0-1): Coverage of expected topics
- **Length Appropriateness** (0-1): Not too verbose or brief
- **Overall Score**: Weighted combination of above metrics

### 2. Claude-Based AI Scoring

Uses advanced Claude models to provide nuanced evaluation:

- **Technical Accuracy**: Deep understanding of assembly correctness
- **Educational Value**: Assessment of teaching effectiveness
- **Clarity & Structure**: Analysis of explanation organization
- **Completeness**: Context-aware coverage evaluation
- **Practical Insights**: Value for real-world development

Benefits over automatic scoring:
- Understands context and relationships between concepts
- Catches subtle technical errors regex patterns miss
- Evaluates pedagogical effectiveness
- Provides detailed feedback on strengths/weaknesses

### 3. Hybrid Scoring

Combines both methods for efficiency:
- Uses automatic scoring for most cases
- Samples a configurable percentage with Claude
- Provides statistical validation of automatic scores
- Balances cost/speed with accuracy

### Scoring Method Selection

```bash
# Use automatic scoring (fastest, default)
uv run prompt-test run --prompt current --scorer automatic

# Use Claude scoring (most accurate, slower)
uv run prompt-test run --prompt current --scorer claude

# Use hybrid (20% Claude sampling)
uv run prompt-test run --prompt current --scorer hybrid --claude-sample-rate 0.2

# Use different Claude model for review
uv run prompt-test run --prompt current --scorer claude --reviewer-model claude-3-opus-20240229
```

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

## Constitutional AI Approach

The Claude-based scoring implements a "constitutional AI" approach where:

1. **Fast Model Generates**: Claude Haiku or Sonnet generates explanations quickly
2. **Advanced Model Reviews**: Claude Opus or Sonnet reviews the outputs with deep thinking
3. **Feedback Loop**: Review scores guide prompt improvements
4. **Self-Improving**: The system learns what makes good explanations

This approach enables:
- **Scalable Quality**: Fast generation with quality assurance
- **Objective Metrics**: AI-based evaluation reduces human bias
- **Continuous Improvement**: Data-driven prompt optimization
- **Cost Efficiency**: Only use expensive models for evaluation

### Customizing Review Criteria

You can customize how Claude evaluates responses by editing `evaluation/review_templates.yaml`:

```yaml
custom_review:
  system_prompt: "Your custom reviewer instructions..."
  evaluation_dimensions:
    your_dimension:
      weight: 0.30
      description: "What to evaluate..."
```

This allows domain-specific evaluation criteria without code changes.
