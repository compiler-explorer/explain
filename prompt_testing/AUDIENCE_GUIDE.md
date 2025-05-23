# Audience and Explanation Type Support in Prompt Testing

This guide describes the new audience and explanation type capabilities added to the prompt testing framework.

## Overview

The prompt testing system now supports testing prompts across different audiences and explanation types, matching the new capabilities added to the main explain API.

### Audience Levels
- **beginner**: Simple language, technical terms defined, step-by-step explanations
- **intermediate**: Assumes basic assembly knowledge, focuses on compiler behavior
- **expert**: Technical terminology, advanced optimizations, architectural details

### Explanation Types
- **assembly**: Focus on assembly instructions and their purpose
- **source**: Focus on source code to assembly mapping
- **optimization**: Focus on compiler optimizations and transformations

## Test Case Format

Test cases can now specify audience and explanation type:

```yaml
cases:
  - id: example_beginner_assembly
    audience: beginner           # Optional, defaults to "beginner"
    explanation_type: assembly   # Optional, defaults to "assembly"
    expected_topics_by_audience: # Optional audience-specific expectations
      beginner: [basic_concepts, simple_terms]
      intermediate: [compiler_behavior, register_usage]
      expert: [microarchitecture, advanced_optimizations]
    # ... rest of test case
```

## Running Tests

### Filter by audience:
```bash
uv run prompt-test run --prompt current --audience beginner
```

### Filter by explanation type:
```bash
uv run prompt-test run --prompt current --explanation-type optimization
```

### Combine filters:
```bash
uv run prompt-test run --prompt current --audience expert --explanation-type optimization
```

## Scoring Adjustments

The automatic scorer now adjusts expectations based on audience:

1. **Clarity scoring**:
   - Beginners: Shorter sentences, fewer technical terms, more explanatory language
   - Experts: Can handle longer sentences and more technical terminology

2. **Length scoring**:
   - Different target lengths for each audience
   - Adjusted by explanation type (source mapping needs more space)

3. **Topic coverage**:
   - Uses audience-specific expected topics when available

## Prompt Templates

The prompt templates now include audience and explanation variables:

```yaml
system_prompt: |
  You are an expert in {arch} assembly code and {language}...

  Target audience: {audience}
  {audience_guidance}

  Explanation type: {explanation_type}
  {explanation_focus}

  # ... rest of prompt

user_prompt: "Explain the {arch} {explanation_type_phrase}."
```

## Migration Notes

- Existing test cases without audience/explanation fields default to "beginner" and "assembly"
- The v1_baseline.yaml prompt remains unchanged for comparison purposes
- All changes are backward compatible

## Example Test Cases

See `test_cases/audience_variations.yaml` for examples demonstrating different audience and explanation type combinations.
