# TODO List from PR Review - Prompt Testing Framework

## Summary of Unresolved Comments

Based on the PR review, here are the unresolved items that need follow-up work:

### 1. **HTML Review Interface Implementation**
- **Location**: `prompt_testing/evaluation/reviewer.py` lines 72 & 180
- **Status**: Marked "For future discussion"
- **Issue**: Current implementation uses string concatenation for HTML generation
- **Suggestions**:
  - Consider using a proper HTML templating system like Pug/Jinja2
  - The current "fake" JavaScript alert in line 180 needs real implementation
  - Copilot also suggested using `textwrap.dedent()` for better formatting

### 2. **Automatic Scorer Refinement**
- **Location**: `prompt_testing/evaluation/scorer.py` line 37
- **Status**: Marked "For refinement in a follow up PR"
- **Issue**: The automatic scorer is "broad and unfocused"
- **Needs Discussion**:
  - Where the scoring ideas came from
  - How to make it more focused and effective
  - Better documentation of the scoring rationale

### 3. **README Update for Script Usage**
- **Location**: `prompt_testing/README.md`
- **Status**: "Partly done. Need to update the README here"
- **Issue**: Some examples still show `python` directly instead of `uv` script
- **Action**: Review and update all command examples to use `uv run`

## Resolved Items (For Reference)
- ✅ Test cases converted from JSON to YAML
- ✅ Prompts converted to YAML format with system/user/assistant sections
- ✅ Template variable expansion implemented
- ✅ Exception logging (marked as "ok" by Matt)

## Proposed Next Steps

### Phase 1: Documentation Cleanup
1. Review README for any remaining `python` direct calls
2. Ensure all examples use `uv run` consistently
3. Add more context about automatic scoring methodology

### Phase 2: HTML Review Interface
1. Research and choose HTML templating library (Jinja2, Pug, etc.)
2. Refactor `reviewer.py` to use proper templating
3. Implement actual form submission instead of fake alerts
4. Add tests for the review interface

### Phase 3: Scorer Refinement
1. Document the rationale behind current scoring metrics
2. Gather feedback on what metrics are most valuable
3. Consider making scoring more configurable/pluggable
4. Add ability to weight different metrics differently
5. Consider adding domain-specific scoring patterns

### Phase 4: Compiler Explorer API Integration
1. Add support for calling CE REST API to fetch assembly output
2. Allow test cases to have empty `asm` blocks that get populated automatically
3. Create command like `uv run prompt-test update-asm` to fetch missing assembly
4. Cache API responses to avoid repeated calls
5. Support different compiler versions and optimization flags
6. Handle API errors gracefully with retry logic

### Phase 5: Future Enhancements (Not from PR)
1. Add support for batch/parallel test execution
2. Add cost tracking and budgeting features
3. Create visualization/dashboards for results
4. Add integration with CI/CD pipelines

## Notes
- The Claude-based scoring system added after the initial review addresses some concerns about automatic scoring
- The error propagation changes ensure failures are visible immediately
- The prompt improvement advisor provides data-driven refinement capabilities
