"""Pydantic models for the Claude Explain API.

Defines request and response types based on the API specification
in claude_explain.md.
"""

from enum import Enum

from pydantic import BaseModel, Field

from app.explanation_types import AudienceLevel, ExplanationType


class SourceMapping(BaseModel):
    """Source code mapping for assembly lines."""

    file: str | None = None
    line: int
    column: int | None = None


class LabelRange(BaseModel):
    """Position range for a label in assembly text."""

    startCol: int
    endCol: int


class Label(BaseModel):
    """Label reference with positioning information."""

    name: str
    range: LabelRange


class AssemblyItem(BaseModel):
    """Individual assembly instruction or label."""

    text: str
    source: SourceMapping | None = None
    labels: list[Label] = Field(default_factory=list)
    isOmissionMarker: bool | None = None  # Added for truncated assembly


class ExplanationFormat(str, Enum):
    """Output format for explanations."""

    MARKDOWN = "markdown"
    STRUCTURED = "structured"


class ExplainRequest(BaseModel):
    """Request body for the Claude Explain API."""

    language: str = Field(..., description="Programming language (e.g., 'c++', 'rust')")
    compiler: str = Field(..., description="Compiler identifier (e.g., 'g112', 'clang1500')")
    code: str = Field(..., description="Original source code")
    compilationOptions: list[str] = Field(default_factory=list, description="Array of compiler flags/options")
    instructionSet: str | None = Field(None, description="Target architecture (e.g., 'amd64', 'arm64')")
    asm: list[AssemblyItem] = Field(..., description="Array of assembly objects")
    labelDefinitions: dict[str, int] | None = Field(None, description="Optional map of label names to line numbers")
    audience: AudienceLevel = Field(
        default=AudienceLevel.BEGINNER, description="Target audience level for the explanation"
    )
    explanation: ExplanationType = Field(
        default=ExplanationType.ASSEMBLY, description="Type of explanation to generate"
    )
    format: ExplanationFormat = Field(
        default=ExplanationFormat.MARKDOWN,
        description="Output format: 'markdown' (default) or 'structured' (JSON with assembly line mappings)",
    )
    bypassCache: bool = Field(default=False, description="If true, skip reading from cache but still write to cache")

    @property
    def instruction_set_with_default(self) -> str:
        """Get the instruction set with fallback to 'unknown' if None."""
        return self.instructionSet or "unknown"


class ExplanationSection(BaseModel):
    """A section of a structured explanation, mapped to assembly lines."""

    model_config = {"json_schema_extra": {"additionalProperties": False}}

    title: str = Field(..., description="Section heading")
    asmStartLine: int = Field(..., description="0-indexed start line in the assembly listing")
    asmEndLine: int = Field(..., description="0-indexed end line (inclusive) in the assembly listing")
    content: str = Field(..., description="Explanation of this group of instructions (markdown)")


class StructuredExplanation(BaseModel):
    """Structured explanation with assembly line mappings."""

    model_config = {"json_schema_extra": {"additionalProperties": False}}

    summary: str = Field(..., description="One-sentence overview of what the compiler did")
    sections: list[ExplanationSection] = Field(..., description="Explanation sections mapped to assembly lines")
    keyInsight: str = Field(..., description="The single most important takeaway")


class TokenUsage(BaseModel):
    """Token usage information."""

    inputTokens: int
    outputTokens: int
    totalTokens: int


class CostBreakdown(BaseModel):
    """Cost breakdown information."""

    inputCost: float
    outputCost: float
    totalCost: float


class ExplainResponse(BaseModel):
    """Response from the Claude Explain API."""

    explanation: str | None = Field(None, description="The generated explanation (markdown format)")
    structuredExplanation: StructuredExplanation | None = Field(
        None, description="Structured explanation with assembly line mappings (structured format)"
    )
    status: str = Field(..., description="'success' or 'error'")
    message: str | None = Field(None, description="Error message (only present on error)")
    model: str | None = Field(None, description="The Claude model used")
    usage: TokenUsage | None = Field(None, description="Token usage information")
    cost: CostBreakdown | None = Field(None, description="Cost breakdown")
    cached: bool = Field(default=False, description="Whether this response was served from cache")


class ExplainErrorResponse(BaseModel):
    """Error response from the Claude Explain API."""

    status: str = Field("error", description="Always 'error' for error responses")
    message: str = Field(..., description="Error message describing what went wrong")


class ExplainSuccessResponse(BaseModel):
    """Success response from the Claude Explain API."""

    status: str = Field("success", description="Always 'success' for successful responses")
    explanation: str = Field(..., description="The generated explanation")
    model: str = Field(..., description="The Claude model used")
    usage: TokenUsage = Field(..., description="Token usage information")
    cost: CostBreakdown = Field(..., description="Cost breakdown")


class OptionDescription(BaseModel):
    """Description of an available option."""

    value: str = Field(..., description="The option value to use in requests")
    description: str = Field(..., description="Human-readable description of the option")


class AvailableOptions(BaseModel):
    """Available options for the explain API."""

    audience: list[OptionDescription] = Field(..., description="Available audience levels")
    explanation: list[OptionDescription] = Field(..., description="Available explanation types")
