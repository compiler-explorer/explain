"""
Main test runner for prompt evaluation.
"""

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from anthropic import Anthropic, AsyncAnthropic
from dotenv import load_dotenv

from app.explain_api import AssemblyItem, ExplainRequest
from app.explanation_types import AudienceLevel, ExplanationType
from app.metrics import NoopMetricsProvider
from app.prompt import Prompt
from prompt_testing.evaluation.claude_reviewer import ClaudeReviewer
from prompt_testing.evaluation.scorer import load_all_test_cases
from prompt_testing.file_utils import load_prompt_file, save_json_results

# Load environment variables from .env file
load_dotenv()


class PromptTester:
    """Main class for running prompt tests."""

    def __init__(
        self,
        project_root: str,
        anthropic_api_key: str | None = None,
        reviewer_model: str = "claude-sonnet-4-0",
        max_concurrent_requests: int = 5,
    ):
        self.project_root = Path(project_root)
        self.prompt_dir = self.project_root / "prompt_testing" / "prompts"
        self.test_cases_dir = self.project_root / "prompt_testing" / "test_cases"
        self.results_dir = self.project_root / "prompt_testing" / "results"

        # Initialize Anthropic clients (both sync and async)
        if anthropic_api_key:
            self.client = Anthropic(api_key=anthropic_api_key)
            self.async_client = AsyncAnthropic(api_key=anthropic_api_key)
        else:
            self.client = Anthropic()  # Will use ANTHROPIC_API_KEY env var
            self.async_client = AsyncAnthropic()

        # Initialize Claude reviewer
        self.scorer = ClaudeReviewer(anthropic_api_key=anthropic_api_key, reviewer_model=reviewer_model)

        self.metrics_provider = NoopMetricsProvider()  # Use noop provider for testing

        # Rate limiting
        self.max_concurrent_requests = max_concurrent_requests
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)

    def load_prompt(self, prompt_version: str) -> dict[str, Any]:
        """Load a prompt configuration from YAML file.

        Special case: 'current' loads from app/prompt.yaml
        """
        if prompt_version == "current":
            # Load the current production prompt from the app directory
            prompt_file = self.project_root / "app" / "prompt.yaml"
        else:
            prompt_file = self.prompt_dir / f"{prompt_version}.yaml"

        return load_prompt_file(prompt_file)

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

    def _format_assembly(self, asm_items: list[AssemblyItem]) -> str:
        """Format assembly items into a readable string for Claude review."""
        lines = []
        for item in asm_items:
            if item.text and item.text.strip():
                lines.append(item.text)
        return "\n".join(lines)

    async def run_single_test_async(
        self, test_case: dict[str, Any], prompt_version: str, model: str | None = None, max_tokens: int | None = None
    ) -> dict[str, Any]:
        """Run a single test case with the specified prompt asynchronously."""
        async with self.semaphore:  # Rate limiting
            case_id = test_case["id"]
            print(f"Running test case: {case_id} with prompt: {prompt_version}")

        # Load prompt configuration and create Prompt instance
        prompt_config = self.load_prompt(prompt_version)
        prompt = Prompt(prompt_config)

        # Convert test case to request
        request = self.convert_test_case_to_request(test_case)

        # Generate messages using Prompt instance
        prompt_data = prompt.generate_messages(request)

        # Use override model/max_tokens if provided, otherwise use prompt defaults
        if model is not None:
            prompt_data["model"] = model
        if max_tokens is not None:
            prompt_data["max_tokens"] = max_tokens

        # Call Claude API asynchronously
        start_time = time.time()
        message = await self.async_client.messages.create(
            model=prompt_data["model"],
            max_tokens=prompt_data["max_tokens"],
            temperature=prompt_data["temperature"],
            system=prompt_data["system"],
            messages=prompt_data["messages"],
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
            # Use Claude reviewer for evaluation (async version)
            metrics = await self.scorer.evaluate_response_async(
                source_code=request.code,
                assembly_code=self._format_assembly(request.asm),
                audience=request.audience,
                explanation_type=request.explanation,
                explanation=explanation,
                test_case=test_case,
                token_count=output_tokens,
                response_time_ms=response_time_ms,
            )
        else:
            metrics = None

        return {
            "case_id": case_id,
            "prompt_version": prompt_version,
            "model": prompt_data["model"],
            "success": success,
            "error": error,
            "response": explanation,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "response_time_ms": response_time_ms,
            "metrics": metrics.__dict__ if metrics else None,
            "timestamp": datetime.now().isoformat(),
        }

    def run_single_test(
        self, test_case: dict[str, Any], prompt_version: str, model: str | None = None, max_tokens: int | None = None
    ) -> dict[str, Any]:
        """Synchronous wrapper for backward compatibility."""
        return asyncio.run(self.run_single_test_async(test_case, prompt_version, model, max_tokens))

    async def run_test_suite_async(
        self,
        prompt_version: str,
        test_cases: list[str] | None = None,
        categories: list[str] | None = None,
        audience: str | None = None,
        explanation_type: str | None = None,
    ) -> dict[str, Any]:
        """Run a full test suite with the specified prompt version asynchronously."""

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

        print(
            f"Running {len(all_cases)} test cases with prompt version: {prompt_version} "
            f"(max {self.max_concurrent_requests} concurrent)"
        )

        # Create tasks for all test cases
        tasks = [self.run_single_test_async(case, prompt_version) for case in all_cases]

        # Run tasks concurrently with progress tracking
        results = []

        # Use asyncio.as_completed to get results as they finish
        for completed, coro in enumerate(asyncio.as_completed(tasks), 1):
            result = await coro
            results.append(result)

            # Print progress
            if result["success"]:
                metrics = result["metrics"]
                if metrics:
                    print(f"  [{completed}/{len(all_cases)}] ✓ {result['case_id']}: {metrics['overall_score']:.2f}")
                else:
                    print(f"  [{completed}/{len(all_cases)}] ✓ {result['case_id']}: completed")
            else:
                print(f"  [{completed}/{len(all_cases)}] ✗ {result['case_id']}: {result['error']}")

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
                    "accuracy": sum(m["accuracy"] for m in all_metrics) / len(all_metrics),
                    "relevance": sum(m["relevance"] for m in all_metrics) / len(all_metrics),
                    "conciseness": sum(m["conciseness"] for m in all_metrics) / len(all_metrics),
                    "insight": sum(m["insight"] for m in all_metrics) / len(all_metrics),
                    "appropriateness": sum(m["appropriateness"] for m in all_metrics) / len(all_metrics),
                    "average_tokens": sum(m["token_count"] for m in all_metrics) / len(all_metrics),
                    "average_response_time": sum(m["response_time_ms"] or 0 for m in all_metrics) / len(all_metrics),
                }

        return {"summary": summary, "results": results}

    def run_test_suite(
        self,
        prompt_version: str,
        test_cases: list[str] | None = None,
        categories: list[str] | None = None,
        audience: str | None = None,
        explanation_type: str | None = None,
    ) -> dict[str, Any]:
        """Synchronous wrapper for backward compatibility."""
        return asyncio.run(
            self.run_test_suite_async(prompt_version, test_cases, categories, audience, explanation_type)
        )

    def save_results(self, test_results: dict[str, Any], output_file: str | None = None) -> str:
        """Save test results to a timestamped file."""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            prompt_version = test_results["summary"]["prompt_version"]
            output_file = f"{timestamp}_{prompt_version}.json"

        output_path = self.results_dir / output_file
        save_json_results(test_results, output_path)
        print(f"Results saved to: {output_path}")
        return str(output_path)

    async def compare_prompt_versions_async(
        self, version1: str, version2: str, test_cases: list[str] | None = None
    ) -> dict[str, Any]:
        """Compare two prompt versions on the same test cases asynchronously."""

        print(f"Comparing prompt versions: {version1} vs {version2}")

        # Run both test suites concurrently
        results1, results2 = await asyncio.gather(
            self.run_test_suite_async(version1, test_cases), self.run_test_suite_async(version2, test_cases)
        )

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
                        "accuracy_difference": m2["accuracy"] - m1["accuracy"],
                        "relevance_difference": m2["relevance"] - m1["relevance"],
                        "conciseness_difference": m2["conciseness"] - m1["conciseness"],
                        "insight_difference": m2["insight"] - m1["insight"],
                        "appropriateness_difference": m2["appropriateness"] - m1["appropriateness"],
                    }
                )

            comparison["case_comparisons"].append(case_comparison)

        return comparison

    def compare_prompt_versions(
        self, version1: str, version2: str, test_cases: list[str] | None = None
    ) -> dict[str, Any]:
        """Synchronous wrapper for backward compatibility."""
        return asyncio.run(self.compare_prompt_versions_async(version1, version2, test_cases))
