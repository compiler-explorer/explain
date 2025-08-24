"""
Claude-based AI reviewer for evaluating prompt responses.
Uses advanced models with constitutional AI principles.
"""

import json
from dataclasses import dataclass

from anthropic import Anthropic, AsyncAnthropic

from app.explanation_types import AudienceLevel, ExplanationType


@dataclass
class EvaluationMetrics:
    """New metrics-based evaluation for a single response."""

    # Core metrics (0-1 scale)
    accuracy: float  # Technical correctness without false claims
    relevance: float  # Discusses actual code, recognizes optimization level
    conciseness: float  # Direct explanation without filler or boilerplate
    insight: float  # Explains WHY and provides actionable understanding
    appropriateness: float  # Matches audience level and explanation type

    overall_score: float  # Weighted combination of above

    # Additional metrics
    token_count: int
    response_time_ms: int | None = None

    # Detailed feedback
    flags: list[str] | None = None  # Issues found (BS patterns, etc)
    strengths: list[str] | None = None  # What was done well
    notes: str | None = None  # General feedback


@dataclass
class ReviewCriteria:
    """New metrics-based criteria for Claude to evaluate responses."""

    accuracy: str = """
    Evaluate technical accuracy (0-100):
    - Are assembly instructions correctly explained?
    - No false claims about hardware behavior (e.g., "single-cycle multiplication")
    - No invented optimizations or non-existent features
    - Correct understanding of instruction semantics
    - Heavily penalize confident incorrectness
    """

    relevance: str = """
    Evaluate relevance to the actual code (0-100):
    - Discusses THIS specific code, not hypothetical versions
    - Recognizes actual optimization level from assembly patterns
    - Acknowledges when code is clearly unoptimized
    - No false claims of "efficiency" for obviously naive/unoptimized code
    - No generic statements that don't match the actual assembly
    """

    conciseness: str = """
    Evaluate conciseness and signal-to-noise ratio (0-100):
    - Direct explanation of assembly vs generic filler
    - No boilerplate headers ("Architecture:", "Optimization Level:", etc.)
    - Focused, to-the-point explanations
    - No padding with obvious restatements
    - Avoids formulaic structure when not needed
    """

    insight: str = """
    Evaluate practical insight and understanding (0-100):
    - Explains WHY the compiler made these specific choices
    - Provides actionable understanding for developers
    - No useless or incorrect suggestions (e.g., "use __builtin_mul")
    - Focuses on actual patterns present in THIS code
    - Helps reader understand compiler behavior principles
    """

    appropriateness: str = """
    Evaluate appropriateness for audience and explanation type (0-100):
    - Matches audience level without condescension
    - Matches explanation type focus (assembly/source/optimization)
    - Beginners get foundations, experts get depth
    - No over-explaining basics to experts
    - No overwhelming beginners with trivia
    - Content matches the requested explanation type
    """

    def get_haiku_criteria(self) -> dict[str, str]:
        """Get haiku-specific evaluation criteria."""
        return {
            "accuracy": """
            Evaluate technical accuracy (0-100):
            - Does the haiku capture the actual behavior of the code?
            - No false claims about what the code does
            - Correctly identifies key actions (recursion, loops, data manipulation)
            - Avoids technical inaccuracies even in poetic form
            """,
            "relevance": """
            Evaluate relevance to the actual code (0-100):
            - Captures the essence of THIS specific code's behavior
            - Reflects key patterns (recursion, optimization, simplicity)
            - Not generic poetry that could apply to any code
            - Connects to the actual assembly operations
            """,
            "conciseness": """
            Evaluate haiku format adherence (0-100):
            - Exactly three lines
            - Appropriate syllable structure (approximately 5-7-5)
            - No extra text beyond the haiku
            - Each line contributes meaningfully
            """,
            "insight": """
            Evaluate poetic insight and imagery (0-100):
            - Uses vivid, concrete imagery
            - Captures deeper meaning of the code's purpose
            - Creative metaphors that illuminate the code's nature
            - Poetic language that enhances understanding
            """,
            "appropriateness": """
            Evaluate haiku quality and appropriateness (0-100):
            - Maintains the spirit and form of traditional haiku
            - Balances technical accuracy with poetic expression
            - Language is evocative and memorable
            - Successfully bridges code analysis and poetry
            """,
        }

    def get_criteria_for_type(self, explanation_type: ExplanationType) -> dict[str, str]:
        """Get criteria appropriate for the explanation type."""
        if explanation_type == ExplanationType.HAIKU:
            return self.get_haiku_criteria()

        # Default assembly criteria
        return {
            "accuracy": self.accuracy,
            "relevance": self.relevance,
            "conciseness": self.conciseness,
            "insight": self.insight,
            "appropriateness": self.appropriateness,
        }


