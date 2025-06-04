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
    accuracy: int  # How accurate is the technical content?
    clarity: int  # How clear and understandable is it?
    completeness: int  # Does it cover all important aspects?
    educational_value: int  # How helpful is it for learning?

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

    def __init__(self, results_dir: str):
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
            avg_clarity = sum(r.clarity for r in reviews) / len(reviews)
            avg_completeness = sum(r.completeness for r in reviews) / len(reviews)
            avg_educational = sum(r.educational_value for r in reviews) / len(reviews)

            summary["average_scores"] = {
                "accuracy": avg_accuracy,
                "clarity": avg_clarity,
                "completeness": avg_completeness,
                "educational_value": avg_educational,
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
    accuracy = int(input("Accuracy (technical correctness): "))
    clarity = int(input("Clarity (how understandable): "))
    completeness = int(input("Completeness (covers all aspects): "))
    educational = int(input("Educational value (helpful for learning): "))

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
        clarity=clarity,
        completeness=completeness,
        educational_value=educational,
        strengths=strengths,
        weaknesses=weaknesses,
        suggestions=suggestions,
        overall_comments=overall_comments,
    )
