"""Helper functions for the AI Task integration."""

from __future__ import annotations

import aiohttp
import asyncio
import base64
import json
import logging
from typing import Any

from homeassistant.exceptions import HomeAssistantError

from .const import (
    ERROR_GETTING_RESPONSE,
    ERROR_INVALID_RESPONSE,
    LOGGER,
    DASHSCOPE_API_BASE,
)


class DashScopeAPIClient:
    """Client for DashScope compatible-mode + native API."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        """Initialize the client."""
        self.session = session
        self.api_key = api_key
        self.compat_base = DASHSCOPE_API_BASE
        self.native_base = "https://dashscope.aliyuncs.com/api/v1/"
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
            # Disable reasoning for models that support it (e.g. qwen3.6-flash).
            # Non-reasoning models simply ignore this parameter.
            "enable_thinking": False,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
            LOGGER.debug("Added %d tools to payload with tool_choice=%s", len(tools), tool_choice)

        try:
            url = f"{self.compat_base}v1/chat/completions"
            headers = {**self.headers}

            LOGGER.debug("Sending DashScope request to %s", url)

            async with self.session.post(
                url,
                headers=headers,
                json=payload,
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    LOGGER.error("DashScope API error: %s - %s", response.status, error_text)
                    raise HomeAssistantError(f"DashScope API error: {response.status}")

                result = await response.json()
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

    async def generate_image(
        self,
        model: str,
        prompt: str,
        image_url: str | None = None,
        size: str = "2048*1536",
        quality: str = "standard",
        n: int = 1,
    ) -> dict[str, Any]:
        """Generate or edit image using DashScope native multimodal generation API.

        Args:
            model: Model ID (e.g. qwen-image-2.0-pro, qwen-image-3.0)
            prompt: Text prompt
            image_url: Optional input image URL or data URI (for image editing)
            size: Image size (e.g. 2048*1536)
            quality: Image quality (ignored by DashScope, kept for compat)
            n: Number of images to generate

        Returns:
            Dict with key "images": list of dicts {"url": "...", "b64_json": "..."}
            (OpenAI-compatible format for downstream code)
        """
        # Build content array for the native API
        content = []
        if image_url:
            # Image editing mode: image comes first
            content.append({"image": image_url})
        content.append({"text": prompt})

        payload = {
            "model": model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": content,
                    }
                ]
            },
            "parameters": {
                "size": size,
                "n": n,
            },
        }

        # For non-editing text-to-image, simplify the payload
        if not image_url:
            payload["input"]["messages"][0]["content"] = [{"text": prompt}]

        try:
            url = f"{self.native_base}services/aigc/multimodal-generation/generation"
            headers = {**self.headers}

            LOGGER.debug("Sending DashScope image request to %s (model=%s, has_image=%s)",
                         url, model, bool(image_url))

            async with self.session.post(
                url, headers=headers, json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    LOGGER.error("DashScope Image API error: %s - %s",
                                 response.status, error_text)
                    raise HomeAssistantError(f"DashScope Image API error: {response.status}")

                result = await response.json()

            # Parse DashScope native response into OpenAI-compatible format
            image_urls = []
            try:
                choices = result.get("output", {}).get("choices", [])
                for choice in choices:
                    contents = choice.get("message", {}).get("content", [])
                    for c in contents:
                        if "image" in c and c["image"]:
                            image_urls.append({"url": c["image"]})
            except Exception as err:
                LOGGER.error("Failed to parse DashScope image response: %s - %s", err, result)
                raise HomeAssistantError("Failed to parse image generation response")

            if not image_urls:
                LOGGER.error("No images found in DashScope response: %s", result)
                raise HomeAssistantError("No images generated")

            return {"data": image_urls}

        except aiohttp.ClientError as err:
            LOGGER.error("Network error calling DashScope Image API: %s", err)
            raise HomeAssistantError(ERROR_GETTING_RESPONSE) from err
        except json.JSONDecodeError as err:
            LOGGER.error("Failed to decode DashScope image response: %s", err)
            raise HomeAssistantError(ERROR_INVALID_RESPONSE) from err


def format_messages_for_dashscope(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Format messages for DashScope compatible-mode API."""
    formatted = []

    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")

        if isinstance(content, list):
            formatted.append({
                "role": role,
                "content": content
            })
        else:
            formatted.append({
                "role": role,
                "content": str(content)
            })

    return formatted


async def file_to_data_uri(file_path: str, mime_type: str | None = None) -> str:
    """Read a local file and convert to a base64 data URI.

    Used for passing local images directly to DashScope's native API
    without needing to upload to a public URL.
    """
    import aiofiles

    if mime_type is None:
        import mimetypes
        mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

    try:
        async with aiofiles.open(file_path, 'rb') as f:
            data = await f.read()
        b64 = base64.b64encode(data).decode("utf-8")
        return f"data:{mime_type};base64,{b64}"
    except Exception as err:
        LOGGER.error("Failed to read file %s: %s", file_path, err)
        raise HomeAssistantError(f"Failed to read image file: {err}")
