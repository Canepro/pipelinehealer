"""Quick Azure OpenAI smoke test for the current backend configuration.

Usage:
  cd backend
  source .venv/bin/activate
  python3 scripts/aoai_smoke.py
"""

from __future__ import annotations

import asyncio

from azure.identity import DefaultAzureCredential

from src.agents.base import create_cloud_agent, get_agent_prompt
from src.config import get_settings


async def main() -> None:
    s = get_settings()
    print("endpoint:", s.azure_openai_endpoint)
    print("deployment:", s.azure_openai_deployment_name)
    print("api_version:", s.azure_openai_api_version)
    print("has_api_key:", bool(s.azure_openai_api_key))

    agent = create_cloud_agent(
        name="smoke",
        instructions=get_agent_prompt("diagnosis"),
        credential=DefaultAzureCredential(),
        settings=s,
    )
    resp = await agent.run("Reply with exactly: model connectivity OK.")
    print(resp)


if __name__ == "__main__":
    asyncio.run(main())

