"""Centralized YAML configuration utilities for consistent formatting."""

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML


def create_yaml_loader() -> YAML:
    """Create a YAML instance configured for safe loading.

    This is used for reading YAML files where we don't need to preserve
    formatting or comments.

    Returns:
        YAML instance configured for safe loading
    """
    return YAML(typ="safe")


def create_yaml_dumper() -> YAML:
    """Create a YAML instance configured for output.

    This configuration ensures consistent formatting across all YAML output:
    - Uses literal block style (|) for multiline strings
    - Sets line width to 120 characters
    - Disables flow style for better readability
    - Preserves quotes where present
    - Preserves comments and formatting when round-tripping files

    Returns:
        YAML instance configured for writing
    """
    yaml = YAML()  # Default is round-trip mode which handles all our needs
    yaml.default_flow_style = False
    yaml.width = 120
    yaml.preserve_quotes = True

    # Configure to use literal block style for multiline strings
    def str_presenter(dumper, data):
        if "\n" in data:  # Use literal block style for multiline strings
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    yaml.representer.add_representer(str, str_presenter)

    return yaml


def load_yaml_file(file_path: Path) -> dict[str, Any]:
    """Load a YAML file using safe loading.

    Args:
        file_path: Path to the YAML file

    Returns:
        Parsed YAML content
    """
    yaml = create_yaml_loader()
    with file_path.open(encoding="utf-8") as f:
        return yaml.load(f)


def save_yaml_file(file_path: Path, data: dict[str, Any]) -> None:
    """Save data to a YAML file with consistent formatting.

    Args:
        file_path: Path to save the YAML file
        data: Data to save
    """
    yaml = create_yaml_dumper()
    with file_path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)
