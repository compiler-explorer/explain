# Prompt Testing Framework

A comprehensive framework for testing and iterating on prompts for the Claude explain service.

## Overview

This framework allows you to:
- Test prompts against a curated set of assembly/source code examples
- Compare different prompt versions automatically
- Score responses using Claude's AI evaluation and human review
- Track performance over time and identify regressions

## Quick Start

```bash
# List available test cases and prompts
uv run prompt-test list

# Run all test cases with current prompt
uv run prompt-test run --prompt current

# Run specific category of tests
uv run prompt-test run --prompt current --categories basic_optimizations

# Compare two prompt versions
uv run prompt-test run --prompt current --compare v1_baseline

# Analyze all previous results
uv run prompt-test analyze

# Get AI-powered prompt improvement suggestions
uv run prompt-test improve --prompt current
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
│   └── v2_improved.yaml
│   # Note: 'current' prompt is loaded from app/prompt.yaml
├── results/              # Test results and analysis
│   └── [timestamp]_[prompt_version].json
└── evaluation/           # Scoring and review tools
    ├── scorer.py        # Test case loading utilities
    ├── claude_reviewer.py # Claude-based AI scoring
    ├── prompt_advisor.py # Prompt improvement suggestions
    ├── reviewer.py       # Human review tools
    └── review_templates.yaml # Customizable evaluation criteria
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

Prompts are defined in YAML files that must match the production schema. Here's the required structure:

```yaml
# Model configuration (required)
model:
  name: claude-3-5-haiku-20241022  # Model to use
  max_tokens: 1024                  # Maximum response tokens
  temperature: 0.0                  # Sampling temperature

# Audience levels (required)
audience_levels:
  beginner:
    description: "Novice programmers"
    guidance: "Use simple language, avoid jargon..."
  intermediate:
    description: "Experienced developers"
    guidance: "Assume familiarity with programming concepts..."
  expert:
    description: "Systems programmers"
    guidance: "Use technical terminology freely..."

# Explanation types (required)
explanation_types:
  assembly:
    description: "Focus on assembly instructions"
    focus_areas:
      - "Instruction-by-instruction breakdown"
      - "Register usage and memory access"
    user_prompt_phrase: "assembly output"
  optimization:
    description: "Focus on compiler optimizations"
    focus_areas:
      - "Optimization techniques applied"
      - "Performance implications"
    user_prompt_phrase: "compiler optimizations"

# Prompt templates (required)
system_prompt: |
  You are an expert in {arch} assembly code and {language}...

  Audience: {audience_description}
  {audience_guidance}

  Explanation Type: {explanation_type_description}
  Focus on: {explanation_type_focus}

user_prompt: "Explain the {arch} {explanation_type_phrase} for this {language} code."

assistant_prefill: "I'll analyze the {explanation_type_phrase} and explain it for {audience_level} level."
```

**Important**: Test prompts must include ALL these fields to work in production. The `current` special prompt loads from `app/prompt.yaml` which contains the complete structure.

## Evaluation Metrics

The framework uses Claude-based AI scoring to provide comprehensive evaluation of prompt responses.

### How Claude Scoring Works

Claude evaluates each response on five key dimensions, as defined in `review_templates.yaml`:

1. **Technical Accuracy** (30% weight):
   - Are assembly instructions correctly explained?
   - Are compiler optimizations accurately described?
   - Are technical claims verifiable and correct?
   - Does it avoid oversimplifications that lead to inaccuracy?
   - Are register names, instruction mnemonics, and calling conventions correct?

2. **Educational Value** (25% weight):
   - Is the explanation at an appropriate level for the target audience?
   - Does it build understanding progressively?
   - Are complex concepts explained clearly?
   - Does it provide insight into why the compiler made certain choices?
   - Would a reader gain actionable knowledge?

3. **Clarity & Structure** (20% weight):
   - Is the explanation well-organized and easy to follow?
   - Are technical terms properly introduced before use?
   - Is the language clear and concise?
   - Does it avoid unnecessary jargon while maintaining precision?
   - Is there a logical flow from simple to complex concepts?

4. **Completeness** (15% weight):
   - Does it address all significant transformations in the assembly?
   - Are important optimizations explained?
   - Does it cover the key differences between source and assembly?
   - Is the scope appropriate (not too narrow or too broad)?
   - Are edge cases or special behaviors noted where relevant?

5. **Practical Insights** (10% weight):
   - Does it help developers understand performance implications?
   - Are there actionable insights about writing better code?
   - Does it explain when/why certain optimizations occur?
   - Does it connect assembly behavior to source code patterns?

### Benefits of Claude Scoring

- **Context-Aware**: Understands relationships between concepts and code
- **Nuanced Evaluation**: Catches subtle technical errors that pattern matching would miss
- **Educational Assessment**: Evaluates pedagogical effectiveness, not just correctness
- **Detailed Feedback**: Provides specific strengths, weaknesses, and improvement suggestions
- **Consistent Standards**: Uses the same high-quality evaluation criteria for all test cases

### Configuring the Claude Reviewer

```bash
# Use the default Claude Sonnet model
uv run prompt-test run --prompt current

