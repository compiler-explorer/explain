"""CLI for prompt testing.

Simple commands:
  prompt-test run                  Run all test cases, save results
  prompt-test run --cases foo bar  Run specific cases
  prompt-test run --review         Also run Opus correctness review
  prompt-test review results.json  Review existing results with Opus
  prompt-test compare A B          Compare two result files side by side
  prompt-test list                 List available test cases
  prompt-test enrich               Enrich test cases with real CE assembly
  prompt-test compilers            List CE compilers
"""

import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

import click
from dotenv import load_dotenv

from app.model_costs import get_model_cost
from prompt_testing.ce_api import CompilerExplorerClient
from prompt_testing.enricher import TestCaseEnricher
from prompt_testing.file_utils import load_all_test_cases
from prompt_testing.runner import PromptTester

load_dotenv()


@click.group(help="Prompt testing for Claude explain service")
@click.option("--project-root", default=str(Path.cwd()), type=click.Path(exists=True))
@click.pass_context
def cli(ctx, project_root):
    ctx.ensure_object(dict)
    ctx.obj["project_root"] = Path(project_root)


@cli.command()
@click.option("--prompt", default="current", help="Prompt version to test (default: current)")
@click.option("--cases", multiple=True, help="Specific test case IDs")
@click.option("--categories", multiple=True, help="Filter by category")
@click.option("--output", help="Output filename")
@click.option("--max-concurrent", type=int, default=5)
@click.option("--review", is_flag=True, help="Also run Opus correctness review on results")
@click.option("--review-model", default="claude-opus-4-7", help="Model for correctness review")
@click.option(
    "--reviewer-thinking",
    type=click.Choice(["off", "adaptive"]),
    default="adaptive",
    help="Extended thinking on the reviewer. Default 'adaptive' improves rigor at ~70% extra reviewer cost.",
)
@click.pass_context
def run(ctx, prompt, cases, categories, output, max_concurrent, review, review_model, reviewer_thinking):
    """Run test cases and save results for review."""
    tester = PromptTester(ctx.obj["project_root"], max_concurrent=max_concurrent)
    results = tester.run(
        prompt_version=prompt,
        case_ids=list(cases) if cases else None,
        categories=list(categories) if categories else None,
    )

    if review:
        thinking = {"type": "adaptive"} if reviewer_thinking == "adaptive" else None
        results = asyncio.run(_run_reviews(ctx.obj["project_root"], results, review_model, thinking))

    tester.save(results, output)

    # Summary
    click.echo(
        f"\n{results['successful']}/{results['total_cases']} succeeded, total cost: ${results['total_cost_usd']:.4f}"
    )
    if review:
        _print_review_summary(results)


@cli.command()
@click.argument("file_a")
@click.argument("file_b")
@click.option("--case", help="Show only this case ID")
@click.pass_context
def compare(ctx, file_a, file_b, case):
    """Compare two result files side by side."""
    results_dir = ctx.obj["project_root"] / "prompt_testing" / "results"

    def load(name):
        path = results_dir / name if not Path(name).is_absolute() else Path(name)
        return json.loads(path.read_text())

    a = load(file_a)
    b = load(file_b)

    a_by_id = {r["case_id"]: r for r in a["results"] if r["success"]}
    b_by_id = {r["case_id"]: r for r in b["results"] if r["success"]}

    common = sorted(set(a_by_id) & set(b_by_id))
    if case:
        common = [c for c in common if c == case]

    if not common:
        click.echo("No common successful cases to compare.")
        return

    click.echo(f"Comparing: {a.get('prompt_version', file_a)} vs {b.get('prompt_version', file_b)}")
    click.echo(f"Model A: {a.get('model', '?')}  Model B: {b.get('model', '?')}")
    click.echo()

    total_a_cost = 0
    total_b_cost = 0

    for cid in common:
        ra = a_by_id[cid]
        rb = b_by_id[cid]
        cost_a = ra["input_tokens"] * 3 / 1e6 + ra["output_tokens"] * 15 / 1e6
        cost_b = rb["input_tokens"] * 3 / 1e6 + rb["output_tokens"] * 15 / 1e6
        total_a_cost += cost_a
        total_b_cost += cost_b

        click.echo(f"{'=' * 72}")
        click.echo(f"Case: {cid}")
        click.echo(
            f"  A: {ra['input_tokens']} in, {ra['output_tokens']} out, ${cost_a:.4f}, {ra.get('elapsed_ms', '?')}ms"
        )
        click.echo(
            f"  B: {rb['input_tokens']} in, {rb['output_tokens']} out, ${cost_b:.4f}, {rb.get('elapsed_ms', '?')}ms"
        )
        click.echo()
        click.echo(f"--- A ({a.get('prompt_version', file_a)}) ---")
        click.echo(ra["explanation"][:2000])
        if len(ra["explanation"]) > 2000:
            click.echo(f"... ({len(ra['explanation'])} chars total)")
        click.echo()
        click.echo(f"--- B ({b.get('prompt_version', file_b)}) ---")
        click.echo(rb["explanation"][:2000])
        if len(rb["explanation"]) > 2000:
            click.echo(f"... ({len(rb['explanation'])} chars total)")
        click.echo()

    click.echo(f"{'=' * 72}")
    click.echo(f"Total cost — A: ${total_a_cost:.4f}  B: ${total_b_cost:.4f}")


