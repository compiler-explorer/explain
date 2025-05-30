"""Tests for the scorer module."""

import tempfile
from pathlib import Path

import pytest

from prompt_testing.evaluation.scorer import load_all_test_cases, load_test_case


def test_load_test_case():
    """Test loading a specific test case from a YAML file."""
    # Create a temporary test file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("""
description: "Test cases for testing"
cases:
  - id: test_case_1
    category: basic
    description: "First test case"
    input:
      language: C++
      code: "int main() {}"
  - id: test_case_2
    category: advanced
    description: "Second test case"
    input:
      language: Python
      code: "def main(): pass"
""")
        temp_path = f.name

    try:
        # Test loading existing case
        case = load_test_case(temp_path, "test_case_1")
        assert case["id"] == "test_case_1"
        assert case["category"] == "basic"
        assert case["input"]["language"] == "C++"

        # Test loading non-existent case
        with pytest.raises(ValueError, match="Test case unknown_case not found"):
            load_test_case(temp_path, "unknown_case")
    finally:
        Path(temp_path).unlink()


def test_load_all_test_cases():
    """Test loading all test cases from a directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test files
        file1 = temp_path / "test1.yaml"
        file1.write_text("""
description: "First test file"
cases:
  - id: case1
    category: basic
  - id: case2
    category: advanced
""")

        file2 = temp_path / "test2.yaml"
        file2.write_text("""
description: "Second test file"
cases:
  - id: case3
    category: expert
""")

        # Test loading all cases
        cases = load_all_test_cases(temp_dir)
        assert len(cases) == 3
        assert {case["id"] for case in cases} == {"case1", "case2", "case3"}
        assert {case["category"] for case in cases} == {"basic", "advanced", "expert"}


def test_load_test_case_with_missing_file():
    """Test loading from non-existent file."""
    with pytest.raises(FileNotFoundError):
        load_test_case("/non/existent/file.yaml", "some_case")


def test_load_all_test_cases_empty_dir():
    """Test loading from empty directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        cases = load_all_test_cases(temp_dir)
        assert cases == []


def test_load_test_case_malformed_yaml():
    """Test loading malformed YAML file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("{ invalid yaml content [")
        temp_path = f.name

    try:
        with pytest.raises((ValueError, OSError)):  # YAML parsing error
            load_test_case(temp_path, "test_case")
    finally:
        Path(temp_path).unlink()
