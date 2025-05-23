# Claude Explain Service

This is a FastAPI-based service that provides AI-powered explanations of compiler assembly output for the Compiler Explorer website. The service uses Anthropic's Claude API to analyze source code and its compiled assembly, providing educational explanations of compiler transformations and optimizations.

## Overview

The service is designed to run both locally for development and as an AWS Lambda function via Mangum adapter. It provides intelligent analysis of compiler output, helping users understand how their code translates to assembly language.

For detailed design documentation, see [claude_explain.md](claude_explain.md).

## Project Structure

See the source code for the current project structure. Key entry points:
- `app/main.py` - FastAPI application entry point
- `test-explain.sh` - Integration test script

## Setup

### Prerequisites

- Python 3.13+
- uv package manager

### Environment Configuration

Create a `.env` file (NOT in git) with your Anthropic API key:

```ini
ANTHROPIC_API_KEY=<your-key-here>
```

### Install Dependencies

```bash
uv sync --group dev
```

## Development

### Running Locally

```bash
# Start development server
uv run fastapi dev
```

The service will be available at http://localhost:8000

### Testing the Service

```bash
# Basic test
./test-explain.sh

# Pretty formatted output
./test-explain.sh --pretty
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test
uv run pytest app/explain_test.py::test_process_request_success
```

### Code Quality

```bash
# Run pre-commit hooks (ruff linting/formatting, shellcheck)
uv run pre-commit run --all-files

# Manual linting
uv run ruff check
uv run ruff format
```

## Key Features

### Key Features

- Smart assembly filtering for large compiler outputs
- AWS CloudWatch metrics integration when deployed
- Local development with `.env` file configuration

## API Usage

### Endpoint

`POST /` (root path)

### Request Format

```json
{
  "language": "c++",
  "compiler": "g112",
  "code": "int square(int x) { return x * x; }",
  "compilationOptions": ["-O2"],
  "instructionSet": "amd64",
  "asm": [
    {
      "text": "square(int):",
      "source": null,
      "labels": []
    },
    {
      "text": "        push    rbp",
      "source": {
        "line": 1,
        "column": 21
      },
      "labels": []
    }
  ]
}
```

### Response Format

```json
{
  "explanation": "The compiler generates efficient assembly...",
  "status": "success",
  "model": "claude-3-5-haiku-20241022",
  "usage": {
    "input_tokens": 123,
    "output_tokens": 456,
    "total_tokens": 579
  },
  "cost": {
    "input_cost": 0.000123,
    "output_cost": 0.000456,
    "total_cost": 0.000579
  }
}
```

## Configuration

See `app/explain.py` for current limits and model configuration. The service includes configurable limits for input size, assembly processing, and response length.

## Deployment

The service is designed for AWS Lambda deployment with API Gateway. See the Terraform configuration in the repository for infrastructure setup. The version of the service that runs in production is controlled by the terraform in our [infra](https://github.com/compiler-explorer/infra) repository.
