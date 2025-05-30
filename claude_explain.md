# Claude Explain Service Design Document

## Overview

The Claude Explain service provides AI-powered explanations of compiler output for Compiler Explorer users. The service receives compiled code and its resulting assembly, then uses Claude 3.5 Haiku to generate explanations that help users understand the relationship between their source code and the generated assembly.

## Architecture

### Service Design

The service is built with **FastAPI** and can run in two modes:
- **Development**: Standalone FastAPI server for local testing
- **Production**: AWS Lambda function via Mangum adapter

This dual-mode design provides excellent developer experience while maintaining serverless scalability for production.

### Core Components

1. **API Layer** (FastAPI)
   - Single POST endpoint at `/` for explanation requests
   - Pydantic models for request/response validation
   - CORS support for browser integration
   - Built-in OpenAPI documentation

2. **Processing Pipeline**
   - Input validation (size limits, required fields)
   - Smart assembly filtering for large outputs (>300 lines)
   - Structured JSON preparation for Claude
   - Cost and token tracking

3. **Claude Integration**
   - Uses Claude 3.5 Haiku model for improved accuracy
   - Structured JSON input preserving source-to-assembly mappings
   - Configurable audience levels and explanation types
   - Token usage and cost metrics

4. **Infrastructure** (when deployed to AWS)
   - Lambda function with Python 3.13 runtime
   - API Gateway for HTTP routing
   - CloudWatch for metrics and monitoring
   - Docker container for consistent deployment
   - S3 bucket for response caching

### Input/Output Contract

**Input**: JSON matching the Compiler Explorer compile API response format
- Source code, compiler details, compilation options
- Assembly output with source line mappings
- Label definitions for function boundaries

**Output**: JSON with explanation and metadata
- Generated explanation text
- Token usage statistics
- Cost breakdown
- Model information

## Prompt Testing Framework

A comprehensive prompt testing system has been developed to:

### Purpose
- Evaluate and improve prompt quality systematically
- Test different audiences (beginner/intermediate/expert) and explanation types
- Compare prompt versions and track improvements
- Ensure consistent quality across various code examples

### Architecture
- **Test Cases**: YAML-based test scenarios with expected topics
- **Prompts**: Versioned prompt templates with variable substitution
- **Scoring**: Multiple evaluation methods:
  - Automatic scoring based on heuristics
  - Claude-based evaluation for accuracy and clarity
  - Human review interface for manual assessment
- **Enrichment**: Integration with Compiler Explorer API to fetch real assembly data

### Integration
The prompt testing framework feeds back into the main service by:
- Validating prompt changes before deployment
- Identifying edge cases and improving coverage
- Providing data-driven prompt refinement
- Ensuring prompts work well across different compiler outputs

## Implementation Status

### ✅ Completed
- Core FastAPI service with all endpoints
- Claude 3.5 Haiku integration
- Smart assembly filtering for large inputs
- Comprehensive test suite
- Docker containerization
- Local development environment
- Cost and token tracking
- Prompt testing framework with CE API integration
- Pre-commit hooks and code quality tools
- AWS deployment (handled by Compiler Explorer infrastructure)
- S3 caching for responses with configurable TTL
- Cache bypass option for fresh responses

### 🔄 In Progress
- Production API key management
- Rate limiting implementation
- Compiler Explorer UI integration

### 📋 TODO
- Prompt caching for cost optimization
- Production monitoring dashboards
- User feedback collection mechanism

## Design Decisions

### Model Selection
**Claude 3.5 Haiku** was chosen for:
- Improved accuracy over earlier models
- Reduced hallucinations about technical details
- Cost-effective for high-volume usage
- Fast response times suitable for interactive use

### Assembly Processing
Smart filtering algorithm prioritizes:
- Function boundaries and entry points
- Instructions with source mappings
- Important control flow instructions
- Context around key operations

### Prompt Strategy
- Structured JSON input preserves rich metadata
- System prompt establishes expert compiler analyst role
- Explicit instructions to avoid speculation about hardware features
- Focus on educational value without patronizing explanations

## Security Considerations

### Input Validation
- Size limits prevent resource exhaustion
- JSON structure validation prevents parsing errors
- No execution of user code

### API Security
- API key stored securely (environment variable in dev, AWS Secrets Manager in prod)
- CORS configuration for authorized domains
- Rate limiting to prevent abuse

### Privacy
- Compiler Explorer will display consent before sending code to Anthropic
- Cached responses stored in S3 with configurable TTL (default 2 days)
- Cache can be bypassed with `bypass_cache` parameter
- Compliance with CE privacy policy

## Cost Management

### Current Pricing (Claude 3.5 Haiku)
- Input: $0.80 per million tokens
- Output: $4.00 per million tokens

### Optimization Strategies
- Smart assembly filtering reduces input tokens
- Response length limits (1024 tokens max)
- S3-based response caching reduces duplicate API calls
- Future: Prompt caching for system prompts

## Future Enhancements

### Near Term
1. **Enhanced Explanations**
   - Compiler warning integration
   - Optimization remarks from compiler
   - Diff explanations for multiple compiler outputs

2. **UI Integration**
   - "Explain" button in CE interface
   - Inline explanations in assembly view
   - User feedback collection
   - Cache status indicator

### Long Term
1. **Advanced Features**
   - Interactive Q&A about specific assembly sections
   - Explanation history and favorites
   - Community-contributed explanation improvements

2. **Model Improvements**
   - Fine-tuning for compiler-specific outputs
   - Support for more architectures and languages
   - Multi-model ensemble for complex cases

## Operational Considerations

### Monitoring
- Request volume and latency metrics
- Token usage and cost tracking
- Error rates and types
- Model performance metrics

### Scaling
- Lambda auto-scaling for traffic spikes
- Consider reserved concurrency for consistent performance
- Cache hit rate optimization

### Maintenance
- Regular prompt testing and refinement
- Model version updates
- Security patching
- Cost optimization reviews

## Development Workflow

### Local Development
```bash
# Install dependencies
uv sync --group dev

# Run local server
uv run fastapi dev

# Test the service
./test-explain.sh
```

### Testing
```bash
# Run tests
uv run pytest

# Run prompt testing
uv run prompt-test run --prompt current

# Enrich test cases with real CE data
uv run prompt-test enrich --input test_cases.yaml
```

## Key Learnings and Notes

### Prompt Engineering
- Explicit instructions about not speculating on hardware features are crucial
- Structured JSON input works better than flattened text
- Audience-specific prompts may need architectural decisions

### Model Observations
- Claude 3.5 Haiku shows significant improvement over earlier versions
- Still requires careful prompting to avoid confident mistakes
- Benefits from explicit examples in test cases

### Implementation Notes
- FastAPI + Mangum provides excellent flexibility
- Pydantic validation catches many issues early
- Comprehensive testing is essential for prompt quality

## Next Steps

1. **Production Configuration**
   - Set up production API key in AWS Secrets Manager
   - Configure rate limiting at API Gateway
   - Set up monitoring dashboards and alerts
   - Configure S3 bucket and IAM permissions for caching

2. **UI Integration**
   - Complete CE frontend integration
   - Implement user consent flow
   - Add "Explain" button to compiler output
   - Support markdown rendering for explanations

3. **Launch Preparation**
   - Load testing and capacity planning
   - Update CE privacy policy
   - User communication and documentation

---

*This document represents the current design and implementation status of the Claude Explain service. For implementation details, see the source code and API documentation.*
