import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Union

from anthropic import Anthropic
import aws_embedded_metrics
from aws_embedded_metrics.logger.metrics_logger import MetricsLogger


class MetricsProvider(ABC):
    """Abstract base class for metrics providers."""

    @abstractmethod
    def put_metric(self, name: str, value: Union[int, float]) -> None:
        """Record a metric with the given name and value."""
        pass

    @abstractmethod
    def set_property(self, name: str, value: str) -> None:
        """Set a property/dimension for metrics."""
        pass


class CloudWatchMetricsProvider(MetricsProvider):
    """Implementation that uses CloudWatch metrics via aws_embedded_metrics."""

    def __init__(self, metrics_logger: MetricsLogger):
        self.metrics = metrics_logger

    def put_metric(self, name: str, value: Union[int, float]) -> None:
        self.metrics.put_metric(name, value)

    def set_property(self, name: str, value: str) -> None:
        self.metrics.set_property(name, value)


class NoopMetricsProvider(MetricsProvider):
    """Metrics provider that does nothing - for testing."""

    def put_metric(self, name: str, value: Union[int, float]) -> None:
        pass

    def set_property(self, name: str, value: str) -> None:
        pass


# Configure logging
logger = logging.getLogger("explain")


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


def create_response(
    status_code: int = 200, body: Optional[Union[Dict, List, str]] = None
) -> Dict:
    """Create a standardized API response."""
    # Default CORS headers for browser access
    default_headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key",
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    response = {
        "statusCode": status_code,
        "headers": default_headers,
    }

    # Add body if provided
    if body is not None:
        if isinstance(body, dict) or isinstance(body, list):
            response["body"] = json.dumps(body)
        else:
            response["body"] = body

    return response


def handle_error(error: Exception, is_internal: bool = False) -> Dict:
    """Centralized error handler that logs and creates error responses."""
    if is_internal:
        print(f"Unexpected error: {str(error)}")
        return create_response(
            status_code=500,
            body={"status": "error", "message": "Internal server error"},
        )
    else:
        print(f"Error: {str(error)}")
        return create_response(
            status_code=500, body={"status": "error", "message": str(error)}
        )


def validate_input(body: Dict) -> Tuple[bool, str]:
    """Validate the input request body."""
    required_fields = ["language", "compiler", "code", "asm"]
    for field in required_fields:
        if field not in body:
            return False, f"Missing required field: {field}"

    # Validate code length
    if len(body.get("code", "")) > MAX_CODE_LENGTH:
        return (
            False,
            f"Source code exceeds maximum length of {MAX_CODE_LENGTH} characters",
        )

    # Validate assembly format
    if not isinstance(body.get("asm", []), list):
        return False, "Assembly must be an array"

    # Check if assembly array is empty
    if len(body.get("asm", [])) == 0:
        return False, "Assembly array cannot be empty"

    return True, ""


