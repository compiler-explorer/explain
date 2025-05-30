"""Tests for the caching functionality."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.cache import (
    NoOpCacheProvider,
    S3CacheProvider,
    cache_response,
    generate_cache_key,
    get_cached_response,
)
from app.explain_api import (
    AssemblyItem,
    CostBreakdown,
    ExplainRequest,
    ExplainResponse,
    SourceMapping,
    TokenUsage,
)
from app.prompt import Prompt


@pytest.fixture
def sample_request():
    """Create a sample ExplainRequest for testing."""
    return ExplainRequest(
        language="c++",
        compiler="g++",
        code="int square(int x) { return x * x; }",
        compilationOptions=["-O2"],
        instructionSet="amd64",
        asm=[
            AssemblyItem(text="square(int):", source=None, labels=[]),
            AssemblyItem(
                text="        mov     eax, edi",
                source=SourceMapping(line=1, column=21),
                labels=[],
            ),
            AssemblyItem(text="        ret", source=None, labels=[]),
        ],
        labelDefinitions={"square(int)": 0},
    )


@pytest.fixture
def test_prompt():
    """Create a test prompt instance."""
    return Prompt(
        {
            "model": {"name": "claude-3-5-sonnet-20241022", "max_tokens": 2000, "temperature": 0.0},
            "system_prompt": (
                "You are an expert {language} programmer analyzing {arch} assembly code for a {audience} audience."
            ),
            "user_prompt": "Please analyze the {arch} assembly:",
            "assistant_prefill": "Looking at this assembly code analysis:",
            "audience_levels": {
                "beginner": {
                    "description": "New to programming",
                    "guidance": "Use simple language and avoid jargon",
                }
            },
            "explanation_types": {
                "assembly": {
                    "description": "Explain assembly instructions",
                    "focus": "Focus on what each instruction does",
                    "user_prompt_phrase": "analyze the assembly",
                }
            },
        }
    )


@pytest.fixture
def sample_response():
    """Create a sample ExplainResponse for testing."""
    return ExplainResponse(
        status="success",
        explanation="This function implements a square operation...",
        model="claude-3-5-sonnet-20241022",
        usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        cost=CostBreakdown(input_cost=0.001, output_cost=0.002, total_cost=0.003),
    )


class TestNoOpCacheProvider:
    """Test the NoOpCacheProvider."""

    @pytest.mark.asyncio
    async def test_get_returns_none(self):
        """Test that get always returns None."""
        cache = NoOpCacheProvider()
        result = await cache.get("any-key")
        assert result is None

    @pytest.mark.asyncio
    async def test_put_does_nothing(self):
        """Test that put does nothing and doesn't raise errors."""
        cache = NoOpCacheProvider()
        # Should not raise any exceptions
        await cache.put("key", {"test": "data"})


