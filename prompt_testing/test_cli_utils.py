"""Tests for CLI utility functions."""

from unittest.mock import Mock

from prompt_testing.cli import _filter_compilers


class MockCompiler:
    """Simple mock compiler object."""

    def __init__(self, id, name, instruction_set=None):
        self.id = id
        self.name = name
        self.instruction_set = instruction_set


def test_filter_compilers_by_instruction_set(capsys):
    """Test filtering compilers by instruction set."""
    # Mock compiler objects
    compilers = [
        MockCompiler("gcc1", "GCC 1", "x86_64"),
        MockCompiler("gcc2", "GCC 2", "arm64"),
        MockCompiler("gcc3", "GCC 3", "x86_64"),
    ]

    # Mock args
    args = Mock(instruction_set="x86_64", search=None)

    # Filter
    filtered = _filter_compilers(compilers, args)

    # Should only have x86_64 compilers
    assert len(filtered) == 2
    assert all(c.instruction_set == "x86_64" for c in filtered)

    # Check printed output
    captured = capsys.readouterr()
    assert "Filtered to 2 compilers" in captured.out


def test_filter_compilers_by_search(capsys):
    """Test filtering compilers by search term."""
    compilers = [
        MockCompiler("gcc1210", "x86-64 gcc 12.1"),
        MockCompiler("clang1500", "x86-64 clang 15.0.0"),
        MockCompiler("gcc1310", "x86-64 gcc 13.1"),
    ]

    # Search for "gcc"
    args = Mock(instruction_set=None, search="gcc")
    filtered = _filter_compilers(compilers, args)

    assert len(filtered) == 2
    assert all("gcc" in c.name.lower() for c in filtered)

    # Search by ID
    args = Mock(instruction_set=None, search="clang1500")
    filtered = _filter_compilers(compilers, args)

    assert len(filtered) == 1
    assert filtered[0].id == "clang1500"


def test_filter_compilers_combined(capsys):
    """Test filtering with multiple criteria."""
    compilers = [
        MockCompiler("gcc1", "x86-64 gcc 12.1", "x86_64"),
        MockCompiler("gcc2", "arm gcc 12.1", "arm64"),
        MockCompiler("clang1", "x86-64 clang 15.0", "x86_64"),
    ]

    # Filter by instruction set AND search
    args = Mock(instruction_set="x86_64", search="gcc")
    filtered = _filter_compilers(compilers, args)

    assert len(filtered) == 1
    assert filtered[0].id == "gcc1"


def test_generate_compiler_mapping(tmp_path):
    """Test generating compiler name to ID mapping."""
    compilers = [
        MockCompiler("gcc1210", "x86-64 gcc 12.1"),
        MockCompiler("gcc1310", "x86-64 gcc 13.1"),
        MockCompiler("clang1500", "x86-64 clang 15.0.0"),
    ]

    output_file = tmp_path / "mapping.json"

    # Import here to avoid circular import
    import json

    from prompt_testing.cli import _generate_compiler_mapping

    # Generate mapping
    _generate_compiler_mapping(compilers, output_file)

    # Load and verify
    with output_file.open() as f:
        mapping = json.load(f)

    # Should have full names
    assert mapping["x86-64 gcc 12.1"] == "gcc1210"
    assert mapping["x86-64 gcc 13.1"] == "gcc1310"
    assert mapping["x86-64 clang 15.0.0"] == "clang1500"

    # Should have short names for gcc
    assert mapping["gcc 12.1"] == "gcc1210"
    assert mapping["gcc 13.1"] == "gcc1310"

    # Should not have short name for clang (not implemented)
    assert "clang 15.0.0" not in mapping