def select_important_assembly(
    asm_array: List[Dict], label_definitions: Dict, max_lines: int = MAX_ASSEMBLY_LINES
) -> List[Dict]:
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
        if asm_item.get("source") and asm_item["source"] is not None:
            if (
                isinstance(asm_item["source"], dict)
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
        important_indices_list = sorted(list(important_indices))
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


def prepare_structured_data(body: Dict) -> Dict:
    """Prepare a structured JSON object for Claude's consumption."""
    # Extract and validate basic fields
    structured_data = {
        "language": body["language"],
        "compiler": body["compiler"],
        "sourceCode": body["code"],
        "instructionSet": body.get("instructionSet", "unknown"),
    }

    # Format compilation options
    comp_options = body.get("compilationOptions", [])
    if isinstance(comp_options, list):
        structured_data["compilationOptions"] = comp_options
    else:
        structured_data["compilationOptions"] = [str(comp_options)]

    # Process assembly array
    asm_array = body.get("asm", [])
    if len(asm_array) > MAX_ASSEMBLY_LINES:
        # If assembly is too large, we need smart truncation
        structured_data["assembly"] = select_important_assembly(
            asm_array, body.get("labelDefinitions", {})
        )
        structured_data["truncated"] = True
        structured_data["originalLength"] = len(asm_array)
    else:
        # Use the full assembly if it's within limits
        structured_data["assembly"] = asm_array
        structured_data["truncated"] = False

    # Include label definitions
    structured_data["labelDefinitions"] = body.get("labelDefinitions", {})

    # Add compiler messages if available
    stderr = body.get("stderr", [])
    if stderr and isinstance(stderr, list):
        structured_data["compilerMessages"] = stderr
    else:
        structured_data["compilerMessages"] = []

    # Add optimization remarks if available
    opt_output = body.get("optimizationOutput", [])
    if opt_output and isinstance(opt_output, list):
        structured_data["optimizationRemarks"] = opt_output
    else:
        structured_data["optimizationRemarks"] = []

    return structured_data


def process_request(
    body: Dict,
    client: Anthropic,
    metrics_provider: Optional[MetricsProvider] = None,
) -> Dict:
    """Process a request and return the response.

    This is the core processing logic, separated from the lambda_handler
    to allow for reuse in the local server mode.

    Args:
        body: The request body as a dictionary
        api_key: Optional API key for local development mode
        metrics_provider: Optional metrics provider for tracking stats

    Returns:
        A response dictionary with status and explanation
    """
    try:
        # Validate input
        valid, error_message = validate_input(body)
        if not valid:
            return create_response(
                status_code=400, body={"status": "error", "message": error_message}
            )

        language = body["language"]
        arch = body.get("instructionSet", "")

        structured_data = prepare_structured_data(body)

        system_prompt = f"""You are an expert in {arch} assembly code and {language}, helping users of the Compiler Explorer website understand how their code compiles to assembly.
The request will be in the form of a JSON document, which explains a source program and how it was compiled, and the resulting assembly code that was generated.
Provide clear, concise explanations. Focus on key transformations, optimizations, and important assembly patterns.
Explanations should be educational and highlight why certain code constructs generate specific assembly instructions.
Give no commentary on the original source: it is expected the user already understands their input, and is only looking for guidance on the assembly output.
If it makes it easiest to explain, note the corresponding parts of the source code, but do not focus on this.
Do not give an overall conclusion.
Be precise and accurate about CPU features and optimizations - avoid making incorrect claims about branch prediction or other hardware details."""

        # Call Claude API with JSON structure
        try:
            logger.info(f"Using Anthropic client with model: {MODEL}")

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
                                "text": f"Explain the {arch} assembly output.",
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

            # Record metrics if metrics provider is available
            if metrics_provider:
                # Add metrics with properties/dimensions
                metrics_provider.set_property("language", language)
                metrics_provider.set_property("compiler", body["compiler"])
                metrics_provider.set_property("instructionSet", arch)
                metrics_provider.put_metric("ClaudeExplainRequest", 1)

                # Track token usage
                metrics_provider.put_metric("ClaudeExplainInputTokens", input_tokens)
                metrics_provider.put_metric("ClaudeExplainOutputTokens", output_tokens)
                metrics_provider.put_metric("ClaudeExplainCost", total_cost)

            # # Record to SQS for long-term stats if available
            # try:
            #     queue_url = os.environ.get("SQS_STATS_QUEUE")
            #     if queue_url:
            #         sqs_client = boto3.client("sqs")
            #         date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
            #         time = datetime.datetime.utcnow().strftime("%H:%M:%S")
            #         sqs_client.send_message(
            #             QueueUrl=queue_url,
            #             MessageBody=json.dumps(
            #                 dict(
            #                     type="ClaudeExplain",
            #                     date=date,
            #                     time=time,
            #                     value=f"{language}:{body['compiler']}:{arch}",
            #                     tokens=total_tokens,
            #                     cost=round(total_cost, 6),
            #                 ),
            #                 sort_keys=True,
            #             ),
            #         )
            # except Exception as e:
            #     # Log but don't fail if stats recording fails
            #     logger.warning(f"Failed to record stats to SQS: {str(e)}")

            # Construct the response with usage and cost information
            response_body = {
                "status": "success",
                "explanation": explanation,
                "model": MODEL,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                },
                "cost": {
                    "input_cost": round(input_cost, 6),
                    "output_cost": round(output_cost, 6),
                    "total_cost": round(total_cost, 6),
                },
            }

        except Exception as e:
            logger.error(f"Error calling Claude API: {str(e)}")
            return create_response(
                500,
                {"status": "error", "message": f"Error calling Claude API: {str(e)}"},
            )

        # Return success response
        return create_response(200, response_body)

    except json.JSONDecodeError:
        return create_response(
            400, {"status": "error", "message": "Invalid JSON in request body"}
        )
    except Exception as e:
        return handle_error(e, is_internal=True)


@aws_embedded_metrics.metric_scope
def lambda_handler(event: Dict, context: object, metrics: MetricsLogger = None) -> Dict:
    """Handle Lambda invocation from API Gateway."""
    # Set up metrics provider - either use CloudWatch metrics or a no-op for testing
    metrics_provider: MetricsProvider
    if metrics:
        # Set metrics namespace for CloudWatch when running in AWS
        metrics.set_namespace("CompilerExplorer")
        metrics_provider = CloudWatchMetricsProvider(metrics)
    else:
        # Use no-op metrics for testing
        metrics_provider = NoopMetricsProvider()

    # Handle OPTIONS request (CORS preflight)
    if event.get("httpMethod") == "OPTIONS":
        return create_response(status_code=200, body={})

    try:
        # Parse request body
        body = json.loads(event.get("body", "{}"))
        return process_request(body, metrics_provider=metrics_provider)
    except json.JSONDecodeError:
        return create_response(
            400, {"status": "error", "message": "Invalid JSON in request body"}
        )
    except Exception as e:
        return handle_error(e, is_internal=True)
