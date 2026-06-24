"""Conversation support for the AI Task integration."""

from __future__ import annotations

import re
from typing import Any, Literal, Optional

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import CONF_LLM_HASS_API, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry, intent
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_PROMPT,
    CONF_RESPONSE_MODE,
    DEFAULT_RESPONSE_MODE,
    DOMAIN,
    LOGGER,
    RESPONSE_MODE_FRIENDLY,
    RESPONSE_MODE_SILENT,
    RESPONSE_MODE_SIMPLE,
)
from .entity import AITaskLLMBaseEntity


def is_service_call(user_input: str) -> bool:
    """Check if user input is a simple service call (Layer 1 detection).

    Returns True if the input contains control keywords that suggest
    a direct device control command, allowing for fast execution without LLM.
    """
    if not user_input:
        return False

    patterns = {
        "control": ["让", "请", "帮我", "麻烦", "把", "将", "计时", "要", "想",
                   "希望", "需要", "能否", "能不能", "可不可以", "可以", "帮忙",
                   "给我", "替我", "为我", "我要", "我想", "我希望"],
        "action": {
            "turn_on": ["打开", "开启", "启动", "激活", "运行", "执行"],
            "turn_off": ["关闭", "关掉", "停止"],
            "toggle": ["切换"],
            "press": ["按", "按下", "点击"],
            "select": ["选择", "下一个", "上一个", "第一个", "最后一个", "上1个", "下1个"],
            "trigger": ["触发", "调用"],
            "number": ["数字", "数值"],
            "media": ["暂停", "继续播放", "停止", "下一首", "下一曲", "下一个",
                     "切歌", "换歌", "上一首", "上一曲", "上一个", "返回上一首",
                     "上1首", "上1曲", "上1个", "下1首", "下1曲", "下1个", "音量"]
        }
    }

    # Check if any control keyword or action keyword is present
    return bool(
        any(k in user_input for k in patterns["control"]) or
        any(k in user_input for action in patterns["action"].values()
            for k in (action if isinstance(action, list) else []))
    )


