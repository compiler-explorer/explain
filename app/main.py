import logging

from anthropic import Anthropic, __version__ as AnthropicVersion
from app.config import settings
from app.explain import process_request
from app.explain_api import ExplainRequest, ExplainResponse
from app.metrics import NoopMetricsProvider
from fastapi import FastAPI
from mangum import Mangum
import aws_embedded_metrics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# TODO consider https://github.com/FanchenBao/fastapi_lambda_api-gateway_sample/blob/main/app/main.py for CORS
app = FastAPI(root_path=settings.root_path)
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


# TODO: work out how to get these headers
"""
    # Default CORS headers for browser access
    default_headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key", # really?
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }
"""


@aws_embedded_metrics.metric_scope
@app.post("/")
async def explain(request: ExplainRequest) -> ExplainResponse:
    return process_request(request, anthropic_client, metrics_provider)
