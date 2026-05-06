"""Model cost configuration for Claude models.

This module provides a flexible way to look up model costs based on
model names, using pattern matching to handle various naming schemes.

Note: Anthropic does not provide a programmatic API for retrieving pricing
information, so costs are maintained manually based on published pricing.
"""

import re
from typing import NamedTuple


class ModelCost(NamedTuple):
    """Cost per token for a model."""

    per_input_token: float
    per_output_token: float


# Model family costs in USD per million tokens
# Updated: 2026-05-06 based on https://platform.claude.com/docs/en/about-claude/pricing
#
# Notes:
# - Opus 4.5+ moved to a new lower price tier ($5/$25) and now bundle the 1M
#   context window at flat rates. Opus 4.1 and earlier remain at the old
#   $15/$75 pricing until retirement.
# - Sonnet 4.x stays at $3/$15 with 1M context included on 4.6.
# - Retired models (Opus 3, Haiku 3, Sonnet 3.5, Sonnet 3.7) have been removed
#   from the lookup; the regex normaliser still parses their names so callers
#   get a clear "not found" error rather than a parse failure.
MODEL_FAMILIES = {
    # Opus 4.5+: new pricing tier, 1M context bundled
    "opus-4.7": ModelCost(5.0, 25.0),
    "opus-4.6": ModelCost(5.0, 25.0),
    "opus-4.5": ModelCost(5.0, 25.0),
    # Opus 4.0/4.1: legacy pricing, 200K context
    "opus-4.1": ModelCost(15.0, 75.0),
    "opus-4": ModelCost(15.0, 75.0),
    # Sonnet 4.x
    "sonnet-4.6": ModelCost(3.0, 15.0),
    "sonnet-4.5": ModelCost(3.0, 15.0),
    "sonnet-4": ModelCost(3.0, 15.0),
    # Haiku
    "haiku-4.5": ModelCost(1.0, 5.0),
    "haiku-3.5": ModelCost(0.80, 4.0),
}


def normalize_model_name(model: str) -> str:
    """Normalize a model name to extract family and version.

    Examples:
        claude-3-5-haiku-20241022 -> haiku-3.5
        claude-3-opus-20240229 -> opus-3
        claude-sonnet-4-0 -> sonnet-4
        claude-3-5-sonnet-20241022 -> sonnet-3.5
        claude-opus-4-1-20250805 -> opus-4.1
    """
    # Convert to lowercase for consistent matching
    model = model.lower()

    # Pattern 1: claude-X-Y-family-date (e.g., claude-3-5-haiku-20241022)
    match = re.match(r"claude-(\d+)-(\d+)-(\w+)-\d+", model)
    if match:
        major, minor, family = match.groups()
        return f"{family}-{major}.{minor}"

    # Pattern 2: claude-X-family-date (e.g., claude-3-opus-20240229)
    match = re.match(r"claude-(\d+)-(\w+)-\d+", model)
    if match:
        major, family = match.groups()
        return f"{family}-{major}"

    # Pattern 3: claude-family-X-Y (e.g., claude-sonnet-4-0)
    match = re.match(r"claude-(\w+)-(\d+)-(\d+)", model)
    if match:
        family, major, minor = match.groups()
        if minor == "0":
            return f"{family}-{major}"
        return f"{family}-{major}.{minor}"

    # Pattern 4: claude-family-X-Y-date (e.g., claude-opus-4-1-20250805)
    match = re.match(r"claude-(\w+)-(\d+)-(\d+)-\d+", model)
    if match:
        family, major, minor = match.groups()
        if minor == "0":
            return f"{family}-{major}"
        return f"{family}-{major}.{minor}"

    # Pattern 5: claude-family-X (e.g., claude-opus-4)
    match = re.match(r"claude-(\w+)-(\d+)$", model)
    if match:
        family, major = match.groups()
        return f"{family}-{major}"

    # If no pattern matches, try to extract any recognizable family name
    for family in ["opus", "sonnet", "haiku"]:
        if family in model:
            # Try to find a version number that appears after the family name
            # Look for patterns like family-X, family-X.Y, family-X-Y
            pattern = rf"{family}[-\s]+(\d+)(?:[-.](\d+))?"
            version_match = re.search(pattern, model)
            if version_match:
                major = version_match.group(1)
                minor = version_match.group(2)
                if minor:
                    return f"{family}-{major}.{minor}"
                return f"{family}-{major}"

    raise ValueError(f"Unable to parse model name: {model}")


def get_model_cost(model: str) -> tuple[float, float]:
    """Get the cost per token for a given model.

    Args:
        model: The model name (e.g., "claude-3-5-haiku-20241022")

    Returns:
        A tuple of (cost_per_input_token, cost_per_output_token) in USD

    Raises:
        ValueError: If the model is not recognized
    """
    normalized = normalize_model_name(model)

    if normalized not in MODEL_FAMILIES:
        raise ValueError(
            f"Model family '{normalized}' not found in pricing data. "
            f"Available families: {', '.join(sorted(MODEL_FAMILIES.keys()))}"
        )

    cost = MODEL_FAMILIES[normalized]
    # Convert from per million to per token
    return (cost.per_input_token / 1_000_000, cost.per_output_token / 1_000_000)


def get_model_cost_info(model: str) -> dict[str, float]:
    """Get detailed cost information for a model.

    Args:
        model: The model name

    Returns:
        A dictionary with per_input_token and per_output_token costs in USD
    """
    input_cost, output_cost = get_model_cost(model)
    return {
        "per_input_token": input_cost,
        "per_output_token": output_cost,
    }
