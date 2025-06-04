#!/usr/bin/env python3
"""
Command-line interface for prompt testing framework.
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.explain_api import AssemblyItem, ExplainRequest
from app.prompt import Prompt
from prompt_testing.ce_api import CompilerExplorerClient
from prompt_testing.enricher import TestCaseEnricher
from prompt_testing.evaluation.prompt_advisor import PromptOptimizer
from prompt_testing.evaluation.reviewer import ReviewManager, create_simple_review_cli
from prompt_testing.evaluation.scorer import load_all_test_cases
from prompt_testing.file_utils import (
    find_latest_results_file,
    save_json_results,
)
from prompt_testing.runner import PromptTester
from prompt_testing.web_review import start_review_server

# Load environment variables from .env file
load_dotenv()


def cmd_run(args):
    """Run test suite command."""
    tester = PromptTester(
        args.project_root,
        reviewer_model=args.reviewer_model,
    )

    if args.compare:
        results = tester.compare_prompt_versions(args.prompt, args.compare, args.cases)
        output_file = args.output or f"comparison_{args.prompt}_vs_{args.compare}.json"
    else:
        results = tester.run_test_suite(
            args.prompt, args.cases, args.categories, audience=args.audience, explanation_type=args.explanation_type
        )
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
    if args.interactive:
        # Start web interface
        try:
            start_review_server(args.project_root, port=args.port, open_browser=not args.no_browser)
        except KeyboardInterrupt:
            print("\n🛑 Review server stopped")
        except Exception as e:
            print(f"❌ Error starting review server: {e}")
            return 1
        return 0

    if args.results_file:
        # Review specific results file via CLI
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
        print("Please specify either --interactive for web interface or --results-file for CLI review")
        return 1

    return 0


def cmd_validate(args):
    """Validate prompt structure and compatibility."""
    project_root = Path(args.project_root)

    if args.prompt == "current":
        prompt_file = project_root / "app" / "prompt.yaml"
    else:
        prompt_file = project_root / "prompt_testing" / "prompts" / f"{args.prompt}.yaml"

    if not prompt_file.exists():
        print(f"Error: Prompt file not found: {prompt_file}")
        return 1

    print(f"Validating prompt: {prompt_file}")

    try:
        # Try to load the prompt using the production Prompt class
        prompt = Prompt(prompt_file)
        print("✓ Prompt structure is valid")

        # Check model configuration
        print(f"✓ Model: {prompt.model}")
        print(f"✓ Max tokens: {prompt.max_tokens}")
        print(f"✓ Temperature: {prompt.temperature}")

        # Check audience levels
        if prompt.audience_levels:
            print(f"✓ Audience levels defined: {', '.join(prompt.audience_levels.keys())}")
        else:
            print("⚠ Warning: No audience levels defined")

        # Check explanation types
        if prompt.explanation_types:
            print(f"✓ Explanation types defined: {', '.join(prompt.explanation_types.keys())}")
        else:
            print("⚠ Warning: No explanation types defined")

        # Test generating messages
        try:
            test_request = ExplainRequest(
                language="C++",
                compiler="gcc 12.1",
                compilationOptions=["-O2"],
                instructionSet="x86_64",
                code="int main() { return 0; }",
                source="int main() { return 0; }",
                asm=[AssemblyItem(text="ret", source={"line": 1})],
                audience="beginner",
                explanation_type="assembly",
            )

            messages = prompt.generate_messages(test_request)
            print(f"✓ Successfully generated {len(messages)} messages")
            print("✓ Prompt is ready for production use")

        except Exception as e:
            print(f"✗ Error generating messages: {e}")
            return 1

    except Exception as e:
        print(f"✗ Error loading prompt: {e}")
        print("\nMake sure the prompt has all required fields:")
        print("- model (with name, max_tokens, temperature)")
        print("- audience_levels")
        print("- explanation_types")
        print("- system_prompt")
        print("- user_prompt")
        print("- assistant_prefill")
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

    # Validate arguments
    if args.create_improved and not args.output:
        print("Error: --output is required when using --create-improved")
        return 1

    optimizer = PromptOptimizer(args.project_root)

    # Find the results file
    if args.results_file:
        results_file = args.results_file
    else:
        results_dir = Path(args.project_root) / "prompt_testing" / "results"
        latest_file = find_latest_results_file(results_dir, args.prompt)
        if not latest_file:
            print(f"No results found for prompt: {args.prompt}")
            print(f"Run 'prompt-test run --prompt {args.prompt}' first")
            return 1
        results_file = latest_file.name
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


def cmd_enrich(args):
    """Enrich test cases with CE API data."""
    input_file = Path(args.input)
    if not input_file.exists():
        print(f"Input file not found: {input_file}")
        return 1

    # Load compiler map if provided
    compiler_map = None
    if args.compiler_map:
        map_file = Path(args.compiler_map)
        if map_file.exists():
            with map_file.open(encoding="utf-8") as f:
                compiler_map = json.load(f)
            print(f"Loaded compiler map with {len(compiler_map)} entries")

    # Create output path
    output_file = None
    if args.output:
        output_file = Path(args.output)

    # Enrich test cases
    with TestCaseEnricher() as enricher:
        try:
            enricher.enrich_file(
                input_file,
                output_file,
                compiler_map,
                delay=args.delay,
            )
        except Exception as e:
            print(f"Enrichment failed: {e}")
            return 1

    return 0


def _generate_compiler_mapping(compilers: list, output_file: Path) -> None:
    """Generate a compiler name to ID mapping file.

    Args:
        compilers: List of compiler objects
        output_file: Path to save the mapping
    """
    mapping = {}
    for compiler in compilers:
        # Use the full name as key
        mapping[compiler.name] = compiler.id
        # Also add common short versions
        if "gcc" in compiler.name.lower():
            # Extract version like "gcc 13.1" from "x86-64 gcc 13.1"
            parts = compiler.name.split()
            for i, part in enumerate(parts):
                if part.lower() == "gcc" and i + 1 < len(parts):
                    short_name = f"gcc {parts[i + 1]}"
                    if short_name not in mapping:
                        mapping[short_name] = compiler.id
                    break

    save_json_results(mapping, output_file)
    print(f"Generated compiler mapping file: {output_file}")


def _filter_compilers(compilers: list, args) -> list:
    """Filter compilers based on command arguments.

    Args:
        compilers: List of compiler objects
        args: Command arguments

    Returns:
        Filtered list of compilers
    """
    # Filter by instruction set if requested
    if args.instruction_set:
        compilers = [c for c in compilers if c.instruction_set == args.instruction_set]
        print(f"Filtered to {len(compilers)} compilers with instruction set '{args.instruction_set}'\\n")

    # Search if requested
    if args.search:
        search_lower = args.search.lower()
        compilers = [c for c in compilers if search_lower in c.name.lower() or search_lower in c.id.lower()]
        print(f"Found {len(compilers)} compilers matching '{args.search}'\\n")

    return compilers


def cmd_compilers(args):
    """List available compilers from CE API."""
    from collections import defaultdict

    with CompilerExplorerClient() as client:
        # Get compilers
        print(f"Fetching compilers{f' for {args.language}' if args.language else ''}...")
        compilers = client.get_compilers(args.language)
        print(f"Found {len(compilers)} compilers\n")

        # Apply filters
        compilers = _filter_compilers(compilers, args)

        if not compilers:
            print("No compilers found matching criteria")
            return 0

        # Generate mapping file if requested
        if args.generate_map:
            _generate_compiler_mapping(compilers, Path(args.generate_map))
            return 0

        # Display compilers
        if args.json:
            # JSON output for scripting
            output = []
            for compiler in compilers:
                output.append(
                    {
                        "id": compiler.id,
                        "name": compiler.name,
                        "version": compiler.version,
                        "lang": compiler.lang,
                        "instruction_set": compiler.instruction_set,
                        "compiler_type": compiler.compiler_type,
                    }
                )
            print(json.dumps(output, indent=2))
        else:
            # Human-readable output
            if args.group:
                # Group by compiler type
                by_type = defaultdict(list)
                for compiler in compilers:
                    by_type[compiler.compiler_type or "unknown"].append(compiler)

                for comp_type, comp_list in sorted(by_type.items()):
                    print(f"\n{comp_type.upper()} ({len(comp_list)} compilers):")
                    for compiler in sorted(comp_list, key=lambda c: c.name)[:20]:
                        print(f"  {compiler.id:25} {compiler.name}")
                    if len(comp_list) > 20:
                        print(f"  ... and {len(comp_list) - 20} more")
            else:
                # List all (limited)
                for compiler in sorted(compilers, key=lambda c: c.name)[: args.limit]:
                    print(f"{compiler.id:25} {compiler.name}")
                    if args.verbose:
                        if compiler.version:
                            print(f"  {'':25} Version: {compiler.version}")
                        if compiler.instruction_set:
                            print(f"  {'':25} Instruction set: {compiler.instruction_set}")
                        if compiler.compiler_type:
                            print(f"  {'':25} Type: {compiler.compiler_type}")
                        print()

                if len(compilers) > args.limit:
                    print(f"\n... and {len(compilers) - args.limit} more compilers")
                    print("Use --limit to show more")

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
  uv run prompt-test run --prompt current --cases basic_loop_001

  # Use a different Claude model for evaluation
  uv run prompt-test run --prompt current --reviewer-model claude-3-5-sonnet-20241022

  # List available test cases and prompts
  uv run prompt-test list

  # Review results interactively (web interface)
  uv run prompt-test review --interactive

  # Review specific results file (CLI)
  uv run prompt-test review --results-file results/20241201_120000_current.json

  # Analyze all results
  uv run prompt-test analyze

  # Get improvement suggestions based on test results
  uv run prompt-test improve --prompt current

  # Create an experimental improved version
  uv run prompt-test improve --prompt current --create-improved --output current_v2

  # List available C++ compilers
  uv run prompt-test compilers --language c++

  # Search for GCC compilers and generate mapping file
  uv run prompt-test compilers --search gcc --generate-map compiler_map.json

  # Enrich test cases with real assembly from CE
  uv run prompt-test enrich --input test_cases/new_tests.yaml --compiler-map compiler_map.json
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

    # Audience and explanation type filtering
    run_parser.add_argument(
        "--audience", choices=["beginner", "intermediate", "expert"], help="Filter test cases by target audience"
    )
    run_parser.add_argument(
        "--explanation-type",
        choices=["assembly", "source", "optimization"],
        help="Filter test cases by explanation type",
    )

    # Claude reviewer configuration
    run_parser.add_argument(
        "--reviewer-model",
        default="claude-sonnet-4-0",
        help="Claude model to use for reviewing (e.g., claude-sonnet-4-0, claude-3-5-sonnet-20241022)",
    )

    run_parser.set_defaults(func=cmd_run)

    # List command
    list_parser = subparsers.add_parser("list", help="List available test cases and prompts")
    list_parser.set_defaults(func=cmd_list)

    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate prompt structure and compatibility")
    validate_parser.add_argument("--prompt", required=True, help="Prompt version to validate")
    validate_parser.set_defaults(func=cmd_validate)

    # Review command
    review_parser = subparsers.add_parser("review", help="Human review interface")
    review_parser.add_argument("--results-file", help="Results file to review (CLI mode)")
    review_parser.add_argument(
        "--interactive", "-i", action="store_true", help="Start web interface for interactive review"
    )
    review_parser.add_argument("--port", type=int, default=5000, help="Port for web interface (default: 5000)")
    review_parser.add_argument("--no-browser", action="store_true", help="Don't automatically open browser")
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

    # Enrich command
    enrich_parser = subparsers.add_parser("enrich", help="Enrich test cases with CE API assembly data")
    enrich_parser.add_argument("--input", "-i", required=True, help="Input test case YAML file")
    enrich_parser.add_argument("--output", "-o", help="Output file (defaults to input.enriched.yaml)")
    enrich_parser.add_argument(
        "--compiler-map",
        "-m",
        help="JSON file mapping test compiler names to CE compiler IDs",
    )
    enrich_parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between API calls in seconds (default: 0.5)",
    )
    enrich_parser.set_defaults(func=cmd_enrich)

    # Compilers command
    compilers_parser = subparsers.add_parser("compilers", help="List and explore CE compilers")
    compilers_parser.add_argument("--language", "-l", help="Filter by language (e.g., c++, c, rust)")
    compilers_parser.add_argument("--search", "-s", help="Search for compiler by name")
    compilers_parser.add_argument("--instruction-set", "-i", help="Filter by instruction set")
    compilers_parser.add_argument("--group", "-g", action="store_true", help="Group by compiler type")
    compilers_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    compilers_parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed compiler info")
    compilers_parser.add_argument("--limit", type=int, default=50, help="Maximum compilers to show (default: 50)")
    compilers_parser.add_argument(
        "--generate-map",
        help="Generate a compiler name to ID mapping file",
    )
    compilers_parser.set_defaults(func=cmd_compilers)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
