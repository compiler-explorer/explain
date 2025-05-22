#!/usr/bin/env python3
"""
Command-line interface for prompt testing framework.
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from prompt_testing.evaluation.reviewer import ReviewManager, create_simple_review_cli
from prompt_testing.evaluation.scorer import load_all_test_cases
from prompt_testing.runner import PromptTester

# Load environment variables from .env file
load_dotenv()


def cmd_run(args):
    """Run test suite command."""
    tester = PromptTester(args.project_root)

    try:
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

    except Exception as e:
        print(f"Error running tests: {e}")
        return 1

    return 0


def cmd_list(args):
    """List available test cases and prompts."""
    project_root = Path(args.project_root)

    # List test cases
    print("Available test cases:")
    try:
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

    except Exception as e:
        print(f"  Error loading test cases: {e}")

    # List prompts
    print("\nAvailable prompts:")
    try:
        prompts_dir = project_root / "prompt_testing" / "prompts"
        if prompts_dir.exists():
            for prompt_file in sorted(prompts_dir.glob("*.txt")):
                prompt_name = prompt_file.stem
                print(f"  {prompt_name}")
        else:
            print("  No prompts directory found")
    except Exception as e:
        print(f"  Error loading prompts: {e}")

    return 0


def cmd_review(args):
    """Human review interface."""
    if args.results_file:
        # Review specific results file
        try:
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

        except Exception as e:
            print(f"Error reviewing results: {e}")
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


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Prompt testing framework for Claude explain service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run basic optimization tests with current prompt
  uv run prompt-test run --prompt current --categories basic_optimizations

  # Compare two prompt versions
  uv run prompt-test run --prompt v1_baseline --compare current

  # Run specific test cases
  uv run prompt-test run --prompt current --cases basic_loop_001 basic_inline_001

  # List available test cases and prompts
  uv run prompt-test list

  # Review results interactively
  uv run prompt-test review --results-file results/20241201_120000_current.json

  # Analyze all results
  uv run prompt-test analyze
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

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
