"""
Main test runner for prompt evaluation.
"""

import json
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from anthropic import Anthropic
from dotenv import load_dotenv

from app.explain import MAX_TOKENS, MODEL, prepare_structured_data
from app.explain_api import AssemblyItem, ExplainRequest
from app.metrics import NoopMetricsProvider
from prompt_testing.evaluation.scorer import AutomaticScorer, load_all_test_cases

# Load environment variables from .env file
load_dotenv()


class PromptTester:
    """Main class for running prompt tests."""

    def __init__(self, project_root: str, anthropic_api_key: str | None = None):
        self.project_root = Path(project_root)
        self.prompt_dir = self.project_root / "prompt_testing" / "prompts"
        self.test_cases_dir = self.project_root / "prompt_testing" / "test_cases"
        self.results_dir = self.project_root / "prompt_testing" / "results"

        # Initialize Anthropic client
        if anthropic_api_key:
            self.client = Anthropic(api_key=anthropic_api_key)
        else:
            self.client = Anthropic()  # Will use ANTHROPIC_API_KEY env var

        self.scorer = AutomaticScorer()
        self.metrics_provider = NoopMetricsProvider()  # Use noop provider for testing

    def load_prompt(self, prompt_version: str) -> dict[str, Any]:
        """Load a prompt configuration from YAML file."""
        prompt_file = self.prompt_dir / f"{prompt_version}.yaml"
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

        with prompt_file.open(encoding="utf-8") as f:
            return yaml.safe_load(f)

    def convert_test_case_to_request(self, test_case: dict[str, Any]) -> ExplainRequest:
        """Convert a test case to an ExplainRequest object."""
        input_data = test_case["input"]

        # Convert assembly to AssemblyItem objects
        asm_items = []
        for asm_dict in input_data["asm"]:
            asm_items.append(AssemblyItem(**asm_dict))

        return ExplainRequest(
            language=input_data["language"],
            compiler=input_data["compiler"],
            compilationOptions=input_data.get("compilationOptions", []),
            instructionSet=input_data.get("instructionSet"),
            code=input_data["code"],
            asm=asm_items,
            labelDefinitions=input_data.get("labelDefinitions", {}),
        )

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

        # Format prompts with language and architecture
        language = request.language
        arch = request.instructionSet or "unknown"

        system_prompt = prompt_config["system_prompt"].format(language=language, arch=arch)
        user_prompt = prompt_config["user_prompt"].format(arch=arch)
        assistant_prefill = prompt_config["assistant_prefill"]

        # Call Claude API
        start_time = time.time()
        try:
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

        except Exception as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            explanation = ""
            input_tokens = 0
            output_tokens = 0
            success = False
            error = str(e)
            # Log full exception details for debugging
            print(f"Error in API call for test case {case_id}: {e}")
            print(f"Full traceback:\n{traceback.format_exc()}")

        # Evaluate response
        if success:
            expected_topics = test_case.get("expected_topics", [])
            difficulty = test_case.get("difficulty", "intermediate")

            metrics = self.scorer.evaluate_response(
                explanation, expected_topics, difficulty, output_tokens, response_time_ms
            )
        else:
            metrics = None

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
            "timestamp": datetime.now().isoformat(),
        }

    def run_test_suite(
        self, prompt_version: str, test_cases: list[str] | None = None, categories: list[str] | None = None
    ) -> dict[str, Any]:
        """Run a full test suite with the specified prompt version."""

        # Load all test cases
        all_cases = load_all_test_cases(str(self.test_cases_dir))

        # Filter test cases if specified
        if test_cases:
            all_cases = [case for case in all_cases if case["id"] in test_cases]

        if categories:
            all_cases = [case for case in all_cases if case["category"] in categories]

        if not all_cases:
            raise ValueError("No test cases found matching the specified criteria")

        print(f"Running {len(all_cases)} test cases with prompt version: {prompt_version}")

        results = []
        for case in all_cases:
            try:
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

            except Exception as e:
                print(f"  ✗ {case['id']}: Unexpected error: {e}")
                print(f"Full traceback:\n{traceback.format_exc()}")
                results.append(
                    {
                        "case_id": case["id"],
                        "prompt_version": prompt_version,
                        "success": False,
                        "error": f"Unexpected error: {e}",
                        "timestamp": datetime.now().isoformat(),
                    }
                )

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

    args = parser.parse_args()

    # Get project root (assuming script is run from project root)
    project_root = str(Path.cwd())

    tester = PromptTester(project_root)

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
