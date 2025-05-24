import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.explain import process_request
from app.explain_api import (
    AssemblyItem,
    ExplainRequest,
    SourceMapping,
)
from app.metrics import NoopMetricsProvider
from app.prompt import MAX_ASSEMBLY_LINES, Prompt


@pytest.fixture
def sample_assembly_items():
    """Create sample assembly items for testing."""
    return [
        AssemblyItem(text="square(int):", source=None, labels=[]),
        AssemblyItem(
            text="        mov     eax, edi",
            source=SourceMapping(line=1, column=21),
            labels=[],
        ),
        AssemblyItem(
            text="        imul    eax, edi",
            source=SourceMapping(line=2, column=10),
            labels=[],
        ),
        AssemblyItem(
            text="        ret",
            source=SourceMapping(line=2, column=10),
            labels=[],
        ),
    ]


@pytest.fixture
def sample_request(sample_assembly_items):
    """Create a sample ExplainRequest for testing."""
    return ExplainRequest(
        language="c++",
        compiler="g++",
        code="int square(int x) {\n  return x * x;\n}",
        compilationOptions=["-O2", "-g"],
        instructionSet="amd64",
        asm=sample_assembly_items,
        labelDefinitions={"square(int)": 0},
    )


@pytest.fixture
def mock_anthropic_client():
    """Create a mock Anthropic client."""
    mock_client = MagicMock()
    mock_message = MagicMock()
    mock_content = MagicMock()
    mock_content.text = "This assembly code implements a simple square function..."
    mock_message.content = [mock_content]

    # Add usage information to the mock
    mock_message.usage = MagicMock()
    mock_message.usage.input_tokens = 100
    mock_message.usage.output_tokens = 50

    mock_client.messages.create.return_value = mock_message
    return mock_client


@pytest.fixture
def noop_metrics():
    """Create a NoopMetricsProvider for testing."""
    return NoopMetricsProvider()


class TestProcessRequest:
    """Test the main process_request function."""

    def test_process_request_success(self, sample_request, mock_anthropic_client, noop_metrics):
        """Test successful processing of a request."""
        # Create a test prompt instance using the actual prompt.yaml
        test_prompt = Prompt(Path("app/prompt.yaml"))
        response = process_request(sample_request, mock_anthropic_client, test_prompt, noop_metrics)

        # Verify response structure
        assert response.status == "success"
        assert response.explanation == "This assembly code implements a simple square function..."
        assert response.model == test_prompt.model

        # Check usage information
        assert response.usage is not None
        assert response.usage.input_tokens == 100
        assert response.usage.output_tokens == 50
        assert response.usage.total_tokens == 150

        # Check cost information
        assert response.cost is not None
        assert isinstance(response.cost.input_cost, float)
        assert isinstance(response.cost.output_cost, float)
        assert isinstance(response.cost.total_cost, float)

        # Verify the mock was called correctly
        mock_anthropic_client.messages.create.assert_called_once()
        args, kwargs = mock_anthropic_client.messages.create.call_args

        # Check that key parameters were passed
        assert kwargs["model"] == test_prompt.model
        assert kwargs["max_tokens"] == test_prompt.max_tokens
        assert "system" in kwargs

        # Verify the system prompt contains appropriate instructions
        system_prompt = kwargs["system"]
        assert "expert" in system_prompt.lower()
        assert "assembly" in system_prompt.lower()
        assert "c++" in system_prompt.lower()
        assert "amd64" in system_prompt.lower()

        # Check that the messages array contains user and assistant messages
        messages = kwargs["messages"]
        assert len(messages) == 2

        # Check user message
        assert messages[0]["role"] == "user"
        assert len(messages[0]["content"]) == 2
        assert messages[0]["content"][0]["type"] == "text"
        assert "amd64" in messages[0]["content"][0]["text"]
        assert messages[0]["content"][1]["type"] == "text"

        # Check assistant message
        assert messages[1]["role"] == "assistant"
        assert len(messages[1]["content"]) == 1
        assert messages[1]["content"][0]["type"] == "text"
        assert "analysis" in messages[1]["content"][0]["text"]

        # Check the structured data has expected fields
        structured_data = json.loads(messages[0]["content"][1]["text"])
        assert structured_data["language"] == "c++"
        assert structured_data["compiler"] == "g++"
        assert structured_data["sourceCode"] == "int square(int x) {\n  return x * x;\n}"


