"""Tests for Compiler Explorer API client."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from .client import CompilationError, CompilerExplorerClient, CompilerExplorerError
from .models import CompileRequest


class TestCompilerExplorerClient:
    """Test suite for CompilerExplorerClient."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return CompilerExplorerClient()

    @pytest.fixture
    def mock_session(self):
        """Create a mock session."""
        with patch("prompt_testing.ce_api.client.requests.Session") as mock:
            yield mock.return_value

    def test_init_default_url(self):
        """Test client initialization with default URL."""
        client = CompilerExplorerClient()
        assert client.base_url == "https://godbolt.org/api/"
        assert client.timeout == 30

    def test_init_custom_url(self):
        """Test client initialization with custom URL."""
        client = CompilerExplorerClient("https://example.com/api/", timeout=60)
        assert client.base_url == "https://example.com/api/"
        assert client.timeout == 60

    def test_compile_success(self, client, mock_session):
        """Test successful compilation."""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 0,
            "asm": [
                {"text": "main:", "address": 0},
                {"text": "  xor eax, eax", "address": 1, "source": {"line": 1}},
                {"text": "  ret", "address": 2},
            ],
            "stdout": [],
            "stderr": [],
        }
        mock_session.post.return_value = mock_response

        # Create request
        request = CompileRequest(
            source="int main() { return 0; }",
            compiler="g122",
            options=["-O2"],
        )

        # Test compilation
        client.session = mock_session
        response = client.compile(request)

        # Verify response
        assert response.code == 0
        assert len(response.asm) == 3
        assert response.asm[0].text == "main:"
        assert response.asm[1].source.line == 1
        assert response.stdout == []
        assert response.stderr == []

        # Verify API call
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert "compiler/g122/compile" in call_args[0][0]
        assert call_args[1]["json"]["source"] == "int main() { return 0; }"

    def test_compile_with_labels(self, client, mock_session):
        """Test compilation with label references."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 0,
            "asm": [
                {"text": "loop:", "address": 0, "labels": [{"name": "loop"}]},
                {"text": "  jmp loop", "address": 1, "labels": ["loop"]},
            ],
            "stdout": [],
            "stderr": [],
        }
        mock_session.post.return_value = mock_response

        request = CompileRequest(source="", compiler="g122", options=[])
        client.session = mock_session
        response = client.compile(request)

        # Check label definitions were extracted
        assert response.label_definitions == {"loop": 0}

    def test_compile_failure(self, client, mock_session):
        """Test compilation failure."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 1,
            "asm": [],
            "stdout": [],
            "stderr": [{"text": "error: expected ';'"}, {"text": "1 error generated."}],
        }
        mock_session.post.return_value = mock_response

        request = CompileRequest(source="invalid code", compiler="g122", options=[])
        client.session = mock_session

        with pytest.raises(CompilationError) as exc_info:
            client.compile(request)

        assert "Compilation failed with code 1" in str(exc_info.value)
        assert exc_info.value.stderr == ["error: expected ';'", "1 error generated."]

    def test_compile_api_error(self, client, mock_session):
        """Test API request error."""
        mock_session.post.side_effect = requests.exceptions.RequestException("Connection error")

        request = CompileRequest(source="", compiler="g122", options=[])
        client.session = mock_session

        with pytest.raises(CompilerExplorerError) as exc_info:
            client.compile(request)

        assert "API request failed" in str(exc_info.value)

    def test_get_compilers(self, client, mock_session):
        """Test fetching compiler list."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "id": "g122",
                "name": "x86-64 gcc 12.2",
                "lang": "c++",
                "compilerType": "gcc",
                "version": "12.2.0",
                "instructionSet": "amd64",
            },
            {
                "id": "clang1500",
                "name": "x86-64 clang 15.0.0",
                "lang": "c++",
                "compilerType": "clang",
                "version": "15.0.0",
            },
        ]
        mock_session.get.return_value = mock_response

        client.session = mock_session
        compilers = client.get_compilers()

        assert len(compilers) == 2
        assert compilers[0].id == "g122"
        assert compilers[0].name == "x86-64 gcc 12.2"
        assert compilers[0].version == "12.2.0"
        assert compilers[0].instruction_set == "amd64"
        assert compilers[1].id == "clang1500"

    def test_get_compilers_by_language(self, client, mock_session):
        """Test fetching compilers filtered by language."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_session.get.return_value = mock_response

        client.session = mock_session
        client.get_compilers("rust")

        mock_session.get.assert_called_once()
        assert "compilers/rust" in mock_session.get.call_args[0][0]

    def test_find_compiler_by_name_exact(self, client, mock_session):
        """Test finding compiler by exact name match."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"id": "g122", "name": "x86-64 gcc 12.2"},
            {"id": "g131", "name": "x86-64 gcc 13.1"},
        ]
        mock_session.get.return_value = mock_response

        client.session = mock_session
        compiler = client.find_compiler_by_name("x86-64 gcc 13.1")

        assert compiler is not None
        assert compiler.id == "g131"
        assert compiler.name == "x86-64 gcc 13.1"

    def test_find_compiler_by_name_no_partial_match(self, client, mock_session):
        """Test that partial name match returns None."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"id": "g122", "name": "x86-64 gcc 12.2"},
            {"id": "g131", "name": "x86-64 gcc 13.1"},
        ]
        mock_session.get.return_value = mock_response

        client.session = mock_session
        compiler = client.find_compiler_by_name("gcc 13.1")

        assert compiler is None

    def test_find_compiler_by_name_not_found(self, client, mock_session):
        """Test finding compiler that doesn't exist."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"id": "g122", "name": "x86-64 gcc 12.2"},
        ]
        mock_session.get.return_value = mock_response

        client.session = mock_session
        compiler = client.find_compiler_by_name("clang 99.0")

        assert compiler is None

    def test_context_manager(self):
        """Test client as context manager."""
        with CompilerExplorerClient() as client:
            assert isinstance(client, CompilerExplorerClient)
            mock_close = MagicMock()
            client.close = mock_close

        mock_close.assert_called_once()


class TestModels:
    """Test data models."""

    def test_assembly_line_to_dict_minimal(self):
        """Test AssemblyLine.to_dict with minimal data."""
        from .models import AssemblyLine

        line = AssemblyLine(text="nop")
        assert line.to_dict() == {"text": "nop"}

    def test_assembly_line_to_dict_full(self):
        """Test AssemblyLine.to_dict with all fields."""
        from .models import AssemblyLine, SourceInfo

        line = AssemblyLine(
            text="mov eax, ebx",
            address=42,
            source=SourceInfo(file="test.c", line=10),
            labels=["loop", "start"],
        )
        result = line.to_dict()
        assert result == {
            "text": "mov eax, ebx",
            "address": 42,
            "source": {"file": "test.c", "line": 10},
            "labels": ["loop", "start"],
        }

    def test_compile_response_from_api_response(self):
        """Test CompileResponse.from_api_response."""
        from .models import CompileResponse

        api_data = {
            "code": 0,
            "asm": [
                {"text": "main:", "labels": [{"name": "main"}]},
                {"text": "  ret", "source": {"line": 2}},
            ],
            "stdout": [{"text": "output"}],
            "stderr": [],
        }

        response = CompileResponse.from_api_response(api_data)
        assert response.code == 0
        assert len(response.asm) == 2
        assert response.asm[0].text == "main:"
        assert response.asm[1].source.line == 2
        assert response.label_definitions == {"main": 0}
