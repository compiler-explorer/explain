"""Tests for YAML utilities."""

import io
import tempfile
from pathlib import Path

import pytest
from ruamel.yaml import YAMLError

from prompt_testing.yaml_utils import create_yaml_dumper, create_yaml_loader, load_yaml_file, save_yaml_file


class TestYAMLUtils:
    """Test YAML utility functions."""

    def test_multiline_string_formatting(self):
        """Test that multiline strings are formatted with literal block style."""
        yaml = create_yaml_dumper()

        data = {
            "single_line": "This is a single line",
            "multiline": "This is line one\nThis is line two\nThis is line three",
            "nested": {"another_multiline": "First line\nSecond line"},
        }

        # Dump to string
        stream = io.StringIO()
        yaml.dump(data, stream)
        result = stream.getvalue()

        # Check that multiline strings use literal block style
        assert "multiline: |" in result
        assert "another_multiline: |" in result
        # Single line should not use block style
        assert "single_line: |" not in result

    def test_preserves_comments(self):
        """Test that comments are preserved when loading and saving."""
        # Create a YAML file with comments
        yaml_content = """# This is a file comment
name: test  # This is an inline comment
# This is a comment before multiline
description: |
  This is a multiline
  description with multiple lines

# Section comment
section:
  key: value  # Another inline comment
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = Path(f.name)

        try:
            # Load with dumper
            yaml = create_yaml_dumper()
            with temp_path.open() as f:
                data = yaml.load(f)

            # Save it back
            output = io.StringIO()
            yaml.dump(data, output)
            result = output.getvalue()

            # Check that comments are preserved
            assert "# This is a file comment" in result
            assert "# This is an inline comment" in result
            assert "# This is a comment before multiline" in result
            assert "# Section comment" in result
            assert "# Another inline comment" in result

        finally:
            temp_path.unlink()

    def test_preserves_formatting(self):
        """Test that original formatting is preserved when loading and saving."""
        yaml_content = """name: "quoted string"
unquoted: string
number: 42
multiline: |
  Line 1
  Line 2
  Line 3
list:
  - item1
  - item2
  - item3
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = Path(f.name)

        try:
            # Load with dumper
            yaml = create_yaml_dumper()
            with temp_path.open() as f:
                data = yaml.load(f)

            # Save it back
            output = io.StringIO()
            yaml.dump(data, output)
            result = output.getvalue()

            # Check that formatting is preserved
            assert '"quoted string"' in result  # Quotes preserved
            assert "unquoted: string" in result  # No quotes added
            assert "multiline: |" in result  # Block style preserved

        finally:
            temp_path.unlink()

    def test_load_yaml_file(self):
        """Test load_yaml_file function."""
        yaml_content = """
name: test
items:
  - one
  - two
  - three
metadata:
  version: 1.0
  description: |
    A test file
    with multiple lines
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = Path(f.name)

        try:
            # Load the file
            data = load_yaml_file(temp_path)

            # Verify content
            assert data["name"] == "test"
            assert data["items"] == ["one", "two", "three"]
            assert data["metadata"]["version"] == 1.0
            assert "A test file\nwith multiple lines" in data["metadata"]["description"]

        finally:
            temp_path.unlink()

    def test_save_yaml_file_with_multiline(self):
        """Test save_yaml_file properly formats multiline strings."""
        data = {
            "title": "Test Document",
            "content": "Line 1\nLine 2\nLine 3",
            "sections": {
                "intro": "Single line intro",
                "body": "This is the body\nwith multiple paragraphs\nand line breaks",
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.yaml"

            # Save the file
            save_yaml_file(output_path, data)

            # Read it back as text to check formatting
            content = output_path.read_text()

            # Check multiline strings use block style
            assert "content: |" in content
            assert "body: |" in content
            # Single line should not use block style
            assert "title: |" not in content
            assert "intro: |" not in content

    def test_safe_loader_does_not_execute_code(self):
        """Test that safe loader doesn't execute arbitrary code."""
        # YAML with Python code that should not be executed
        dangerous_yaml = """
test: !!python/object/apply:os.system ['echo "danger"']
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(dangerous_yaml)
            temp_path = Path(f.name)

        try:
            # This should raise an error, not execute the code
            with pytest.raises(YAMLError):
                load_yaml_file(temp_path)

        finally:
            temp_path.unlink()

    def test_create_yaml_loader_is_safe(self):
        """Test that create_yaml_loader returns a safe YAML instance."""
        yaml = create_yaml_loader()

        # Should not be able to load Python objects
        dangerous_yaml = "test: !!python/object/apply:os.system ['echo danger']"

        stream = io.StringIO(dangerous_yaml)

        with pytest.raises(YAMLError):
            yaml.load(stream)
