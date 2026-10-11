"""Model and gateway configuration for the Campus Customs agents.

Every agent on the team uses one model, gpt-6-luna, reached through the Portkey
gateway with PORTKEY_API_KEY. The key is read from the project `.env` at import
time and is never logged, returned or placed in a prompt.
"""

from __future__ import annotations

import os
from pathlib import Path

import certifi
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

BACKEND_DIR = Path(__file__).resolve().parent
HW_ROOT = BACKEND_DIR.parent

MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# Where the MCP server is declared. The agents reach the shop only through the
# server described here — the same file Claude Code loads in Problem 4.
MCP_CONFIG_PATH = HW_ROOT / ".mcp.json"


def use_certifi_tls() -> None:
    """Point OpenSSL at certifi's bundle.

    The Python.org build on this machine ships without a usable system trust
    store, so without this every HTTPS call to the gateway fails.
    """
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())


def load_api_key() -> str:
    """Read PORTKEY_API_KEY from HW5 or any parent project folder.

    The value is returned to the OpenAI client and nowhere else: it is never
    printed, written to the audit trail, or interpolated into a prompt.
    """
    for folder in (HW_ROOT, *HW_ROOT.parents):
        env_file = folder / ".env"
        if env_file.is_file():
            load_dotenv(env_file, override=False)
    key = os.getenv("PORTKEY_API_KEY")
    if not key:
        raise RuntimeError(
            "PORTKEY_API_KEY was not found in HW5 or its parent project folders. "
            "Add it to the project-root .env before running the agents."
        )
    return key


def build_model() -> OpenAIResponsesModel:
    """Build the one model every agent shares.

    The Responses endpoint is required rather than chat completions: this
    gateway rejects function tools on chat completions when reasoning is on,
    and every agent here has tools.
    """
    use_certifi_tls()
    client = AsyncOpenAI(
        base_url=PORTKEY_BASE_URL,
        api_key=load_api_key(),
        timeout=180.0,
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
