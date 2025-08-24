"""
Prompt improvement advisor using Claude to analyze results and suggest improvements.
"""

import json
from pathlib import Path
from typing import Any

from anthropic import Anthropic

from prompt_testing.evaluation.reviewer import HumanReview, ReviewManager
from prompt_testing.yaml_utils import create_yaml_dumper, load_yaml_file


class PromptAdvisor:
    """Uses Claude to analyze test results and suggest prompt improvements."""

    def __init__(
        self,
        anthropic_api_key: str | None = None,
        advisor_model: str = "claude-sonnet-4-0",
    ):
        self.client = Anthropic(api_key=anthropic_api_key) if anthropic_api_key else Anthropic()
        self.advisor_model = advisor_model

    def load_human_reviews_for_prompt(self, results_dir: str | Path, prompt_version: str) -> dict[str, HumanReview]:
        """Load human reviews for a specific prompt, indexed by case_id."""
        review_manager = ReviewManager(results_dir)
        reviews = review_manager.load_reviews(prompt_version=prompt_version)
        return {review.case_id: review for review in reviews}

    def _extract_human_insights(self, human_reviews: dict[str, HumanReview]) -> str:
        """Extract key patterns and insights from human reviews."""
        if not human_reviews:
            return "No human reviews available."

        # Aggregate scores (1-5 scale)
        avg_scores = {
            "accuracy": sum(r.accuracy for r in human_reviews.values()) / len(human_reviews),
            "relevance": sum(r.relevance for r in human_reviews.values()) / len(human_reviews),
            "conciseness": sum(r.conciseness for r in human_reviews.values()) / len(human_reviews),
            "insight": sum(r.insight for r in human_reviews.values()) / len(human_reviews),
            "appropriateness": sum(r.appropriateness for r in human_reviews.values()) / len(human_reviews),
        }

        # Collect all qualitative feedback
        all_weaknesses = []
        all_suggestions = []
        all_strengths = []

        for review in human_reviews.values():
            all_weaknesses.extend(review.weaknesses)
            all_suggestions.extend(review.suggestions)
            all_strengths.extend(review.strengths)

        # Find recurring patterns
        weakness_counts = {}
        for weakness in all_weaknesses:
            weakness_counts[weakness] = weakness_counts.get(weakness, 0) + 1

        common_weaknesses = [w for w, count in weakness_counts.items() if count > 1]
        unique_suggestions = list(set(all_suggestions))

        scores_text = (
            f"Accuracy {avg_scores['accuracy']:.1f}, Relevance {avg_scores['relevance']:.1f}, "
            f"Conciseness {avg_scores['conciseness']:.1f}, Insight {avg_scores['insight']:.1f}, "
            f"Appropriateness {avg_scores['appropriateness']:.1f}"
        )

        return f"""Human Review Summary ({len(human_reviews)} reviews):
- Average Scores (1-5): {scores_text}
- Recurring Issues: {", ".join(common_weaknesses) if common_weaknesses else "No recurring patterns detected"}
- Key Suggestions: {", ".join(unique_suggestions) if unique_suggestions else "No specific suggestions provided"}
- Noted Strengths: {", ".join(set(all_strengths)) if all_strengths else "No strengths specifically noted"}

Low-scoring areas that need attention:
{self._identify_problem_areas(avg_scores)}"""

    def _identify_problem_areas(self, avg_scores: dict[str, float]) -> str:
        """Identify areas scoring below 3.5 that need improvement."""
        problem_areas = []
        for area, score in avg_scores.items():
            if score < 3.5:
                problem_areas.append(f"- {area.replace('_', ' ').title()}: {score:.1f}/5 (needs improvement)")

        return "\n".join(problem_areas) if problem_areas else "All areas scoring reasonably well (≥3.5/5)"

    def analyze_with_human_feedback(
        self,
        current_prompt: dict[str, str],
        test_results: list[dict[str, Any]],
        human_reviews: dict[str, HumanReview],
        focus_areas: list[str] | None = None,
    ) -> dict[str, Any]:
        """Enhanced analysis that incorporates human feedback alongside automated metrics."""

        # Extract human insights
        human_insights = self._extract_human_insights(human_reviews)

        # Get automated analysis components (existing logic)
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

        # Build enhanced analysis prompt
        analysis_prompt = self._build_analysis_prompt_with_human_feedback(
            current_prompt,
            human_insights,
            all_missing_topics,
            all_incorrect_claims,
            all_notes,
            score_distribution,
            len(test_results),
            len(human_reviews),
            focus_areas,
        )

        # Get Claude's advice
        message = self.client.messages.create(
            model=self.advisor_model,
            max_tokens=4000,
            temperature=0.3,
            system=(
                "You are an expert in prompt engineering and technical documentation, "
                "helping improve prompts for compiler explanation generation. You have both "
                "automated metrics and human expert feedback to guide your suggestions."
            ),
            messages=[{"role": "user", "content": analysis_prompt}],
        )

        try:
            # Parse Claude's response
            response_text = message.content[0].text

            # Extract JSON from response
            json_start = response_text.find("```json")
            json_end = response_text.find("```", json_start + 7)

            if json_start != -1 and json_end != -1:
                json_str = response_text[json_start + 7 : json_end].strip()
                suggestions = json.loads(json_str)
            else:
                # Fallback: try to parse entire response as JSON
                suggestions = json.loads(response_text)

            return {
                "current_prompt": current_prompt,
                "human_feedback_summary": human_insights,
                "analysis_summary": {
                    "total_cases": len(test_results),
                    "human_reviewed_cases": len(human_reviews),
                    "human_coverage": f"{len(human_reviews)}/{len(test_results)} "
                    f"({100 * len(human_reviews) / len(test_results):.0f}%)"
                    if len(test_results) > 0
                    else "0/0 (0%)",
                    "average_score": sum(score_distribution) / len(score_distribution) if score_distribution else 0,
                    "common_missing_topics": list(set(all_missing_topics)),
                    "common_incorrect_claims": list(set(all_incorrect_claims)),
                },
                "suggestions": suggestions,
            }

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            return {
                "error": f"Failed to parse Claude's analysis: {e}",
                "raw_response": message.content[0].text,
                "current_prompt": current_prompt,
                "human_feedback_summary": human_insights,
            }

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
5. **Targeted Improvements**: Consider whether each suggestion should apply to:
   - Specific audiences (beginner/intermediate/expert)
   - Specific explanation types (assembly/source/optimization)
   - General guidelines (applies to all cases)

