"""Tests for file utilities."""

import tempfile
from pathlib import Path

import pytest

from prompt_testing.file_utils import (
    ensure_directory,
    find_latest_results_file,
    load_json_results,
    save_json_results,
)


def test_ensure_directory():
    """Test directory creation."""
    with tempfile.TemporaryDirectory() as temp_dir:
        test_path = Path(temp_dir) / "a" / "b" / "c"

        # Directory shouldn't exist yet
        assert not test_path.exists()

        # Create it
        result = ensure_directory(test_path)

        # Should exist now and return the path
        assert test_path.exists()
        assert test_path.is_dir()
        assert result == test_path

        # Should be idempotent
        result2 = ensure_directory(test_path)
        assert result2 == test_path


def test_save_and_load_json_results():
    """Test saving and loading JSON results."""
    with tempfile.TemporaryDirectory() as temp_dir:
        test_file = Path(temp_dir) / "results.json"
        test_data = {"test": "data", "numbers": [1, 2, 3], "nested": {"key": "value"}}

        # Save data
        save_json_results(test_data, test_file)
        assert test_file.exists()

        # Load data back
        loaded_data = load_json_results(test_file)
        assert loaded_data == test_data


def test_save_json_results_creates_directory():
    """Test that save creates parent directories."""
    with tempfile.TemporaryDirectory() as temp_dir:
        test_file = Path(temp_dir) / "nested" / "dir" / "results.json"
        test_data = {"test": "data"}

        # Parent directory shouldn't exist
        assert not test_file.parent.exists()

        # Save should create it
        save_json_results(test_data, test_file)
        assert test_file.exists()
        assert test_file.parent.exists()


def test_save_json_results_error_handling():
    """Test error handling for save."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a read-only directory
        read_only_dir = Path(temp_dir) / "readonly"
        read_only_dir.mkdir()
        read_only_dir.chmod(0o444)

        test_data = {"test": "data"}
        test_file = read_only_dir / "test.json"

        with pytest.raises(RuntimeError, match="Failed to save results"):
            save_json_results(test_data, test_file)


def test_load_json_results_file_not_found():
    """Test loading non-existent file."""
    with pytest.raises(RuntimeError, match="Failed to load results"):
        load_json_results(Path("/non/existent/file.json"))


def test_load_json_results_invalid_json():
    """Test loading invalid JSON."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{ invalid json ]")
        temp_path = Path(f.name)

    try:
        with pytest.raises(RuntimeError, match="Invalid JSON"):
            load_json_results(temp_path)
    finally:
        temp_path.unlink()


def test_find_latest_results_file():
    """Test finding the latest results file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        results_dir = Path(temp_dir)

        # Create some test files with different timestamps
        file1 = results_dir / "20240101_120000_prompt1.json"
        file2 = results_dir / "20240102_120000_prompt1.json"
        file3 = results_dir / "20240103_120000_prompt2.json"

        # Create files with slight time delays
        import time

        file1.write_text("{}")
        time.sleep(0.01)
        file2.write_text("{}")
        time.sleep(0.01)
        file3.write_text("{}")

        # Find latest for prompt1
        latest = find_latest_results_file(results_dir, "prompt1")
        assert latest == file2

        # Find latest for prompt2
        latest = find_latest_results_file(results_dir, "prompt2")
        assert latest == file3

        # Find latest overall
        latest = find_latest_results_file(results_dir)
        assert latest == file3


def test_find_latest_results_file_no_results():
    """Test finding results when none exist."""
    with tempfile.TemporaryDirectory() as temp_dir:
        results_dir = Path(temp_dir)

        # No files
        assert find_latest_results_file(results_dir) is None
        assert find_latest_results_file(results_dir, "prompt1") is None

        # Directory doesn't exist
        assert find_latest_results_file(results_dir / "nonexistent") is None
