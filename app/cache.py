"""S3-based caching for explanation responses.

This module provides caching functionality to reduce duplicate requests to Anthropic's API.
The cache key is generated from all data that affects the response, including prompt content.
"""

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from app.explain_api import ExplainRequest, ExplainResponse
from app.prompt import Prompt

LOGGER = logging.getLogger("cache")


class CacheProvider(ABC):
    """Abstract base class for cache providers."""

    @abstractmethod
    async def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve a cached response by key.

        Args:
            key: The cache key to look up

        Returns:
            The cached response data as a dict, or None if not found
        """

    @abstractmethod
    async def put(self, key: str, value: dict[str, Any]) -> None:
        """Store a response in the cache.

        Args:
            key: The cache key to store under
            value: The response data to cache
        """


class NoOpCacheProvider(CacheProvider):
    """A cache provider that does nothing - for testing or when caching is disabled."""

    async def get(self, key: str) -> dict[str, Any] | None:  # noqa: ARG002
        """Return None (no-op implementation)."""
        return None

    async def put(self, key: str, value: dict[str, Any]) -> None:
        """Do nothing (no-op implementation)."""


class S3CacheProvider(CacheProvider):
    """S3-based cache provider."""

    def __init__(self, bucket: str, prefix: str = "explain-cache/"):
        """Initialize the S3 cache provider.

        Args:
            bucket: The S3 bucket name
            prefix: The key prefix for cache objects (default: "explain-cache/")
        """
        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/"  # Ensure trailing slash
        self._s3_client = None

    @property
    def s3_client(self):
        """Lazy-load S3 client."""
        if self._s3_client is None:
            self._s3_client = boto3.client("s3")
        return self._s3_client

    def _get_s3_key(self, cache_key: str) -> str:
        """Generate the full S3 key for a cache key."""
        return f"{self.prefix}{cache_key}.json"

    async def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve a cached response from S3."""
        s3_key = self._get_s3_key(key)

        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=s3_key)
            content = response["Body"].read().decode("utf-8")
            return json.loads(content)
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "NoSuchKey":
                LOGGER.debug(f"Cache miss for key {key}")
                return None
            LOGGER.warning(f"S3 error retrieving cache key {key}: {e}")
            return None
        except (json.JSONDecodeError, NoCredentialsError) as e:
            LOGGER.warning(f"Error retrieving cache key {key}: {e}")
            return None

    async def put(self, key: str, value: dict[str, Any]) -> None:
        """Store a response in S3 cache."""
        s3_key = self._get_s3_key(key)

        try:
            content = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=content.encode("utf-8"),
                ContentType="application/json",
                CacheControl="max-age=172800",  # 2 days
            )
            LOGGER.debug(f"Cached response for key {key}")
        except (ClientError, NoCredentialsError) as e:
            LOGGER.warning(f"Error caching response for key {key}: {e}")


def generate_cache_key(request: ExplainRequest, prompt: Prompt) -> str:
    """Generate a cache key for the given request and prompt.

    The cache key captures all data that affects the Anthropic API response:
    - All message content (system prompt, user messages, assistant prefill)
    - Model configuration (name, temperature, max_tokens)
    - Prompt template version (hash of prompt config)

    Args:
        request: The explanation request
        prompt: The prompt instance with templates

    Returns:
        A SHA-256 hash string to use as cache key
    """
    # Generate the full message data that would be sent to Anthropic
    prompt_data = prompt.generate_messages(request)

    # Create a deterministic representation of all cache-affecting data
    cache_data = {
        "model": prompt_data["model"],
        "max_tokens": prompt_data["max_tokens"],
        "temperature": prompt_data["temperature"],
        "system": prompt_data["system"],
        "messages": prompt_data["messages"],
        # Include a hash of the prompt config to invalidate cache when prompts change
        "prompt_version": _get_prompt_config_hash(prompt.config),
    }

    # Convert to JSON with consistent ordering for deterministic hashing
    cache_json = json.dumps(cache_data, sort_keys=True, ensure_ascii=True, separators=(",", ":"))

    # Generate SHA-256 hash
    return hashlib.sha256(cache_json.encode("utf-8")).hexdigest()


def _get_prompt_config_hash(config: dict[str, Any]) -> str:
    """Generate a hash of the prompt configuration for cache versioning."""
    # Remove any non-deterministic fields if they exist
    config_for_hash = {k: v for k, v in config.items() if k not in ["_internal", "metadata"]}
    config_json = json.dumps(config_for_hash, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(config_json.encode("utf-8")).hexdigest()[:16]  # Use first 16 chars


async def get_cached_response(
    request: ExplainRequest, prompt: Prompt, cache_provider: CacheProvider
) -> ExplainResponse | None:
    """Attempt to retrieve a cached response for the given request.

    Args:
        request: The explanation request
        prompt: The prompt instance
        cache_provider: The cache provider to use

    Returns:
        The cached ExplainResponse if found, None otherwise
    """
    if request.bypass_cache:
        LOGGER.debug("Cache bypassed by request")
        return None

    cache_key = generate_cache_key(request, prompt)
    cached_data = await cache_provider.get(cache_key)

    if cached_data is None:
        return None

    try:
        # Convert cached dict back to ExplainResponse
        response = ExplainResponse(**cached_data)
        # Mark this response as cached
        response.cached = True
        return response
    except Exception as e:
        LOGGER.warning(f"Error deserializing cached response: {e}")
        return None


async def cache_response(
    request: ExplainRequest,
    prompt: Prompt,
    response: ExplainResponse,
    cache_provider: CacheProvider,
) -> None:
    """Cache the response for future use.

    Args:
        request: The original request
        prompt: The prompt instance
        response: The response to cache
        cache_provider: The cache provider to use
    """
    cache_key = generate_cache_key(request, prompt)

    try:
        # Convert response to dict for caching
        response_data = response.model_dump()
        await cache_provider.put(cache_key, response_data)
        LOGGER.debug(f"Cached response with key {cache_key[:16]}...")
    except Exception as e:
        LOGGER.warning(f"Error caching response: {e}")