def extract_service_info(user_input: str, hass: HomeAssistant) -> Optional[dict[str, Any]]:
    """Extract service call information from user input (Layer 1 extraction).

    Analyzes the user input to determine:
    - Which entity to control (by name matching)
    - What service to call (turn_on, turn_off, etc.)
    - What parameters to pass

    Returns a dict with 'domain', 'service', 'data' keys, or None if extraction fails.
    """

    def find_entity(domain: str, text: str) -> Optional[str]:
        """Find entity by friendly_name, entity_id, or alias."""
        text = text.lower()

        # First pass: check friendly_name and entity_id
        for entity_id in hass.states.async_entity_ids(domain):
            state = hass.states.get(entity_id)
            if not state:
                continue

            friendly_name = state.attributes.get("friendly_name", "").lower()
            entity_name = entity_id.split(".")[1].lower()

            if text in entity_name or text in friendly_name or \
               entity_name in text or friendly_name in text:
                return entity_id

        # Second pass: check aliases
        ent_reg = entity_registry.async_get(hass)
        for entity_id in hass.states.async_entity_ids(domain):
            reg_entity = ent_reg.async_get(entity_id)
            if reg_entity and hasattr(reg_entity, "aliases") and reg_entity.aliases:
                for alias in reg_entity.aliases:
                    if text in alias.lower() or alias.lower() in text:
                        return entity_id

        return None

    # Detect turn on/off actions
    if any(k in user_input for k in ["打开", "开启", "启动", "开", "turn_on"]):
        # Extract entity name (simplified version)
        # Try to find domain hints
        domains_to_try = []

        if any(k in user_input for k in ["灯", "light"]):
            domains_to_try.append("light")
        if any(k in user_input for k in ["空调", "climate", "ac"]):
            domains_to_try.append("climate")
        if any(k in user_input for k in ["开关", "switch"]):
            domains_to_try.append("switch")
        if any(k in user_input for k in ["风扇", "fan"]):
            domains_to_try.append("fan")

        # If no domain hint, try common domains
        if not domains_to_try:
            domains_to_try = ["light", "switch", "climate", "fan", "cover"]

        # Extract potential entity name (remove action keywords)
        cleaned_input = user_input
        for keyword in ["打开", "开启", "启动", "请", "帮我", "麻烦", "把", "将", "开"]:
            cleaned_input = cleaned_input.replace(keyword, " ")
        cleaned_input = cleaned_input.strip()

        # Try to find entity
        for domain in domains_to_try:
            entity_id = find_entity(domain, cleaned_input)
            if entity_id:
                return {
                    "domain": domain,
                    "service": "turn_on",
                    "data": {"entity_id": entity_id}
                }

    elif any(k in user_input for k in ["关闭", "关掉", "停止", "关", "turn_off"]):
        # Similar logic for turn_off
        domains_to_try = []

        if any(k in user_input for k in ["灯", "light"]):
            domains_to_try.append("light")
        if any(k in user_input for k in ["空调", "climate", "ac"]):
            domains_to_try.append("climate")
        if any(k in user_input for k in ["开关", "switch"]):
            domains_to_try.append("switch")
        if any(k in user_input for k in ["风扇", "fan"]):
            domains_to_try.append("fan")

        if not domains_to_try:
            domains_to_try = ["light", "switch", "climate", "fan", "cover"]

        cleaned_input = user_input
        for keyword in ["关闭", "关掉", "停止", "请", "帮我", "麻烦", "把", "将", "关"]:
            cleaned_input = cleaned_input.replace(keyword, " ")
        cleaned_input = cleaned_input.strip()

        for domain in domains_to_try:
            entity_id = find_entity(domain, cleaned_input)
            if entity_id:
                return {
                    "domain": domain,
                    "service": "turn_off",
                    "data": {"entity_id": entity_id}
                }

    # More complex patterns can be added here
    # For now, return None to fall back to LLM
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up conversation entities."""
    for subentry in config_entry.subentries.values():
        if subentry.subentry_type != "conversation":
            continue

        async_add_entities(
            [AITaskConversationEntity(config_entry, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


class AITaskConversationEntity(
    conversation.ConversationEntity,
    conversation.AbstractConversationAgent,
    AITaskLLMBaseEntity,
):
    """AI Task conversation agent."""

    _attr_supports_streaming = False  # ModelScope doesn't support streaming yet

    def __init__(self, entry: ConfigEntry, subentry: ConfigSubentry) -> None:
        """Initialize the agent."""
        super().__init__(entry, subentry)
        if self.subentry.data.get(CONF_LLM_HASS_API):
            self._attr_supported_features = (
                conversation.ConversationEntityFeature.CONTROL
            )

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return a list of supported languages."""
        return MATCH_ALL

    async def async_added_to_hass(self) -> None:
        """When entity is added to Home Assistant."""
        await super().async_added_to_hass()
        conversation.async_set_agent(self.hass, self.entry, self)

    async def async_will_remove_from_hass(self) -> None:
        """When entity will be removed from Home Assistant."""
        conversation.async_unset_agent(self.hass, self.entry)
        await super().async_will_remove_from_hass()

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult:
        """Handle user message with three-layer processing.

        Layer 1: Quick service call detection (50-200ms)
        Layer 2/3: AI processing with LLM
        """
        options = self.subentry.data
        user_text = user_input.text

        # Layer 1: Fast service call detection
        if is_service_call(user_text):
            LOGGER.debug("🔍 Layer 1: Detected potential service call: %s", user_text)
            service_info = extract_service_info(user_text, self.hass)

            if service_info:
                LOGGER.info("✅ Layer 1: Service call matched - executing %s.%s",
                           service_info["domain"], service_info["service"])

                try:
                    # Execute the service directly
                    await self.hass.services.async_call(
                        service_info["domain"],
                        service_info["service"],
                        service_info["data"],
                        blocking=True,
                    )

                    # Create success response (like HAOS built-in intents)
                    intent_response = intent.IntentResponse(language=user_input.language or "zh")
                    intent_response.response_type = intent.IntentResponseType.ACTION_DONE

                    # Get response mode configuration
                    response_mode = options.get(CONF_RESPONSE_MODE, DEFAULT_RESPONSE_MODE)

                    # Generate response based on configured mode
                    response_text = ""

                    if response_mode == RESPONSE_MODE_SILENT:
                        # Silent mode: no speech, just audio cue
                        response_text = ""
                        LOGGER.debug("Layer 1: Using silent mode - no speech")

                    elif response_mode == RESPONSE_MODE_SIMPLE:
                        # Simple mode: always return simple confirmation
                        response_text = "完成"
                        LOGGER.debug("Layer 1: Using simple mode - '完成'")

                    elif response_mode == RESPONSE_MODE_FRIENDLY:
                        # Friendly mode: use friendly_name if available, otherwise silent
                        entity_id = service_info["data"].get("entity_id", "")
                        entity_state = self.hass.states.get(entity_id)

                        if entity_state:
                            friendly_name = entity_state.attributes.get("friendly_name")
                            if friendly_name:
                                action_text = "已打开" if service_info["service"] == "turn_on" else "已关闭"
                                response_text = f"{action_text}{friendly_name}"
                                LOGGER.debug("Layer 1: Using friendly mode with name - '%s'", response_text)
                            else:
                                response_text = ""
                                LOGGER.debug("Layer 1: Using friendly mode - no friendly_name, silent")
                        else:
                            response_text = ""
                            LOGGER.debug("Layer 1: Using friendly mode - entity not found, silent")

                    # Set speech only if we have response text
                    if response_text:
                        intent_response.async_set_speech(response_text)

                    LOGGER.debug("Layer 1: Executed successfully in <200ms")
                    return conversation.ConversationResult(
                        response=intent_response,
                        conversation_id=user_input.conversation_id,
                    )

                except Exception as err:
                    LOGGER.warning("Layer 1: Service call failed: %s, falling back to LLM", err)
                    # Fall through to LLM processing
            else:
                LOGGER.debug("⚠️ Layer 1: Could not extract service info, falling back to Layer 2/3")
        else:
            LOGGER.debug("⚠️ Layer 1: Not a service call, proceeding to Layer 2/3 (AI processing)")

        # Layer 2/3: AI processing with LLM
        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                options.get(CONF_LLM_HASS_API),
                options.get(CONF_PROMPT),
                user_input.extra_system_prompt,
            )
        except conversation.ConverseError as err:
            return err.as_conversation_result()

        await self._async_handle_chat_log(chat_log)

        return conversation.async_get_result_from_chat_log(user_input, chat_log)
