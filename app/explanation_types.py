"""Centralized definitions for audience levels and explanation types.

This module contains simple enums for audience levels and explanation types.
The associated metadata (descriptions, guidance, etc.) is stored in the
prompt configuration and accessed via the Prompt class.
"""

from enum import StrEnum


class AudienceLevel(StrEnum):
    """Target audience for the explanation."""

    BEGINNER = "beginner"
    EXPERIENCED = "experienced"


class ExplanationType(StrEnum):
    """Type of explanation to generate."""

    ASSEMBLY = "assembly"
    HAIKU = "haiku"
