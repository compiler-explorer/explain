"""
Claude-based AI reviewer for evaluating prompt responses.
Uses advanced models with constitutional AI principles.
"""

import json
from dataclasses import dataclass

from anthropic import Anthropic

from prompt_testing.evaluation.scorer import EvaluationMetrics


@dataclass
class ReviewCriteria:
    """Criteria for Claude to evaluate responses against."""

    technical_accuracy: str = """
    Evaluate the technical accuracy of the explanation:
    - Are the assembly instructions correctly explained?
    - Are compiler optimizations accurately described?
    - Are technical claims verifiable and correct?
    - Does it avoid oversimplifications that lead to inaccuracy?
    """

    educational_value: str = """
    Assess the educational value for someone learning about compilers:
    - Is the explanation at an appropriate level for the target audience?
    - Does it build understanding progressively?
    - Are complex concepts explained clearly?
    - Does it provide insight into why the compiler made certain choices?
    """

    clarity_structure: str = """
    Evaluate clarity and structure:
    - Is the explanation well-organized and easy to follow?
    - Are technical terms properly introduced before use?
    - Is the language clear and concise?
    - Does it avoid unnecessary jargon while maintaining precision?
    """

    completeness: str = """
    Assess completeness relative to the input:
    - Does it address all significant transformations in the assembly?
    - Are important optimizations explained?
    - Does it cover the key differences between source and assembly?
    - Is the scope appropriate (not too narrow or too broad)?
    """

    practical_insights: str = """
    Evaluate practical insights provided:
    - Does it help developers understand performance implications?
    - Are there actionable insights about writing better code?
    - Does it explain when/why certain optimizations occur?
    - Does it connect assembly behavior to source code patterns?
    """


class ClaudeReviewer:
    """Uses Claude to evaluate prompt responses with sophisticated analysis."""

    def __init__(
        self,
        anthropic_api_key: str | None = None,
        reviewer_model: str = "claude-sonnet-4-0",
        enable_thinking: bool = True,
    ):
        self.client = Anthropic(api_key=anthropic_api_key) if anthropic_api_key else Anthropic()
        self.reviewer_model = reviewer_model
        self.enable_thinking = enable_thinking
        self.criteria = ReviewCriteria()

    def _build_evaluation_prompt(
        self,
        source_code: str,
        assembly_code: str,
        explanation: str,
        expected_topics: list[str] | None = None,
        difficulty: str = "intermediate",
    ) -> str:
        """Build the evaluation prompt for Claude."""

        prompt = f"""You are an expert in compiler technology and technical education.
Your task is to evaluate an AI-generated explanation of compiler output.

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

## Evaluation Criteria

Please evaluate the explanation on these dimensions:

1. **Technical Accuracy (0-100)**
{self.criteria.technical_accuracy}

2. **Educational Value (0-100)**
{self.criteria.educational_value}

3. **Clarity and Structure (0-100)**
{self.criteria.clarity_structure}

4. **Completeness (0-100)**
{self.criteria.completeness}

5. **Practical Insights (0-100)**
{self.criteria.practical_insights}

"""

        if expected_topics:
            prompt += f"""
## Expected Topics
The explanation should cover these topics: {", ".join(expected_topics)}
Note which ones are missing or inadequately covered.

"""

        prompt += f"""
## Target Audience
This explanation is for a {difficulty} level audience.

## Response Format

{"First, think through your evaluation step by step." if self.enable_thinking else ""}

Then provide your evaluation in this exact JSON format:
```json
{{
    "scores": {{
        "technical_accuracy": <0-100>,
        "educational_value": <0-100>,
        "clarity_structure": <0-100>,
        "completeness": <0-100>,
        "practical_insights": <0-100>
    }},
    "strengths": ["strength1", "strength2", ...],
    "weaknesses": ["weakness1", "weakness2", ...],
    "missing_topics": ["topic1", "topic2", ...],
    "incorrect_claims": ["claim1", "claim2", ...],
    "suggestions": ["suggestion1", "suggestion2", ...],
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
        expected_topics: list[str] | None = None,
        difficulty: str = "intermediate",
        token_count: int = 0,
        response_time_ms: int | None = None,
    ) -> EvaluationMetrics:
        """Evaluate a response using Claude."""

        evaluation_prompt = self._build_evaluation_prompt(
            source_code, assembly_code, explanation, expected_topics, difficulty
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
        json_str = response_text[json_start:json_end]

        evaluation = json.loads(json_str)

        # Convert Claude's 0-100 scores to 0-1 range
        scores = evaluation["scores"]

        # Calculate overall score with weights
        overall_score = (
            scores["technical_accuracy"] * 0.30
            + scores["educational_value"] * 0.25
            + scores["clarity_structure"] * 0.20
            + scores["completeness"] * 0.15
            + scores["practical_insights"] * 0.10
        ) / 100

        # Map to EvaluationMetrics format
        return EvaluationMetrics(
            accuracy_score=scores["technical_accuracy"] / 100,
            clarity_score=scores["clarity_structure"] / 100,
            completeness_score=scores["completeness"] / 100,
            consistency_score=scores["educational_value"] / 100,  # Using educational value as proxy
            length_score=self._calculate_length_score(explanation, difficulty),
            technical_accuracy=scores["technical_accuracy"] / 100,
            overall_score=overall_score,
            token_count=token_count,
            response_time_ms=response_time_ms,
            missing_topics=evaluation.get("missing_topics"),
            incorrect_claims=evaluation.get("incorrect_claims"),
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


class HybridScorer:
    """Combines regex-based and Claude-based scoring for efficiency."""

    def __init__(
        self, use_claude_for_all: bool = False, claude_sample_rate: float = 0.2, anthropic_api_key: str | None = None
    ):
        from prompt_testing.evaluation.scorer import AutomaticScorer

        self.automatic_scorer = AutomaticScorer()
        self.claude_reviewer = ClaudeReviewer(anthropic_api_key=anthropic_api_key)
        self.use_claude_for_all = use_claude_for_all
        self.claude_sample_rate = claude_sample_rate

    def should_use_claude(self, case_id: str) -> bool:
        """Determine if Claude should be used for this case."""
        if self.use_claude_for_all:
            return True

        # Use hash of case_id for deterministic sampling
        import hashlib

        hash_val = int(hashlib.md5(case_id.encode()).hexdigest()[:8], 16)
        return (hash_val % 100) < (self.claude_sample_rate * 100)

    def evaluate_response(
        self,
        source_code: str,
        assembly_code: str,
        explanation: str,
        expected_topics: list[str],
        difficulty: str,
        token_count: int,
        response_time_ms: int | None = None,
        case_id: str | None = None,
    ) -> tuple[EvaluationMetrics, str]:
        """
        Evaluate using either automatic scorer or Claude reviewer.
        Returns (metrics, method_used).
        """
        if case_id and self.should_use_claude(case_id):
            metrics = self.claude_reviewer.evaluate_response(
                source_code, assembly_code, explanation, expected_topics, difficulty, token_count, response_time_ms
            )
            return metrics, "claude"

        # Use automatic scorer
        metrics = self.automatic_scorer.evaluate_response(
            explanation, expected_topics, difficulty, token_count, response_time_ms
        )
        return metrics, "automatic"
