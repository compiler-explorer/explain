"""Common file handling utilities for the prompt testing framework."""

import json
from pathlib import Path
from typing import Any

from prompt_testing.yaml_utils import create_yaml_dumper, load_yaml_file


def ensure_directory(path: Path) -> Path:
    """Ensure a directory exists, creating it if necessary.

    Args:
        path: Directory path to ensure exists

    Returns:
        The path object for chaining
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json_results(data: dict[str, Any], output_path: Path) -> None:
    """Save results to a JSON file with proper error handling.

    Args:
        data: Data to save
        output_path: Path to save to

    Raises:
        RuntimeError: If saving fails
    """
    ensure_directory(output_path.parent)

    try:
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as e:
        raise RuntimeError(f"Failed to save results to {output_path}: {e}") from e


def load_json_results(file_path: Path) -> dict[str, Any]:
    """Load results from a JSON file with error handling.

    Args:
        file_path: Path to load from

    Returns:
        Loaded data

    Raises:
        RuntimeError: If loading fails
    """
    try:
        with file_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise RuntimeError(f"Failed to load results from {file_path}: {e}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON in {file_path}: {e}") from e


def find_latest_results_file(results_dir: Path, prompt_version: str | None = None) -> Path | None:
    """Find the most recent results file, optionally filtered by prompt version.

    Args:
        results_dir: Directory containing result files
        prompt_version: Optional prompt version to filter by

    Returns:
        Path to the most recent matching file, or None if none found
    """
    if not results_dir.exists():
        return None

    pattern = f"*_{prompt_version}.json" if prompt_version else "*.json"
    result_files = list(results_dir.glob(pattern))

    if not result_files:
        return None

    # Sort by modification time, most recent first
    return max(result_files, key=lambda p: p.stat().st_mtime)


def load_prompt_file(prompt_path: Path) -> dict[str, Any]:
    """Load a prompt configuration from YAML file.

    Args:
        prompt_path: Path to the prompt YAML file

    Returns:
        Loaded prompt configuration

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file can't be parsed
    """
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    try:
        return load_yaml_file(prompt_path)
    except Exception as e:
        raise ValueError(f"Failed to load prompt from {prompt_path}: {e}") from e


def save_prompt_file(prompt_data: dict[str, Any], output_path: Path) -> None:
    """Save a prompt configuration to YAML file.

    Args:
        prompt_data: Prompt configuration to save
        output_path: Path to save to

    Raises:
        RuntimeError: If saving fails
    """
    ensure_directory(output_path.parent)
    yaml = create_yaml_dumper()

    try:
        with output_path.open("w", encoding="utf-8") as f:
            yaml.dump(prompt_data, f)
    except OSError as e:
        raise RuntimeError(f"Failed to save prompt to {output_path}: {e}") from e
