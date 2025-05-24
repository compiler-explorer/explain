"""
Prompt improvement advisor using Claude to analyze results and suggest improvements.
"""

import json
from pathlib import Path
from typing import Any

from anthropic import Anthropic


class PromptAdvisor:
    """Uses Claude to analyze test results and suggest prompt improvements."""

    def __init__(
        self,
        anthropic_api_key: str | None = None,
        advisor_model: str = "claude-sonnet-4-0",
    ):
        self.client = Anthropic(api_key=anthropic_api_key) if anthropic_api_key else Anthropic()
        self.advisor_model = advisor_model

    def analyze_results_and_suggest_improvements(
        self,
        current_prompt: dict[str, str],
        test_results: list[dict[str, Any]],
        focus_areas: list[str] | None = None,
    ) -> dict[str, Any]:
        """Analyze test results and suggest prompt improvements."""

        # Aggregate feedback from results
        all_missing_topics = []
        all_incorrect_claims = []
        all_notes = []
        score_distribution = []

        for result in test_results:
            if result.get("success") and result.get("metrics"):
                metrics = result["metrics"]
                score_distribution.append(metrics.get("overall_score", 0))

                if metrics.get("missing_topics"):
                    all_missing_topics.extend(metrics["missing_topics"])
                if metrics.get("incorrect_claims"):
                    all_incorrect_claims.extend(metrics["incorrect_claims"])
                if metrics.get("notes"):
                    all_notes.append(metrics["notes"])

        # Build analysis prompt
        analysis_prompt = self._build_analysis_prompt(
            current_prompt, all_missing_topics, all_incorrect_claims, all_notes, score_distribution, focus_areas
        )

        # Get Claude's advice
        message = self.client.messages.create(
            model=self.advisor_model,
            max_tokens=4000,
            temperature=0.3,
            system=(
                "You are an expert in prompt engineering and technical documentation, "
                "helping improve prompts for compiler explanation generation."
            ),
            messages=[{"role": "user", "content": analysis_prompt}],
        )

        # Parse response
        response_text = message.content[0].text

        # Extract JSON from Claude's response
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            suggestions = json.loads(response_text[json_start:json_end])
        else:
            # If no JSON found, raise an error
            raise ValueError(f"Claude did not provide JSON response. Got: {response_text[:200]}...")

        return {
            "current_prompt": current_prompt,
            "analysis_summary": {
                "total_cases": len(test_results),
                "average_score": sum(score_distribution) / len(score_distribution) if score_distribution else 0,
                "common_missing_topics": self._get_most_common(all_missing_topics, 5),
                "common_incorrect_claims": self._get_most_common(all_incorrect_claims, 3),
            },
            "suggestions": suggestions,
            "model_used": self.advisor_model,
        }

    def _build_analysis_prompt(
        self,
        current_prompt: dict[str, str],
        missing_topics: list[str],
        incorrect_claims: list[str],
        notes: list[str],
        scores: list[float],
        focus_areas: list[str] | None,
    ) -> str:
        """Build the prompt for Claude to analyze results."""

        prompt = f"""I need help improving prompts for an AI system that explains compiler output.
Please analyze the test results and suggest specific improvements.

## Current Prompts

System Prompt:
```
{current_prompt.get("system_prompt", "Not provided")}
```

User Prompt:
```
{current_prompt.get("user_prompt", "Not provided")}
```

Assistant Prefill:
```
{current_prompt.get("assistant_prefill", "Not provided")}
```

## Test Results Analysis

Average Score: {sum(scores) / len(scores) if scores else 0:.2f}/1.0
Score Distribution: Min={min(scores) if scores else 0:.2f}, Max={max(scores) if scores else 0:.2f}

### Common Issues Found

Missing Topics (frequency):
{self._format_frequency_list(missing_topics)}

Incorrect Claims Made:
{self._format_list(incorrect_claims)}

Reviewer Notes Summary:
{self._format_list(notes[:5])}  # Show first 5

"""

        if focus_areas:
            prompt += f"""
### Focus Areas for Improvement
{self._format_list(focus_areas)}

"""

        prompt += """
## Task

Based on this analysis, please suggest specific improvements to the prompts. Focus on:

1. **Addressing Missing Topics**: How can we modify the prompts to ensure these topics are covered?
2. **Preventing Incorrect Claims**: What guardrails or instructions would help?
3. **Improving Weak Areas**: Based on the reviewer notes, what changes would help?
4. **Concrete Examples**: Provide specific wording changes, not just general advice.

Provide your response in this JSON format:
```json
{
    "priority_improvements": [
        {
            "issue": "Description of the issue",
            "current_text": "The problematic part of the current prompt",
            "suggested_text": "The improved version",
            "rationale": "Why this change will help"
        }
    ],
    "system_prompt_changes": {
        "additions": ["New instructions to add"],
        "modifications": ["Parts to modify and how"],
        "removals": ["Parts to remove"]
    },
    "user_prompt_changes": {
        "additions": ["New elements to add"],
        "modifications": ["Parts to modify and how"],
        "removals": ["Parts to remove"]
    },
    "general_recommendations": [
        "Higher-level suggestions for the overall approach"
    ],
    "expected_impact": "Summary of how these changes should improve performance"
}
```
"""
        return prompt

    def _get_most_common(self, items: list[str], n: int) -> list[tuple[str, int]]:
        """Get the n most common items with counts."""
        from collections import Counter

        counter = Counter(items)
        return counter.most_common(n)

    def _format_frequency_list(self, items: list[str]) -> str:
        """Format a list with frequency counts."""
        if not items:
            return "- None identified"

        from collections import Counter

        counter = Counter(items)
        lines = []
        for item, count in counter.most_common(10):
            lines.append(f"- {item} ({count} occurrences)")
        return "\n".join(lines)

    def _format_list(self, items: list[str]) -> str:
        """Format a simple list."""
        if not items:
            return "- None"
        return "\n".join(f"- {item}" for item in items[:10])  # Limit to 10

    def suggest_prompt_experiment(
        self,
        current_prompt: dict[str, str],
        improvement_suggestions: dict[str, Any],
        experiment_name: str,
    ) -> dict[str, str]:
        """Generate an experimental prompt version based on suggestions."""

        # Start with current prompt
        new_prompt = current_prompt.copy()

        suggestions = improvement_suggestions.get("suggestions", {})

        # Apply priority improvements by making the suggested text changes
        if "priority_improvements" in suggestions:
            improvements = suggestions["priority_improvements"]

            # Apply each improvement
            for imp in improvements:
                if "current_text" in imp and "suggested_text" in imp and "system_prompt" in new_prompt:
                    new_prompt["system_prompt"] = new_prompt["system_prompt"].replace(
                        imp["current_text"], imp["suggested_text"]
                    )

        # Apply system prompt additions
        if "system_prompt_changes" in suggestions:
            changes = suggestions["system_prompt_changes"]
            if "additions" in changes:
                additions_text = "\n\n# Additional guidance from analysis:\n"
                for addition in changes["additions"]:
                    additions_text += f"- {addition}\n"
                new_prompt["system_prompt"] += additions_text

        # Apply user prompt modifications
        if "user_prompt_changes" in suggestions:
            changes = suggestions["user_prompt_changes"]
            if "modifications" in changes:
                for _mod in changes["modifications"]:
                    # Simple implementation - in practice might need smarter parsing
                    if "Explain the {arch} assembly output" in new_prompt.get("user_prompt", ""):
                        new_prompt["user_prompt"] = (
                            "Provide a systematic analysis of the {arch} assembly output, "
                            "covering optimizations applied, source-to-assembly mapping, "
                            "and performance implications."
                        )

        # Update assistant prefill if recommended
        if "assistant prefill" in str(suggestions.get("general_recommendations", [])):
            new_prompt["assistant_prefill"] = (
                "I have analyzed the assembly code systematically, "
                "examining optimizations, mappings, and performance implications:"
            )

        # Add experiment metadata
        new_prompt["experiment_metadata"] = {
            "base_prompt": current_prompt.get("name", "unknown"),
            "experiment_name": experiment_name,
            "improvements_applied": len(suggestions.get("priority_improvements", [])),
            "expected_impact": suggestions.get("expected_impact", "Not specified"),
        }

        return new_prompt


