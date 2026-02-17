"""OpenAI-compatible provider runtime agent wrapper."""

from __future__ import annotations

from typing import Any

from openai import OpenAI


class OpenAICompatibleAgent:
    """Minimal async-compatible wrapper around OpenAI-compatible chat completions."""

    def __init__(self, *, base_url: str, api_key: str, model: str, instructions: str):
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._instructions = instructions

    async def run(self, prompt: str) -> str:
        completion = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._instructions},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        message = completion.choices[0].message if completion.choices else None
        content: Any = message.content if message is not None else ""
        return str(content or "")
