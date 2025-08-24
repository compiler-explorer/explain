import logging
from contextlib import asynccontextmanager
from pathlib import Path

from anthropic import Anthropic
from anthropic import __version__ as anthropic_version
from fastapi import FastAPI, Request
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


def configure_logging(log_level: str) -> None:
    """Configure logging with the specified level."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,  # Reconfigure if already configured
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Configure app on startup, cleanup on shutdown."""
    # Startup
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    # Store shared resources in app.state
    app.state.settings = settings
    app.state.anthropic_client = Anthropic(api_key=settings.anthropic_api_key)

    # Load the prompt configuration
    prompt_config_path = Path(__file__).parent / "prompt.yaml"
    app.state.prompt = Prompt(prompt_config_path)

    logger.info(f"Application started with log level: {settings.log_level}")
    logger.info(f"Anthropic SDK version: {anthropic_version}")
    logger.info(f"Loaded prompt configuration from {prompt_config_path}")

    yield

    # Shutdown
    logger.info("Application shutting down")


# Get settings once for app-level configuration
# This is acceptable since these settings don't change during runtime
_app_settings = get_settings()
app = FastAPI(root_path=_app_settings.root_path, lifespan=lifespan)

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


def get_cache_provider(settings) -> NoOpCacheProvider | S3CacheProvider:
    """Get the configured cache provider."""
    logger = logging.getLogger(__name__)

    if not settings.cache_enabled:
        logger.info("Caching disabled by configuration")
        return NoOpCacheProvider()

    if not settings.cache_s3_bucket:
        logger.warning("Cache enabled but no S3 bucket configured, disabling cache")
        return NoOpCacheProvider()

    logger.info(
        f"S3 cache enabled: bucket={settings.cache_s3_bucket}, "
        f"prefix={settings.cache_s3_prefix}, ttl={settings.cache_ttl} ({settings.cache_ttl_seconds}s)"
    )
    return S3CacheProvider(
        bucket=settings.cache_s3_bucket,
        prefix=settings.cache_s3_prefix,
        settings=settings,
    )


@app.get("/", response_model=AvailableOptions)
async def get_options(request: Request) -> AvailableOptions:
    """Get available options for the explain API."""
    prompt = request.app.state.prompt
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
async def explain(explain_request: ExplainRequest, request: Request) -> ExplainResponse:
    """Explain a Compiler Explorer compilation from its source and output assembly."""
    async with get_metrics_provider() as metrics_provider:
        cache_provider = get_cache_provider(request.app.state.settings)
        return await process_request(
            explain_request,
            request.app.state.anthropic_client,
            request.app.state.prompt,
            metrics_provider,
            cache_provider,
        )