# Use a different Claude model for review
uv run prompt-test run --prompt current --reviewer-model claude-3-5-sonnet-20241022
```

## Example Output

### Test Run Output
```
Running 3 test cases with prompt version: current
  ✓ basic_loop_001: 0.85
  ✓ basic_inline_001: 0.92
  ✓ complex_vectorization_001: 0.78

Summary for current:
  Success rate: 100.0%
  Cases: 3/3
  Average score: 0.85
  Average accuracy: 0.87
  Average clarity: 0.83
  Average tokens: 420
  Average response time: 2845ms

Detailed results saved to: prompt_testing/results/20241201_120000_current.json
```

### Detailed Feedback Example
When examining the results file, Claude's evaluation includes:
- Missing topics: ["SIMD instruction specifics", "Memory alignment considerations"]
- Incorrect claims: ["The compiler always unrolls this loop"]
- Strengths: ["Clear explanation of function inlining", "Good use of beginner-friendly language"]
- Weaknesses: ["Could explain register allocation choices", "Missing performance implications"]
- Overall assessment: "Strong foundational explanation but lacks some advanced optimization details"

### Improvement Suggestions Output
```
=== PROMPT IMPROVEMENT SUGGESTIONS ===

Average Score: 0.87

🎯 Priority Improvements:
  Issue: Incorrect claims about optimization techniques
  Current: 'Be precise and accurate about CPU features...'
  Suggested: 'Be precise and accurate about all compiler optimizations...'
  Rationale: Expanded guidance prevents misidentifying optimizations

