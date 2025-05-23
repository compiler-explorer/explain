import json
import logging

from anthropic import Anthropic

from app.explain_api import CostBreakdown, ExplainRequest, ExplainResponse, TokenUsage
from app.metrics import MetricsProvider

# Configure logging
LOGGER = logging.getLogger("explain")


# Constants
MAX_CODE_LENGTH = 10000  # 10K chars should be enough for most source files
MAX_ASM_LENGTH = 20000  # 20K chars for assembly output
MAX_ASSEMBLY_LINES = 300  # Maximum number of assembly lines to process
MODEL = "claude-3-5-haiku-20241022"
MAX_TOKENS = 1024  # Adjust based on desired explanation length

# Claude token costs (USD)
# As of November 2024, these are the costs for Claude 3.5 Haiku
# Update if model or pricing changes
COST_PER_INPUT_TOKEN = 0.0000008  # $0.80/1M tokens
COST_PER_OUTPUT_TOKEN = 0.000004  # $4.00/1M tokens


def select_important_assembly(
    asm_array: list[dict], label_definitions: dict, max_lines: int = MAX_ASSEMBLY_LINES
) -> list[dict]:
    """Select the most important assembly lines if the output is too large.

    This function identifies and preserves:
    1. Function boundaries (entry points and returns)
    2. Instructions with source mappings
    3. Important contextual instructions
    """
    if len(asm_array) <= max_lines:
        return asm_array

    # Identify important blocks (function boundaries, etc.)
    important_indices = set()

    # Mark label definitions as important
    for _label, line_idx in label_definitions.items():
        if isinstance(line_idx, int) and 0 <= line_idx < len(asm_array):
            # Add the label line and a few lines after it (function prologue)
            for i in range(line_idx, min(line_idx + 5, len(asm_array))):
                important_indices.add(i)

    # Mark function epilogues and lines with source mappings
    for idx, asm_item in enumerate(asm_array):
        if not isinstance(asm_item, dict) or "text" not in asm_item:
            continue

        # Source mapping makes this important
        if (
            asm_item.get("source")
            and asm_item["source"] is not None
            and isinstance(asm_item["source"], dict)
            and asm_item["source"].get("line") is not None
        ):
            important_indices.add(idx)

        # Function returns and epilogues are important
        text = asm_item.get("text", "").strip()
        if text in ("ret", "leave", "pop rbp") or text.startswith("ret "):
            # Add the return line and a few lines before it
            for i in range(max(0, idx - 3), idx + 1):
                important_indices.add(i)

    # Also include context around important lines
    context_indices = set()
    for idx in important_indices:
        # Add a few lines before and after for context
        for i in range(max(0, idx - 2), min(len(asm_array), idx + 3)):
            context_indices.add(i)

    # Combine all important indices
    all_indices = important_indices.union(context_indices)

    # If we still have too many lines, prioritize
    if len(all_indices) > max_lines:
        # Prioritize function boundaries and source mappings over context
        important_indices_list = sorted(important_indices)
        all_indices = set(important_indices_list[:max_lines])

    # Collect selected assembly items
    selected_assembly = []

    # Sort indices to maintain original order
    sorted_indices = sorted(all_indices)

    # Find gaps and add "omitted" markers
    last_idx = -2
    for idx in sorted_indices:
        if idx > last_idx + 1:
            # There's a gap, add a special marker
            selected_assembly.append(
                {
                    "text": f"... ({idx - last_idx - 1} lines omitted) ...",
                    "isOmissionMarker": True,
                }
            )

        # Add the actual assembly item
        if 0 <= idx < len(asm_array):
            selected_assembly.append(asm_array[idx])

        last_idx = idx

    # Add a final omission marker if needed
    if last_idx < len(asm_array) - 1:
        selected_assembly.append(
            {
                "text": f"... ({len(asm_array) - last_idx - 1} lines omitted) ...",
                "isOmissionMarker": True,
            }
        )

    return selected_assembly


