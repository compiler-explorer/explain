import asyncio
import logging

from anthropic import APIConnectionError, APIStatusError, APITimeoutError, AsyncAnthropic

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

# Default wall-clock budget for the Claude call. Overridden per request from
# settings.anthropic_timeout_seconds; the default keeps direct callers (tests,
# local server) bounded below the API Gateway 30s integration ceiling too.
DEFAULT_ANTHROPIC_DEADLINE_SECONDS = 27.0


async def process_request(
    body: ExplainRequest,
    client: AsyncAnthropic,
    prompt: Prompt,
    metrics_provider: MetricsProvider,
    cache_provider: CacheProvider | None = None,
    deadline_seconds: float = DEFAULT_ANTHROPIC_DEADLINE_SECONDS,
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
        deadline_seconds: wall-clock budget for the Claude call before giving up

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
    response = await _call_anthropic_api(body, client, prompt, metrics_provider, deadline_seconds)

    # Cache the response (if cache provider is available). Don't cache
    # error responses — they consume real tokens but produce no useful
    # content, and we want a retry to hit the API rather than the cache.
    if cache_provider is not None and response.status == "success":
        await cache_response(body, prompt, response, cache_provider)
        metrics_provider.put_metric("ClaudeExplainCacheMiss", 1)

    return response


def _transient_error_response(
    body: ExplainRequest,
    model: str,
    metrics_provider: MetricsProvider,
    error: Exception,
) -> ExplainResponse:
    """Build a structured error response for a timed-out or transiently failed call.

    Returned (rather than raised) so the client gets a clear, retryable message
    well within the API Gateway 30s window instead of an opaque 503. No token
    usage is available because the call did not complete.
    """
    if isinstance(error, (TimeoutError, APITimeoutError)):
        message_text = (
            "Claude Explain took too long to respond — the input may be very large "
            "or the model is under heavy load. Please try again in a moment."
        )
    else:
        message_text = "Claude Explain is temporarily unavailable. Please try again in a moment."
    LOGGER.warning("Anthropic call failed (%s): %s", type(error).__name__, error)
    metrics_provider.set_property("language", body.language)
    metrics_provider.set_property("compiler", body.compiler)
    metrics_provider.set_property("instructionSet", body.instructionSet or "unknown")
    metrics_provider.set_property("cached", "false")
    metrics_provider.put_metric("ClaudeExplainRequest", 1)
    if isinstance(error, (TimeoutError, APITimeoutError)):
        metrics_provider.put_metric("ClaudeExplainTimeout", 1)
    else:
        metrics_provider.put_metric("ClaudeExplainTransientError", 1)
    return ExplainResponse(
        status="error",
        message=message_text,
        model=model,
        usage=TokenUsage(inputTokens=0, outputTokens=0, totalTokens=0),
    )


async def _call_anthropic_api(
    body: ExplainRequest,
    client: AsyncAnthropic,
    prompt: Prompt,
    metrics_provider: MetricsProvider,
    deadline_seconds: float = DEFAULT_ANTHROPIC_DEADLINE_SECONDS,
) -> ExplainResponse:
    """Make the actual call to Anthropic API and create response.

    This is the original process_request logic, extracted for clarity.
    """
    prompt_data = prompt.build_api_payload(body)

    # Debug logging for prompts
    LOGGER.debug(f"=== PROMPT DEBUG FOR {body.explanation.value.upper()} (audience: {body.audience.value}) ===")
    LOGGER.debug("=== SYSTEM PROMPT ===")
    LOGGER.debug(prompt_data["system"])
    LOGGER.debug("=== MESSAGES ===")
    for message in prompt_data["messages"]:
        LOGGER.debug(message)
    LOGGER.debug("=== END PROMPT DEBUG ===")

    # Call Claude API. `prompt_data` is already exactly the kwargs
    # `messages.create` expects — `build_api_payload` resolved the
    # thinking-vs-temperature exclusivity for us.
    LOGGER.info(
        "Using Anthropic client with model: %s (thinking=%s)",
        prompt_data["model"],
        bool(prompt_data.get("thinking")),
    )
    # Bound the call to a wall-clock budget below the API Gateway HTTP API
    # integration timeout (a hard 30s ceiling). Without this, a slow generation
    # runs to completion inside the Lambda — billing tokens we never deliver —
    # while the gateway has already returned an opaque 503 to the user. Failing
    # within the budget lets us surface a clear, retryable message instead.
    try:
        async with asyncio.timeout(deadline_seconds):
            message = await client.messages.create(**prompt_data)
    except (TimeoutError, APITimeoutError, APIConnectionError) as e:
        return _transient_error_response(body, prompt_data["model"], metrics_provider, e)
    except APIStatusError as e:
        # Surface only transient upstream failures gracefully; let genuine
        # client errors (e.g. a malformed 400) propagate as a real failure.
        if e.status_code in (408, 409, 429, 500, 502, 503, 504, 529):
            return _transient_error_response(body, prompt_data["model"], metrics_provider, e)
        raise

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