✨ Expected Impact: Score should improve from 0.87 to 0.90+
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
   cp app/prompt.yaml prompt_testing/prompts/v3_experiment.yaml
   # Edit the new prompt
   ```

2. Test the new prompt:
   ```bash
   uv run prompt-test run --prompt v3_experiment --compare current
   ```

3. Validate the new prompt structure:
   ```bash
   # Ensure the prompt loads correctly in production code
   uv run python -c "from app.prompt import Prompt; Prompt.from_yaml('prompt_testing/prompts/v3_experiment.yaml')"
   ```

4. If it performs better AND validates, publish to production:
   ```bash
   # Automated deployment with validation and safety checks
   uv run prompt-test publish --prompt v3_experiment --name "Production v4"

   # Manual deployment (alternative, but automated is recommended)
   # cp prompt_testing/prompts/v3_experiment.yaml app/prompt.yaml
   # uv run pytest app/test_explain.py::test_process_request_success
   ```

### Adding Test Cases

1. Add new cases to existing YAML files or create new category files
2. Include realistic assembly output (you can use Compiler Explorer to generate examples)
3. Specify expected topics that a good explanation should cover
4. Test your new cases to ensure they work as expected

### Prompt Improvement Workflow

1. Run tests with Claude scoring to get detailed feedback:
   ```bash
   uv run prompt-test run --prompt current --scorer claude
   ```

2. Analyze results and get improvement suggestions:
   ```bash
   uv run prompt-test improve --prompt current
   ```

3. Create an experimental improved version:
   ```bash
   uv run prompt-test improve --prompt current --create-improved --output current_v2
   ```

4. Test the improved version:
   ```bash
   uv run prompt-test run --prompt current_v2 --scorer claude --compare current
   ```

5. Review deployment criteria:
   - **Score improvement**: New prompt should score higher (e.g., 0.85+ average)
   - **No regressions**: No individual test case should drop significantly
   - **Cost efficiency**: Token usage should not increase dramatically
   - **Error-free**: All test cases should complete without errors

6. If ALL criteria are met, deploy to production:
   ```bash
   # Validate prompt structure
   uv run python -c "from app.prompt import Prompt; Prompt.from_yaml('prompt_testing/prompts/current_v2.yaml')"

   # Deploy (git tracks previous versions)
   cp prompt_testing/prompts/current_v2.yaml app/prompt.yaml

   # Test production integration
   uv run pytest app/test_explain.py
   ```

### Human Review Workflow

1. Run tests to generate results:
   ```bash
   uv run prompt-test run --prompt current --output my_test_results.json
   ```

2. Review results interactively via web interface:
   ```bash
   uv run prompt-test review --results-file prompt_testing/results/my_test_results.json
   ```

   **Features:**
   - Visual status indicators (✅ reviewed, ⚪ pending) with colored borders
   - Progress tracking with animated completion bar
   - Side-by-side source code and assembly display
   - Form pre-population with existing review data
   - Update functionality for modifying reviews
   - localStorage persistence for reviewer information
   - 1-5 scale metrics aligned with human evaluation standards
   - Line-separated input format for natural feedback entry

3. Analyze review data:
   ```bash
   uv run prompt-test analyze
   ```

### Production Deployment Workflow

Once you've tested and validated a prompt, publish it to production:

```bash
# Automated deployment with full validation and safety checks
uv run prompt-test publish --prompt v7 --name "Production v8"

# Or let it auto-generate a production name
uv run prompt-test publish --prompt v7
```

**The publish command automatically:**
- ✅ **Cleans metadata**: Removes experiment_metadata and cleans up names/descriptions
- ✅ **Validates structure**: Ensures prompt loads correctly in main service
- ✅ **Tests compatibility**: Verifies message generation works end-to-end
- ✅ **Creates backup**: Automatically backs up existing production prompt
- ✅ **Runs integration tests**: Executes full test suite to catch regressions
- ✅ **Provides guidance**: Clear next steps for local testing and committing

**Safety features:**
- Temp file handling with automatic cleanup on errors
- Error rollback if validation fails
- Comprehensive error reporting for debugging

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

### Error Handling

The framework uses **fail-fast error propagation**:
- No silent failures or fallbacks that hide issues
- Full stack traces for debugging
- Errors immediately bubble up rather than being caught and logged
- This ensures you always know when something goes wrong

Example: If Claude API fails during scoring, the entire test run stops with a clear error.

For more help, check the CLI help:
```bash
uv run prompt-test --help
uv run prompt-test run --help
```

## Constitutional AI Approach

The Claude-based scoring implements a "constitutional AI" approach where:

1. **Fast Model Generates**: Claude Haiku or Sonnet generates explanations quickly
2. **Advanced Model Reviews**: Claude Sonnet 4.0 (default) reviews outputs with deep analysis
3. **Feedback Loop**: Review scores guide prompt improvements
4. **Self-Improving**: The system learns what makes good explanations

This approach enables:
- **Scalable Quality**: Fast generation with quality assurance
- **Objective Metrics**: AI-based evaluation reduces human bias
- **Continuous Improvement**: Data-driven prompt optimization
- **Cost Efficiency**: Only use expensive models for evaluation

### Model Configuration

Default models:
- **Generation**: claude-3-5-haiku-20241022 (from main service)
- **Review**: claude-sonnet-4-0 (for evaluation)
- **Improvement**: claude-sonnet-4-0 (for suggestions)

You can override the review model:
```bash
uv run prompt-test run --prompt current --scorer claude --reviewer-model claude-3-opus-20240229
```

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
