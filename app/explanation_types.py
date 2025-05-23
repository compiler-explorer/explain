"""Centralized definitions for audience levels and explanation types.

This module contains all the metadata about audience levels and explanation types
in one place to avoid duplication across the codebase.
"""

from enum import Enum


class AudienceLevel(str, Enum):
    """Target audience for the explanation.

    Each member contains: (value, description, guidance)
    """

    def __new__(cls, value: str, description: str, guidance: str):
        """Create a new AudienceLevel with associated metadata."""
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.description = description
        obj.guidance = guidance
        return obj

    BEGINNER = (
        "beginner",
        "For beginners learning assembly language. Uses simple language and explains technical terms.",
        "Use simple, clear language. Define technical terms. Explain concepts step-by-step.",
    )
    INTERMEDIATE = (
        "intermediate",
        "For users familiar with basic assembly concepts. Focuses on compiler behavior and choices.",
        "Assume familiarity with basic assembly concepts. Focus on the 'why' behind compiler choices.",
    )
    EXPERT = (
        "expert",
        "For advanced users. Uses technical terminology and covers advanced optimizations.",
        "Use technical terminology freely. Focus on advanced optimizations and architectural details.",
    )


class ExplanationType(str, Enum):
    """Type of explanation to generate.

    Each member contains: (value, description, focus, user_prompt_phrase)
    """

    def __new__(cls, value: str, description: str, focus: str, user_prompt_phrase: str):
        """Create a new ExplanationType with associated metadata."""
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.description = description
        obj.focus = focus
        obj.user_prompt_phrase = user_prompt_phrase
        return obj

    ASSEMBLY = (
        "assembly",
        "Explains the assembly instructions and their purpose.",
        "Focus on explaining the assembly instructions and their purpose.",
        "assembly output",
    )
    SOURCE = (
        "source",
        "Explains how source code constructs map to assembly instructions.",
        "Focus on how source code constructs map to assembly instructions.",
        "code transformations",
    )
    OPTIMIZATION = (
        "optimization",
        "Explains compiler optimizations and transformations applied to the code.",
        "Focus on compiler optimizations and transformations applied to the code.",
        "optimizations",
    )