class TestS3CacheProvider:
    """Test the S3CacheProvider."""

    def test_init_with_default_prefix(self):
        """Test initialization with default prefix."""
        cache = S3CacheProvider("test-bucket")
        assert cache.bucket == "test-bucket"
        assert cache.prefix == "explain-cache/"

    def test_init_with_custom_prefix(self):
        """Test initialization with custom prefix."""
        cache = S3CacheProvider("test-bucket", "custom-prefix")
        assert cache.bucket == "test-bucket"
        assert cache.prefix == "custom-prefix/"

    def test_get_s3_key(self):
        """Test S3 key generation."""
        cache = S3CacheProvider("test-bucket", "cache/")
        key = cache._get_s3_key("abcd1234")
        assert key == "cache/abcd1234.json"

    @patch("boto3.client")
    @pytest.mark.asyncio
    async def test_get_cache_hit(self, mock_boto3_client):
        """Test successful cache retrieval."""
        # Setup mock S3 client
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3

        test_data = {"status": "success", "explanation": "cached response"}
        mock_response = {"Body": MagicMock()}
        mock_response["Body"].read.return_value = json.dumps(test_data).encode("utf-8")
        mock_s3.get_object.return_value = mock_response

        cache = S3CacheProvider("test-bucket")
        result = await cache.get("test-key")

        assert result == test_data
        mock_s3.get_object.assert_called_once_with(Bucket="test-bucket", Key="explain-cache/test-key.json")

    @patch("boto3.client")
    @pytest.mark.asyncio
    async def test_get_cache_miss(self, mock_boto3_client):
        """Test cache miss (NoSuchKey error)."""
        # Setup mock S3 client
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3

        from botocore.exceptions import ClientError

        mock_s3.get_object.side_effect = ClientError(
            error_response={"Error": {"Code": "NoSuchKey"}}, operation_name="GetObject"
        )

        cache = S3CacheProvider("test-bucket")
        result = await cache.get("nonexistent-key")

        assert result is None

    @patch("boto3.client")
    @pytest.mark.asyncio
    async def test_put_success(self, mock_boto3_client):
        """Test successful cache storage."""
        # Setup mock S3 client
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3

        cache = S3CacheProvider("test-bucket")
        test_data = {"status": "success", "explanation": "test response"}

        await cache.put("test-key", test_data)

        # Verify S3 put_object was called
        mock_s3.put_object.assert_called_once()
        call_args = mock_s3.put_object.call_args
        assert call_args[1]["Bucket"] == "test-bucket"
        assert call_args[1]["Key"] == "explain-cache/test-key.json"
        assert call_args[1]["ContentType"] == "application/json"

        # Verify the content
        content = call_args[1]["Body"].decode("utf-8")
        assert json.loads(content) == test_data


class TestCacheKeyGeneration:
    """Test cache key generation."""

    def test_generate_cache_key_deterministic(self, sample_request, test_prompt):
        """Test that cache key generation is deterministic."""
        key1 = generate_cache_key(sample_request, test_prompt)
        key2 = generate_cache_key(sample_request, test_prompt)
        assert key1 == key2
        assert len(key1) == 64  # SHA-256 produces 64-character hex string

    def test_generate_cache_key_different_requests(self, test_prompt):
        """Test that different requests generate different cache keys."""
        request1 = ExplainRequest(
            language="c++",
            compiler="g++",
            code="int add(int a, int b) { return a + b; }",
            asm=[AssemblyItem(text="add:", source=None)],
        )
        request2 = ExplainRequest(
            language="c++",
            compiler="g++",
            code="int sub(int a, int b) { return a - b; }",
            asm=[AssemblyItem(text="sub:", source=None)],
        )

        key1 = generate_cache_key(request1, test_prompt)
        key2 = generate_cache_key(request2, test_prompt)
        assert key1 != key2

    def test_generate_cache_key_different_prompts(self, sample_request):
        """Test that different prompt configs generate different cache keys."""
        prompt1 = Prompt(
            {
                "model": {"name": "claude-3-5-sonnet-20241022", "max_tokens": 2000},
                "system_prompt": "Template 1",
                "user_prompt": "User 1",
                "assistant_prefill": "Assistant 1",
                "audience_levels": {"beginner": {"guidance": "Simple"}},
                "explanation_types": {"assembly": {"focus": "Instructions", "user_prompt_phrase": "analyze"}},
            }
        )
        prompt2 = Prompt(
            {
                "model": {"name": "claude-3-5-sonnet-20241022", "max_tokens": 2000},
                "system_prompt": "Template 2",  # Different template
                "user_prompt": "User 1",
                "assistant_prefill": "Assistant 1",
                "audience_levels": {"beginner": {"guidance": "Simple"}},
                "explanation_types": {"assembly": {"focus": "Instructions", "user_prompt_phrase": "analyze"}},
            }
        )

        key1 = generate_cache_key(sample_request, prompt1)
        key2 = generate_cache_key(sample_request, prompt2)
        assert key1 != key2

    def test_generate_cache_key_bypass_cache_ignored(self, test_prompt):
        """Test that bypass_cache field doesn't affect cache key."""
        request1 = ExplainRequest(
            language="c++",
            compiler="g++",
            code="int test() { return 0; }",
            asm=[AssemblyItem(text="test:", source=None)],
            bypass_cache=False,
        )
        request2 = ExplainRequest(
            language="c++",
            compiler="g++",
            code="int test() { return 0; }",
            asm=[AssemblyItem(text="test:", source=None)],
            bypass_cache=True,
        )

        key1 = generate_cache_key(request1, test_prompt)
        key2 = generate_cache_key(request2, test_prompt)
        assert key1 == key2  # bypass_cache shouldn't affect cache key


