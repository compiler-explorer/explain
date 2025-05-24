import logging

from anthropic import Anthropic

from app.explain_api import CostBreakdown, ExplainRequest, ExplainResponse, TokenUsage
from app.metrics import MetricsProvider
from app.model_costs import get_model_cost
from app.prompt import Prompt

# Configure logging
LOGGER = logging.getLogger("explain")


# Constants
MAX_CODE_LENGTH = 10000  # 10K chars should be enough for most source files
MAX_ASM_LENGTH = 20000  # 20K chars for assembly output


def process_request(
    body: ExplainRequest,
    client: Anthropic,
    prompt: Prompt,
    metrics_provider: MetricsProvider,
) -> ExplainResponse:
    """Process a request and return the response.

    This is the core processing logic, separated from the lambda_handler
    to allow for reuse in the local server mode.

    Args:
        body: The request body as a Pydantic model
        client: Anthropic client instance
        prompt: Prompt instance for generating messages
        metrics_provider: metrics provider for tracking stats

    Returns:
        An ExplainResponse Pydantic model
    """
    # Generate messages using the Prompt instance
    prompt_data = prompt.generate_messages(body)

    # Call Claude API
    LOGGER.info(f"Using Anthropic client with model: {prompt_data['model']}")

    message = client.messages.create(
        model=prompt_data["model"],
        max_tokens=prompt_data["max_tokens"],
        temperature=prompt_data["temperature"],
        system=prompt_data["system"],
        messages=prompt_data["messages"],
    )

    # Get explanation and strip leading/trailing whitespace
    explanation = message.content[0].text.strip()

    # Extract usage information
    input_tokens = message.usage.input_tokens
    output_tokens = message.usage.output_tokens
    total_tokens = input_tokens + output_tokens

    # Calculate costs based on model
    cost_per_input_token, cost_per_output_token = get_model_cost(prompt_data["model"])
    input_cost = input_tokens * cost_per_input_token
    output_cost = output_tokens * cost_per_output_token
    total_cost = input_cost + output_cost

    # Add metrics with properties/dimensions
    metrics_provider.set_property("language", body.language)
    metrics_provider.set_property("compiler", body.compiler)
    metrics_provider.set_property("instructionSet", body.instructionSet or "unknown")
    metrics_provider.put_metric("ClaudeExplainRequest", 1)

    # Track token usage
    metrics_provider.put_metric("ClaudeExplainInputTokens", input_tokens)
    metrics_provider.put_metric("ClaudeExplainOutputTokens", output_tokens)
    metrics_provider.put_metric("ClaudeExplainCost", total_cost)

    # Create and return ExplainResponse object
    return ExplainResponse(
        status="success",
        explanation=explanation,
        model=prompt_data["model"],
        usage=TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        ),
        cost=CostBreakdown(
            input_cost=round(input_cost, 6),
            output_cost=round(output_cost, 6),
            total_cost=round(total_cost, 6),
        ),
    )
