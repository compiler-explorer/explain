import logging
from typing import Any

from anthropic import AsyncAnthropic

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
    client: AsyncAnthropic,
    prompt: Prompt,
    metrics_provider: MetricsProvider,
    cache_provider: CacheProvider | None = None,
) -> ExplainResponse:
    """Process a request and return the response.

    This is the core processing logic, separated from the lambda_handler
    to allow for reuse in the local server mode.

    Args:
        body: The request body as a Pydantic model
        client: AsyncAnthropic client instance
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
            metrics_provider.set_property("instructionSet", body.instruction_set_with_default)
            metrics_provider.set_property("cached", "true")
            metrics_provider.put_metric("ClaudeExplainRequest", 1)
            metrics_provider.put_metric("ClaudeExplainCachedResponse", 1)

            return cached_response

    # Cache miss or no cache - proceed with Anthropic API call
    response = await _call_anthropic_api(body, client, prompt, metrics_provider)

    # Cache the response (if cache provider is available). Don't cache
    # error responses — they consume real tokens but produce no useful
    # content, and we want a retry to hit the API rather than the cache.
    if cache_provider is not None and response.status == "success":
        await cache_response(body, prompt, response, cache_provider)
        metrics_provider.put_metric("ClaudeExplainCacheMiss", 1)

    return response


async def _call_anthropic_api(
    body: ExplainRequest,
    client: AsyncAnthropic,
    prompt: Prompt,
    metrics_provider: MetricsProvider,
) -> ExplainResponse:
    """Make the actual call to Anthropic API and create response.

    This is the original process_request logic, extracted for clarity.
    """
    # Generate messages using the Prompt instance
    prompt_data = prompt.generate_messages(body)

    # Debug logging for prompts
    LOGGER.debug(f"=== PROMPT DEBUG FOR {body.explanation.value.upper()} (audience: {body.audience.value}) ===")
    LOGGER.debug("=== SYSTEM PROMPT ===")
    LOGGER.debug(prompt_data["system"])
    LOGGER.debug("=== MESSAGES ===")
    for message in prompt_data["messages"]:
        LOGGER.debug(message)
    LOGGER.debug("=== END PROMPT DEBUG ===")

    # Call Claude API
    LOGGER.info("Using Anthropic client with model: %s", prompt_data["model"])

    api_kwargs: dict[str, Any] = {
        "model": prompt_data["model"],
        "max_tokens": prompt_data["max_tokens"],
        "system": prompt_data["system"],
        "messages": prompt_data["messages"],
    }
    if prompt_data.get("thinking"):
        # Extended thinking: API requires temperature to be unset.
        api_kwargs["thinking"] = prompt_data["thinking"]
    else:
        api_kwargs["temperature"] = prompt_data["temperature"]

    message = await client.messages.create(**api_kwargs)

    # Extract usage information
    input_tokens = message.usage.input_tokens
    output_tokens = message.usage.output_tokens
    total_tokens = input_tokens + output_tokens

    # Pick the last text block — when thinking is enabled the response
    # contains thinking blocks before the final text block.
    text_blocks = [c for c in message.content if getattr(c, "type", None) == "text"]
    explanation = text_blocks[-1].text.strip() if text_blocks else ""
    if not explanation:
        # Can happen if extended thinking exhausts max_tokens before any
        # text block is emitted. Surface the failure to the caller with
        # token usage populated, and emit a metric so this is visible on
        # dashboards rather than buried in a generic 500.
        message_text = (
            f"Claude returned no text content "
            f"(stop_reason={message.stop_reason}, in={input_tokens}, out={output_tokens}). "
            f"If thinking is enabled, max_tokens may be too low."
        )
        LOGGER.warning(message_text)
        metrics_provider.set_property("language", body.language)
        metrics_provider.set_property("compiler", body.compiler)
        metrics_provider.set_property("instructionSet", body.instructionSet or "unknown")
        metrics_provider.set_property("cached", "false")
        metrics_provider.put_metric("ClaudeExplainRequest", 1)
        metrics_provider.put_metric("ClaudeExplainEmptyResponse", 1)
        metrics_provider.put_metric("ClaudeExplainInputTokens", input_tokens)
        metrics_provider.put_metric("ClaudeExplainOutputTokens", output_tokens)
        return ExplainResponse(
            status="error",
            message=message_text,
            model=prompt_data["model"],
            usage=TokenUsage(
                inputTokens=input_tokens,
                outputTokens=output_tokens,
                totalTokens=total_tokens,
            ),
        )

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