class TestCacheHighLevelFunctions:
    """Test the high-level cache functions."""

    @pytest.mark.asyncio
    async def test_get_cached_response_bypass_cache(self, sample_request, test_prompt):
        """Test that bypass_cache skips cache retrieval."""
        mock_cache = AsyncMock()
        mock_cache.get.return_value = {"status": "success", "explanation": "cached"}

        sample_request.bypass_cache = True
        result = await get_cached_response(sample_request, test_prompt, mock_cache)

        assert result is None
        mock_cache.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_cached_response_cache_hit(self, sample_request, test_prompt, sample_response):
        """Test successful cache retrieval."""
        mock_cache = AsyncMock()
        mock_cache.get.return_value = sample_response.model_dump()

        result = await get_cached_response(sample_request, test_prompt, mock_cache)

        assert result is not None
        assert result.status == "success"
        assert result.explanation == "This function implements a square operation..."
        mock_cache.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_cached_response_cache_miss(self, sample_request, test_prompt):
        """Test cache miss returns None."""
        mock_cache = AsyncMock()
        mock_cache.get.return_value = None

        result = await get_cached_response(sample_request, test_prompt, mock_cache)

        assert result is None
        mock_cache.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_cached_response_malformed_data(self, sample_request, test_prompt):
        """Test that malformed cached data returns None."""
        mock_cache = AsyncMock()
        mock_cache.get.return_value = {"invalid": "response_structure"}

        result = await get_cached_response(sample_request, test_prompt, mock_cache)

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_response_success(self, sample_request, test_prompt, sample_response):
        """Test successful response caching."""
        mock_cache = AsyncMock()

        await cache_response(sample_request, test_prompt, sample_response, mock_cache)

        mock_cache.put.assert_called_once()
        call_args = mock_cache.put.call_args
        cached_data = call_args[0][1]

        assert cached_data["status"] == "success"
        assert cached_data["explanation"] == "This function implements a square operation..."

    @pytest.mark.asyncio
    async def test_cache_response_error_handling(self, sample_request, test_prompt, sample_response):
        """Test that cache errors don't break the response flow."""
        mock_cache = AsyncMock()
        mock_cache.put.side_effect = Exception("S3 error")

        # Should not raise an exception
        await cache_response(sample_request, test_prompt, sample_response, mock_cache)


class TestCacheIntegration:
    """Integration tests for cache functionality."""

    @pytest.mark.asyncio
    async def test_cache_key_consistency_with_real_prompt(self, sample_request):
        """Test cache key consistency with actual prompt.yaml file."""
        # Use the real prompt configuration if available
        prompt_path = Path("app/prompt.yaml")
        if prompt_path.exists():
            real_prompt = Prompt(prompt_path)

            # Generate cache key multiple times
            key1 = generate_cache_key(sample_request, real_prompt)
            key2 = generate_cache_key(sample_request, real_prompt)

            assert key1 == key2
            assert len(key1) == 64
        else:
            pytest.skip("prompt.yaml not found")

    @pytest.mark.asyncio
    async def test_end_to_end_cache_flow(self, sample_request, test_prompt, sample_response):
        """Test complete cache flow: miss -> store -> hit."""
        mock_cache = AsyncMock()

        # Initial cache miss
        mock_cache.get.return_value = None
        result = await get_cached_response(sample_request, test_prompt, mock_cache)
        assert result is None

        # Store response in cache
        await cache_response(sample_request, test_prompt, sample_response, mock_cache)
        mock_cache.put.assert_called_once()

        # Simulate cache hit by returning the stored data
        mock_cache.get.return_value = sample_response.model_dump()
        result = await get_cached_response(sample_request, test_prompt, mock_cache)

        assert result is not None
        assert result.status == sample_response.status
        assert result.explanation == sample_response.explanation
