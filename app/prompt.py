"""Prompt management for the explain service.

This module contains the Prompt class which handles all prompt-related logic,
including loading templates, preparing data, and generating messages for Claude.
"""

import json
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from app.explain_api import ExplainRequest

# Constants from explain.py that are needed for data preparation
MAX_ASSEMBLY_LINES = 300  # Maximum number of assembly lines to process


class Prompt:
    """Manages prompt templates and generates messages for Claude API."""

    def __init__(self, config: dict[str, Any] | Path):
        """Initialize the Prompt with configuration.

        Args:
            config: Either a dict with the configuration, or a Path to a YAML file
        """
        if isinstance(config, Path):
            yaml = YAML(typ="safe")
            with config.open(encoding="utf-8") as f:
                self.config = yaml.load(f)
        else:
            self.config = config

        # Extract model configuration
        self.model = self.config["model"]["name"]
        self.max_tokens = self.config["model"]["max_tokens"]
        self.temperature = self.config["model"].get("temperature", 0.0)

        # Extract prompt templates
        self.system_prompt_template = self.config["system_prompt"]
        self.user_prompt_template = self.config["user_prompt"]
        self.assistant_prefill = self.config["assistant_prefill"]

        # Extract metadata
        self.audience_levels = self.config["audience_levels"]
        self.explanation_types = self.config["explanation_types"]

    def get_audience_metadata(self, audience: str) -> dict[str, str]:
        """Get metadata for an audience level."""
        return self.audience_levels[audience]

    def get_explanation_metadata(self, explanation: str) -> dict[str, str]:
        """Get metadata for an explanation type."""
        return self.explanation_types[explanation]

    def select_important_assembly(
        self, asm_array: list[dict], label_definitions: dict, max_lines: int = MAX_ASSEMBLY_LINES
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

    def prepare_structured_data(self, request: ExplainRequest) -> dict[str, Any]:
        """Prepare a structured JSON object for Claude's consumption."""
        # Extract and validate basic fields
        structured_data = {
            "language": request.language,
            "compiler": request.compiler,
            "sourceCode": request.code,
            "instructionSet": request.instruction_set_with_default,
        }

        # Format compilation options
        structured_data["compilationOptions"] = request.compilationOptions

        # Convert assembly array to dict format for JSON serialization
        asm_dicts = [item.model_dump() for item in request.asm]

        if len(asm_dicts) > MAX_ASSEMBLY_LINES:
            # If assembly is too large, we need smart truncation
            structured_data["assembly"] = self.select_important_assembly(asm_dicts, request.labelDefinitions or {})
            structured_data["truncated"] = True
            structured_data["originalLength"] = len(asm_dicts)
        else:
            # Use the full assembly if it's within limits
            structured_data["assembly"] = asm_dicts
            structured_data["truncated"] = False

        # Include label definitions
        structured_data["labelDefinitions"] = request.labelDefinitions or {}

        return structured_data

    def generate_messages(self, request: ExplainRequest) -> dict[str, Any]:
        """Generate the complete message structure for Claude API.

        Returns a dict with:
        - model: The model name
        - max_tokens: Max tokens for the response
        - temperature: Temperature setting
        - system: The formatted system prompt
        - messages: The messages array for Claude
        - structured_data: The prepared data (for reference/debugging)
        """
        # Get metadata
        audience_meta = self.get_audience_metadata(request.audience.value)
        explanation_meta = self.get_explanation_metadata(request.explanation.value)

        # Prepare structured data
        structured_data = self.prepare_structured_data(request)

        # Format the system prompt
        arch = request.instruction_set_with_default
        system_prompt = self.system_prompt_template.format(
            arch=arch,
            language=request.language,
            audience=request.audience.value,
            audience_guidance=audience_meta["guidance"],
            explanation_type=request.explanation.value,
            explanation_focus=explanation_meta["focus"],
        )

        # Format the user prompt
        user_prompt = self.user_prompt_template.format(
            arch=arch,
            user_prompt_phrase=explanation_meta["user_prompt_phrase"],
        )

        # Build messages array
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "text", "text": json.dumps(structured_data)},
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": self.assistant_prefill},
                ],
            },
        ]

        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": system_prompt,
            "messages": messages,
            "structured_data": structured_data,  # Include for reference
        }