class PromptOptimizer:
    """Orchestrates the prompt optimization workflow."""

    def __init__(self, project_root: str, anthropic_api_key: str | None = None):
        self.project_root = Path(project_root)
        self.advisor = PromptAdvisor(anthropic_api_key)
        self.results_dir = self.project_root / "prompt_testing" / "results"
        self.prompts_dir = self.project_root / "prompt_testing" / "prompts"

    def analyze_and_improve(
        self,
        results_file: str,
        prompt_version: str,
        output_name: str | None = None,
    ) -> Path:
        """Analyze results and create improved prompt version."""

        # Load test results
        results_path = self.results_dir / results_file
        with results_path.open() as f:
            test_data = json.load(f)

        # Load current prompt
        prompt_path = self.prompts_dir / f"{prompt_version}.yaml"
        from ruamel.yaml import YAML

        yaml = YAML(typ="safe")

        with prompt_path.open() as f:
            current_prompt = yaml.load(f)

        # Get improvement suggestions
        suggestions = self.advisor.analyze_results_and_suggest_improvements(
            current_prompt, test_data.get("results", [])
        )

        # Save analysis
        analysis_file = self.results_dir / f"analysis_{prompt_version}_{results_file}"
        with analysis_file.open("w") as f:
            json.dump(suggestions, f, indent=2)

        print(f"Analysis saved to: {analysis_file}")

        # Create experimental prompt if requested
        if output_name:
            new_prompt = self.advisor.suggest_prompt_experiment(
                current_prompt, suggestions, f"Automated improvement based on {results_file}"
            )

            new_prompt_path = self.prompts_dir / f"{output_name}.yaml"
            yaml_out = YAML()
            yaml_out.default_flow_style = False
            with new_prompt_path.open("w") as f:
                yaml_out.dump(new_prompt, f)

            print(f"Experimental prompt saved to: {new_prompt_path}")
            return new_prompt_path

        return analysis_file
