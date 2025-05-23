import logging

import aws_embedded_metrics
from anthropic import Anthropic
from anthropic import __version__ as anthropic_version
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.config import settings
from app.explain import process_request
from app.explain_api import AvailableOptions, ExplainRequest, ExplainResponse, OptionDescription
from app.explanation_types import AudienceLevel, ExplanationType
from app.metrics import NoopMetricsProvider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

app = FastAPI(root_path=settings.root_path)

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

anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
logger.info(f"Anthropic SDK version: {anthropic_version}")

metrics_provider = NoopMetricsProvider()
#    if metrics:
#        # Set metrics namespace for CloudWatch when running in AWS
#        metrics.set_namespace("CompilerExplorer")
#        metrics_provider = CloudWatchMetricsProvider(metrics)


@app.get("/", response_model=AvailableOptions)
async def get_options() -> AvailableOptions:
    """Get available options for the explain API."""
    return AvailableOptions(
        audience=[
            OptionDescription(
                value=level.value,
                description=level.description,
            )
            for level in AudienceLevel
        ],
        explanation=[
            OptionDescription(
                value=exp_type.value,
                description=exp_type.description,
            )
            for exp_type in ExplanationType
        ],
    )


@aws_embedded_metrics.metric_scope
@app.post("/")
async def explain(request: ExplainRequest) -> ExplainResponse:
    """Explain a Compiler Explorer compilation from its source and output assembly."""
    return process_request(request, anthropic_client, metrics_provider)
