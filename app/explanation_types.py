"""Centralized definitions for audience levels and explanation types.

This module contains all the metadata about audience levels and explanation types
in one place to avoid duplication across the codebase.
"""

from enum import Enum
from pathlib import Path

from ruamel.yaml import YAML

# Load metadata from prompt configuration
_PROMPT_CONFIG_PATH = Path(__file__).parent / "prompt.yaml"
yaml = YAML(typ="safe")
with _PROMPT_CONFIG_PATH.open(encoding="utf-8") as f:
    _PROMPT_CONFIG = yaml.load(f)


class AudienceLevel(str, Enum):
    """Target audience for the explanation.

    Each member loads its metadata from the prompt configuration.
    """

    def __new__(cls, value: str):
        """Create a new AudienceLevel with metadata from config."""
        obj = str.__new__(cls, value)
        obj._value_ = value
        # Load metadata from config
        config = _PROMPT_CONFIG["audience_levels"][value]
        obj.description = config["description"]
        obj.guidance = config["guidance"]
        return obj

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    EXPERT = "expert"


class ExplanationType(str, Enum):
    """Type of explanation to generate.

    Each member loads its metadata from the prompt configuration.
    """

    def __new__(cls, value: str):
        """Create a new ExplanationType with metadata from config."""
        obj = str.__new__(cls, value)
        obj._value_ = value
        # Load metadata from config
        config = _PROMPT_CONFIG["explanation_types"][value]
        obj.description = config["description"]
        obj.focus = config["focus"]
        obj.user_prompt_phrase = config["user_prompt_phrase"]
        return obj

    ASSEMBLY = "assembly"
    SOURCE = "source"
    OPTIMIZATION = "optimization"
