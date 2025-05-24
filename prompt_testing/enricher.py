"""Test case enrichment using Compiler Explorer API."""

import time
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

    def enrich_file(
        self,
        input_file: Path,
        output_file: Path | None = None,
        compiler_map: dict[str, str] | None = None,
        delay: float = 0.5,
    ) -> Path:
        """Enrich all test cases in a YAML file.

        Args:
            input_file: Input YAML file with test cases
            output_file: Output file path. If None, enriches in place
            compiler_map: Optional mapping from test compiler names to CE compiler IDs
            delay: Delay between API calls in seconds

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

        # Process each case
        enriched_cases = []
        total = len(data["cases"])

        for i, case in enumerate(data["cases"]):
            print(f"Processing case {i + 1}/{total}: {case.get('id', 'unknown')}")
            try:
                enriched = self.enrich_test_case(case, compiler_map)
                enriched_cases.append(enriched)

                # Delay between requests to be nice to the API
                if i < total - 1:
                    time.sleep(delay)

            except Exception as e:
                print(f"  Error: {e}")
                # Continue with other cases
                enriched_cases.append(case)

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
