import anthropic
import boto3
import functools
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PARAM_NAME = "/ce/claude/api-key"  # Stored in Parameter Store


# AWS clients are initialized on demand with caching to make testing easier
# TODO probba
@functools.cache
def get_ssm_client():
    """Get or initialize SSM client"""
    return boto3.client("ssm")


def get_anthropic_client(api_key=None) -> anthropic.Anthropic:
    """Get or initialize Anthropic client with API key.

    Args:
        api_key: Optional API key to use instead of retrieving from SSM
    """
    try:
        # Use provided API key if available (for local dev)
        if api_key:
            logger.info("Using provided API key")
            return anthropic.Anthropic(api_key=api_key)
        else:
            # Otherwise get from SSM (for lambda) TODO inject as ENV
            response = get_ssm_client().get_parameter(
                Name=PARAM_NAME, WithDecryption=True
            )
            api_key = response["Parameter"]["Value"]
            logger.info("Using API key from SSM Parameter Store")
            return anthropic.Anthropic(api_key=api_key)
    except RuntimeError as e:
        logger.error(f"Error creating Anthropic client: {type(e).__name__}: {str(e)}")
        raise


def read_api_key_from_file(file_path: Path):
    """Read the Claude API key from a file.

    Args:
        file_path: Path to the file containing the API key

    Returns:
        The API key as a string, with any whitespace stripped
    """
    try:
        api_key = file_path.read_text(encoding="utf-8").strip()
        if not api_key:
            raise ValueError("API key file is empty")
        return api_key
    except FileNotFoundError as fnf_error:
        raise FileNotFoundError(f"API key file not found: {file_path}") from fnf_error
