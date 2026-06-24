"""AI Task integration."""

from __future__ import annotations

import aiohttp
from json import JSONDecodeError
from typing import TYPE_CHECKING

from homeassistant.components import ai_task, conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.json import json_loads

from .const import (
    CONF_CHAT_MODEL,
    CONF_CUSTOM_IMAGE_MODEL,
    CONF_IMAGE_MODEL,
    CONF_RECOMMENDED,
    LOGGER,
    RECOMMENDED_CHAT_MODEL,
    RECOMMENDED_IMAGE_MODEL,
)
from .entity import (
    ERROR_GETTING_RESPONSE,
    AITaskLLMBaseEntity,
)
from .helpers import file_to_data_uri

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigSubentry
    from . import AITaskConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AI Task entities."""
    for subentry in config_entry.subentries.values():
        if subentry.subentry_type != "ai_task_data":
            continue
        async_add_entities(
            [AITaskEntity(hass, config_entry, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


class AITaskEntity(
    ai_task.AITaskEntity,
    AITaskLLMBaseEntity,
):
    """AI Task entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: AITaskConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the entity."""
        super().__init__(entry, subentry)
        self.hass = hass
        self._attr_supported_features = (
            ai_task.AITaskEntityFeature.GENERATE_DATA
            | ai_task.AITaskEntityFeature.GENERATE_IMAGE
            | ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
        )

    async def _async_generate_data(
        self,
        task: ai_task.GenDataTask,
        chat_log: conversation.ChatLog,
    ) -> ai_task.GenDataTaskResult:
        """Handle a generate data task."""
        LOGGER.debug("Starting generate_data task. Chat log has %d items before processing",
                     len(chat_log.content))

        try:
            await self._async_handle_chat_log(chat_log, task.structure)
        except Exception as err:
            LOGGER.error("Error in _async_handle_chat_log: %s", err, exc_info=True)
            raise HomeAssistantError(f"Error processing chat: {err}") from err

        if not chat_log.content:
            LOGGER.error("Chat log is empty after processing")
            raise HomeAssistantError("No response generated - empty chat log")

        if not isinstance(chat_log.content[-1], conversation.AssistantContent):
            LOGGER.error(
                "Last content in chat log is not an AssistantContent: %s. "
                "This could be due to the model not returning a valid response. "
                "Chat log contents: %s",
                chat_log.content[-1],
                [type(c).__name__ for c in chat_log.content],
            )
            raise HomeAssistantError(ERROR_GETTING_RESPONSE)

        text = chat_log.content[-1].content or ""
        LOGGER.debug("Extracted text from AssistantContent: %s", text[:100])

        if not task.structure:
            return ai_task.GenDataTaskResult(
                conversation_id=chat_log.conversation_id,
                data=text,
            )

        try:
            data = json_loads(text)
        except JSONDecodeError as err:
            LOGGER.error("Failed to parse JSON response: %s. Response: %s", err, text)
            raise HomeAssistantError(f"Failed to parse JSON response: {err}") from err

        return ai_task.GenDataTaskResult(
            conversation_id=chat_log.conversation_id,
            data=data,
        )

    async def _async_generate_image(
        self,
        task: ai_task.GenImageTask,
        chat_log: conversation.ChatLog,
    ) -> ai_task.GenImageTaskResult:
        """Handle a generate image task."""

        # Extract prompt from the last user message
        prompt = ""
        image_attachment_path = None
        image_attachment_mime_type = None

        for content in reversed(chat_log.content):
            if isinstance(content, conversation.UserContent):
                prompt = content.content

                # Check for image attachments (for image editing)
                if content.attachments:
                    for attachment in content.attachments:
                        if attachment.mime_type and attachment.mime_type.startswith("image/"):
                            image_attachment_path = attachment.path
                            image_attachment_mime_type = attachment.mime_type
                            LOGGER.debug("Found image attachment for editing: %s (mime_type: %s)",
                                         attachment.path, attachment.mime_type)
                            break
                break

        if not prompt:
            raise HomeAssistantError("No prompt found for image generation")

        # Get configured image model
        custom_image_model = self._get_option(CONF_CUSTOM_IMAGE_MODEL)
        if custom_image_model and custom_image_model.strip():
            image_model = custom_image_model.strip()
            LOGGER.debug("Using custom image model: %s", image_model)
        else:
            image_model = self._get_option(CONF_IMAGE_MODEL, RECOMMENDED_IMAGE_MODEL)
            LOGGER.debug("Using predefined image model: %s", image_model)

        # Handle image URL for editing models
        image_url = None

        # 1. Extract URL from prompt text (public URLs)
        import re
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        url_matches = re.findall(url_pattern, prompt)

        if url_matches:
            image_url = url_matches[0]
            prompt = re.sub(url_pattern, '', prompt).strip()
            LOGGER.info("Extracted image URL from prompt: %s", image_url)

        # 2. For local attachment, convert to base64 data URI (works with DashScope native API)
        elif image_attachment_path:
            try:
                image_url = await file_to_data_uri(
                    image_attachment_path, image_attachment_mime_type
                )
                LOGGER.debug("Converted local image to data URI (%d chars)", len(image_url))
            except Exception as err:
                LOGGER.warning("Failed to convert local image: %s, will try without it", err)

        LOGGER.debug("Using image model: %s for prompt: %s (image_url: %s)",
                     image_model, prompt[:100], "yes" if image_url else "none")

        try:
            response = await self.client.generate_image(
                model=image_model,
                prompt=prompt,
                image_url=image_url,
                size="2048*1536",
                n=1,
            )

            # Extract image URLs from response (OpenAI-compatible format)
            image_urls = []
            if "data" in response:
                for item in response["data"]:
                    if "url" in item:
                        image_urls.append(item["url"])

            if not image_urls:
                LOGGER.error("No image URLs found in response: %s", response)
                raise HomeAssistantError("Failed to generate image")

            # Download the first image
            image_url_result = image_urls[0]
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url_result) as img_response:
                    if img_response.status != 200:
                        raise HomeAssistantError(f"Failed to download image: HTTP {img_response.status}")

                    image_data = await img_response.read()
                    content_type = img_response.headers.get("content-type", "image/png")

            return ai_task.GenImageTaskResult(
                conversation_id=chat_log.conversation_id,
                image_data=image_data,
                mime_type=content_type,
                model=image_model,
                revised_prompt=prompt,
            )

        except Exception as err:
            LOGGER.error("Error generating image: %s", err)
            raise HomeAssistantError(f"Error generating image: {err}") from err
