import logging

from anthropic import Anthropic, __version__ as AnthropicVersion
from app.config import settings
from app.explain import process_request
from app.explain_api import ExplainRequest, ExplainResponse
from app.metrics import NoopMetricsProvider
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
import aws_embedded_metrics

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
logger.info(f"Anthropic SDK version: {AnthropicVersion}")

metrics_provider = NoopMetricsProvider()
#    if metrics:
#        # Set metrics namespace for CloudWatch when running in AWS
#        metrics.set_namespace("CompilerExplorer")
#        metrics_provider = CloudWatchMetricsProvider(metrics)


@app.get("/")
async def root() -> str:
    return "Hello, world!"


@aws_embedded_metrics.metric_scope
@app.post("/")
async def explain(request: ExplainRequest) -> ExplainResponse:
    return process_request(request, anthropic_client, metrics_provider)
