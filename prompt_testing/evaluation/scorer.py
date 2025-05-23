"""
Scoring and evaluation system for prompt testing.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class EvaluationMetrics:
    """Metrics for evaluating a single response."""

    accuracy_score: float  # 0-1, how well it covers expected topics
    clarity_score: float  # 0-1, readability and educational value
    completeness_score: float  # 0-1, covers all relevant aspects
    consistency_score: float  # 0-1, consistent with similar cases
    length_score: float  # 0-1, appropriate length (not too verbose/brief)
    technical_accuracy: float  # 0-1, technical correctness

    overall_score: float  # Weighted combination of above

    # Additional metrics
    token_count: int
    response_time_ms: int | None = None

    # Detailed feedback
    missing_topics: list[str] | None = None
    incorrect_claims: list[str] | None = None
    notes: str | None = None


class AutomaticScorer:
    """Automatic scoring based on keyword matching and heuristics."""

    def __init__(self):
        # Define keyword patterns for different technical concepts
        self.topic_patterns = {
            "loop_optimization": [
                r"\bloop\s+optimization\b",
                r"\bvectorization\b",
                r"\bunrolling\b",
                r"\bSIMD\b",
                r"\bSSE\b",
                r"\bAVX\b",
            ],
            "function_inlining": [r"\binlin(e|ing)\b", r"\bfunction\s+call\s+eliminated\b", r"\bcall\s+overhead\b"],
            "constant_folding": [
                r"\bconstant\s+fold(ing)?\b",
                r"\bcompile.?time\s+evaluation\b",
                r"\bconstant\s+propagation\b",
            ],
            "vectorization": [
                r"\bvectoriz(ed|ation)\b",
                r"\bSIMD\b",
                r"\bmovdqa\b",
                r"\baddps\b",
                r"\bXMM\b",
                r"\bYMM\b",
                r"\bparallel\s+processing\b",
            ],
            "branch_prediction": [
                r"\bbranch\s+predict(ion|or)\b",
                r"\blikely\b",
                r"\bunlikely\b",
                r"\b__builtin_expect\b",
            ],
            "memory_alignment": [r"\bmemory\s+alignment\b", r"\baligned\s+access\b", r"\bcache\s+line\b"],
            "register_allocation": [
                r"\bregister\s+allocation\b",
                r"\bregister\s+spill(ing)?\b",
                r"\bregister\s+pressure\b",
            ],
            "calling_convention": [
                r"\bcalling\s+convention\b",
                r"\bfunction\s+prologue\b",
                r"\bfunction\s+epilogue\b",
                r"\bstack\s+frame\b",
            ],
        }

        # Patterns that indicate technical inaccuracies
        self.inaccuracy_patterns = [
            r"\bbranch\s+predictor\s+will\s+always\b",  # Overly definitive claims
            r"\bcache\s+will\s+definitely\b",
            r"\bCPU\s+will\s+never\b",
            r"\bcompiler\s+always\s+does\b",
        ]

    def score_topic_coverage(self, response: str, expected_topics: list[str]) -> tuple[float, list[str]]:
        """Score how well the response covers expected topics."""
        response_lower = response.lower()
        covered_topics = []
        missing_topics = []

        for topic in expected_topics:
            if topic in self.topic_patterns:
                patterns = self.topic_patterns[topic]
                found = any(re.search(pattern, response_lower, re.IGNORECASE) for pattern in patterns)
                if found:
                    covered_topics.append(topic)
                else:
                    missing_topics.append(topic)
            else:
                # Fallback: simple keyword matching
                if topic.replace("_", " ") in response_lower:
                    covered_topics.append(topic)
                else:
                    missing_topics.append(topic)

        score = len(covered_topics) / len(expected_topics) if expected_topics else 1.0
        return score, missing_topics

    def score_technical_accuracy(self, response: str) -> tuple[float, list[str]]:
        """Check for technical inaccuracies."""
        incorrect_claims = []

        for pattern in self.inaccuracy_patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            incorrect_claims.extend(matches)

        # Deduct points for each inaccuracy
        penalty = min(0.2 * len(incorrect_claims), 1.0)
        score = max(0.0, 1.0 - penalty)

        return score, incorrect_claims

    def score_length_appropriateness(self, response: str, target_length_range: tuple[int, int] = (100, 800)) -> float:
        """Score based on response length appropriateness."""
        length = len(response)
        min_length, max_length = target_length_range

        if min_length <= length <= max_length:
            return 1.0
        if length < min_length:
            # Too short
            return max(0.0, length / min_length)
        # Too long - more gradual penalty
        excess = length - max_length
        penalty = min(0.5, excess / max_length)
        return max(0.0, 1.0 - penalty)

    def score_clarity(self, response: str, audience: str = "intermediate") -> float:
        """Heuristic scoring for clarity based on sentence structure and readability."""
        sentences = re.split(r"[.!?]+", response)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return 0.0

        # Check average sentence length (adjust based on audience)
        avg_sentence_length = sum(len(s.split()) for s in sentences) / len(sentences)

        # Beginners prefer shorter sentences, experts can handle longer ones
        audience_ranges = {"beginner": (10, 20), "intermediate": (15, 25), "expert": (15, 30)}
        min_len, max_len = audience_ranges.get(audience, (15, 25))

        length_score = 1.0
        if avg_sentence_length < min_len:
            length_score = avg_sentence_length / min_len
        elif avg_sentence_length > max_len:
            length_score = max(0.5, 1.0 - (avg_sentence_length - max_len) / 20)

        # Check for technical jargon balance (adjust based on audience)
        pattern = r"\b(?:register|instruction|optimization|assembly|compiler|CPU|cache|pipeline|vector|SIMD|branch)\b"
        technical_terms = len(re.findall(pattern, response, re.IGNORECASE))
        total_words = len(response.split())
        tech_ratio = technical_terms / max(total_words, 1)

        # Adjust technical term expectations by audience
        audience_tech_ranges = {
            "beginner": (0.02, 0.10),  # 2-10% technical terms
            "intermediate": (0.05, 0.15),  # 5-15% technical terms
            "expert": (0.08, 0.25),  # 8-25% technical terms
        }
        min_tech, max_tech = audience_tech_ranges.get(audience, (0.05, 0.15))

        tech_score = 1.0
        if tech_ratio < min_tech:
            tech_score = tech_ratio / min_tech
        elif tech_ratio > max_tech:
            tech_score = max(0.5, 1.0 - (tech_ratio - max_tech) / 0.10)

        # Check for explanatory language (important for beginners)
        if audience == "beginner":
            explanatory_patterns = [
                r"\bmeans?\b",
                r"\bwhich\s+is\b",
                r"\bin\s+other\s+words\b",
                r"\bthis\s+tells\b",
                r"\bbasically\b",
                r"\bsimply\s+put\b",
            ]
            explanatory_count = sum(len(re.findall(p, response, re.IGNORECASE)) for p in explanatory_patterns)
            explanation_score = min(1.0, explanatory_count / 3)  # Expect at least 3 explanatory phrases
            return (length_score + tech_score + explanation_score) / 3

        return (length_score + tech_score) / 2

    def evaluate_response(
        self,
        response: str,
        expected_topics: list[str],
        token_count: int,
        response_time_ms: int | None = None,
        audience: str = "intermediate",
        explanation_type: str = "assembly",
    ) -> EvaluationMetrics:
        """Perform complete automatic evaluation of a response."""

        # Score individual dimensions
        accuracy_score, missing_topics = self.score_topic_coverage(response, expected_topics)
        technical_accuracy, incorrect_claims = self.score_technical_accuracy(response)
        clarity_score = self.score_clarity(response, audience)

        # Adjust target length based on audience and explanation type
        # Beginners need more explanation, experts prefer conciseness
        # Source mapping explanations tend to be longer than pure assembly
        base_ranges = {"beginner": (100, 400), "intermediate": (150, 500), "expert": (120, 400)}

        # Adjust for explanation type
        if explanation_type == "source":
            # Source mapping explanations need more space
            base_min, base_max = base_ranges.get(audience, (150, 500))
            target_range = (int(base_min * 1.2), int(base_max * 1.2))
        elif explanation_type == "optimization":
            # Optimization explanations can be quite detailed
            base_min, base_max = base_ranges.get(audience, (150, 500))
            target_range = (int(base_min * 1.1), int(base_max * 1.3))
        else:
            # Assembly explanations
            target_range = base_ranges.get(audience, (150, 500))

        length_score = self.score_length_appropriateness(response, target_range)

        # For now, use accuracy as proxy for completeness and consistency
        # In a real system, you'd want more sophisticated metrics
        completeness_score = accuracy_score
        consistency_score = 0.8  # Placeholder - would need comparison with similar cases

        # Calculate weighted overall score
        weights = {
            "accuracy": 0.25,
            "technical_accuracy": 0.25,
            "clarity": 0.20,
            "completeness": 0.15,
            "length": 0.10,
            "consistency": 0.05,
        }

        overall_score = (
            weights["accuracy"] * accuracy_score
            + weights["technical_accuracy"] * technical_accuracy
            + weights["clarity"] * clarity_score
            + weights["completeness"] * completeness_score
            + weights["length"] * length_score
            + weights["consistency"] * consistency_score
        )

        return EvaluationMetrics(
            accuracy_score=accuracy_score,
            clarity_score=clarity_score,
            completeness_score=completeness_score,
            consistency_score=consistency_score,
            length_score=length_score,
            technical_accuracy=technical_accuracy,
            overall_score=overall_score,
            token_count=token_count,
            response_time_ms=response_time_ms,
            missing_topics=missing_topics if missing_topics else None,
            incorrect_claims=incorrect_claims if incorrect_claims else None,
        )


def load_test_case(file_path: str, case_id: str) -> dict[str, Any]:
    """Load a specific test case from a YAML file."""
    path = Path(file_path)
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    for case in data["cases"]:
        if case["id"] == case_id:
            return case

    raise ValueError(f"Test case {case_id} not found in {file_path}")


def load_all_test_cases(test_cases_dir: str) -> list[dict[str, Any]]:
    """Load all test cases from the test_cases directory."""
    all_cases = []
    test_dir = Path(test_cases_dir)

    for file_path in test_dir.glob("*.yaml"):
        with file_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
            all_cases.extend(data["cases"])

    return all_cases
