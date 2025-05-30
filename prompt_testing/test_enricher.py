"""Tests for the enricher module."""

from unittest.mock import Mock

import pytest

from prompt_testing.ce_api import AssemblyLine, CompilationError, CompileResponse
from prompt_testing.enricher import TestCaseEnricher


class TestTestCaseEnricher:
    """Tests for TestCaseEnricher class."""

    def test_init_with_client(self):
        """Test initializing with provided client."""
        mock_client = Mock()
        enricher = TestCaseEnricher(ce_client=mock_client)
        assert enricher.client is mock_client
        assert enricher._owned_client is False

    def test_init_without_client(self):
        """Test initializing without client creates one."""
        enricher = TestCaseEnricher()
        assert enricher.client is not None
        assert enricher._owned_client is True

    def test_enrich_test_case_missing_compiler(self):
        """Test enriching test case without compiler field."""
        enricher = TestCaseEnricher(ce_client=Mock())
        test_case = {
            "id": "test1",
            "input": {
                "code": "int main() {}",
            },
        }

        with pytest.raises(ValueError, match="missing compiler field"):
            enricher.enrich_test_case(test_case)

    def test_enrich_test_case_compiler_not_found(self):
        """Test enriching when compiler is not found."""
        mock_client = Mock()
        mock_client.find_compiler_by_name.return_value = None

        enricher = TestCaseEnricher(ce_client=mock_client)
        test_case = {
            "id": "test1",
            "input": {
                "compiler": "nonexistent",
                "language": "C++",
                "code": "int main() {}",
            },
        }

        with pytest.raises(ValueError, match="Could not find compiler"):
            enricher.enrich_test_case(test_case)

    def test_enrich_test_case_success(self):
        """Test successful test case enrichment."""
        # Mock client and compiler
        mock_client = Mock()
        mock_compiler = Mock()
        mock_compiler.id = "gcc1210"
        mock_client.find_compiler_by_name.return_value = mock_compiler

        # Mock compilation response
        from prompt_testing.ce_api.models import SourceInfo

        asm_lines = [
            AssemblyLine(text="push rbp", address=1, source=SourceInfo(file=None, line=1)),
            AssemblyLine(text="mov rbp, rsp", address=2, source=SourceInfo(file=None, line=1)),
        ]
        mock_response = CompileResponse(
            code=0,
            asm=asm_lines,
            stdout=[],
            stderr=[],
            label_definitions={"main": 1},
        )
        mock_client.compile.return_value = mock_response

        enricher = TestCaseEnricher(ce_client=mock_client)
        test_case = {
            "id": "test1",
            "category": "basic",
            "input": {
                "compiler": "gcc 12.1",
                "language": "C++",
                "code": "int main() {}",
                "compilationOptions": ["-O2"],
            },
        }

        result = enricher.enrich_test_case(test_case)

        # Check enriched data
        assert result["id"] == "test1"
        assert result["category"] == "basic"
        assert len(result["input"]["asm"]) == 2
        assert result["input"]["asm"][0]["text"] == "push rbp"
        assert result["input"]["labelDefinitions"] == {"main": 1}

        # Verify API calls
        mock_client.find_compiler_by_name.assert_called_once_with("gcc 12.1", "c++")
        assert mock_client.compile.called

    def test_enrich_test_case_with_compiler_map(self):
        """Test enrichment using compiler map."""
        mock_client = Mock()
        mock_response = CompileResponse(code=0, asm=[], stdout=[], stderr=[], label_definitions={})
        mock_client.compile.return_value = mock_response

        enricher = TestCaseEnricher(ce_client=mock_client)
        test_case = {
            "id": "test1",
            "input": {
                "compiler": "gcc latest",
                "code": "int main() {}",
            },
        }
        compiler_map = {"gcc latest": "gcc1310"}

        enricher.enrich_test_case(test_case, compiler_map)

        # Should use mapped compiler ID directly
        mock_client.find_compiler_by_name.assert_not_called()
        compile_request = mock_client.compile.call_args[0][0]
        assert compile_request.compiler == "gcc1310"

    def test_enrich_test_case_compilation_error(self):
        """Test handling compilation errors."""
        mock_client = Mock()
        mock_compiler = Mock()
        mock_compiler.id = "gcc1210"
        mock_client.find_compiler_by_name.return_value = mock_compiler

        # Mock compilation error
        mock_client.compile.side_effect = CompilationError(
            "Compilation failed", stderr=["error: expected ';'", "error: undefined reference"]
        )

        enricher = TestCaseEnricher(ce_client=mock_client)
        test_case = {
            "id": "test1",
            "input": {
                "compiler": "gcc 12.1",
                "code": "invalid code",
            },
        }

        with pytest.raises(CompilationError):
            enricher.enrich_test_case(test_case)

    def test_context_manager(self):
        """Test context manager functionality."""
        mock_client = Mock()

        with TestCaseEnricher(ce_client=mock_client) as enricher:
            assert enricher.client is mock_client

        # Should not close client we don't own
        mock_client.close.assert_not_called()

        # Test with owned client
        with TestCaseEnricher() as enricher:
            owned_client = enricher.client
            mock_close = Mock()
            owned_client.close = mock_close

        # Should close owned client
        mock_close.assert_called_once()
