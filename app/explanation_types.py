"""Centralized definitions for audience levels and explanation types.

This module contains simple enums for audience levels and explanation types.
The associated metadata (descriptions, guidance, etc.) is stored in the
prompt configuration and accessed via the Prompt class.
"""

from enum import Enum


class AudienceLevel(str, Enum):
    """Target audience for the explanation."""

    BEGINNER = "beginner"
    EXPERIENCED = "experienced"


class ExplanationType(str, Enum):
    """Type of explanation to generate."""

    ASSEMBLY = "assembly"
    HAIKU = "haiku"
