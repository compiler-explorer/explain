"""
Human review tools for prompt evaluation.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class HumanReview:
    """Human review of a prompt response."""

    case_id: str
    prompt_version: str
    reviewer: str
    timestamp: str

    # Scores (1-5 scale)
    accuracy: int  # Technical correctness without false claims
    relevance: int  # Discusses actual code, recognizes optimization level
    conciseness: int  # Direct explanation without filler or boilerplate
    insight: int  # Explains WHY and provides actionable understanding
    appropriateness: int  # Matches audience level and explanation type

    # Qualitative feedback
    strengths: list[str]
    weaknesses: list[str]
    suggestions: list[str]
    overall_comments: str

    # Comparison (when reviewing multiple versions)
    compared_to: str | None = None
    preference: str | None = None  # 'this', 'other', 'similar'
    preference_reason: str | None = None


class ReviewManager:
    """Manages human reviews and creates comparison interfaces."""

    def __init__(self, results_dir: str | Path):
        self.results_dir = Path(results_dir)
        self.reviews_file = self.results_dir / "human_reviews.jsonl"

    def save_review(self, review: HumanReview) -> None:
        """Save a human review to the reviews file."""
        self.results_dir.mkdir(parents=True, exist_ok=True)

        with self.reviews_file.open("a") as f:
            f.write(json.dumps(asdict(review)) + "\n")

    def load_reviews(self, case_id: str | None = None, prompt_version: str | None = None) -> list[HumanReview]:
        """Load reviews, optionally filtered by case ID or prompt version."""
        if not self.reviews_file.exists():
            return []

        reviews = []
        with self.reviews_file.open() as f:
            for line in f:
                review_data = json.loads(line.strip())
                review = HumanReview(**review_data)

                if case_id and review.case_id != case_id:
                    continue
                if prompt_version and review.prompt_version != prompt_version:
                    continue

                reviews.append(review)

        return reviews

    def export_review_summary(self, output_file: str) -> None:
        """Export a summary of all reviews to a JSON file."""
        reviews = self.load_reviews()

        summary = {"total_reviews": len(reviews), "by_prompt_version": {}, "by_case": {}, "average_scores": {}}

        # Group by prompt version
        for review in reviews:
            version = review.prompt_version
            if version not in summary["by_prompt_version"]:
                summary["by_prompt_version"][version] = []
            summary["by_prompt_version"][version].append(asdict(review))

        # Group by case
        for review in reviews:
            case_id = review.case_id
            if case_id not in summary["by_case"]:
                summary["by_case"][case_id] = []
            summary["by_case"][case_id].append(asdict(review))

        # Calculate average scores
        if reviews:
            avg_accuracy = sum(r.accuracy for r in reviews) / len(reviews)
            avg_relevance = sum(r.relevance for r in reviews) / len(reviews)
            avg_conciseness = sum(r.conciseness for r in reviews) / len(reviews)
            avg_insight = sum(r.insight for r in reviews) / len(reviews)
            avg_appropriateness = sum(r.appropriateness for r in reviews) / len(reviews)

            summary["average_scores"] = {
                "accuracy": avg_accuracy,
                "relevance": avg_relevance,
                "conciseness": avg_conciseness,
                "insight": avg_insight,
                "appropriateness": avg_appropriateness,
            }

        output_path = Path(output_file)
        with output_path.open("w") as f:
            json.dump(summary, f, indent=2)


def create_simple_review_cli(case_id: str, response: str, prompt_version: str) -> HumanReview:
    """Create a simple CLI for reviewing a single response."""
    print(f"\n=== REVIEWING CASE: {case_id} ===")
    print(f"Prompt Version: {prompt_version}")
    print(f"\nResponse:\n{response}")
    print("\n" + "=" * 50)

    reviewer = input("Reviewer name: ").strip()

    print("\nPlease rate the following aspects (1-5 scale):")
    accuracy = int(input("Accuracy (technical correctness without false claims): "))
    relevance = int(input("Relevance (discusses actual code, recognizes optimization level): "))
    conciseness = int(input("Conciseness (direct explanation without filler): "))
    insight = int(input("Insight (explains WHY, provides actionable understanding): "))
    appropriateness = int(input("Appropriateness (matches audience level and explanation type): "))

    print("\nPlease provide qualitative feedback:")
    strengths = input("Strengths (comma-separated): ").split(",")
    strengths = [s.strip() for s in strengths if s.strip()]

    weaknesses = input("Weaknesses (comma-separated): ").split(",")
    weaknesses = [w.strip() for w in weaknesses if w.strip()]

    suggestions = input("Suggestions (comma-separated): ").split(",")
    suggestions = [s.strip() for s in suggestions if s.strip()]

    overall_comments = input("Overall comments: ").strip()

    return HumanReview(
        case_id=case_id,
        prompt_version=prompt_version,
        reviewer=reviewer,
        timestamp=datetime.now().isoformat(),
        accuracy=accuracy,
        relevance=relevance,
        conciseness=conciseness,
        insight=insight,
        appropriateness=appropriateness,
        strengths=strengths,
        weaknesses=weaknesses,
        suggestions=suggestions,
        overall_comments=overall_comments,
    )
