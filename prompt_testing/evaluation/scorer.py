"""
Metrics-based scoring system for prompt testing.
"""

from pathlib import Path
from typing import Any, ClassVar

from prompt_testing.yaml_utils import create_yaml_loader


def load_test_case(file_path: str, case_id: str) -> dict[str, Any]:
    """Load a specific test case from a YAML file."""
    path = Path(file_path)
    yaml = create_yaml_loader()
    with path.open(encoding="utf-8") as f:
        data = yaml.load(f)

    for case in data["cases"]:
        if case["id"] == case_id:
            return case

    raise ValueError(f"Test case {case_id} not found in {file_path}")


def load_all_test_cases(test_cases_dir: str) -> list[dict[str, Any]]:
    """Load all test cases from the test_cases directory."""
    all_cases = []
    test_dir = Path(test_cases_dir)
    yaml = create_yaml_loader()

    for file_path in test_dir.glob("*.yaml"):
        with file_path.open(encoding="utf-8") as f:
            data = yaml.load(f)
            all_cases.extend(data["cases"])

    return all_cases


class MetricsScorer:
    """New metrics-based scorer focusing on quality over topic coverage."""

    METRICS: ClassVar[dict[str, dict[str, str]]] = {
        "accuracy": {"name": "Accuracy", "description": "Technical correctness without false claims"},
        "relevance": {"name": "Relevance", "description": "Discusses actual code, recognizes optimization level"},
        "conciseness": {"name": "Conciseness", "description": "Direct explanation without filler or boilerplate"},
        "insight": {"name": "Insight", "description": "Explains WHY and provides actionable understanding"},
        "appropriateness": {"name": "Appropriateness", "description": "Matches audience level and explanation type"},
    }

    def calculate_automatic_score(self, explanation: str, test_case: dict[str, Any]) -> dict[str, Any]:
        """
        Basic heuristic scoring. Claude reviewer will provide the real scores.

        This is mainly for quick feedback and catching obvious issues.
        """
        scores = {}
        flags = []

        # Accuracy heuristics - check for common misleading patterns
        accuracy_score = 1.0
        misleading_patterns = [
            "likely leverages",  # Hedge words for made-up claims
            "compile-time optimization converts",  # Vague technical-sounding nonsense
            "might inline this function",  # Speculation without evidence
        ]
        for pattern in misleading_patterns:
            if pattern.lower() in explanation.lower():
                accuracy_score -= 0.3
                flags.append(f"Potentially misleading: '{pattern}'")

        scores["accuracy"] = max(0.0, accuracy_score)

        # Relevance heuristics - check for false optimization claims
        relevance_score = 1.0
        if (
            any(word in explanation.lower() for word in ["efficient", "optimized", "optimal"])
            and "unoptimized" not in test_case.get("description", "").lower()
        ):
            # If test case doesn't mention being unoptimized, this might be wrong
            relevance_score -= 0.2
            flags.append("Claims efficiency - check if code is actually optimized")

        scores["relevance"] = max(0.0, relevance_score)

        # Conciseness heuristics - check for boilerplate headers
        conciseness_score = 1.0
        boilerplate_patterns = [
            "architecture:",
            "optimization level:",
            "calling convention:",
            "microarchitectural observations:",
            "performance implications:",
        ]
        boilerplate_count = sum(1 for pattern in boilerplate_patterns if pattern.lower() in explanation.lower())
        if boilerplate_count > 0:
            conciseness_score -= boilerplate_count * 0.2
            flags.append(f"Found {boilerplate_count} boilerplate headers")

        scores["conciseness"] = max(0.0, conciseness_score)

        # Insight and appropriateness - hard to measure automatically
        # Default to neutral scores, let Claude reviewer handle these
        scores["insight"] = 0.6
        scores["appropriateness"] = 0.6

        # Calculate overall score as weighted average
        weights = {
            "accuracy": 0.3,  # Critical - false info is bad
            "relevance": 0.25,  # Very important - must match actual code
            "conciseness": 0.2,  # Important - avoid fluff
            "insight": 0.15,  # Nice to have - explains WHY
            "appropriateness": 0.1,  # Important but harder to measure
        }

        overall_score = sum(scores[metric] * weights[metric] for metric in scores)

        return {
            "overall_score": overall_score,
            "metric_scores": scores,
            "flags": flags,
            "scoring_method": "automatic_heuristics",
        }

    def get_metrics_definition(self) -> dict[str, Any]:
        """Return the metrics definition for use by Claude reviewer."""
        return self.METRICS


def calculate_scores(explanation: str, test_case: dict[str, Any]) -> dict[str, Any]:
    """Calculate scores for an explanation using the new metrics system."""
    scorer = MetricsScorer()
    return scorer.calculate_automatic_score(explanation, test_case)