def prepare_structured_data(body: ExplainRequest) -> dict:
    """Prepare a structured JSON object for Claude's consumption."""
    # Extract and validate basic fields
    structured_data = {
        "language": body.language,
        "compiler": body.compiler,
        "sourceCode": body.code,
        "instructionSet": body.instructionSet or "unknown",
    }

    # Format compilation options
    structured_data["compilationOptions"] = body.compilationOptions

    # Convert assembly array to dict format for JSON serialization
    asm_dicts = [item.model_dump() for item in body.asm]

    if len(asm_dicts) > MAX_ASSEMBLY_LINES:
        # If assembly is too large, we need smart truncation
        structured_data["assembly"] = select_important_assembly(asm_dicts, body.labelDefinitions or {})
        structured_data["truncated"] = True
        structured_data["originalLength"] = len(asm_dicts)
    else:
        # Use the full assembly if it's within limits
        structured_data["assembly"] = asm_dicts
        structured_data["truncated"] = False

    # Include label definitions
    structured_data["labelDefinitions"] = body.labelDefinitions or {}

    # For now, these fields are not in the Pydantic model but kept for compatibility
    structured_data["compilerMessages"] = []
    structured_data["optimizationRemarks"] = []

    return structured_data


def process_request(
    body: ExplainRequest,
    client: Anthropic,
    metrics_provider: MetricsProvider,
) -> ExplainResponse:
    """Process a request and return the response.

    This is the core processing logic, separated from the lambda_handler
    to allow for reuse in the local server mode.

    Args:
        body: The request body as a Pydantic model
        client: Anthropic client instance
        metrics_provider: metrics provider for tracking stats

    Returns:
        An ExplainResponse Pydantic model
    """
    language = body.language
    arch = body.instructionSet or "unknown"

    structured_data = prepare_structured_data(body)

    # TODO: consider not baking the language and arch here for system prompt caching later on.
    #  We'll need to hit minimum token lengths.

    system_prompt = f"""You are an expert in {arch} assembly code and {language}, helping users of the
Compiler Explorer website understand how their code compiles to assembly.
The request will be in the form of a JSON document, which explains a source program and how it was compiled,
and the resulting assembly code that was generated.

Target audience: {body.audience.value}
{body.audience.guidance}

Explanation type: {body.explanation.value}
{body.explanation.focus}

Provide clear, concise explanations. Explanations should be educational and highlight
why certain code constructs generate specific assembly instructions.
Give no commentary on the original source: it is expected the user already understands their input, and is only
looking for guidance on the assembly output.
If it makes it easiest to explain, note the corresponding parts of the source code, but do not focus on this.
Do not give an overall conclusion.
Be precise and accurate about CPU features and optimizations - avoid making incorrect claims about branch
prediction or other hardware details."""

    # Call Claude API with JSON structure
    LOGGER.info(f"Using Anthropic client with model: {MODEL}")

    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Explain the {arch} {body.explanation.user_prompt_phrase}.",
                    },
                    {"type": "text", "text": json.dumps(structured_data)},
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "I have analysed the assembly code and my analysis is:",
                    },
                ],
            },
        ],
    )

    # Get explanation and strip leading/trailing whitespace
    explanation = message.content[0].text.strip()

    # Extract usage information
    input_tokens = message.usage.input_tokens
    output_tokens = message.usage.output_tokens
    total_tokens = input_tokens + output_tokens

    # Calculate costs
    input_cost = input_tokens * COST_PER_INPUT_TOKEN
    output_cost = output_tokens * COST_PER_OUTPUT_TOKEN
    total_cost = input_cost + output_cost

    # Add metrics with properties/dimensions
    metrics_provider.set_property("language", language)
    metrics_provider.set_property("compiler", body.compiler)
    metrics_provider.set_property("instructionSet", arch)
    metrics_provider.put_metric("ClaudeExplainRequest", 1)

    # Track token usage
    metrics_provider.put_metric("ClaudeExplainInputTokens", input_tokens)
    metrics_provider.put_metric("ClaudeExplainOutputTokens", output_tokens)
    metrics_provider.put_metric("ClaudeExplainCost", total_cost)

    # Create and return ExplainResponse object
    return ExplainResponse(
        status="success",
        explanation=explanation,
        model=MODEL,
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
