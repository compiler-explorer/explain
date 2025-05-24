"""
Scoring and evaluation system for prompt testing.
"""

from pathlib import Path
from typing import Any

from prompt_testing.yaml_utils import create_yaml_loader


def load_test_case(file_path: str, case_id: str) -> dict[str, Any]:
    """Load a specific test case from a YAML file."""
    path = Path(file_path)
    yaml = create_yaml_loader()
    with path.open(encoding="utf-8") as f:
        data = yaml.load(f)

    for case in data["cases"]:
        if case["id"] == case_id:
            return case

    raise ValueError(f"Test case {case_id} not found in {file_path}")


def load_all_test_cases(test_cases_dir: str) -> list[dict[str, Any]]:
    """Load all test cases from the test_cases directory."""
    all_cases = []
    test_dir = Path(test_cases_dir)
    yaml = create_yaml_loader()

    for file_path in test_dir.glob("*.yaml"):
        with file_path.open(encoding="utf-8") as f:
            data = yaml.load(f)
            all_cases.extend(data["cases"])

    return all_cases
