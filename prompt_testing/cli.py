#!/usr/bin/env python3
"""
Command-line interface for prompt testing framework.
"""

import asyncio
import json
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from app.explain_api import AssemblyItem, ExplainRequest
from app.explanation_types import AudienceLevel, ExplanationType
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


@click.group(
    help="Prompt testing framework for Claude explain service",
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

  # Publish a tested prompt to production
  uv run prompt-test publish --prompt v7 --name "Production v8"

  # List available C++ compilers
  uv run prompt-test compilers --language c++

  # Search for GCC compilers and generate mapping file
  uv run prompt-test compilers --search gcc --generate-map compiler_map.json

  # Enrich test cases with real assembly from CE
  uv run prompt-test enrich --input test_cases/new_tests.yaml --compiler-map compiler_map.json
""",
)
@click.option(
    "--project-root",
    default=str(Path.cwd()),
    help="Project root directory (default: current directory)",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
)
@click.pass_context
def cli(ctx, project_root):
    """Main CLI group."""
    ctx.ensure_object(dict)
    ctx.obj["project_root"] = Path(project_root)


@cli.command()
@click.option("--prompt", required=True, help="Prompt version to test")
@click.option("--cases", multiple=True, help="Specific test case IDs to run")
@click.option("--categories", multiple=True, help="Test case categories to run")
@click.option("--compare", help="Compare with another prompt version")
@click.option("--output", help="Output file name (auto-generated if not specified)")
@click.option(
    "--audience",
    type=click.Choice([level.value for level in AudienceLevel]),
    help="Filter test cases by target audience",
)
@click.option(
    "--explanation-type",
    type=click.Choice([exp_type.value for exp_type in ExplanationType]),
    help="Filter test cases by explanation type",
)
@click.option(
    "--reviewer-model",
    default="claude-sonnet-4-0",
    help="Claude model to use for reviewing (e.g., claude-sonnet-4-0, claude-3-5-sonnet-20241022)",
)
@click.option(
    "--max-concurrent",
    type=int,
    default=5,
    help="Maximum concurrent API requests (default: 5)",
)
@click.pass_context
def run(ctx, prompt, cases, categories, compare, output, audience, explanation_type, reviewer_model, max_concurrent):
    """Run test suite."""
    project_root = ctx.obj["project_root"]
    tester = PromptTester(
        project_root,
        reviewer_model=reviewer_model,
        max_concurrent_requests=max_concurrent,
    )

    if compare:
        results = tester.compare_prompt_versions(prompt, compare, list(cases) if cases else None)
        output_file = output or f"comparison_{prompt}_vs_{compare}.json"
    else:
        results = tester.run_test_suite(
            prompt,
            list(cases) if cases else None,
            list(categories) if categories else None,
            audience=audience,
            explanation_type=explanation_type,
        )
        output_file = output

    output_path = tester.save_results(results, output_file)

    # Print summary
    if "summary" in results:
        summary = results["summary"]
        click.echo(f"\nSummary for {prompt}:")
        click.echo(f"  Success rate: {summary['success_rate']:.1%}")
        click.echo(f"  Cases: {summary['successful_cases']}/{summary['total_cases']}")

        if "average_metrics" in summary:
            avg = summary["average_metrics"]
            click.echo(f"  Average score: {avg['overall_score']:.2f}")
            click.echo(f"  Accuracy: {avg['accuracy']:.2f}")
            click.echo(f"  Relevance: {avg['relevance']:.2f}")
            click.echo(f"  Conciseness: {avg['conciseness']:.2f}")
            click.echo(f"  Insight: {avg['insight']:.2f}")
            click.echo(f"  Appropriateness: {avg['appropriateness']:.2f}")
            click.echo(f"  Average tokens: {avg['average_tokens']:.0f}")
            click.echo(f"  Average response time: {avg['average_response_time']:.0f}ms")

    if compare and "case_comparisons" in results:
        comparisons = results["case_comparisons"]
        better_v1 = sum(1 for c in comparisons if c.get("better_version") == prompt)
        better_v2 = sum(1 for c in comparisons if c.get("better_version") == compare)
        click.echo(f"\nComparison {prompt} vs {compare}:")
        click.echo(f"  {prompt} better: {better_v1} cases")
        click.echo(f"  {compare} better: {better_v2} cases")

    click.echo(f"\nDetailed results saved to: {output_path}")


@cli.command()
@click.pass_context
def list(ctx):
    """List available test cases and prompts."""
    project_root = ctx.obj["project_root"]

    # List test cases
    click.echo("Available test cases:")
    test_cases = load_all_test_cases(str(project_root / "prompt_testing" / "test_cases"))

    by_category = {}
    for case in test_cases:
        category = case.get("category", "unknown")
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(case)

    for category, cases in sorted(by_category.items()):
        click.echo(f"\n  {category}:")
        for case in cases:
            quality = case.get("quality", "unknown")
            difficulty = case.get("difficulty", "unknown")
            click.echo(f"    {case['id']} - {case.get('description', 'No description')} ({quality}, {difficulty})")

    # List prompts
    click.echo("\nAvailable prompts:")
    prompts_dir = project_root / "prompt_testing" / "prompts"
    if prompts_dir.exists():
        for prompt_file in sorted(prompts_dir.glob("*.yaml")):
            prompt_name = prompt_file.stem
            click.echo(f"  {prompt_name}")
    else:
        click.echo("  No prompts directory found")


@cli.command()
@click.option("--results-file", help="Results file to review (CLI mode)")
@click.option("--interactive", "-i", is_flag=True, help="Start web interface for interactive review")
@click.option("--port", type=int, default=5000, help="Port for web interface (default: 5000)")
@click.option("--no-browser", is_flag=True, help="Don't automatically open browser")
@click.pass_context
def review(ctx, results_file, interactive, port, no_browser):
    """Human review interface."""
    project_root = ctx.obj["project_root"]

    if interactive:
        # Start web interface
        try:
            start_review_server(project_root, port=port, open_browser=not no_browser)
        except KeyboardInterrupt:
            click.echo("\n🛑 Review server stopped")
        except Exception as e:
            click.echo(f"❌ Error starting review server: {e}")
            ctx.exit(1)
        return

    if results_file:
        # Review specific results file via CLI
        results_path = Path(results_file)
        with results_path.open() as f:
            results = json.load(f)

        if "results" in results:
            # Single test run
            for result in results["results"]:
                if not result["success"]:
                    continue

                review = create_simple_review_cli(result["case_id"], result["response"], result["prompt_version"])

                # Save review
                manager = ReviewManager(str(Path(project_root) / "prompt_testing" / "results"))
                manager.save_review(review)

                click.echo("Review saved!")

                if click.confirm("\nContinue to next case?", default=False):
                    continue
                break
        else:
            click.echo("Invalid results file format")
            ctx.exit(1)
    else:
        click.echo("Please specify either --interactive for web interface or --results-file for CLI review")
        ctx.exit(1)


@cli.command()
@click.option("--prompt", required=True, help="Prompt version to validate")
@click.pass_context
def validate(ctx, prompt):
    """Validate prompt structure and compatibility."""
    project_root = ctx.obj["project_root"]

    if prompt == "current":
        prompt_file = project_root / "app" / "prompt.yaml"
    else:
        prompt_file = project_root / "prompt_testing" / "prompts" / f"{prompt}.yaml"

    if not prompt_file.exists():
        click.echo(f"Error: Prompt file not found: {prompt_file}")
        ctx.exit(1)

    click.echo(f"Validating prompt: {prompt_file}")

    try:
        # Try to load the prompt using the production Prompt class
        prompt_obj = Prompt(prompt_file)
        click.echo("✓ Prompt structure is valid")

        # Check model configuration
        click.echo(f"✓ Model: {prompt_obj.model}")
        click.echo(f"✓ Max tokens: {prompt_obj.max_tokens}")
        click.echo(f"✓ Temperature: {prompt_obj.temperature}")

        # Check audience levels
        if prompt_obj.audience_levels:
            click.echo(f"✓ Audience levels defined: {', '.join(prompt_obj.audience_levels.keys())}")
        else:
            click.echo("⚠ Warning: No audience levels defined")

        # Check explanation types
        if prompt_obj.explanation_types:
            click.echo(f"✓ Explanation types defined: {', '.join(prompt_obj.explanation_types.keys())}")
        else:
            click.echo("⚠ Warning: No explanation types defined")

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

            messages = prompt_obj.generate_messages(test_request)
            click.echo(f"✓ Successfully generated {len(messages)} messages")
            click.echo("✓ Prompt is ready for production use")

        except Exception as e:
            click.echo(f"✗ Error generating messages: {e}")
            ctx.exit(1)

    except Exception as e:
        click.echo(f"✗ Error loading prompt: {e}")
        click.echo("\nMake sure the prompt has all required fields:")
        click.echo("- model (with name, max_tokens, temperature)")
        click.echo("- audience_levels")
        click.echo("- explanation_types")
        click.echo("- system_prompt")
        click.echo("- user_prompt")
        click.echo("- assistant_prefill")
        ctx.exit(1)


@cli.command()
@click.pass_context
def analyze(ctx):
    """Analyze results and generate reports."""
    project_root = ctx.obj["project_root"]
    results_dir = project_root / "prompt_testing" / "results"

    if not results_dir.exists():
        click.echo("No results directory found")
        ctx.exit(1)

    # Find all result files
    result_files = list(results_dir.glob("*.json"))
    if not result_files:
        click.echo("No result files found")
        ctx.exit(1)

    click.echo(f"Found {len(result_files)} result files:")

    all_summaries = []
    for result_file in sorted(result_files):
        try:
            with result_file.open() as f:
                data = json.load(f)

            if "summary" in data:
                summary = data["summary"]
                summary["file"] = result_file.name
                all_summaries.append(summary)

                click.echo(f"\n{result_file.name}:")
                click.echo(f"  Prompt: {summary['prompt_version']}")
                click.echo(f"  Success rate: {summary['success_rate']:.1%}")
                click.echo(f"  Cases: {summary['successful_cases']}/{summary['total_cases']}")

                if "average_metrics" in summary:
                    avg = summary["average_metrics"]
                    click.echo(f"  Avg score: {avg['overall_score']:.2f}")
                    click.echo(f"  Accuracy: {avg['accuracy']:.2f}")
                    click.echo(f"  Relevance: {avg['relevance']:.2f}")
                    click.echo(f"  Conciseness: {avg['conciseness']:.2f}")
                    click.echo(f"  Insight: {avg['insight']:.2f}")
                    click.echo(f"  Appropriateness: {avg['appropriateness']:.2f}")

        except Exception as e:
            click.echo(f"  Error reading {result_file.name}: {e}")

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

        click.echo(f"\nAnalysis summary saved to: {summary_file}")


@cli.command()
@click.option("--prompt", required=True, help="Prompt version to publish")
@click.option("--name", help="Production name for the prompt (auto-generated if not specified)")
@click.option("--description", help="Production description (auto-cleaned if not specified)")
@click.pass_context
def publish(ctx, prompt, name, description):
    """Publish a tested prompt to production (app/prompt.yaml)."""
    import shutil
    import subprocess
    import tempfile

    from ruamel.yaml import YAML

    project_root = ctx.obj["project_root"]
    prompt_file = project_root / "prompt_testing" / "prompts" / f"{prompt}.yaml"
    production_file = project_root / "app" / "prompt.yaml"

    # Check if prompt file exists
    if not prompt_file.exists():
        click.echo(f"✗ Prompt file not found: {prompt_file}")
        ctx.exit(1)

    click.echo(f"📋 Publishing prompt '{prompt}' to production...")

    try:
        # Load and clean up the prompt
        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.default_flow_style = False

        with prompt_file.open(encoding="utf-8") as f:
            prompt_data = yaml.load(f)

        # Clean up metadata for production
        original_name = prompt_data.get("name", prompt)
        original_description = prompt_data.get("description", "")

        # Remove experimental metadata
        if "experiment_metadata" in prompt_data:
            click.echo("🧹 Removing experiment_metadata for production")
            del prompt_data["experiment_metadata"]

        # Update name and description for production
        if name:
            prompt_data["name"] = name
            click.echo(f"📝 Updated name: '{original_name}' → '{name}'")
        else:
            # Auto-generate production name
            prod_name = f"Production {original_name.replace('Version', 'v').strip()}"
            prompt_data["name"] = prod_name
            click.echo(f"📝 Auto-generated name: '{original_name}' → '{prod_name}'")

        if description:
            prompt_data["description"] = description
            click.echo("📝 Updated description")
        else:
            # Clean up description to remove experimental language
            clean_desc = original_description.replace("Human feedback integration", "Production prompt")
            clean_desc = clean_desc.replace("improved markdown formatting, conciseness", "optimized for clarity")
            clean_desc = clean_desc.replace("based on", "incorporating")
            prompt_data["description"] = clean_desc
            if clean_desc != original_description:
                click.echo("📝 Cleaned up description for production")

        # Write to temporary file first
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as temp_file:
            yaml.dump(prompt_data, temp_file)
            temp_path = Path(temp_file.name)

        click.echo("✅ Cleaned up prompt metadata")

        # Validate the prompt loads correctly in main service
        click.echo("🔍 Validating prompt structure...")
        try:
            from app.prompt import Prompt

            prompt_obj = Prompt(temp_path)
            click.echo("✅ Prompt structure validation passed")
        except Exception as e:
            click.echo(f"✗ Prompt validation failed: {e}")
            temp_path.unlink()  # Clean up temp file
            ctx.exit(1)

        # Test that we can generate messages
        click.echo("🧪 Testing message generation...")
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
            messages = prompt_obj.generate_messages(test_request)
            click.echo(f"✅ Successfully generated {len(messages)} messages")
        except Exception as e:
            click.echo(f"✗ Message generation test failed: {e}")
            temp_path.unlink()  # Clean up temp file
            ctx.exit(1)

        # Backup existing production prompt
        if production_file.exists():
            backup_file = production_file.with_suffix(".yaml.backup")
            shutil.copy2(production_file, backup_file)
            click.echo(f"💾 Backed up existing prompt to {backup_file.name}")

        # Copy to production
        shutil.copy2(temp_path, production_file)
        temp_path.unlink()  # Clean up temp file
        click.echo(f"🚀 Copied prompt to {production_file}")

        # Run integration tests
        click.echo("🧪 Running integration tests...")
        try:
            result = subprocess.run(
                ["uv", "run", "pytest", "app/test_explain.py", "-v"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                click.echo("✅ Integration tests passed")
            else:
                click.echo("⚠️  Integration tests had issues:")
                click.echo(result.stdout)
                if result.stderr:
                    click.echo("STDERR:")
                    click.echo(result.stderr)
                click.echo("❗ Consider reviewing the test failures")
        except subprocess.TimeoutExpired:
            click.echo("⚠️  Integration tests timed out")
        except Exception as e:
            click.echo(f"⚠️  Could not run integration tests: {e}")

        click.echo(f"\n🎉 Successfully published '{prompt}' to production!")
        click.echo(f"📁 Location: {production_file}")
        click.echo("\n📋 Next steps:")
        click.echo("  1. Test the service locally: uv run fastapi dev")
        click.echo("  2. Run manual tests: ./test-explain.sh")
        click.echo("  3. Commit the changes: git add app/prompt.yaml && git commit")

    except Exception as e:
        click.echo(f"✗ Publication failed: {e}")
        ctx.exit(1)


@cli.command()
@click.option("--prompt", required=True, help="Prompt version to improve")
@click.option("--results-file", help="Specific results file to analyze (uses most recent if not specified)")
@click.option("--show-suggestions", is_flag=True, default=True, help="Display suggestions in terminal")
@click.option("--create-improved", is_flag=True, help="Create an experimental improved prompt version")
@click.option("--output", help="Name for the improved prompt version")
@click.pass_context
def improve(ctx, prompt, results_file, show_suggestions, create_improved, output):
    """Analyze results and suggest prompt improvements."""
    project_root = ctx.obj["project_root"]

    # Validate arguments
    if create_improved and not output:
        click.echo("Error: --output is required when using --create-improved")
        ctx.exit(1)

    optimizer = PromptOptimizer(project_root)

    # Find the results file
    if results_file:
        results_file_path = results_file
    else:
        results_dir = project_root / "prompt_testing" / "results"
        latest_file = find_latest_results_file(results_dir, prompt)
        if not latest_file:
            click.echo(f"No results found for prompt: {prompt}")
            click.echo(f"Run 'prompt-test run --prompt {prompt}' first")
            ctx.exit(1)
        results_file_path = latest_file.name
        click.echo(f"Using most recent results: {results_file_path}")

    # Analyze and potentially create improved version with human feedback integration
    output_path, human_stats = optimizer.analyze_and_improve_with_human_feedback(
        results_file_path, prompt, output if create_improved else None
    )

    # Show human review status
    if human_stats["total_reviews"] > 0:
        coverage_pct = human_stats["coverage"] * 100
        click.echo(f"✓ Incorporated {human_stats['total_reviews']} human reviews ({coverage_pct:.0f}% coverage)")
    else:
        click.echo("📝 No human reviews found, using automated analysis only")

    # Display key suggestions
    if show_suggestions and not create_improved:
        with output_path.open() as f:
            analysis = json.load(f)

        click.echo("\n=== PROMPT IMPROVEMENT SUGGESTIONS ===")

        if "analysis_summary" in analysis:
            summary = analysis["analysis_summary"]
            click.echo(f"\nAverage Score: {summary['average_score']:.2f}")
            click.echo("\nMost Common Missing Topics:")
            topics = summary.get("common_missing_topics", [])
            if topics:
                for topic in topics:
                    click.echo(f"  - {topic}")
            else:
                click.echo("  None identified")

        if "suggestions" in analysis and isinstance(analysis["suggestions"], dict):
            suggestions = analysis["suggestions"]

            if "priority_improvements" in suggestions:
                click.echo("\n🎯 Priority Improvements:")
                for imp in suggestions["priority_improvements"][:3]:
                    click.echo(f"\n  Issue: {imp['issue']}")
                    click.echo(f"  Current: '{imp.get('current_text', 'N/A')[:60]}...'")
                    click.echo(f"  Suggested: '{imp.get('suggested_text', 'N/A')[:60]}...'")
                    click.echo(f"  Rationale: {imp.get('rationale', 'N/A')}")

            if "expected_impact" in suggestions:
                click.echo(f"\n✨ Expected Impact: {suggestions['expected_impact']}")


@cli.command()
@click.option("--input", "-i", required=True, help="Input test case YAML file")
@click.option("--output", "-o", help="Output file (defaults to input.enriched.yaml)")
@click.option("--compiler-map", "-m", help="JSON file mapping test compiler names to CE compiler IDs")
@click.option(
    "--delay",
    type=float,
    default=0.5,
    help="Delay between API calls in seconds (default: 0.5, ignored when using parallel mode)",
)
@click.option("--max-concurrent", type=int, default=3, help="Maximum concurrent CE API requests (default: 3)")
@click.pass_context
def enrich(ctx, input, output, compiler_map, delay, max_concurrent):  # noqa: ARG001
    """Enrich test cases with CE API data."""
    input_file = Path(input)
    if not input_file.exists():
        click.echo(f"Input file not found: {input_file}")
        ctx.exit(1)

    # Load compiler map if provided
    compiler_map_data = None
    if compiler_map:
        map_file = Path(compiler_map)
        if map_file.exists():
            with map_file.open(encoding="utf-8") as f:
                compiler_map_data = json.load(f)
            click.echo(f"Loaded compiler map with {len(compiler_map_data)} entries")

    # Create output path
    output_file = None
    if output:
        output_file = Path(output)

    # Enrich test cases
    with TestCaseEnricher() as enricher:
        try:
            # Use async version with max_concurrent parameter
            asyncio.run(
                enricher.enrich_file_async(
                    input_file,
                    output_file,
                    compiler_map_data,
                    max_concurrent=max_concurrent,
                )
            )
        except Exception as e:
            click.echo(f"Enrichment failed: {e}")
            ctx.exit(1)


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
    click.echo(f"Generated compiler mapping file: {output_file}")


def _filter_compilers(compilers: list, instruction_set, search) -> list:
    """Filter compilers based on command arguments.

    Args:
        compilers: List of compiler objects
        instruction_set: Instruction set filter
        search: Search string

    Returns:
        Filtered list of compilers
    """
    # Filter by instruction set if requested
    if instruction_set:
        compilers = [c for c in compilers if c.instruction_set == instruction_set]
        click.echo(f"Filtered to {len(compilers)} compilers with instruction set '{instruction_set}'\n")

    # Search if requested
    if search:
        search_lower = search.lower()
        compilers = [c for c in compilers if search_lower in c.name.lower() or search_lower in c.id.lower()]
        click.echo(f"Found {len(compilers)} compilers matching '{search}'\n")

    return compilers


@cli.command()
@click.option("--language", "-l", help="Filter by language (e.g., c++, c, rust)")
@click.option("--search", "-s", help="Search for compiler by name")
@click.option("--instruction-set", "-i", help="Filter by instruction set")
@click.option("--group", "-g", is_flag=True, help="Group by compiler type")
@click.option("--json", "json_output", is_flag=True, help="Output in JSON format")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed compiler info")
@click.option("--limit", type=int, default=50, help="Maximum compilers to show (default: 50)")
@click.option("--generate-map", help="Generate a compiler name to ID mapping file")
@click.pass_context
def compilers(ctx, language, search, instruction_set, group, json_output, verbose, limit, generate_map):  # noqa: ARG001
    """List available compilers from CE API."""
    from collections import defaultdict

    with CompilerExplorerClient() as client:
        # Get compilers
        click.echo(f"Fetching compilers{f' for {language}' if language else ''}...")
        compilers = client.get_compilers(language)
        click.echo(f"Found {len(compilers)} compilers\n")

        # Apply filters
        compilers = _filter_compilers(compilers, instruction_set, search)

        if not compilers:
            click.echo("No compilers found matching criteria")
            return

        # Generate mapping file if requested
        if generate_map:
            _generate_compiler_mapping(compilers, Path(generate_map))
            return

        # Display compilers
        if json_output:
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
            click.echo(json.dumps(output, indent=2))
        else:
            # Human-readable output
            if group:
                # Group by compiler type
                by_type = defaultdict(list)
                for compiler in compilers:
                    by_type[compiler.compiler_type or "unknown"].append(compiler)

                for comp_type, comp_list in sorted(by_type.items()):
                    click.echo(f"\n{comp_type.upper()} ({len(comp_list)} compilers):")
                    for compiler in sorted(comp_list, key=lambda c: c.name)[:20]:
                        click.echo(f"  {compiler.id:25} {compiler.name}")
                    if len(comp_list) > 20:
                        click.echo(f"  ... and {len(comp_list) - 20} more")
            else:
                # List all (limited)
                for compiler in sorted(compilers, key=lambda c: c.name)[:limit]:
                    click.echo(f"{compiler.id:25} {compiler.name}")
                    if verbose:
                        if compiler.version:
                            click.echo(f"  {'':25} Version: {compiler.version}")
                        if compiler.instruction_set:
                            click.echo(f"  {'':25} Instruction set: {compiler.instruction_set}")
                        if compiler.compiler_type:
                            click.echo(f"  {'':25} Type: {compiler.compiler_type}")
                        click.echo()

                if len(compilers) > limit:
                    click.echo(f"\n... and {len(compilers) - limit} more compilers")
                    click.echo("Use --limit to show more")


def main():
    """Main CLI entry point."""
    cli()


if __name__ == "__main__":
    sys.exit(main())
