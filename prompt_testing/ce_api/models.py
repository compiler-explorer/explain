"""Data models for Compiler Explorer API."""

from dataclasses import dataclass
from typing import Any


@dataclass
class CompileRequest:
    """Request to compile source code."""

    source: str
    compiler: str
    options: list[str]
    filters: dict[str, bool] | None = None


@dataclass
class SourceInfo:
    """Source line information for an assembly instruction."""

    file: str | None
    line: int


@dataclass
class AssemblyLine:
    """Single line of assembly output."""

    text: str
    source: SourceInfo | None = None
    address: int | None = None
    labels: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format used in test cases."""
        result: dict[str, Any] = {"text": self.text}
        if self.address is not None:
            result["address"] = self.address
        if self.source:
            result["source"] = {"line": self.source.line}
            if self.source.file:
                result["source"]["file"] = self.source.file
        if self.labels:
            result["labels"] = self.labels
        return result


def derive_label_definitions(asm_texts: list[str]) -> dict[str, int]:
    """Map each label to the 1-based line it is defined on, matching CE's `labelDefinitions` convention.

    A definition is an unindented line ending in a colon (`.L3:`, `main:`, `sum(int const*, int):`).
    """
    definitions: dict[str, int] = {}
    for number, text in enumerate(asm_texts, start=1):
        if text.endswith(":") and not text[:1].isspace():
            definitions.setdefault(text[:-1], number)
    return definitions


@dataclass
class CompileResponse:
    """Response from compilation request."""

    code: int
    asm: list[AssemblyLine]
    stdout: list[dict[str, Any]]
    stderr: list[dict[str, Any]]
    label_definitions: dict[str, int]
    instruction_set: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "CompileResponse":
        """Create from CE API response."""
        asm_lines = []

        for line in data.get("asm", []):
            # Extract source info
            source = None
            if line.get("source"):
                source = SourceInfo(
                    file=line["source"].get("file"),
                    line=line["source"].get("line"),
                )

            # Create assembly line
            asm_line = AssemblyLine(
                text=line.get("text", ""),
                source=source,
                address=line.get("address"),
                labels=line.get("labels", []),
            )
            asm_lines.append(asm_line)

        # CE's own map is label -> 1-based line in the filtered asm, which is what the frontend sends the
        # explain service. A line's `labels` field lists the labels it *references*, not defines, so it is
        # no use for this; derive from the definition lines only if the API omitted the map.
        api_definitions = data.get("labelDefinitions")
        if isinstance(api_definitions, dict):
            label_definitions = dict(api_definitions)
        else:
            label_definitions = derive_label_definitions([line.text for line in asm_lines])

        return cls(
            code=data.get("code", 0),
            asm=asm_lines,
            stdout=data.get("stdout", []),
            stderr=data.get("stderr", []),
            label_definitions=label_definitions,
        )


@dataclass
class CompilerInfo:
    """Information about a compiler."""

    id: str
    name: str
    version: str | None = None
    lang: str | None = None
    instruction_set: str | None = None
    compiler_type: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "CompilerInfo":
        """Create from CE API response."""
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            version=data.get("version"),
            lang=data.get("lang"),
            instruction_set=data.get("instructionSet"),
            compiler_type=data.get("compilerType"),
        )
