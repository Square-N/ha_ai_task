"""Constants for the Yanfeng AI Task integration."""

import logging

from homeassistant.const import CONF_LLM_HASS_API
from homeassistant.helpers import llm

DOMAIN = "yanfeng_ai_task"
LOGGER = logging.getLogger(__package__)

# Configuration keys
CONF_API_KEY = "api_key"
CONF_MODEL_ID = "model_id"
CONF_PROMPT = "prompt"
CONF_TEMPERATURE = "temperature"
CONF_TOP_P = "top_p"
CONF_MAX_TOKENS = "max_tokens"
CONF_CHAT_MODEL = "chat_model"
CONF_CUSTOM_CHAT_MODEL = "custom_chat_model"
CONF_IMAGE_MODEL = "image_model"
CONF_CUSTOM_IMAGE_MODEL = "custom_image_model"
CONF_RECOMMENDED = "recommended"
CONF_RESPONSE_MODE = "response_mode"

# Default values
DEFAULT_TITLE = "Yanfeng AI Task"
DEFAULT_AI_TASK_NAME = "Yanfeng AI Task"
DEFAULT_CONVERSATION_NAME = "Yanfeng AI Conversation"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TOP_P = 0.9
DEFAULT_MAX_TOKENS = 8192  # Increased from 2048 — reasoning models (e.g. qwen3.6-flash) consume significant tokens for thinking
DEFAULT_RESPONSE_MODE = "friendly"

# Default Chinese-optimized prompt for Home Assistant
DEFAULT_PROMPT = """你是一个专业的智能家居助手，运行在 Home Assistant 系统中。

## 你的身份和能力
- 你可以控制家中的各种智能设备（灯光、空调、窗帘、开关等）
- 你可以查询设备状态和环境信息（温度、湿度、能耗等）
- 你可以执行自动化场景和日常任务
- 你可以回答关于智能家居的问题

## 交互原则
1. **简洁直接**：回答简短、准确、切中要点
2. **主动行动**：用户提出需求时，优先使用工具执行操作，而不是只给建议
3. **确认反馈**：执行操作后明确告知用户结果
4. **友好自然**：使用自然的中文表达，像朋友一样交流

## 设备控制指南
- 用户说"打开客厅灯"→ 立即调用工具打开灯光
- 用户说"太热了"→ 理解意图，询问是否需要降低空调温度或打开风扇
- 用户说"晚安"→ 可以关闭所有灯光，调整窗帘等
- 不确定时：礼貌询问用户更多细节

## 响应格式
- ✅ 正确："已为您打开客厅灯"
- ✅ 正确："客厅温度现在是 24.5°C"
- ❌ 错误："我可以帮您打开客厅灯，您想让我这么做吗？"（太啰嗦）
- ❌ 错误："根据我的分析..."（太正式）

## 特殊情况
- 设备不存在：友好提示并建议可能的设备名称
- 操作失败：说明原因，提供解决建议
- 不理解意图：礼貌询问，不要猜测

记住：你的目标是让用户的智能家居体验更加便捷和愉快。"""

# DashScope compatible-mode API base URL
DASHSCOPE_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/"

# Supported chat models (DashScope compatible-mode)
SUPPORTED_CHAT_MODELS = [
    "qwen3.6-flash",
    "qwen3-vl-flash",
    "qwen-plus",
]

SUPPORTED_IMAGE_MODELS = [
    "qwen-image-2.0-pro",
]

IMAGE_EDITING_MODELS = [
    "qwen-image-2.0-pro",
]

# Recommended models
RECOMMENDED_CHAT_MODEL = "qwen3.6-flash"
RECOMMENDED_IMAGE_MODEL = "qwen-image-2.0-pro"

# Task polling settings
TASK_POLL_INTERVAL = 2
TASK_MAX_WAIT_TIME = 300

# Response modes
RESPONSE_MODE_FRIENDLY = "friendly"
RESPONSE_MODE_SILENT = "silent"
RESPONSE_MODE_SIMPLE = "simple"

RESPONSE_MODES = [
    RESPONSE_MODE_FRIENDLY,
    RESPONSE_MODE_SILENT,
    RESPONSE_MODE_SIMPLE,
]

# Recommended options for Conversation
RECOMMENDED_CONVERSATION_OPTIONS = {
    CONF_PROMPT: DEFAULT_PROMPT,
    CONF_LLM_HASS_API: [llm.LLM_API_ASSIST],
    CONF_RESPONSE_MODE: DEFAULT_RESPONSE_MODE,
    CONF_RECOMMENDED: True,
}

# Recommended options for AI Task
RECOMMENDED_AI_TASK_OPTIONS = {
    CONF_CHAT_MODEL: RECOMMENDED_CHAT_MODEL,
    CONF_TEMPERATURE: DEFAULT_TEMPERATURE,
    CONF_TOP_P: DEFAULT_TOP_P,
    CONF_MAX_TOKENS: DEFAULT_MAX_TOKENS,
    CONF_RECOMMENDED: True,
}

# Timeout settings — increased from 30 to 60s for reasoning models (e.g. qwen3.6-flash takes longer)
TIMEOUT_SECONDS = 60

# Error messages
ERROR_API_KEY_REQUIRED = "API key is required"
ERROR_MODEL_NOT_SUPPORTED = "Model not supported"
ERROR_GETTING_RESPONSE = "Error getting response from AI API"
ERROR_INVALID_RESPONSE = "Invalid response from AI API"
