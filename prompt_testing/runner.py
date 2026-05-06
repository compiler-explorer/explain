"""Simple test runner for prompt evaluation.

Runs test cases against the explain API and saves outputs for human review.
No automated scoring — the human reads the output and decides if it's good.
"""

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic
from dotenv import load_dotenv

from app.explain_api import AssemblyItem, ExplainRequest
from app.explanation_types import AudienceLevel, ExplanationType
from app.prompt import Prompt
from prompt_testing.file_utils import load_all_test_cases

load_dotenv()


class PromptTester:
    """Runs test cases against a prompt and collects outputs."""

    def __init__(
        self,
        project_root: str | Path,
        max_concurrent: int = 5,
    ):
        self.project_root = Path(project_root)
        self.test_cases_dir = self.project_root / "prompt_testing" / "test_cases"
        self.results_dir = self.project_root / "prompt_testing" / "results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.async_client = AsyncAnthropic()
        self.semaphore = asyncio.Semaphore(max_concurrent)

    def load_prompt(self, prompt_version: str) -> Prompt:
        """Load a prompt. 'current' loads from app/prompt.yaml."""
        if prompt_version == "current":
            path = self.project_root / "app" / "prompt.yaml"
        else:
            path = self.project_root / "prompt_testing" / "prompts" / f"{prompt_version}.yaml"
        return Prompt(path)

    @staticmethod
    def _to_request(test_case: dict[str, Any]) -> ExplainRequest:
        """Convert a test case dict to an ExplainRequest."""
        inp = test_case["input"]
        audience = test_case.get("audience", "beginner")
        explanation = test_case.get("explanation_type", "assembly")
        return ExplainRequest(
            language=inp["language"],
            compiler=inp["compiler"],
            compilationOptions=inp.get("compilationOptions", []),
            instructionSet=inp.get("instructionSet"),
            code=inp["code"],
            asm=[AssemblyItem(**a) for a in inp["asm"]],
            labelDefinitions=inp.get("labelDefinitions", {}),
            audience=AudienceLevel(audience) if isinstance(audience, str) else audience,
            explanation=ExplanationType(explanation) if isinstance(explanation, str) else explanation,
        )

    async def _run_one(self, test_case: dict[str, Any], prompt: Prompt) -> dict[str, Any]:
        """Run a single test case."""
        async with self.semaphore:
            case_id = test_case["id"]
            request = self._to_request(test_case)
            prompt_data = prompt.generate_messages(request)

            api_kwargs: dict[str, Any] = {
                "model": prompt_data["model"],
                "max_tokens": prompt_data["max_tokens"],
                "system": prompt_data["system"],
                "messages": prompt_data["messages"],
            }
            if prompt_data.get("thinking"):
                # Extended thinking: temperature must be 1 / unset.
                api_kwargs["thinking"] = prompt_data["thinking"]
            else:
                api_kwargs["temperature"] = prompt_data["temperature"]

            start = time.time()
            try:
                msg = await self.async_client.messages.create(**api_kwargs)
                elapsed_ms = int((time.time() - start) * 1000)
                text_blocks = [c for c in msg.content if getattr(c, "type", None) == "text"]
                explanation = text_blocks[-1].text.strip() if text_blocks else ""
                if not explanation:
                    # Treat empty output as a failure so suite metrics aren't
                    # skewed. Common cause: thinking exhausting max_tokens
                    # before any text block is emitted.
                    return {
                        "case_id": case_id,
                        "success": False,
                        "error": (
                            f"empty response (stop_reason={msg.stop_reason}, "
                            f"in={msg.usage.input_tokens}, out={msg.usage.output_tokens})"
                        ),
                    }
                return {
                    "case_id": case_id,
                    "success": True,
                    "explanation": explanation,
                    "model": prompt_data["model"],
                    "input_tokens": msg.usage.input_tokens,
                    "output_tokens": msg.usage.output_tokens,
                    "elapsed_ms": elapsed_ms,
                }
            except Exception as e:
                return {
                    "case_id": case_id,
                    "success": False,
                    "error": str(e),
                }

    async def run_async(
        self,
        prompt_version: str = "current",
        case_ids: list[str] | None = None,
        categories: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run test cases and return results."""
        prompt = self.load_prompt(prompt_version)
        cases = load_all_test_cases(str(self.test_cases_dir))

        if case_ids:
            cases = [c for c in cases if c["id"] in case_ids]
        if categories:
            cases = [c for c in cases if c.get("category") in categories]
        if not cases:
            raise ValueError("No test cases matched filters")

        print(f"Running {len(cases)} test cases with prompt: {prompt_version}")

        tasks = [self._run_one(c, prompt) for c in cases]
        results = []
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            result = await coro
            results.append(result)
            status = "✓" if result["success"] else "✗"
            tokens = f"in={result.get('input_tokens', '?')} out={result.get('output_tokens', '?')}"
            print(f"  [{i}/{len(cases)}] {status} {result['case_id']} ({tokens})")

        successful = [r for r in results if r["success"]]
        total_cost = sum(
            r["input_tokens"] * 3 / 1e6 + r["output_tokens"] * 15 / 1e6  # Sonnet pricing
            for r in successful
        )

        return {
            "prompt_version": prompt_version,
            "model": prompt.model,
            "timestamp": datetime.now().isoformat(),
            "total_cases": len(results),
            "successful": len(successful),
            "failed": len(results) - len(successful),
            "total_cost_usd": round(total_cost, 6),
            "results": results,
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Synchronous wrapper."""
        return asyncio.run(self.run_async(**kwargs))

    def save(self, data: dict[str, Any], filename: str | None = None) -> Path:
        """Save results to JSON."""
        import json

        if not filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{ts}_{data['prompt_version']}.json"
        path = self.results_dir / filename
        path.write_text(json.dumps(data, indent=2))
        print(f"Saved to {path}")
        return path
