#!/usr/bin/env python3
"""
Command-line interface for prompt testing framework.
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from prompt_testing.evaluation.prompt_advisor import PromptOptimizer
from prompt_testing.evaluation.reviewer import ReviewManager, create_simple_review_cli
from prompt_testing.evaluation.scorer import load_all_test_cases
from prompt_testing.runner import PromptTester

# Load environment variables from .env file
load_dotenv()


def cmd_run(args):
    """Run test suite command."""
    tester = PromptTester(
        args.project_root,
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

    output_path = tester.save_results(results, output_file)

    # Print summary
    if "summary" in results:
        summary = results["summary"]
        print(f"\nSummary for {args.prompt}:")
        print(f"  Success rate: {summary['success_rate']:.1%}")
        print(f"  Cases: {summary['successful_cases']}/{summary['total_cases']}")

        if "average_metrics" in summary:
            avg = summary["average_metrics"]
            print(f"  Average score: {avg['overall_score']:.2f}")
            print(f"  Average accuracy: {avg['accuracy_score']:.2f}")
            print(f"  Average clarity: {avg['clarity_score']:.2f}")
            print(f"  Average tokens: {avg['average_tokens']:.0f}")
            print(f"  Average response time: {avg['average_response_time']:.0f}ms")

    if args.compare and "case_comparisons" in results:
        comparisons = results["case_comparisons"]
        better_v1 = sum(1 for c in comparisons if c.get("better_version") == args.prompt)
        better_v2 = sum(1 for c in comparisons if c.get("better_version") == args.compare)
        print(f"\nComparison {args.prompt} vs {args.compare}:")
        print(f"  {args.prompt} better: {better_v1} cases")
        print(f"  {args.compare} better: {better_v2} cases")

    print(f"\nDetailed results saved to: {output_path}")

    return 0


def cmd_list(args):
    """List available test cases and prompts."""
    project_root = Path(args.project_root)

    # List test cases
    print("Available test cases:")
    test_cases = load_all_test_cases(str(project_root / "prompt_testing" / "test_cases"))

    by_category = {}
    for case in test_cases:
        category = case.get("category", "unknown")
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(case)

    for category, cases in sorted(by_category.items()):
        print(f"\n  {category}:")
        for case in cases:
            quality = case.get("quality", "unknown")
            difficulty = case.get("difficulty", "unknown")
            print(f"    {case['id']} - {case.get('description', 'No description')} ({quality}, {difficulty})")

    # List prompts
    print("\nAvailable prompts:")
    prompts_dir = project_root / "prompt_testing" / "prompts"
    if prompts_dir.exists():
        for prompt_file in sorted(prompts_dir.glob("*.yaml")):
            prompt_name = prompt_file.stem
            print(f"  {prompt_name}")
    else:
        print("  No prompts directory found")

    return 0


def cmd_review(args):
    """Human review interface."""
    if args.results_file:
        # Review specific results file
        results_path = Path(args.results_file)
        with results_path.open() as f:
            results = json.load(f)

        if "results" in results:
            # Single test run
            for result in results["results"]:
                if not result["success"]:
                    continue

                review = create_simple_review_cli(result["case_id"], result["response"], result["prompt_version"])

                # Save review
                manager = ReviewManager(str(Path(args.project_root) / "prompt_testing" / "results"))
                manager.save_review(review)

                print("Review saved!")

                if input("\nContinue to next case? (y/N): ").lower() != "y":
                    break
        else:
            print("Invalid results file format")
            return 1
    else:
        # Interactive review mode
        print("Interactive review mode not yet implemented")
        print("Please specify a results file with --results-file")
        return 1

    return 0


def cmd_analyze(args):
    """Analyze results and generate reports."""
    results_dir = Path(args.project_root) / "prompt_testing" / "results"

    if not results_dir.exists():
        print("No results directory found")
        return 1

    # Find all result files
    result_files = list(results_dir.glob("*.json"))
    if not result_files:
        print("No result files found")
        return 1

    print(f"Found {len(result_files)} result files:")

    all_summaries = []
    for result_file in sorted(result_files):
        try:
            with result_file.open() as f:
                data = json.load(f)

            if "summary" in data:
                summary = data["summary"]
                summary["file"] = result_file.name
                all_summaries.append(summary)

                print(f"\n{result_file.name}:")
                print(f"  Prompt: {summary['prompt_version']}")
                print(f"  Success rate: {summary['success_rate']:.1%}")
                print(f"  Cases: {summary['successful_cases']}/{summary['total_cases']}")

                if "average_metrics" in summary:
                    avg = summary["average_metrics"]
                    print(f"  Avg score: {avg['overall_score']:.2f}")
                    print(f"  Avg accuracy: {avg['accuracy_score']:.2f}")
                    print(f"  Avg clarity: {avg['clarity_score']:.2f}")

        except Exception as e:
            print(f"  Error reading {result_file.name}: {e}")

    # Create summary report
    if all_summaries:
        summary_file = results_dir / "analysis_summary.json"
        with summary_file.open("w") as f:
            best_prompt = None
            if all_summaries:
                best_summary = max(all_summaries, key=lambda x: x.get("average_metrics", {}).get("overall_score", 0))
                best_prompt = best_summary["prompt_version"]

            json.dump(
                {"total_files": len(all_summaries), "summaries": all_summaries, "best_prompt": best_prompt}, f, indent=2
            )

        print(f"\nAnalysis summary saved to: {summary_file}")

    return 0


def cmd_improve(args):
    """Analyze results and suggest prompt improvements."""

    optimizer = PromptOptimizer(args.project_root)

    # If specific results file provided
    if args.results_file:
        results_file = args.results_file
    else:
        # Find the most recent results file for the prompt
        results_dir = Path(args.project_root) / "prompt_testing" / "results"
        pattern = f"*_{args.prompt}.json"
        files = list(results_dir.glob(pattern))
        if not files:
            print(f"No results found for prompt: {args.prompt}")
            return 1

        # Get most recent
        results_file = max(files, key=lambda f: f.stat().st_mtime).name
        print(f"Using most recent results: {results_file}")

    # Analyze and potentially create improved version
    output_path = optimizer.analyze_and_improve(
        results_file, args.prompt, args.output if args.create_improved else None
    )

    # Display key suggestions
    if args.show_suggestions and not args.create_improved:
        with output_path.open() as f:
            analysis = json.load(f)

        print("\n=== PROMPT IMPROVEMENT SUGGESTIONS ===")

        if "analysis_summary" in analysis:
            summary = analysis["analysis_summary"]
            print(f"\nAverage Score: {summary['average_score']:.2f}")
            print("\nMost Common Missing Topics:")
            for topic, count in summary.get("common_missing_topics", []):
                print(f"  - {topic} ({count} times)")

        if "suggestions" in analysis and isinstance(analysis["suggestions"], dict):
            suggestions = analysis["suggestions"]

            if "priority_improvements" in suggestions:
                print("\n🎯 Priority Improvements:")
                for imp in suggestions["priority_improvements"][:3]:
                    print(f"\n  Issue: {imp['issue']}")
                    print(f"  Current: '{imp.get('current_text', 'N/A')[:60]}...'")
                    print(f"  Suggested: '{imp.get('suggested_text', 'N/A')[:60]}...'")
                    print(f"  Rationale: {imp.get('rationale', 'N/A')}")

            if "expected_impact" in suggestions:
                print(f"\n✨ Expected Impact: {suggestions['expected_impact']}")

    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Prompt testing framework for Claude explain service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run basic optimization tests with current prompt (automatic scoring)
  uv run prompt-test run --prompt current --categories basic_optimizations

  # Use Claude-based AI scoring for deeper evaluation
  uv run prompt-test run --prompt current --scorer claude

  # Use hybrid scoring (20% Claude sampling)
  uv run prompt-test run --prompt current --scorer hybrid --claude-sample-rate 0.2

  # Compare two prompt versions
  uv run prompt-test run --prompt v1_baseline --compare current

  # Run specific test cases with Claude scoring
  uv run prompt-test run --prompt current --cases basic_loop_001 --scorer claude

  # List available test cases and prompts
  uv run prompt-test list

  # Review results interactively
  uv run prompt-test review --results-file results/20241201_120000_current.json

  # Analyze all results
  uv run prompt-test analyze

  # Get improvement suggestions based on test results
  uv run prompt-test improve --prompt current

  # Create an experimental improved version
  uv run prompt-test improve --prompt current --create-improved --output current_v2
        """,
    )

    parser.add_argument(
        "--project-root", default=str(Path.cwd()), help="Project root directory (default: current directory)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run test suite")
    run_parser.add_argument("--prompt", required=True, help="Prompt version to test")
    run_parser.add_argument("--cases", nargs="*", help="Specific test case IDs to run")
    run_parser.add_argument("--categories", nargs="*", help="Test case categories to run")
    run_parser.add_argument("--compare", help="Compare with another prompt version")
    run_parser.add_argument("--output", help="Output file name (auto-generated if not specified)")

    # Scorer configuration
    run_parser.add_argument(
        "--scorer",
        choices=["automatic", "claude", "hybrid"],
        default="automatic",
        help="Scoring method: automatic (regex), claude (AI review), or hybrid",
    )
    run_parser.add_argument(
        "--claude-sample-rate",
        type=float,
        default=0.2,
        help="For hybrid scorer: fraction of cases to evaluate with Claude (0.0-1.0)",
    )
    run_parser.add_argument(
        "--reviewer-model",
        default="claude-sonnet-4-0",
        help="Claude model to use for reviewing (e.g., claude-sonnet-4-0, claude-3-5-sonnet-20241022)",
    )

    run_parser.set_defaults(func=cmd_run)

    # List command
    list_parser = subparsers.add_parser("list", help="List available test cases and prompts")
    list_parser.set_defaults(func=cmd_list)

    # Review command
    review_parser = subparsers.add_parser("review", help="Human review interface")
    review_parser.add_argument("--results-file", help="Results file to review")
    review_parser.set_defaults(func=cmd_review)

    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze results and generate reports")
    analyze_parser.set_defaults(func=cmd_analyze)

    # Improve command
    improve_parser = subparsers.add_parser("improve", help="Get AI suggestions for prompt improvements")
    improve_parser.add_argument("--prompt", required=True, help="Prompt version to improve")
    improve_parser.add_argument(
        "--results-file", help="Specific results file to analyze (uses most recent if not specified)"
    )
    improve_parser.add_argument(
        "--show-suggestions", action="store_true", default=True, help="Display suggestions in terminal"
    )
    improve_parser.add_argument(
        "--create-improved", action="store_true", help="Create an experimental improved prompt version"
    )
    improve_parser.add_argument("--output", help="Name for the improved prompt version")
    improve_parser.set_defaults(func=cmd_improve)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
