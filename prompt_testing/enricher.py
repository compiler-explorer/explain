"""Test case enrichment using Compiler Explorer API."""

import asyncio
from pathlib import Path
from typing import Any

from prompt_testing.ce_api import CompilationError, CompileRequest, CompilerExplorerClient
from prompt_testing.yaml_utils import create_yaml_dumper


class TestCaseEnricher:
    """Enriches test cases with assembly data from Compiler Explorer."""

    def __init__(self, ce_client: CompilerExplorerClient | None = None):
        """Initialize enricher.

        Args:
            ce_client: CE API client instance. If None, creates a new one.
        """
        self.client = ce_client or CompilerExplorerClient()
        self._owned_client = ce_client is None

    def enrich_test_case(self, test_case: dict[str, Any], compiler_map: dict[str, str] | None = None) -> dict[str, Any]:
        """Enrich a single test case with CE API data.

        Args:
            test_case: Test case to enrich
            compiler_map: Optional mapping from test compiler names to CE compiler IDs

        Returns:
            Enriched test case with assembly data
        """
        input_data = test_case.get("input", {})

        # Get compiler ID
        compiler_name = input_data.get("compiler")
        if not compiler_name:
            raise ValueError(f"Test case {test_case['id']} missing compiler field")

        # Use compiler map if provided
        if compiler_map and compiler_name in compiler_map:
            compiler_id = compiler_map[compiler_name]
        else:
            # Try to find compiler by name
            language = input_data.get("language", "").lower() if input_data.get("language") else None

            compiler_info = self.client.find_compiler_by_name(compiler_name, language)
            if not compiler_info:
                raise ValueError(f"Could not find compiler matching '{compiler_name}' for language '{language}'")
            compiler_id = compiler_info.id

        # Prepare compilation request
        source = input_data.get("code", "")
        options = input_data.get("compilationOptions", [])

        request = CompileRequest(
            source=source,
            compiler=compiler_id,
            options=options,
            filters={"labels": True, "directives": True, "commentOnly": True, "intel": True},
        )

        # Compile and get assembly
        print(f"  Compiling {test_case['id']} with {compiler_id}...")
        try:
            response = self.client.compile(request)
        except CompilationError as e:
            print(f"    Compilation failed: {e}")
            if e.stderr:
                print("    Stderr:")
                for line in e.stderr[:5]:  # Show first 5 error lines
                    print(f"      {line}")
            raise

        # Build enriched test case
        enriched = test_case.copy()
        enriched_input = input_data.copy()

        # Add assembly data
        enriched_input["asm"] = [line.to_dict() for line in response.asm]
        enriched_input["labelDefinitions"] = response.label_definitions

        enriched["input"] = enriched_input
        return enriched

    async def enrich_file_async(
        self,
        input_file: Path,
        output_file: Path | None = None,
        compiler_map: dict[str, str] | None = None,
        max_concurrent: int = 3,
    ) -> Path:
        """Enrich all test cases in a YAML file asynchronously.

        Args:
            input_file: Input YAML file with test cases
            output_file: Output file path. If None, enriches in place
            compiler_map: Optional mapping from test compiler names to CE compiler IDs
            max_concurrent: Maximum concurrent API requests

        Returns:
            Path to enriched output file
        """
        # Initialize YAML handler to preserve formatting
        yaml = create_yaml_dumper()

        # Load input file
        with input_file.open(encoding="utf-8") as f:
            data = yaml.load(f)

        if "cases" not in data:
            raise ValueError("Input file missing 'cases' field")

        # Process cases concurrently with rate limiting
        semaphore = asyncio.Semaphore(max_concurrent)

        async def enrich_with_semaphore(case: dict[str, Any], index: int, total: int) -> dict[str, Any]:
            async with semaphore:
                print(f"Processing case {index + 1}/{total}: {case.get('id', 'unknown')}")
                try:
                    # Since the CE client is sync, run in thread pool
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(None, self.enrich_test_case, case, compiler_map)
                except Exception as e:
                    print(f"  Error: {e}")
                    # Continue with other cases
                    return case

        # Create tasks for all test cases
        total = len(data["cases"])
        tasks = [enrich_with_semaphore(case, i, total) for i, case in enumerate(data["cases"])]

        # Run tasks concurrently
        enriched_cases = await asyncio.gather(*tasks)

        # Prepare output
        data["cases"] = enriched_cases

        # Determine output file
        if output_file is None:
            output_file = input_file

        # Write output
        with output_file.open("w", encoding="utf-8") as f:
            yaml.dump(data, f)

        print(f"\nEnriched test cases written to: {output_file}")
        return output_file

    def enrich_file(
        self,
        input_file: Path,
        output_file: Path | None = None,
        compiler_map: dict[str, str] | None = None,
        delay: float = 0.5,
    ) -> Path:
        """Enrich all test cases in a YAML file (synchronous wrapper).

        Args:
            input_file: Input YAML file with test cases
            output_file: Output file path. If None, enriches in place
            compiler_map: Optional mapping from test compiler names to CE compiler IDs
            delay: Delay between API calls in seconds (ignored in async version)

        Returns:
            Path to enriched output file
        """
        # Convert delay to max concurrent requests (approximate)
        max_concurrent = max(1, int(1.0 / delay)) if delay > 0 else 5

        return asyncio.run(self.enrich_file_async(input_file, output_file, compiler_map, max_concurrent))

    def close(self):
        """Close the client if we own it."""
        if self._owned_client and self.client:
            self.client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
