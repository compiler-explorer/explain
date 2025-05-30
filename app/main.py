import logging
from pathlib import Path

from anthropic import Anthropic
from anthropic import __version__ as anthropic_version
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.cache import NoOpCacheProvider, S3CacheProvider
from app.config import get_settings
from app.explain import process_request
from app.explain_api import (
    AvailableOptions,
    ExplainRequest,
    ExplainResponse,
    OptionDescription,
)
from app.explanation_types import AudienceLevel, ExplanationType
from app.metrics import get_metrics_provider
from app.prompt import Prompt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

app = FastAPI(root_path=get_settings().root_path)

# Configure CORS - allows all origins for public API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Must be False when using allow_origins=["*"]
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    max_age=86400,  # Cache preflight requests for 24 hours
)
handler = Mangum(app)

anthropic_client = Anthropic(api_key=get_settings().anthropic_api_key)
logger.info(f"Anthropic SDK version: {anthropic_version}")

# Load the prompt configuration
prompt_config_path = Path(__file__).parent / "prompt.yaml"
prompt = Prompt(prompt_config_path)
logger.info(f"Loaded prompt configuration from {prompt_config_path}")


def get_cache_provider():
    """Get the configured cache provider."""
    settings = get_settings()

    if not settings.cache_enabled:
        logger.info("Caching disabled by configuration")
        return NoOpCacheProvider()

    if not settings.cache_s3_bucket:
        logger.warning("Cache enabled but no S3 bucket configured, disabling cache")
        return NoOpCacheProvider()

    logger.info(f"S3 cache enabled: bucket={settings.cache_s3_bucket}, prefix={settings.cache_s3_prefix}")
    return S3CacheProvider(
        bucket=settings.cache_s3_bucket,
        prefix=settings.cache_s3_prefix,
    )


@app.get("/", response_model=AvailableOptions)
async def get_options() -> AvailableOptions:
    """Get available options for the explain API."""
    async with get_metrics_provider() as metrics_provider:
        metrics_provider.put_metric("ClaudeExplainOptionsRequest", 1)
        return AvailableOptions(
            audience=[
                OptionDescription(
                    value=level.value,
                    description=prompt.get_audience_metadata(level.value)["description"],
                )
                for level in AudienceLevel
            ],
            explanation=[
                OptionDescription(
                    value=exp_type.value,
                    description=prompt.get_explanation_metadata(exp_type.value)["description"],
                )
                for exp_type in ExplanationType
            ],
        )


@app.post("/")
async def explain(request: ExplainRequest) -> ExplainResponse:
    """Explain a Compiler Explorer compilation from its source and output assembly."""
    async with get_metrics_provider() as metrics_provider:
        cache_provider = get_cache_provider()
        return await process_request(request, anthropic_client, prompt, metrics_provider, cache_provider)
