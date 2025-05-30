import logging

from anthropic import Anthropic

from app.cache import CacheProvider, cache_response, get_cached_response
from app.explain_api import CostBreakdown, ExplainRequest, ExplainResponse, TokenUsage
from app.metrics import MetricsProvider
from app.model_costs import get_model_cost
from app.prompt import Prompt

# Configure logging
LOGGER = logging.getLogger("explain")


# Constants
MAX_CODE_LENGTH = 10000  # 10K chars should be enough for most source files
MAX_ASM_LENGTH = 20000  # 20K chars for assembly output


async def process_request(
    body: ExplainRequest,
    client: Anthropic,
    prompt: Prompt,
    metrics_provider: MetricsProvider,
    cache_provider: CacheProvider | None = None,
) -> ExplainResponse:
    """Process a request and return the response.

    This is the core processing logic, separated from the lambda_handler
    to allow for reuse in the local server mode.

    Args:
        body: The request body as a Pydantic model
        client: Anthropic client instance
        prompt: Prompt instance for generating messages
        metrics_provider: metrics provider for tracking stats
        cache_provider: cache provider for storing/retrieving responses

    Returns:
        An ExplainResponse Pydantic model
    """
    # Try to get cached response first (if cache provider is available)
    if cache_provider is not None:
        cached_response = await get_cached_response(body, prompt, cache_provider)
        if cached_response is not None:
            LOGGER.info("Returning cached response")
            metrics_provider.put_metric("ClaudeExplainCacheHit", 1)

            # Still track the request metrics for cached responses
            metrics_provider.set_property("language", body.language)
            metrics_provider.set_property("compiler", body.compiler)
            metrics_provider.set_property("instructionSet", body.instructionSet or "unknown")
            metrics_provider.set_property("cached", "true")
            metrics_provider.put_metric("ClaudeExplainRequest", 1)
            metrics_provider.put_metric("ClaudeExplainCachedResponse", 1)

            return cached_response

    # Cache miss or no cache - proceed with Anthropic API call
    response = await _call_anthropic_api(body, client, prompt, metrics_provider)

    # Cache the response (if cache provider is available)
    if cache_provider is not None:
        await cache_response(body, prompt, response, cache_provider)
        metrics_provider.put_metric("ClaudeExplainCacheMiss", 1)

    return response


async def _call_anthropic_api(
    body: ExplainRequest,
    client: Anthropic,
    prompt: Prompt,
    metrics_provider: MetricsProvider,
) -> ExplainResponse:
    """Make the actual call to Anthropic API and create response.

    This is the original process_request logic, extracted for clarity.
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
    metrics_provider.set_property("cached", "false")
    metrics_provider.put_metric("ClaudeExplainRequest", 1)
    metrics_provider.put_metric("ClaudeExplainFreshResponse", 1)

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
            inputTokens=input_tokens,
            outputTokens=output_tokens,
            totalTokens=total_tokens,
        ),
        cost=CostBreakdown(
            inputCost=round(input_cost, 6),
            outputCost=round(output_cost, 6),
            totalCost=round(total_cost, 6),
        ),
        cached=False,  # This is a fresh response from the API
    )
