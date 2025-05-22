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

    def create_review_interface(self, case_id: str, responses: dict[str, dict]) -> str:
        """Create an HTML interface for reviewing multiple responses to the same case."""

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Review Interface - {case_id}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .response-container {{ border: 1px solid #ccc; margin: 20px 0; padding: 20px; }}
                .response-header {{ background-color: #f5f5f5; padding: 10px; margin: -20px -20px 20px -20px; }}
                .code-block {{ background-color: #f8f8f8; padding: 10px; margin: 10px 0; font-family: monospace; }}
                .metrics {{ background-color: #e8f4f8; padding: 10px; margin: 10px 0; }}
                .review-form {{ background-color: #fff8dc; padding: 15px; margin: 20px 0; }}
                .score-input {{ width: 50px; }}
                textarea {{ width: 100%; min-height: 60px; }}
                button {{ background-color: #4CAF50; color: white; padding: 10px 20px; border: none; cursor: pointer; }}
            </style>
        </head>
        <body>
            <h1>Review Interface: {case_id}</h1>
        """

        # Add test case details
        html += f"""
            <div class="response-container">
                <div class="response-header">
                    <h2>Test Case Details</h2>
                </div>
                <p><strong>Case ID:</strong> {case_id}</p>
                <!-- Add more test case details here -->
            </div>
        """

        # Add each response
        for version, response_data in responses.items():
            response_text = response_data.get("response", "No response")
            metrics = response_data.get("metrics", {})

            html += f"""
                <div class="response-container">
                    <div class="response-header">
                        <h2>Prompt Version: {version}</h2>
                    </div>

                    <h3>Response:</h3>
                    <div class="code-block">{response_text}</div>

                    <h3>Automatic Metrics:</h3>
                    <div class="metrics">
                        <p><strong>Overall Score:</strong> {metrics.get("overall_score", "N/A"):.2f}</p>
                        <p><strong>Accuracy:</strong> {metrics.get("accuracy_score", "N/A"):.2f}</p>
                        <p><strong>Clarity:</strong> {metrics.get("clarity_score", "N/A"):.2f}</p>
                        <p><strong>Token Count:</strong> {metrics.get("token_count", "N/A")}</p>
                    </div>

                    <div class="review-form">
                        <h3>Human Review</h3>
                        <form>
                            <p>
                                <label>Accuracy (1-5): <input type="number" min="1" max="5" class="score-input" name="accuracy_{version}"></label>
                                <label>Clarity (1-5): <input type="number" min="1" max="5" class="score-input" name="clarity_{version}"></label>
                                <label>Completeness (1-5): <input type="number" min="1" max="5" class="score-input" name="completeness_{version}"></label>
                                <label>Educational Value (1-5): <input type="number" min="1" max="5" class="score-input" name="educational_{version}"></label>
                            </p>
                            <p>
                                <label>Strengths:<br><textarea name="strengths_{version}" placeholder="What does this response do well?"></textarea></label>
                            </p>
                            <p>
                                <label>Weaknesses:<br><textarea name="weaknesses_{version}" placeholder="What could be improved?"></textarea></label>
                            </p>
                            <p>
                                <label>Suggestions:<br><textarea name="suggestions_{version}" placeholder="Specific suggestions for improvement"></textarea></label>
                            </p>
                            <p>
                                <label>Overall Comments:<br><textarea name="comments_{version}" placeholder="General feedback"></textarea></label>
                            </p>
                            <button type="button" onclick="saveReview('{version}')">Save Review</button>
                        </form>
                    </div>
                </div>
            """

        # Add comparison section
        if len(responses) > 1:
            version_options = "\n".join(f'<option value="{v}">{v}</option>' for v in responses)
            html += f"""
                <div class="response-container">
                    <div class="response-header">
                        <h2>Comparison</h2>
                    </div>
                    <p>
                        <label>Which version is better overall?</label><br>
                        <select name="preference">
                            <option value="">Select...</option>
                            {version_options}
                            <option value="similar">About the same</option>
                        </select>
                    </p>
                    <p>
                        <label>Why?<br><textarea name="preference_reason" placeholder="Explain your preference"></textarea></label>
                    </p>
                </div>
            """

        html += """
            <script>
                function saveReview(version) {
                    // In a real implementation, this would submit the review data
                    // For now, just show an alert
                    alert('Review for ' + version + ' would be saved');
                }
            </script>
        </body>
        </html>
        """

        return html

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
