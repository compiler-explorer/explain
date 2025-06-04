# What's Next - Prompt Testing Framework Improvements

## Overview

This document outlines the next steps for improving the prompt testing framework based on PR review feedback and recent development work.

## Recently Completed ✅

### Compiler Explorer API Integration
- Added support for calling CE REST API to fetch assembly output
- Test cases can now have empty `asm` blocks that get populated automatically
- Created `uv run prompt-test enrich` command to fetch real assembly data
- Support for different compiler versions and optimization flags
- Basic error handling for API failures
- Switched to ruamel.yaml for better YAML formatting preservation

### Code Quality Improvements (PR #2)
- Added error handling for JSON parsing in `claude_reviewer.py`
- Added tests for `scorer.py` (test case loading)
- Fixed test prompt formats (v1_baseline.yaml, v2_baseline.yaml)
- Added `prompt-test validate` command for prompt structure validation
- Extracted common file handling utilities to `file_utils.py`
- Refactored large functions in `cli.py` and `runner.py`
- Added tests for pure functions (12 new tests)

### Caching Implementation
- Added S3-based caching for explanation responses
- Cache key generation based on all response-affecting data including prompt content
- Configurable TTL and human-readable duration support
- Cost reduction for duplicate API requests

### Claude-Only Scoring Migration
- Removed AutomaticScorer and HybridScorer classes
- ClaudeReviewer is now the primary evaluation method
- Simplified CLI scoring options
- Improved evaluation quality at the cost of API usage

## Priority Improvements

### 1. **Prompt Structure Architecture Decision**
**Priority**: High - Blocks prompt improvement workflow

We need to decide on the fundamental architecture for how prompts handle audience levels and explanation types:

**Option A**: Separate system prompts for each combination
- Pro: More focused, specific instructions
- Con: More prompts to maintain

**Option B**: Single system prompt with user-specified parameters
- Pro: Easier to maintain and test
- Con: Less specialized instructions

**Decision needed**: This affects how the prompt advisor can feed improvements back into the system.

### 2. **Enhance Claude-Only Scoring**
**Priority**: Medium - Performance and usability improvement

Current state:
- Successfully transitioned to Claude-only scoring
- ClaudeReviewer is the primary evaluation method
- AutomaticScorer and HybridScorer have been removed

Remaining actions:
1. Add cost warnings and progress indicators for long evaluation runs
2. Consider adding parallel evaluation for performance
3. Add cost tracking and budgeting features
4. Document best practices for cost-effective evaluation

### 3. **HTML Review Interface**
**Priority**: Medium - Quality of life improvement

Current issues:
- Uses string concatenation for HTML generation
- "Fake" JavaScript alerts need real implementation

Actions needed:
1. Choose and implement proper HTML templating (Jinja2 recommended)
2. Replace string concatenation in `reviewer.py`
3. Implement real form submission handling
4. Add proper CSS styling
5. Add tests for the review interface

### 4. **Compiler Warning Integration**
**Priority**: Medium - Feature enhancement

Add support for compiler warnings in explanations:
1. Modify CE API client to capture warnings
2. Update test case format to include warnings
3. Enhance prompts to explain warnings when present
4. Add test cases specifically for warning scenarios

### 5. **Documentation Updates**
**Priority**: Low - Cleanup

- Update README to use `uv run` consistently
- Add more context about automatic scoring methodology
- Document the prompt testing workflow end-to-end

## Future Enhancements

### Performance & Scalability
1. Add caching for CE API responses (not yet implemented in prompt testing)
2. Implement retry logic with exponential backoff
3. Support batch/parallel test execution
4. Add progress indicators for long-running operations

### Analytics & Monitoring
1. Add cost tracking and budgeting features
2. Create visualization dashboards for results
3. Track prompt performance over time
4. Add regression detection

### Integration & Automation
1. CI/CD pipeline integration
2. Automated prompt regression testing
3. GitHub PR comments with test results
4. Slack/Discord notifications for failures
5. **Add `prompt-test deploy` command** - Automate the deployment process with validation, backup, and rollback capabilities

## Technical Debt

### Code Quality
1. Add more comprehensive error handling
2. Improve test coverage (target 90%+)
   - `runner.py` needs tests (requires mocking Claude API)
   - `cli.py` command functions need tests (requires mocking)
   - `prompt_advisor.py` needs tests (requires mocking)
3. Add type hints throughout
4. Standardize logging approach
5. Break down remaining large functions

### Architecture
1. ~~Consider abstracting scorer interface~~ (Simplified to Claude-only scoring)
2. Make reviewer interface pluggable
3. Add plugin system for custom evaluators

## Questions for Discussion

1. Should we support multiple LLM providers beyond Anthropic?
2. How should we handle rate limiting for the CE API?
3. What's the best way to version prompts?
4. Should test cases be in a separate repository?

## Next Session Recommendations

Based on priority and dependencies, I recommend tackling in this order:
1. Make the prompt structure architecture decision
2. Add compiler warning support
3. Improve the HTML review interface with proper templating
4. Add cost tracking and progress indicators for Claude evaluation
