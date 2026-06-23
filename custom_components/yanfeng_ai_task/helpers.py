"""Helper functions for Yanfeng AI Task integration."""

from __future__ import annotations

import aiohttp
import asyncio
import json
import logging
from typing import Any

from homeassistant.exceptions import HomeAssistantError

from .const import (
    ERROR_GETTING_RESPONSE,
    ERROR_INVALID_RESPONSE,
    LOGGER,
    DASHSCOPE_API_BASE,
    TASK_MAX_WAIT_TIME,
    TASK_POLL_INTERVAL,
)


class DashScopeAPIClient:
    """Client for DashScope compatible-mode API."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        """Initialize the client."""
        self.session = session
        self.api_key = api_key
        self.api_base_url = DASHSCOPE_API_BASE
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def generate_text(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 2048,
        stream: bool = False,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
    ) -> dict[str, Any]:
        """Generate text using DashScope compatible-mode API with optional function calling."""

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }

        # Add tools if provided (OpenAI-compatible function calling)
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
            LOGGER.debug("Added %d tools to payload with tool_choice=%s", len(tools), tool_choice)

        try:
            url = f"{self.api_base_url}v1/chat/completions"
            headers = {**self.headers}

            LOGGER.debug("Sending DashScope request to %s", url)

            async with self.session.post(
                url,
                headers=headers,
                json=payload,
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    LOGGER.error(
                        "DashScope API error: %s - %s", response.status, error_text
                    )
                    raise HomeAssistantError(f"DashScope API error: {response.status}")

                result = await response.json()
                LOGGER.debug("Received DashScope response: %s", result)

                # DashScope compatible-mode returns OpenAI-compatible format
                if "choices" in result:
                    return result
                else:
                    LOGGER.error("Invalid DashScope response format: %s", result)
                    raise HomeAssistantError(ERROR_INVALID_RESPONSE)

        except aiohttp.ClientError as err:
            LOGGER.error("Network error calling DashScope API: %s", err)
            raise HomeAssistantError(ERROR_GETTING_RESPONSE) from err
        except json.JSONDecodeError as err:
            LOGGER.error("Failed to decode DashScope JSON response: %s", err)
            raise HomeAssistantError(ERROR_INVALID_RESPONSE) from err

    async def upload_file(
        self,
        file_path: str,
        mime_type: str | None = None,
    ) -> str:
        """Upload a file.

        ⚠️ NOT YET IMPLEMENTED for DashScope.
        DashScope compatible-mode does not provide a file upload endpoint.
        File upload for image editing may require using DashScope's native API.
        """
        raise HomeAssistantError(
            "File upload is not supported via DashScope compatible-mode. "
            "Image editing with local files requires the DashScope native API endpoint."
        )

    async def generate_image(
        self,
        model: str,
        prompt: str,
        image_url: str | None = None,
        size: str = "1024x1024",
        quality: str = "standard",
        n: int = 1,
    ) -> dict[str, Any]:
        """Generate image using DashScope's Qwen-Image models.

        ⚠️ NOT YET IMPLEMENTED for DashScope compatible-mode.
        Image generation requires DashScope's native multimodal generation endpoint.
        """
        raise HomeAssistantError(
            "Image generation is not yet implemented for DashScope. "
            "Use the fallback method via the DashScope native API or mark this as TODO."
        )


def format_messages_for_dashscope(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Format messages for DashScope compatible-mode API."""
    formatted = []

    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")

        # Handle different content types
        if isinstance(content, list):
            # Multi-modal content (text + images) - keep original format for VL models
            formatted.append({
                "role": role,
                "content": content
            })
        else:
            # Simple text content
            formatted.append({
                "role": role,
                "content": str(content)
            })

    return formatted