class TestSelectImportantAssembly:
    """Test the select_important_assembly function."""

    def test_select_important_assembly_under_limit(self):
        """Test that assembly under the limit is returned unchanged."""
        test_asm = [
            {"text": "main:", "source": None, "labels": []},
            {
                "text": "  mov eax, edi",
                "source": {"line": 1, "column": 0},
                "labels": [],
            },
            {"text": "  ret", "source": None, "labels": []},
        ]
        label_defs = {"main": 0}

        # Create a minimal prompt instance for testing
        test_prompt = Prompt(
            {
                "model": {"name": "test", "max_tokens": 100},
                "system_prompt": "",
                "user_prompt": "",
                "assistant_prefill": "",
                "audience_levels": {},
                "explanation_types": {},
            }
        )
        result = test_prompt.select_important_assembly(test_asm, label_defs, max_lines=10)

        assert len(result) == 3
        assert result == test_asm

    def test_select_important_assembly_over_limit(self):
        """Test assembly selection when over the limit."""
        # Create test assembly with more lines than the max
        test_asm = []
        for i in range(50):
            asm_line = {"text": f"instruction {i}", "source": None, "labels": []}
            # Add source mapping to some lines to make them important
            if i % 10 == 0:
                asm_line["source"] = {"line": i // 10, "column": 0}
            # Add some return instructions
            if i % 20 == 19:
                asm_line["text"] = "ret"
            test_asm.append(asm_line)

        # Label definitions for function starts
        label_defs = {
            "func1": 0,
            "func2": 20,
            "func3": 40,
        }

        # Run the function with a small max_lines for testing
        # Create a minimal prompt instance for testing
        test_prompt = Prompt(
            {
                "model": {"name": "test", "max_tokens": 100},
                "system_prompt": "",
                "user_prompt": "",
                "assistant_prefill": "",
                "audience_levels": {},
                "explanation_types": {},
            }
        )
        result = test_prompt.select_important_assembly(test_asm, label_defs, max_lines=15)

        # Verify the result has fewer lines than the original
        # Note: The function may exceed max_lines slightly due to context lines and omission markers
        assert len(result) < len(test_asm)

        # Check that we have some omission markers
        has_markers = any("isOmissionMarker" in line for line in result)
        assert has_markers

        # Check that important lines (with sources) are included
        has_source_lines = False
        for line in result:
            if (
                "isOmissionMarker" not in line
                and line.get("source") is not None
                and isinstance(line["source"], dict)
                and line["source"].get("line") is not None
            ):
                has_source_lines = True
                break
        assert has_source_lines

    def test_select_important_assembly_preserves_function_boundaries(self):
        """Test that function boundaries are preserved."""
        test_asm = []
        for i in range(100):
            test_asm.append({"text": f"instruction {i}", "source": None, "labels": []})

        # Add function labels
        test_asm[0]["text"] = "func1:"
        test_asm[50]["text"] = "func2:"

        # Add return instructions
        test_asm[25]["text"] = "ret"
        test_asm[75]["text"] = "ret"

        label_defs = {"func1": 0, "func2": 50}

        # Create a minimal prompt instance for testing
        test_prompt = Prompt(
            {
                "model": {"name": "test", "max_tokens": 100},
                "system_prompt": "",
                "user_prompt": "",
                "assistant_prefill": "",
                "audience_levels": {},
                "explanation_types": {},
            }
        )
        result = test_prompt.select_important_assembly(test_asm, label_defs, max_lines=20)

        # Check that function labels are included
        func_labels = [line["text"] for line in result if "func" in line["text"]]
        assert len(func_labels) > 0

        # Check that return instructions are included
        ret_instructions = [line["text"] for line in result if line["text"] == "ret"]
        assert len(ret_instructions) > 0


class TestPrepareStructuredData:
    """Test the prepare_structured_data function."""

    def test_prepare_structured_data_basic(self, sample_request):
        """Test basic structured data preparation."""
        # Create a minimal prompt instance for testing
        test_prompt = Prompt(
            {
                "model": {"name": "test", "max_tokens": 100},
                "system_prompt": "",
                "user_prompt": "",
                "assistant_prefill": "",
                "audience_levels": {},
                "explanation_types": {},
            }
        )
        result = test_prompt.prepare_structured_data(sample_request)

        # Verify all required fields exist
        assert result["language"] == "c++"
        assert result["compiler"] == "g++"
        assert result["sourceCode"] == "int square(int x) {\n  return x * x;\n}"
        assert result["compilationOptions"] == ["-O2", "-g"]
        assert result["instructionSet"] == "amd64"
        assert len(result["assembly"]) == 4
        assert result["labelDefinitions"] == {"square(int)": 0}
        assert result["compilerMessages"] == []
        assert result["optimizationRemarks"] == []
        assert not result["truncated"]

    def test_prepare_structured_data_missing_optional_fields(self):
        """Test structured data preparation with missing optional fields."""
        minimal_request = ExplainRequest(
            language="rust",
            compiler="rustc",
            code="fn main() {}",
            asm=[AssemblyItem(text="main:", source=None)],
        )

        # Create a minimal prompt instance for testing
        test_prompt = Prompt(
            {
                "model": {"name": "test", "max_tokens": 100},
                "system_prompt": "",
                "user_prompt": "",
                "assistant_prefill": "",
                "audience_levels": {},
                "explanation_types": {},
            }
        )
        result = test_prompt.prepare_structured_data(minimal_request)

        assert result["language"] == "rust"
        assert result["compiler"] == "rustc"
        assert result["instructionSet"] == "unknown"  # Default when None
        assert result["compilationOptions"] == []  # Default empty list
        assert result["labelDefinitions"] == {}  # Default when None

    def test_prepare_structured_data_truncation(self):
        """Test structured data preparation with truncation for large assembly."""
        # Create a large assembly array
        large_asm = []
        for i in range(MAX_ASSEMBLY_LINES + 100):
            large_asm.append(AssemblyItem(text=f"instruction {i}", source=None))

        large_request = ExplainRequest(
            language="c++",
            compiler="g++",
            code="int main() { return 0; }",
            asm=large_asm,
        )

        # Create a minimal prompt instance for testing
        test_prompt = Prompt(
            {
                "model": {"name": "test", "max_tokens": 100},
                "system_prompt": "",
                "user_prompt": "",
                "assistant_prefill": "",
                "audience_levels": {},
                "explanation_types": {},
            }
        )
        result = test_prompt.prepare_structured_data(large_request)

        # Verify truncation occurred
        assert result["truncated"]
        assert result["originalLength"] == MAX_ASSEMBLY_LINES + 100
        assert len(result["assembly"]) <= MAX_ASSEMBLY_LINES

    def test_prepare_structured_data_assembly_dict_conversion(self, sample_request):
        """Test that assembly items are properly converted to dicts."""
        # Create a minimal prompt instance for testing
        test_prompt = Prompt(
            {
                "model": {"name": "test", "max_tokens": 100},
                "system_prompt": "",
                "user_prompt": "",
                "assistant_prefill": "",
                "audience_levels": {},
                "explanation_types": {},
            }
        )
        result = test_prompt.prepare_structured_data(sample_request)

        # Check that assembly items are dictionaries
        for asm_item in result["assembly"]:
            assert isinstance(asm_item, dict)
            assert "text" in asm_item

        # Check specific assembly content
        assert result["assembly"][0]["text"] == "square(int):"
        assert result["assembly"][1]["text"] == "        mov     eax, edi"
        assert result["assembly"][1]["source"]["line"] == 1
        assert result["assembly"][1]["source"]["column"] == 21


class TestValidation:
    """Test Pydantic validation behavior."""

    def test_request_validation_success(self, sample_assembly_items):
        """Test that valid request data validates correctly."""
        request_data = {
            "language": "c++",
            "compiler": "g++",
            "code": "int main() { return 0; }",
            "asm": [item.model_dump() for item in sample_assembly_items],
        }

        request = ExplainRequest.model_validate(request_data)
        assert request.language == "c++"
        assert request.compiler == "g++"
        assert len(request.asm) == 4

    def test_request_validation_missing_required_field(self):
        """Test that missing required fields raise validation errors."""
        request_data = {
            "compiler": "g++",
            "code": "int main() { return 0; }",
            "asm": [],
        }

        with pytest.raises(ValueError, match="language"):
            ExplainRequest.model_validate(request_data)

    def test_request_validation_invalid_assembly_item(self):
        """Test that invalid assembly items raise validation errors."""
        request_data = {
            "language": "c++",
            "compiler": "g++",
            "code": "int main() { return 0; }",
            "asm": [{"invalid": "data"}],  # Missing required 'text' field
        }

        with pytest.raises(ValueError):
            ExplainRequest.model_validate(request_data)

    def test_source_mapping_optional_fields(self):
        """Test that SourceMapping handles optional file and column fields."""
        # Test with all fields present
        source_full = SourceMapping(file="test.c", line=10, column=5)
        assert source_full.file == "test.c"
        assert source_full.line == 10
        assert source_full.column == 5

        # Test with only required line field
        source_minimal = SourceMapping(line=10)
        assert source_minimal.file is None
        assert source_minimal.line == 10
        assert source_minimal.column is None

        # Test with file but no column (like in your legitimate document)
        source_no_column = SourceMapping(file=None, line=0)
        assert source_no_column.file is None
        assert source_no_column.line == 0
        assert source_no_column.column is None

    def test_assembly_item_with_source_variations(self):
        """Test AssemblyItem with different source mapping variations."""
        # Assembly with full source info
        asm_full = AssemblyItem(text="mov eax, edi", source=SourceMapping(file="test.c", line=5, column=10))
        assert asm_full.source.file == "test.c"
        assert asm_full.source.line == 5
        assert asm_full.source.column == 10

        # Assembly with minimal source info (just line)
        asm_minimal = AssemblyItem(text="ret", source=SourceMapping(line=0))
        assert asm_minimal.source.file is None
        assert asm_minimal.source.line == 0
        assert asm_minimal.source.column is None

        # Assembly with no source info
        asm_no_source = AssemblyItem(text="label:")
        assert asm_no_source.source is None

    def test_legitimate_document_validation(self):
        """Test validation with the legitimate document structure that was failing."""
        # This represents the structure from your legitimate document
        request_data = {
            "language": "ispc",
            "compiler": "ispc 1.25.3",
            "code": "// Test code",
            "compilationOptions": ["--target=avx2-i32x8", "-g"],
            "instructionSet": "amd64",
            "asm": [
                {"text": "square_even___vyi:", "source": None, "labels": []},
                {
                    "text": "        vblendvps       ymm0, ymm0, ymm2, ymm3",
                    "source": {"file": None, "line": 6, "column": 16},
                    "labels": [],
                },
                {
                    "text": "        ret",
                    "source": {"file": None, "line": 0},  # Missing column field
                    "labels": [],
                },
            ],
        }

        # This should not raise a validation error
        request = ExplainRequest.model_validate(request_data)
        assert request.language == "ispc"
        assert request.compiler == "ispc 1.25.3"
        assert len(request.asm) == 3

        # Check the source mappings
        assert request.asm[0].source is None
        assert request.asm[1].source.file is None
        assert request.asm[1].source.line == 6
        assert request.asm[1].source.column == 16
        assert request.asm[2].source.file is None
        assert request.asm[2].source.line == 0
        assert request.asm[2].source.column is None  # This was the missing field