IMPORTANT: Avoid prescriptive language that creates checklist-style behavior. Instead of:
- "Always include X" → "When X would help understanding, explain it"
- "Explicitly state Y" → "When Y is relevant to the explanation, mention it"
- "Include Z as a standard part" → "Weave Z into the explanation where it adds value"

The goal is natural, contextual explanations, not formulaic outputs with mandatory sections.

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

    def _build_analysis_prompt_with_human_feedback(
        self,
        current_prompt: dict[str, str],
        human_insights: str,
        missing_topics: list[str],
        incorrect_claims: list[str],
        notes: list[str],
        scores: list[float],
        total_cases: int,
        human_reviewed_cases: int,
        focus_areas: list[str] | None,
    ) -> str:
        """Build enhanced analysis prompt that incorporates human feedback."""

        coverage_pct = (human_reviewed_cases / total_cases * 100) if total_cases > 0 else 0

        prompt = f"""I need help improving prompts for an AI system that explains compiler output.
Please analyze the test results using BOTH automated metrics and human expert feedback.

## Test Results Overview

Total test cases: {total_cases}
Human review coverage: {human_reviewed_cases}/{total_cases} ({coverage_pct:.0f}%)
Automated average score: {sum(scores) / len(scores) if scores else 0:.2f}/1.0

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

## Human Expert Feedback (Priority Insights)

{human_insights}

## Automated Analysis Summary

Score Distribution: Min={min(scores) if scores else 0:.2f}, Max={max(scores) if scores else 0:.2f}

Missing Topics (automated detection):
{self._format_frequency_list(missing_topics)}

Incorrect Claims Made (automated detection):
{self._format_list(incorrect_claims)}

Sample Reviewer Notes:
{self._format_list(notes[:3])}  # Show first 3

## Improvement Priority Framework

1. **CRITICAL**: Issues flagged by human review (educational value, clarity, appropriateness)
2. **HIGH**: Patterns confirmed by both human and automated feedback
3. **MEDIUM**: Automated flags where human reviews don't contradict
4. **LOW**: Automated-only issues where humans rated positively

## Analysis Instructions

When humans and automated systems disagree, prioritize human judgment on:
- Educational value and pedagogical clarity
- Audience appropriateness
- Real-world applicability
- Engagement and interest level

Trust automated systems for:
- Technical accuracy detection
- Consistency checking
- Pattern recognition across many cases

Focus improvement suggestions on addressing human-identified issues first,
then automated issues that don't conflict with human feedback.

"""

        if focus_areas:
            prompt += f"""
### Specific Focus Areas Requested
{self._format_list(focus_areas)}
"""

        prompt += """
## Response Format

Provide your analysis in this JSON format:

```json
{
    "priority_improvements": [
        {
            "issue": "Issue description (specify if human-flagged, automated, or both)",
            "current_text": "The problematic part of the current prompt",
            "suggested_text": "The improved version",
            "rationale": "Why this change will help (reference human/automated feedback)",
            "priority": "critical|high|medium|low"
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
    "human_feedback_integration": {
        "human_priorities_addressed": ["Which human concerns are being addressed"],
        "automated_retained": ["Which automated findings remain relevant"],
        "conflicts_resolved": ["How human/automated disagreements were resolved"]
    },
    "expected_impact": "Summary of how these changes should improve both human satisfaction and automated metrics"
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

        # Apply priority improvements with smart targeting
        if "priority_improvements" in suggestions:
            improvements = suggestions["priority_improvements"]

            # Apply each improvement to the appropriate section
            for imp in improvements:
                if "current_text" in imp and "suggested_text" in imp:
                    self._apply_targeted_improvement(new_prompt, imp)

        # Apply system prompt changes with smart targeting
        if "system_prompt_changes" in suggestions:
            changes = suggestions["system_prompt_changes"]
            if "additions" in changes:
                self._apply_targeted_additions(new_prompt, changes["additions"])

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

    def _classify_suggestion_target(self, suggestion_text: str) -> dict[str, list[str]]:
        """Classify where a suggestion should be applied based on its content."""
        targets = {"audiences": [], "explanation_types": [], "general": False}

        suggestion_lower = suggestion_text.lower()

        # Calling convention - primarily for beginners and assembly explanations
        if any(term in suggestion_lower for term in ["calling convention", "parameter passing", "register roles"]):
            targets["audiences"].append("beginner")
            targets["explanation_types"].append("assembly")

        # Optimization analysis - for optimization explanations and intermediate+ audiences
        if any(term in suggestion_lower for term in ["optimization", "compare", "level", "-o0", "-o1", "-o2", "-o3"]):
            targets["explanation_types"].append("optimization")
            targets["audiences"].extend(["intermediate", "expert"])

        # Performance implications - for intermediate+ audiences
        if any(term in suggestion_lower for term in ["performance", "practical", "developer", "compiler-friendly"]):
            targets["audiences"].extend(["intermediate", "expert"])

        # Source mapping - for source explanations
        if any(term in suggestion_lower for term in ["source", "mapping", "construct", "high-level"]):
            targets["explanation_types"].append("source")

        # Technical accuracy - applies to general guidelines
        if any(
            term in suggestion_lower for term in ["instruction", "operand", "verify", "trace", "accurate", "precise"]
        ):
            targets["general"] = True

        # Expert-level content
        if any(
            term in suggestion_lower for term in ["microarchitecture", "pipeline", "advanced", "comparative analysis"]
        ):
            targets["audiences"].append("expert")

        # Remove duplicates
        targets["audiences"] = list(set(targets["audiences"]))
        targets["explanation_types"] = list(set(targets["explanation_types"]))

        return targets

    def _apply_targeted_improvement(self, new_prompt: dict[str, Any], improvement: dict[str, str]) -> None:
        """Apply an improvement to the appropriate section of the prompt."""
        current_text = improvement["current_text"]
        suggested_text = improvement["suggested_text"]

        # Classify the suggestion
        targets = self._classify_suggestion_target(improvement.get("issue", "") + " " + suggested_text)

        # Apply to system prompt if it's a general improvement or direct system prompt change
        if (
            targets["general"] or current_text in new_prompt.get("system_prompt", "")
        ) and "system_prompt" in new_prompt:
            new_prompt["system_prompt"] = new_prompt["system_prompt"].replace(current_text, suggested_text)

        # Apply to specific audience levels (check both base and explanation-specific locations)
        # TODO: In the future, we may need to create new explanation-specific audience overrides
        if targets["audiences"]:
            for audience in targets["audiences"]:
                # Check base audience level
                if "audience_levels" in new_prompt and audience in new_prompt["audience_levels"]:
                    guidance = new_prompt["audience_levels"][audience].get("guidance", "")
                    if current_text in guidance:
                        new_prompt["audience_levels"][audience]["guidance"] = guidance.replace(
                            current_text, suggested_text
                        )

                # Check explanation-specific audience overrides
                if "explanation_types" in new_prompt:
                    for exp_config in new_prompt["explanation_types"].values():
                        if (
                            isinstance(exp_config, dict)
                            and "audience_levels" in exp_config
                            and audience in exp_config["audience_levels"]
                        ):
                            guidance = exp_config["audience_levels"][audience].get("guidance", "")
                            if current_text in guidance:
                                exp_config["audience_levels"][audience]["guidance"] = guidance.replace(
                                    current_text, suggested_text
                                )

        # Apply to specific explanation types
        if targets["explanation_types"] and "explanation_types" in new_prompt:
            for exp_type in targets["explanation_types"]:
                if exp_type in new_prompt["explanation_types"]:
                    focus = new_prompt["explanation_types"][exp_type].get("focus", "")
                    if current_text in focus:
                        new_prompt["explanation_types"][exp_type]["focus"] = focus.replace(current_text, suggested_text)

    def _apply_targeted_additions(self, new_prompt: dict[str, Any], additions: list[str]) -> None:
        """Apply additions to the appropriate sections based on their content."""
        general_additions = []

        for addition in additions:
            targets = self._classify_suggestion_target(addition)
            applied = False

            # Apply to specific audience levels (check both base and explanation-specific locations)
            if targets["audiences"]:
                for audience in targets["audiences"]:
                    # Check base audience level
                    if "audience_levels" in new_prompt and audience in new_prompt["audience_levels"]:
                        current_guidance = new_prompt["audience_levels"][audience].get("guidance", "")
                        new_prompt["audience_levels"][audience]["guidance"] = (
                            current_guidance.rstrip() + f"\n{addition}\n"
                        )
                        applied = True

                    # Check explanation-specific audience overrides
                    if "explanation_types" in new_prompt:
                        for exp_config in new_prompt["explanation_types"].values():
                            if (
                                isinstance(exp_config, dict)
                                and "audience_levels" in exp_config
                                and audience in exp_config["audience_levels"]
                            ):
                                current_guidance = exp_config["audience_levels"][audience].get("guidance", "")
                                exp_config["audience_levels"][audience]["guidance"] = (
                                    current_guidance.rstrip() + f"\n{addition}\n"
                                )
                                applied = True

            # Apply to specific explanation types
            if targets["explanation_types"] and "explanation_types" in new_prompt:
                for exp_type in targets["explanation_types"]:
                    if exp_type in new_prompt["explanation_types"]:
                        current_focus = new_prompt["explanation_types"][exp_type].get("focus", "")
                        new_prompt["explanation_types"][exp_type]["focus"] = current_focus.rstrip() + f"\n{addition}\n"
                        applied = True

            # If not applied to specific sections or is general, add to general additions
            if not applied or targets["general"]:
                general_additions.append(addition)

        # Apply remaining general additions to system prompt
        if general_additions and "system_prompt" in new_prompt:
            additions_text = "\n\n# Additional guidance from analysis:\n"
            for addition in general_additions:
                additions_text += f"- {addition}\n"
            new_prompt["system_prompt"] += additions_text


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

        # Load current prompt - handle "current" special case
        if prompt_version == "current":
            prompt_path = self.project_root / "app" / "prompt.yaml"
        else:
            prompt_path = self.prompts_dir / f"{prompt_version}.yaml"
        current_prompt = load_yaml_file(prompt_path)

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
            yaml_out = create_yaml_dumper()
            with new_prompt_path.open("w") as f:
                yaml_out.dump(new_prompt, f)

            print(f"Experimental prompt saved to: {new_prompt_path}")
            return new_prompt_path

        return analysis_file

    def analyze_and_improve_with_human_feedback(
        self,
        results_file: str,
        prompt_version: str,
        output_name: str | None = None,
    ) -> tuple[Path, dict[str, int]]:
        """Enhanced analysis that automatically incorporates human reviews if available."""

        # Load test results
        results_path = self.results_dir / results_file
        with results_path.open() as f:
            test_data = json.load(f)

        # Load current prompt - handle "current" special case
        if prompt_version == "current":
            prompt_path = self.project_root / "app" / "prompt.yaml"
        else:
            prompt_path = self.prompts_dir / f"{prompt_version}.yaml"
        current_prompt = load_yaml_file(prompt_path)

        # Load human reviews for this prompt
        human_reviews = self.advisor.load_human_reviews_for_prompt(self.results_dir, prompt_version)

        # Determine which analysis method to use
        if human_reviews:
            suggestions = self.advisor.analyze_with_human_feedback(
                current_prompt, test_data.get("results", []), human_reviews
            )
            analysis_suffix = "human_enhanced"
        else:
            suggestions = self.advisor.analyze_results_and_suggest_improvements(
                current_prompt, test_data.get("results", [])
            )
            analysis_suffix = "automated_only"

        # Save analysis with descriptive filename
        analysis_file = self.results_dir / f"analysis_{prompt_version}_{analysis_suffix}_{results_file}"
        with analysis_file.open("w") as f:
            json.dump(suggestions, f, indent=2)

        # Create human review stats
        total_test_cases = len(test_data.get("results", []))
        human_stats = {
            "total_reviews": len(human_reviews),
            "coverage": len(human_reviews) / total_test_cases if total_test_cases > 0 else 0,
        }

        # Create experimental prompt if requested
        if output_name:
            new_prompt = self.advisor.suggest_prompt_experiment(
                current_prompt,
                suggestions,
                f"Improvement based on {results_file} ({'with human feedback' if human_reviews else 'automated only'})",
            )

            new_prompt_path = self.prompts_dir / f"{output_name}.yaml"
            yaml_out = create_yaml_dumper()
            with new_prompt_path.open("w") as f:
                yaml_out.dump(new_prompt, f)

            print(f"Experimental prompt saved to: {new_prompt_path}")
            return new_prompt_path, human_stats

        return analysis_file, human_stats
