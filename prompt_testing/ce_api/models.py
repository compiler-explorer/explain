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
        label_definitions = {}

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

            # Track label definitions
            if "labels" in line:
                for label in line["labels"]:
                    if isinstance(label, dict) and "name" in label:
                        label_name = label["name"]
                        if label_name not in label_definitions:
                            label_definitions[label_name] = len(asm_lines) - 1

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