@cli.command("list")
@click.pass_context
def list_cases(ctx):
    """List available test cases."""
    test_dir = ctx.obj["project_root"] / "prompt_testing" / "test_cases"
    cases = load_all_test_cases(str(test_dir))

    by_cat = defaultdict(list)
    for c in cases:
        by_cat[c.get("category", "unknown")].append(c)

    for cat, items in sorted(by_cat.items()):
        click.echo(f"\n{cat}:")
        for c in items:
            audience = c.get("audience", "beginner")
            click.echo(f"  {c['id']:40} {c.get('description', '')[:50]}  [{audience}]")


@cli.command()
@click.option("--input", "-i", "input_file", required=True, help="Input YAML file")
@click.option("--output", "-o", help="Output file")
@click.option("--compiler-map", "-m", help="Compiler name → CE ID mapping JSON")
@click.option("--max-concurrent", type=int, default=3)
@click.pass_context
def enrich(ctx, input_file, output, compiler_map, max_concurrent):
    """Enrich test cases with real assembly from CE API."""
    input_path = Path(input_file)
    if not input_path.exists():
        click.echo(f"Not found: {input_path}")
        ctx.exit(1)

    compiler_map_data = None
    if compiler_map:
        compiler_map_data = json.loads(Path(compiler_map).read_text())

    output_path = Path(output) if output else None

    with TestCaseEnricher() as enricher:
        asyncio.run(
            enricher.enrich_file_async(input_path, output_path, compiler_map_data, max_concurrent=max_concurrent)
        )


@cli.command()
@click.option("--language", "-l", help="Filter by language")
@click.option("--search", "-s", help="Search by name")
@click.option("--limit", type=int, default=50)
@click.pass_context
def compilers(ctx, language, search, limit):  # noqa: ARG001
    """List available compilers from CE API."""
    with CompilerExplorerClient() as client:
        results = client.get_compilers(language)
        if search:
            sl = search.lower()
            results = [c for c in results if sl in c.name.lower() or sl in c.id.lower()]
        for c in sorted(results, key=lambda c: c.name)[:limit]:
            click.echo(f"{c.id:25} {c.name}")
        if len(results) > limit:
            click.echo(f"... and {len(results) - limit} more")


async def _run_reviews(project_root: Path, results: dict, model: str, thinking: dict | None = None) -> dict:
    """Run correctness reviews on all successful results."""
    from prompt_testing.reviewer import CorrectnessReviewer

    reviewer = CorrectnessReviewer(model=model, thinking=thinking)
    test_dir = project_root / "prompt_testing" / "test_cases"
    all_cases = load_all_test_cases(str(test_dir))
    cases_by_id = {c["id"]: c for c in all_cases}

    successful = [r for r in results["results"] if r["success"]]
    click.echo(f"\nReviewing {len(successful)} results with {model}...")

    review_cost = 0.0
    errors_found = 0
    cost_per_input_token, cost_per_output_token = get_model_cost(model)

    for i, result in enumerate(successful, 1):
        case = cases_by_id.get(result["case_id"])
        if not case:
            continue

        review = await reviewer.review_test_result(case, result["explanation"])
        result["review"] = review

        status = "✓" if review.get("correct") else "✗"
        n_issues = len(review.get("issues", []))
        if not review.get("correct"):
            errors_found += 1
        cost = (
            review.get("reviewer_input_tokens", 0) * cost_per_input_token
            + review.get("reviewer_output_tokens", 0) * cost_per_output_token
        )
        review_cost += cost
        click.echo(f"  [{i}/{len(successful)}] {status} {result['case_id']} ({n_issues} issues, ${cost:.4f})")

    results["review_model"] = model
    results["review_cost_usd"] = round(review_cost, 6)
    results["total_cost_usd"] = round(results["total_cost_usd"] + review_cost, 6)
    results["errors_found"] = errors_found
    return results


def _print_review_summary(results: dict) -> None:
    """Print a summary of correctness reviews."""
    reviewed = [r for r in results["results"] if r.get("review")]
    correct = sum(1 for r in reviewed if r["review"].get("correct"))
    incorrect = len(reviewed) - correct

    click.echo(f"\nCorrectness: {correct}/{len(reviewed)} passed")
    if incorrect:
        click.echo(f"\n⚠ {incorrect} case(s) with issues:")
        for r in reviewed:
            review = r["review"]
            if not review.get("correct"):
                click.echo(f"\n  {r['case_id']}:")
                for issue in review.get("issues", []):
                    sev = "🔴" if issue["severity"] == "error" else "🟡"
                    click.echo(f"    {sev} {issue['claim']}")
                    click.echo(f"       → {issue['correction']}")

    click.echo(f"\nReview cost: ${results.get('review_cost_usd', 0):.4f} ({results.get('review_model', '?')})")


@cli.command()
@click.argument("results_file")
@click.option("--model", default="claude-opus-4-7", help="Reviewer model")
@click.option(
    "--thinking",
    type=click.Choice(["off", "adaptive"]),
    default="adaptive",
    help="Extended thinking on the reviewer (default 'adaptive' for tighter rigor).",
)
@click.pass_context
def review(ctx, results_file, model, thinking):
    """Run Opus correctness review on existing results."""
    results_dir = ctx.obj["project_root"] / "prompt_testing" / "results"
    path = results_dir / results_file if not Path(results_file).is_absolute() else Path(results_file)

    thinking_cfg = {"type": "adaptive"} if thinking == "adaptive" else None
    results = json.loads(path.read_text())
    results = asyncio.run(_run_reviews(ctx.obj["project_root"], results, model, thinking_cfg))

    # Save updated results
    path.write_text(json.dumps(results, indent=2))
    click.echo(f"\nUpdated {path}")
    _print_review_summary(results)


def main():
    cli()


if __name__ == "__main__":
    sys.exit(main())
