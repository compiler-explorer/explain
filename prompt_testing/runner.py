"""
Main test runner for prompt evaluation.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv
from ruamel.yaml import YAML

from app.explain import MAX_TOKENS, MODEL, prepare_structured_data
from app.explain_api import AssemblyItem, ExplainRequest
from app.explanation_types import AudienceLevel, ExplanationType
from app.metrics import NoopMetricsProvider
from prompt_testing.evaluation.claude_reviewer import ClaudeReviewer, HybridScorer
from prompt_testing.evaluation.scorer import AutomaticScorer, load_all_test_cases

# Load environment variables from .env file
load_dotenv()


class PromptTester:
    """Main class for running prompt tests."""

    def __init__(
        self,
        project_root: str,
        anthropic_api_key: str | None = None,
        scorer_type: str = "automatic",  # "automatic", "claude", or "hybrid"
        claude_sample_rate: float = 0.2,
        reviewer_model: str = "claude-sonnet-4-0",
    ):
        self.project_root = Path(project_root)
        self.prompt_dir = self.project_root / "prompt_testing" / "prompts"
        self.test_cases_dir = self.project_root / "prompt_testing" / "test_cases"
        self.results_dir = self.project_root / "prompt_testing" / "results"

        # Initialize Anthropic client
        if anthropic_api_key:
            self.client = Anthropic(api_key=anthropic_api_key)
        else:
            self.client = Anthropic()  # Will use ANTHROPIC_API_KEY env var

        # Initialize scorer based on type
        self.scorer_type = scorer_type
        if scorer_type == "automatic":
            self.scorer = AutomaticScorer()
        elif scorer_type == "claude":
            self.scorer = ClaudeReviewer(anthropic_api_key=anthropic_api_key, reviewer_model=reviewer_model)
        elif scorer_type == "hybrid":
            self.scorer = HybridScorer(
                use_claude_for_all=False, claude_sample_rate=claude_sample_rate, anthropic_api_key=anthropic_api_key
            )
        else:
            raise ValueError(f"Unknown scorer type: {scorer_type}")

        self.metrics_provider = NoopMetricsProvider()  # Use noop provider for testing

    def load_prompt(self, prompt_version: str) -> dict[str, Any]:
        """Load a prompt configuration from YAML file."""
        prompt_file = self.prompt_dir / f"{prompt_version}.yaml"
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

        yaml = YAML(typ="safe")
        with prompt_file.open(encoding="utf-8") as f:
            return yaml.load(f)

    def convert_test_case_to_request(self, test_case: dict[str, Any]) -> ExplainRequest:
        """Convert a test case to an ExplainRequest object."""
        input_data = test_case["input"]

        # Convert assembly to AssemblyItem objects
        asm_items = []
        for asm_dict in input_data["asm"]:
            asm_items.append(AssemblyItem(**asm_dict))

        # Get audience and explanation type from test case, with defaults
        audience = test_case.get("audience", "beginner")
        if isinstance(audience, str):
            audience = AudienceLevel(audience)

        explanation = test_case.get("explanation_type", "assembly")
        if isinstance(explanation, str):
            explanation = ExplanationType(explanation)

        return ExplainRequest(
            language=input_data["language"],
            compiler=input_data["compiler"],
            compilationOptions=input_data.get("compilationOptions", []),
            instructionSet=input_data.get("instructionSet"),
            code=input_data["code"],
            asm=asm_items,
            labelDefinitions=input_data.get("labelDefinitions", {}),
            audience=audience,
            explanation=explanation,
        )

    def _build_template_context(self, request: ExplainRequest) -> dict[str, Any]:
        """Build template context dictionary from request data for prompt formatting."""
        # Include variables that come directly from the ExplainRequest
        context = {
            "language": request.language,
            "arch": request.instructionSet or "unknown",
            "compiler": request.compiler,
            "audience": request.audience.value,
            "explanation_type": request.explanation.value,
        }

        # Add compilation options as a formatted string (directly from request)
        if request.compilationOptions:
            context["compilation_options"] = " ".join(request.compilationOptions)
        else:
            context["compilation_options"] = ""

        # Include boolean indicating if labels are present (from labelDefinitions field)
        context["has_labels"] = bool(request.labelDefinitions and request.labelDefinitions)

        # Get audience and explanation info from centralized definitions
        context["audience_guidance"] = request.audience.guidance
        context["explanation_focus"] = request.explanation.focus
        context["explanation_type_phrase"] = request.explanation.user_prompt_phrase

        return context

    def _format_assembly(self, asm_items: list[AssemblyItem]) -> str:
        """Format assembly items into a readable string for Claude review."""
        lines = []
        for item in asm_items:
            if item.text and item.text.strip():
                lines.append(item.text)
        return "\n".join(lines)

    def run_single_test(
        self, test_case: dict[str, Any], prompt_version: str, model: str = MODEL, max_tokens: int = MAX_TOKENS
    ) -> dict[str, Any]:
        """Run a single test case with the specified prompt."""

        case_id = test_case["id"]
        print(f"Running test case: {case_id} with prompt: {prompt_version}")

        # Load prompt configuration
        prompt_config = self.load_prompt(prompt_version)

        # Convert test case to request
        request = self.convert_test_case_to_request(test_case)

        # Prepare structured data (same as in explain.py)
        structured_data = prepare_structured_data(request)

        # Build template context from request data
        template_context = self._build_template_context(request)

        # Format prompts using template context
        system_prompt = prompt_config["system_prompt"].format(**template_context)
        user_prompt = prompt_config["user_prompt"].format(**template_context)
        assistant_prefill = prompt_config["assistant_prefill"].format(**template_context)

        # Call Claude API
        start_time = time.time()
        message = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": user_prompt,
                        },
                        {"type": "text", "text": json.dumps(structured_data)},
                    ],
                },
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": assistant_prefill,
                        },
                    ],
                },
            ],
        )

        response_time_ms = int((time.time() - start_time) * 1000)
        explanation = message.content[0].text.strip()

        # Extract token usage
        input_tokens = message.usage.input_tokens
        output_tokens = message.usage.output_tokens

        success = True
        error = None

        # Evaluate response
        if success:
            # Handle audience-specific expected topics
            expected_topics_by_audience = test_case.get("expected_topics_by_audience", {})
            if expected_topics_by_audience and request.audience.value in expected_topics_by_audience:
                expected_topics = expected_topics_by_audience[request.audience.value]
            else:
                # Fall back to general expected topics
                expected_topics = test_case.get("expected_topics", [])

            # Get difficulty for Claude reviewer (still uses it)
            difficulty = test_case.get("difficulty", "intermediate")

            # Different evaluation based on scorer type
            if self.scorer_type == "automatic":
                metrics = self.scorer.evaluate_response(
                    explanation,
                    expected_topics,
                    output_tokens,
                    response_time_ms,
                    audience=request.audience.value,
                    explanation_type=request.explanation.value,
                )
                scorer_method = "automatic"
            elif self.scorer_type == "claude":
                # Claude reviewer needs source and assembly code
                metrics = self.scorer.evaluate_response(
                    source_code=request.code,
                    assembly_code=self._format_assembly(request.asm),
                    explanation=explanation,
                    expected_topics=expected_topics,
                    difficulty=difficulty,
                    token_count=output_tokens,
                    response_time_ms=response_time_ms,
                )
                scorer_method = "claude"
            elif self.scorer_type == "hybrid":
                # Hybrid scorer decides which method to use
                metrics, scorer_method = self.scorer.evaluate_response(
                    source_code=request.code,
                    assembly_code=self._format_assembly(request.asm),
                    explanation=explanation,
                    expected_topics=expected_topics,
                    difficulty=difficulty,
                    token_count=output_tokens,
                    response_time_ms=response_time_ms,
                    case_id=case_id,
                )
            else:
                metrics = None
                scorer_method = "none"
        else:
            metrics = None
            scorer_method = "none"

        return {
            "case_id": case_id,
            "prompt_version": prompt_version,
            "model": model,
            "success": success,
            "error": error,
            "response": explanation,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "response_time_ms": response_time_ms,
            "metrics": metrics.__dict__ if metrics else None,
            "scorer_method": scorer_method,
            "timestamp": datetime.now().isoformat(),
        }

    def run_test_suite(
        self,
        prompt_version: str,
        test_cases: list[str] | None = None,
        categories: list[str] | None = None,
        audience: str | None = None,
        explanation_type: str | None = None,
    ) -> dict[str, Any]:
        """Run a full test suite with the specified prompt version."""

        # Load all test cases
        all_cases = load_all_test_cases(str(self.test_cases_dir))

        # Filter test cases if specified
        if test_cases:
            all_cases = [case for case in all_cases if case["id"] in test_cases]

        if categories:
            all_cases = [case for case in all_cases if case["category"] in categories]

        if audience:
            all_cases = [case for case in all_cases if case.get("audience") == audience]

        if explanation_type:
            all_cases = [case for case in all_cases if case.get("explanation_type") == explanation_type]

        if not all_cases:
            raise ValueError("No test cases found matching the specified criteria")

        print(f"Running {len(all_cases)} test cases with prompt version: {prompt_version}")

        results = []
        for case in all_cases:
            result = self.run_single_test(case, prompt_version)
            results.append(result)

            # Print progress
            if result["success"]:
                metrics = result["metrics"]
                if metrics:
                    print(f"  ✓ {result['case_id']}: {metrics['overall_score']:.2f}")
                else:
                    print(f"  ✓ {result['case_id']}: completed")
            else:
                print(f"  ✗ {result['case_id']}: {result['error']}")

        # Calculate summary statistics
        successful_results = [r for r in results if r["success"]]
        summary = {
            "prompt_version": prompt_version,
            "total_cases": len(results),
            "successful_cases": len(successful_results),
            "failed_cases": len(results) - len(successful_results),
            "success_rate": len(successful_results) / len(results) if results else 0,
            "timestamp": datetime.now().isoformat(),
        }

        if successful_results:
            # Calculate average metrics
            all_metrics = [r["metrics"] for r in successful_results if r["metrics"]]
            if all_metrics:
                summary["average_metrics"] = {
                    "overall_score": sum(m["overall_score"] for m in all_metrics) / len(all_metrics),
                    "accuracy_score": sum(m["accuracy_score"] for m in all_metrics) / len(all_metrics),
                    "clarity_score": sum(m["clarity_score"] for m in all_metrics) / len(all_metrics),
                    "technical_accuracy": sum(m["technical_accuracy"] for m in all_metrics) / len(all_metrics),
                    "average_tokens": sum(m["token_count"] for m in all_metrics) / len(all_metrics),
                    "average_response_time": sum(m["response_time_ms"] or 0 for m in all_metrics) / len(all_metrics),
                }

        return {"summary": summary, "results": results}

    def save_results(self, test_results: dict[str, Any], output_file: str | None = None) -> str:
        """Save test results to a timestamped file."""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            prompt_version = test_results["summary"]["prompt_version"]
            output_file = f"{timestamp}_{prompt_version}.json"

        output_path = self.results_dir / output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w") as f:
            json.dump(test_results, f, indent=2)

        print(f"Results saved to: {output_path}")
        return str(output_path)

    def compare_prompt_versions(
        self, version1: str, version2: str, test_cases: list[str] | None = None
    ) -> dict[str, Any]:
        """Compare two prompt versions on the same test cases."""

        print(f"Comparing prompt versions: {version1} vs {version2}")

        results1 = self.run_test_suite(version1, test_cases)
        results2 = self.run_test_suite(version2, test_cases)

        # Create comparison
        comparison = {
            "version1": version1,
            "version2": version2,
            "summary1": results1["summary"],
            "summary2": results2["summary"],
            "case_comparisons": [],
        }

        # Compare individual cases
        results1_by_id = {r["case_id"]: r for r in results1["results"]}
        results2_by_id = {r["case_id"]: r for r in results2["results"]}

        for case_id in set(results1_by_id.keys()) & set(results2_by_id.keys()):
            r1 = results1_by_id[case_id]
            r2 = results2_by_id[case_id]

            case_comparison = {
                "case_id": case_id,
                "version1_success": r1["success"],
                "version2_success": r2["success"],
            }

            if r1["success"] and r2["success"] and r1["metrics"] and r2["metrics"]:
                m1 = r1["metrics"]
                m2 = r2["metrics"]
                case_comparison.update(
                    {
                        "score_difference": m2["overall_score"] - m1["overall_score"],
                        "version1_score": m1["overall_score"],
                        "version2_score": m2["overall_score"],
                        "better_version": version2 if m2["overall_score"] > m1["overall_score"] else version1,
                        "accuracy_difference": m2["accuracy_score"] - m1["accuracy_score"],
                        "clarity_difference": m2["clarity_score"] - m1["clarity_score"],
                    }
                )

            comparison["case_comparisons"].append(case_comparison)

        return comparison


def main():
    """Simple CLI interface for running tests."""
    import argparse

    parser = argparse.ArgumentParser(description="Run prompt tests")
    parser.add_argument("--prompt", required=True, help="Prompt version to test")
    parser.add_argument("--cases", nargs="*", help="Specific test case IDs to run")
    parser.add_argument("--categories", nargs="*", help="Test case categories to run")
    parser.add_argument("--compare", help="Compare with another prompt version")
    parser.add_argument("--output", help="Output file name")

    # Scorer configuration
    parser.add_argument(
        "--scorer",
        choices=["automatic", "claude", "hybrid"],
        default="automatic",
        help="Scoring method: automatic (regex), claude (AI review), or hybrid",
    )
    parser.add_argument(
        "--claude-sample-rate",
        type=float,
        default=0.2,
        help="For hybrid scorer: fraction of cases to evaluate with Claude (0.0-1.0)",
    )
    parser.add_argument(
        "--reviewer-model",
        default="claude-3-sonnet-20241022",
        help="Claude model to use for reviewing (e.g., claude-3-opus-20240229)",
    )

    args = parser.parse_args()

    # Get project root (assuming script is run from project root)
    project_root = str(Path.cwd())

    tester = PromptTester(
        project_root,
        scorer_type=args.scorer,
        claude_sample_rate=args.claude_sample_rate,
        reviewer_model=args.reviewer_model,
    )

    if args.compare:
        results = tester.compare_prompt_versions(args.prompt, args.compare, args.cases)
        output_file = args.output or f"comparison_{args.prompt}_vs_{args.compare}.json"
    else:
        results = tester.run_test_suite(args.prompt, args.cases, args.categories)
        output_file = args.output

    tester.save_results(results, output_file)

    # Print summary
    if "summary" in results:
        summary = results["summary"]
        print("\nSummary:")
        print(f"  Success rate: {summary['success_rate']:.1%}")
        if "average_metrics" in summary:
            avg = summary["average_metrics"]
            print(f"  Average score: {avg['overall_score']:.2f}")
            print(f"  Average tokens: {avg['average_tokens']:.0f}")


if __name__ == "__main__":
    main()
