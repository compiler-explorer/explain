"""Compiler Explorer API client.

This module provides a clean Python interface to the Compiler Explorer REST API.
It handles compilation requests, compiler discovery, and error handling.
"""

from typing import Any
from urllib.parse import quote, urljoin

import requests

from .models import CompileRequest, CompileResponse, CompilerInfo


class CompilerExplorerError(Exception):
    """Base exception for Compiler Explorer API errors."""


class CompilationError(CompilerExplorerError):
    """Raised when compilation fails."""

    def __init__(self, message: str, stderr: list[str] | None = None):
        super().__init__(message)
        self.stderr = stderr or []


class CompilerExplorerClient:
    """Client for interacting with Compiler Explorer API."""

    def __init__(self, base_url: str = "https://godbolt.org/api/", timeout: int = 30):
        """Initialize the client.

        Args:
            base_url: Base URL for the API
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def compile(self, request: CompileRequest) -> CompileResponse:
        """Compile source code and return assembly output.

        Args:
            request: Compilation request

        Returns:
            CompileResponse with assembly output

        Raises:
            CompilationError: If compilation fails
            CompilerExplorerError: For other API errors
        """
        # Build compilation endpoint URL
        compiler_id = quote(request.compiler, safe="")
        url = urljoin(self.base_url, f"compiler/{compiler_id}/compile")

        # Prepare request data
        data: dict[str, Any] = {
            "source": request.source,
            "options": {
                "userArguments": " ".join(request.options),
                "filters": request.filters or {},
            },
        }

        try:
            response = self.session.post(url, json=data, timeout=self.timeout)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise CompilerExplorerError(f"API request failed: {e}") from e

        result = response.json()

        # Check for compilation errors
        if result.get("code", 0) != 0:
            stderr_lines = [line.get("text", "") for line in result.get("stderr", [])]
            raise CompilationError(f"Compilation failed with code {result.get('code')}", stderr_lines)

        return CompileResponse.from_api_response(result)

    def get_compilers(self, language: str | None = None) -> list[CompilerInfo]:
        """Get list of available compilers.

        Args:
            language: Filter by language (e.g., "c++", "c", "rust")

        Returns:
            List of available compilers
        """
        url = urljoin(self.base_url, "compilers")
        if language:
            url = urljoin(self.base_url, f"compilers/{quote(language, safe='')}")

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise CompilerExplorerError(f"Failed to fetch compilers: {e}") from e

        compilers_data = response.json()
        return [CompilerInfo.from_api_response(c) for c in compilers_data]

    def get_languages(self) -> list[dict[str, Any]]:
        """Get list of supported languages.

        Returns:
            List of language information
        """
        url = urljoin(self.base_url, "languages")

        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise CompilerExplorerError(f"Failed to fetch languages: {e}") from e

        return response.json()

    def find_compiler_by_name(self, name: str, language: str | None = None) -> CompilerInfo | None:
        """Find a compiler by its exact human-readable name.

        Args:
            name: Exact compiler name to search for (e.g., "x86-64 gcc 13.2")
            language: Optional language filter

        Returns:
            CompilerInfo if found, None otherwise
        """
        compilers = self.get_compilers(language)

        for compiler in compilers:
            if compiler.name.lower() == name.lower():
                return compiler

        return None

    def close(self):
        """Close the session."""
        self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