_AUDIENCE_LEVEL = {
    AudienceLevel.BEGINNER: """The explanation should be aimed at beginners.
They will need basic concepts about assembly explained, and may need to know about
calling conventions and other key information.""",
    AudienceLevel.EXPERIENCED: """The explanation should target an experienced audience.
They will not need explanation about trivial assembly idioms, calling conventions etc. They
may need to be told about more esoteric instructions. Assume the audience knows most instructions
and can handle technical terminology and advanced optimizations.""",
}

_EXPLANATION_TYPE = {
    ExplanationType.ASSEMBLY: """The explanation should be predominantly about the compiled assembly.""",
    ExplanationType.HAIKU: """The explanation should be in the form of a haiku,
    capturing the essence of the code's behavior in a poetic way.""",
}


class ClaudeReviewer:
    """Uses Claude to evaluate prompt responses with sophisticated analysis."""

    def __init__(
        self,
        anthropic_api_key: str | None = None,
        reviewer_model: str = "claude-sonnet-4-0",
        enable_thinking: bool = True,
    ):
        self.client = Anthropic(api_key=anthropic_api_key) if anthropic_api_key else Anthropic()
        self.async_client = AsyncAnthropic(api_key=anthropic_api_key) if anthropic_api_key else AsyncAnthropic()
        self.reviewer_model = reviewer_model
        self.enable_thinking = enable_thinking
        self.criteria = ReviewCriteria()

    def _build_evaluation_prompt(
        self,
        source_code: str,
        assembly_code: str,
        explanation: str,
        test_case: dict,
        audience: AudienceLevel,
        explanation_type: ExplanationType,
    ) -> str:
        """Build the evaluation prompt for Claude."""

        # Get type-specific criteria
        criteria = self.criteria.get_criteria_for_type(explanation_type)

        prompt = f"""You are an expert in compiler technology and technical education.
Your task is to evaluate an AI-generated explanation of Compiler Explorer's output using our metrics.

## Context

The user provided this source code:
```
{source_code}
```

Which compiled to this assembly:
```
{assembly_code}
```

## The AI's Explanation to Evaluate

{explanation}

## Evaluation Context

We assume the user is aware of which compiler they've selected, and if they have provided
command-line parameters, they are aware what those do. Similarly they know the architecture
they've selected and so there is no need to repeat any of this information unless it is
critical to a point that needs to be made later on.

Target audience: {audience.value}
{_AUDIENCE_LEVEL[audience]}

Explanation type: {explanation_type.value}
{_EXPLANATION_TYPE[explanation_type]}

Test case description: {test_case.get("description", "No description provided")}

## METRICS SYSTEM

Evaluate the explanation on these 5 dimensions:

1. **Accuracy (0-100)**
{criteria["accuracy"]}

2. **Relevance (0-100)**
{criteria["relevance"]}

3. **Conciseness (0-100)**
{criteria["conciseness"]}

4. **Insight (0-100)**
{criteria["insight"]}

5. **Appropriateness (0-100)**
{criteria["appropriateness"]}

"""

        # Add test case specific context if available
        if test_case.get("common_mistakes"):
            prompt += f"""
## Common Mistakes to Watch For
This test case commonly produces these mistakes: {", ".join(test_case["common_mistakes"])}
Check if the explanation falls into any of these traps.

"""

        prompt += f"""
## Response Format

{"First, think through your evaluation step by step." if self.enable_thinking else ""}

Then provide your evaluation in this exact JSON format:
```json
{{
    "scores": {{
        "accuracy": <0-100>,
        "relevance": <0-100>,
        "conciseness": <0-100>,
        "insight": <0-100>,
        "appropriateness": <0-100>
    }},
    "flags": ["Unverified technical claims", "Claims efficiency on unoptimized code", ...],
    "strengths": ["Correctly explains instruction behavior", "Good contextual relevance", ...],
    "overall_assessment": "A 1-2 sentence overall assessment"
}}
```
"""
        return prompt

    def evaluate_response(
        self,
        source_code: str,
        assembly_code: str,
        explanation: str,
        test_case: dict,
        audience: AudienceLevel,
        explanation_type: ExplanationType,
        token_count: int = 0,
        response_time_ms: int | None = None,
    ) -> EvaluationMetrics:
        """Evaluate a response using Claude."""

        evaluation_prompt = self._build_evaluation_prompt(
            source_code, assembly_code, explanation, test_case, audience, explanation_type
        )

        # Call Claude for evaluation
        message = self.client.messages.create(
            model=self.reviewer_model,
            max_tokens=2000,
            temperature=0.2,  # Lower temperature for more consistent evaluation
            system="You are a meticulous technical reviewer with expertise in compilers and education.",
            messages=[{"role": "user", "content": evaluation_prompt}],
        )

        # Parse the JSON response
        response_text = message.content[0].text

        # Extract JSON from the response (handle thinking output if present)
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1

        if json_start == -1 or json_end == 0:
            raise ValueError(f"No valid JSON found in Claude's response: {response_text[:200]}...")

        json_str = response_text[json_start:json_end]

        try:
            evaluation = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse Claude's evaluation response as JSON: {e}\nResponse: {json_str[:200]}..."
            ) from e

        # Convert Claude's 0-100 scores to 0-1 range
        if "scores" not in evaluation:
            raise ValueError(f"Missing 'scores' in evaluation response: {list(evaluation.keys())}")

        scores = evaluation["scores"]

        # Validate required score fields
        required_scores = ["accuracy", "relevance", "conciseness", "insight", "appropriateness"]
        missing_scores = [field for field in required_scores if field not in scores]
        if missing_scores:
            raise ValueError(f"Missing required scores: {missing_scores}")

        # Calculate overall score with new weights
        weights = {"accuracy": 0.3, "relevance": 0.25, "conciseness": 0.2, "insight": 0.15, "appropriateness": 0.1}
        overall_score = sum(scores[metric] * weights[metric] for metric in weights) / 100

        # Map to EvaluationMetrics format
        return EvaluationMetrics(
            accuracy=scores["accuracy"] / 100,
            relevance=scores["relevance"] / 100,
            conciseness=scores["conciseness"] / 100,
            insight=scores["insight"] / 100,
            appropriateness=scores["appropriateness"] / 100,
            overall_score=overall_score,
            token_count=token_count,
            response_time_ms=response_time_ms,
            flags=evaluation.get("flags"),
            strengths=evaluation.get("strengths"),
            notes=evaluation.get("overall_assessment"),
        )

    def _calculate_length_score(self, explanation: str, difficulty: str) -> float:
        """Simple length scoring (can be refined based on Claude's feedback)."""
        length = len(explanation)
        length_ranges = {"beginner": (150, 400), "intermediate": (200, 600), "advanced": (250, 800)}
        min_len, max_len = length_ranges.get(difficulty, (200, 600))

        if min_len <= length <= max_len:
            return 1.0
        if length < min_len:
            return max(0.3, length / min_len)
        return max(0.5, 1.0 - (length - max_len) / max_len)

    async def evaluate_response_async(
        self,
        source_code: str,
        assembly_code: str,
        explanation: str,
        test_case: dict,
        audience: AudienceLevel,
        explanation_type: ExplanationType,
        token_count: int = 0,
        response_time_ms: int | None = None,
    ) -> EvaluationMetrics:
        """Evaluate a response using Claude asynchronously."""

        evaluation_prompt = self._build_evaluation_prompt(
            source_code, assembly_code, explanation, test_case, audience, explanation_type
        )

        # Call Claude for evaluation asynchronously
        message = await self.async_client.messages.create(
            model=self.reviewer_model,
            max_tokens=2000,
            temperature=0.2,  # Lower temperature for more consistent evaluation
            system="You are a meticulous technical reviewer with expertise in compilers and education.",
            messages=[{"role": "user", "content": evaluation_prompt}],
        )

        # Parse the JSON response
        response_text = message.content[0].text

        # Extract JSON from the response (handle thinking output if present)
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1

        if json_start == -1 or json_end == 0:
            raise ValueError(f"No valid JSON found in Claude's response: {response_text[:200]}...")

        json_str = response_text[json_start:json_end]

        try:
            evaluation = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse Claude's evaluation response as JSON: {e}\nResponse: {json_str[:200]}..."
            ) from e

        # Convert Claude's 0-100 scores to 0-1 range
        if "scores" not in evaluation:
            raise ValueError(f"Missing 'scores' in evaluation response: {list(evaluation.keys())}")

        scores = evaluation["scores"]

        # Validate required score fields
        required_scores = ["accuracy", "relevance", "conciseness", "insight", "appropriateness"]
        missing_scores = [field for field in required_scores if field not in scores]
        if missing_scores:
            raise ValueError(f"Missing required scores: {missing_scores}")

        # Calculate overall score with new weights
        weights = {"accuracy": 0.3, "relevance": 0.25, "conciseness": 0.2, "insight": 0.15, "appropriateness": 0.1}
        overall_score = sum(scores[metric] * weights[metric] for metric in weights) / 100

        # Map to EvaluationMetrics format
        return EvaluationMetrics(
            accuracy=scores["accuracy"] / 100,
            relevance=scores["relevance"] / 100,
            conciseness=scores["conciseness"] / 100,
            insight=scores["insight"] / 100,
            appropriateness=scores["appropriateness"] / 100,
            overall_score=overall_score,
            token_count=token_count,
            response_time_ms=response_time_ms,
            flags=evaluation.get("flags"),
            strengths=evaluation.get("strengths"),
            notes=evaluation.get("overall_assessment"),
        )
