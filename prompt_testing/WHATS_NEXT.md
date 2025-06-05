# What's Next - Prompt Testing Framework Improvements

## Overview

This document outlines the next steps for improving the prompt testing framework based on audit findings and recent development work.

## Recently Completed ✅

### Web Review Interface (Latest)
- **Fixed HTML review interface** - Replaced string concatenation with Flask + Jinja2
- **Added markdown rendering** - AI responses now display with proper formatting using client-side marked.js
- **Fixed template errors** - Resolved "dict has no attribute request" by enriching results with test case data
- **Improved result descriptions** - Clear labels like "Current Production Prompt - 12 cases" instead of "unknown"
- **Added CSS styling** - Proper code block, header, and list formatting
- **Interactive web server** - `uv run prompt-test review --interactive` launches Flask app on localhost:5001
- **COMPLETED: Quality of Life Improvements** ✅
  * Phase 1: localStorage reviewer persistence + 1-5 metrics scale alignment
  * Phase 2: Side-by-side source/assembly code display with responsive grid
  * Phase 3: Line-separated input format (more natural than comma-separated)
  * Phase 4: Review status indicators + progress tracking + update functionality
  * Professional review management system with visual status, form pre-population, and real-time updates

### Automated Prompt Publishing System (Latest)
- **✅ COMPLETED: Production deployment automation** - `uv run prompt-test publish --prompt <version>`
- **Metadata cleanup** - Automatically removes experiment_metadata and cleans names/descriptions for production
- **Built-in validation** - Ensures prompt loads correctly in main service and can generate messages
- **Safety features** - Automatic backup, temp file handling, error rollback, integration test execution
- **Professional workflow** - Clear next steps guidance and comprehensive error reporting

### Prompt Improvement System Audit & Fixes
- **Fixed critical "current" prompt loading bug** - PromptOptimizer now handles "current" → `app/prompt.yaml` mapping
- **Verified PromptAdvisor functionality** - Claude-based analysis with structured JSON suggestions working
- **Tested improvement workflow** - `uv run prompt-test improve --prompt current` now works correctly
- **Found existing analysis files** - Comprehensive suggestions in `/results/analysis_*` files with specific improvements

### Earlier Improvements
- Added support for calling CE REST API to fetch assembly output
- Test cases can now have empty `asm` blocks that get populated automatically
- Created `uv run prompt-test enrich` command to fetch real assembly data
- Support for different compiler versions and optimization flags
- Added error handling for JSON parsing in `claude_reviewer.py`
- Added tests for `scorer.py` (test case loading)
- Added S3-based caching for explanation responses
- Migrated to Claude-only scoring (removed AutomaticScorer and HybridScorer)

## Immediate Priority Actions

### 1. **Integrate Human Review Data into Improvement Workflow**
**Priority**: High - Critical gap in feedback loop

**Current State**:
- Web interface collects human reviews in JSONL format via ReviewManager
- PromptAdvisor only uses automated Claude reviewer metrics
- No integration between human feedback and improvement suggestions

**Actions Needed**:
1. Modify `PromptAdvisor.analyze_results_and_suggest_improvements()` to accept human review data
2. Add human review aggregation alongside automated metrics in analysis prompt
3. Update CLI improve command to load and pass human reviews to advisor
4. Create unified feedback format combining human + automated reviews

### 2. **Add File Selection Intelligence for Improve Command**
**Priority**: Medium - Usability improvement

**Current Issue**:
- `uv run prompt-test improve --prompt current` uses "most recent results" which could be comparison/analysis files
- No filtering by prompt version when multiple results exist

**Actions Needed**:
1. Add logic to skip analysis files (containing "analysis_" or "comparison_")
2. Filter results by prompt version to avoid cross-contamination
3. Prefer newer timestamp files when multiple valid options exist
4. Add `--results-file` flag for manual override when needed

### 3. **Add Iteration Tracking and Version History**
**Priority**: Medium - Proper development workflow

**Current Gap**: No tracking of prompt improvement lineage or performance over time

**Actions Needed**:
1. Add version history metadata to prompt YAML files
2. Track what each version builds on (parent version, improvements applied)
3. Performance tracking across iterations (score trends, regression detection)
4. Add `prompt-test history` command to show improvement lineage

## System Architecture Status

### ✅ Working Components:
- **Core testing infrastructure** - PromptTester, test case loading, Claude API integration
- **Claude-based evaluation** - ClaudeReviewer with structured feedback
- **Prompt improvement advisor** - PromptAdvisor with JSON-structured suggestions
- **Web review interface** - Flask app with markdown rendering and test case enrichment
- **Human review collection** - JSONL storage via ReviewManager
- **File utilities** - YAML handling, result storage, enrichment logic

### 🔧 Integration Gaps:
- **Human reviews → Automated improvements** - Reviews collected but not fed into PromptAdvisor
- **File selection logic** - Manual results file selection required
- **Version tracking** - No lineage or performance history
- **Cross-prompt contamination** - No filtering to avoid using wrong results files

## Discovered Analysis Files

Several comprehensive analysis files already exist with detailed improvement suggestions:

1. `/results/analysis_current_20250524_135349_current.json` - Production prompt analysis (0.67 avg score)
   - Focus on verification steps, pattern identification, missing topics coverage

2. `/results/analysis_v1_baseline_comparison_current_vs_v1_baseline.json` - Baseline comparison
   - Structured prompt improvements, prefill changes, user prompt restructuring

These contain actionable suggestions that could be applied to create improved prompt versions.

## Future Enhancements

### Performance & Scalability
1. Parallel evaluation for cost-effective Claude review
2. Add progress indicators for long-running operations
3. Cost tracking and budgeting features

### Integration & Automation
1. CI/CD pipeline integration for prompt regression testing
2. **✅ COMPLETED: Automated deployment with validation and rollback**
   - Added `uv run prompt-test publish --prompt <version>` command
   - Automatic metadata cleanup (removes experiment_metadata, cleans names/descriptions)
   - Built-in validation that prompt loads correctly in main service
   - Message generation testing to ensure compatibility
   - Automatic backup of existing production prompt
   - Integration test execution with clear pass/fail reporting
   - Safety features: temp file handling, error rollback, clear next steps
3. Performance monitoring and regression detection

## Technical Debt

### Code Quality
1. Add tests for `prompt_advisor.py` (requires mocking Claude API)
2. Add tests for web review interface components
3. Improve error handling in file selection logic
4. Add type hints for human review integration

## Next Session Recommendations

**For immediate continuation**:
1. **Human review integration** - Highest impact, completes feedback loop
2. **File selection intelligence** - Prevents workflow errors, improves usability
3. **Apply existing analysis suggestions** - Use discovered analysis files to create improved prompt versions
4. **Version tracking implementation** - Foundation for proper iterative development

**Key Files for Human Review Integration**:
- `prompt_testing/evaluation/prompt_advisor.py:25` - `analyze_results_and_suggest_improvements()`
- `prompt_testing/evaluation/reviewer.py` - ReviewManager and HumanReview classes
- `prompt_testing/cli.py` - improve command implementation

The human review integration is the critical missing piece that would create a complete feedback loop from web interface → analysis → improved prompts.
