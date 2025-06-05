"""
Flask web interface for interactive prompt review.
"""

import json
import webbrowser
from datetime import datetime
from pathlib import Path
from threading import Timer

from flask import Flask, jsonify, render_template, request

from prompt_testing.evaluation.reviewer import HumanReview, ReviewManager
from prompt_testing.evaluation.scorer import load_all_test_cases


class ReviewWebServer:
    """Web server for interactive prompt review."""

    def __init__(self, project_root: str, port: int = 5000):
        self.project_root = Path(project_root)
        self.results_dir = self.project_root / "prompt_testing" / "results"
        self.test_cases_dir = self.project_root / "prompt_testing" / "test_cases"
        self.review_manager = ReviewManager(str(self.results_dir))
        self.port = port

        # Load test cases for enriching results with original data
        self.test_cases = {}
        try:
            all_cases = load_all_test_cases(str(self.test_cases_dir))
            for case in all_cases:
                self.test_cases[case["id"]] = case
        except Exception:
            # If test cases can't be loaded, continue without enrichment
            pass

        template_dir = Path(__file__).parent / "templates"
        self.app = Flask(__name__, template_folder=str(template_dir))
        self.app.json.compact = False  # Pretty print JSON responses

        self._setup_routes()

    def _enrich_result_with_test_case(self, result: dict) -> dict:
        """Enrich a result with test case information."""
        case_id = result.get("case_id")
        if case_id and case_id in self.test_cases:
            test_case = self.test_cases[case_id]
            input_data = test_case.get("input", {})

            # Add test case metadata to the result
            result["test_case"] = {
                "language": input_data.get("language", "Unknown"),
                "compiler": input_data.get("compiler", "Unknown"),
                "compilation_options": input_data.get("compilationOptions", []),
                "instruction_set": input_data.get("instructionSet", "Unknown"),
                "source_code": input_data.get("code", ""),
                "assembly": input_data.get("asm", []),
                "description": test_case.get("description", ""),
                "category": test_case.get("category", ""),
                "quality": test_case.get("quality", ""),
                "audience": test_case.get("audience", "beginner"),
                "explanation_type": test_case.get("explanation_type", "assembly"),
            }
        else:
            # Fallback if test case not found
            result["test_case"] = {
                "language": "Unknown",
                "compiler": "Unknown",
                "compilation_options": [],
                "instruction_set": "Unknown",
                "source_code": "",
                "assembly": [],
                "description": f"Test case {case_id}",
                "category": "",
                "quality": "",
                "audience": "beginner",
                "explanation_type": "assembly",
            }
        return result

    def _get_result_description(self, summary: dict, filename: str) -> str:
        """Generate a descriptive label for a result file."""
        prompt_version = summary.get("prompt_version", "unknown")
        total_cases = summary.get("total_cases", 0)

        # Better description based on prompt version
        if prompt_version == "current":
            prompt_desc = "Current Production Prompt"
        elif "baseline" in prompt_version:
            prompt_desc = f"Baseline Prompt ({prompt_version})"
        elif "improved" in prompt_version:
            prompt_desc = f"Improved Prompt ({prompt_version})"
        else:
            prompt_desc = prompt_version.replace("_", " ").title()

        # Add context from filename
        if "comparison" in filename:
            prompt_desc = f"Comparison: {prompt_desc}"

        return f"{prompt_desc} - {total_cases} cases"

    def _setup_routes(self):
        """Set up Flask routes."""

        @self.app.route("/")
        def index():
            """Main review interface."""
            return render_template("index.html")

        @self.app.route("/api/results")
        def list_results():
            """List available result files."""
            if not self.results_dir.exists():
                return jsonify({"results": []})

            results = []
            for result_file in sorted(self.results_dir.glob("*.json"), reverse=True):
                if result_file.name.startswith("analysis_") or result_file.name.startswith("human_"):
                    continue

                try:
                    with result_file.open() as f:
                        data = json.load(f)

                    summary = data.get("summary", {})

                    # Format timestamp for display
                    timestamp = summary.get("timestamp", "")
                    if timestamp:
                        try:
                            from datetime import datetime

                            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                            display_timestamp = dt.strftime("%m/%d/%Y %H:%M")
                        except Exception:
                            display_timestamp = timestamp[:10]  # Just date part
                    else:
                        display_timestamp = "Unknown"

                    results.append(
                        {
                            "file": result_file.name,
                            "prompt_version": summary.get("prompt_version", "unknown"),
                            "description": self._get_result_description(summary, result_file.name),
                            "timestamp": display_timestamp,
                            "success_rate": summary.get("success_rate", 0),
                            "total_cases": summary.get("total_cases", 0),
                            "average_score": summary.get("average_metrics", {}).get("overall_score", 0),
                        }
                    )
                except Exception:
                    continue

            return jsonify({"results": results})

        @self.app.route("/api/results/<filename>")
        def get_result_details(filename):
            """Get detailed results for a specific file."""
            result_file = self.results_dir / filename
            if not result_file.exists():
                return jsonify({"error": "Result file not found"}), 404

            try:
                with result_file.open() as f:
                    data = json.load(f)
                return jsonify(data)
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route("/review/<filename>")
        def review_results(filename):
            """Review interface for a specific result file."""
            result_file = self.results_dir / filename
            if not result_file.exists():
                return "Result file not found", 404

            try:
                with result_file.open() as f:
                    data = json.load(f)

                # Enrich results with test case information
                if "results" in data:
                    for result in data["results"]:
                        if result.get("success"):
                            self._enrich_result_with_test_case(result)

                return render_template("review.html", filename=filename, data=data)
            except Exception as e:
                return f"Error loading results: {e}", 500

        @self.app.route("/api/review", methods=["POST"])
        def save_review():
            """Save a human review."""
            try:
                review_data = request.json

                # Create HumanReview object
                review = HumanReview(
                    case_id=review_data["case_id"],
                    prompt_version=review_data["prompt_version"],
                    reviewer=review_data["reviewer"],
                    timestamp=datetime.now().isoformat(),
                    accuracy=int(review_data["accuracy"]),
                    relevance=int(review_data["relevance"]),
                    conciseness=int(review_data["conciseness"]),
                    insight=int(review_data["insight"]),
                    appropriateness=int(review_data["appropriateness"]),
                    strengths=[s.strip() for s in review_data.get("strengths", "").split("\n") if s.strip()],
                    weaknesses=[w.strip() for w in review_data.get("weaknesses", "").split("\n") if w.strip()],
                    suggestions=[s.strip() for s in review_data.get("suggestions", "").split("\n") if s.strip()],
                    overall_comments=review_data.get("overall_comments", ""),
                    compared_to=review_data.get("compared_to"),
                    preference=review_data.get("preference"),
                    preference_reason=review_data.get("preference_reason"),
                )

                # Save review
                self.review_manager.save_review(review)

                return jsonify({"success": True, "message": "Review saved successfully"})

            except Exception as e:
                return jsonify({"success": False, "error": str(e)}), 500

        @self.app.route("/api/reviews/<case_id>")
        def get_reviews(case_id):
            """Get existing reviews for a case."""
            reviews = self.review_manager.load_reviews(case_id=case_id)
            return jsonify({"reviews": [review.__dict__ for review in reviews]})

        @self.app.route("/api/reviews/prompt/<prompt_version>")
        def get_reviews_for_prompt(prompt_version):
            """Get all existing reviews for a specific prompt version."""
            reviews = self.review_manager.load_reviews(prompt_version=prompt_version)
            # Group reviews by case_id for easier frontend consumption
            reviews_by_case = {}
            for review in reviews:
                reviews_by_case[review.case_id] = review.__dict__
            return jsonify({"reviews_by_case": reviews_by_case, "total_reviews": len(reviews)})

    def start(self, open_browser: bool = True):
        """Start the web server."""
        if open_browser:
            # Open browser after a short delay
            Timer(1.0, lambda: webbrowser.open(f"http://localhost:{self.port}")).start()

        print(f"🚀 Review interface starting at http://localhost:{self.port}")
        print("Press Ctrl+C to stop the server")

        self.app.run(host="127.0.0.1", port=self.port, debug=False)


def start_review_server(project_root: str, port: int = 5000, open_browser: bool = True):
    """Start the review web server."""
    server = ReviewWebServer(project_root, port)
    server.start(open_browser)
