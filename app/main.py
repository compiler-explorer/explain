import logging

from anthropic import Anthropic, __version__ as AnthropicVersion
from app.config import settings
from fastapi import FastAPI
from mangum import Mangum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# TODO consider https://github.com/FanchenBao/fastapi_lambda_api-gateway_sample/blob/main/app/main.py for CORS
app = FastAPI(root_path=settings.root_path)
handler = Mangum(app)

anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
logger.info(f"Anthropic SDK version: {AnthropicVersion}")


@app.get("/")
async def root() -> str:
    return "Hello, world!"


@app.post("/explain")
async def explain() -> dict:
    return {}
