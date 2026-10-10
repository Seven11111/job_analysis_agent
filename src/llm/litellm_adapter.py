"""LiteLLM-backed structured generation with one bounded JSON repair attempt."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from src.config import Settings, get_settings
from src.llm.adapter import LLMGenerationError, LLMNotConfiguredError


logger = logging.getLogger(__name__)
_FENCED_JSON = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


class LiteLLMAdapter:
    def __init__(
        self,
        settings: Settings | None = None,
        completion_fn: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._completion_fn = completion_fn

    def generate_structured(
        self,
        *,
        prompt: str,
        response_type: type[BaseModel],
        system_prompt: str | None = None,
    ):
        model = self.settings.litellm_model.strip()
        if not model:
            raise LLMNotConfiguredError("未配置 LITELLM_MODEL，请先在项目 .env 中设置模型。")
        provider = self.settings.litellm_provider
        if provider and not model.startswith(f"{provider}/"):
            model = f"{provider}/{model}"

        completion = self._completion()
        first = self._complete(completion, model, prompt, system_prompt=system_prompt)
        try:
            return self._parse(first, response_type)
        except (ValueError, ValidationError) as first_error:
            repair_prompt = (
                "将下面的模型输出修复为严格合法、符合指定 JSON Schema 的 JSON。"
                "只返回 JSON；不要添加说明。\nJSON Schema:\n"
                + json.dumps(response_type.model_json_schema(), ensure_ascii=False)
                + "\n原始输出：\n"
                + first[:16000]
            )
            try:
                repaired = self._complete(completion, model, repair_prompt, system_prompt=system_prompt)
            except LLMGenerationError:
                raise
            try:
                return self._parse(repaired, response_type)
            except (ValueError, ValidationError) as exc:
                logger.warning("LiteLLM structured response validation failed after repair (%s)", type(exc).__name__)
                raise LLMGenerationError("模型输出无法解析为符合契约的结构化报告。") from first_error

    def _completion(self) -> Callable[..., Any]:
        if self._completion_fn is not None:
            return self._completion_fn
        try:
            from litellm import completion
        except ImportError as exc:
            raise LLMGenerationError("LiteLLM 依赖不可用，请安装项目 requirements.txt。") from exc
        return completion

    def stream_chat(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        """Start a native tool-calling stream using the project's configured provider."""
        model = self.settings.litellm_model.strip()
        if not model:
            raise LLMNotConfiguredError("未配置 LITELLM_MODEL，请先在项目 .env 中设置模型。")
        provider = self.settings.litellm_provider
        if provider and not model.startswith(f"{provider}/"):
            model = f"{provider}/{model}"

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "stream": True,
            "temperature": self.settings.llm_temperature,
            "timeout": self.settings.llm_timeout_seconds,
            "num_retries": 0,
        }
        if self.settings.openai_api_key:
            kwargs["api_key"] = self.settings.openai_api_key
        if self.settings.openai_base_url:
            kwargs["api_base"] = self.settings.openai_base_url
        try:
            return self._completion()(**kwargs)
        except Exception as exc:
            logger.warning("LiteLLM streaming request failed (%s)", type(exc).__name__)
            raise LLMGenerationError(f"LiteLLM 调用失败：{type(exc).__name__}") from exc

    def _complete(
        self,
        completion: Callable[..., Any],
        model: str,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": ([{"role": "system", "content": system_prompt}] if system_prompt else [])
            + [{"role": "user", "content": prompt}],
            "temperature": self.settings.llm_temperature,
            "timeout": self.settings.llm_timeout_seconds,
            "num_retries": 0,
            "response_format": {"type": "json_object"},
        }
        if self.settings.openai_api_key:
            kwargs["api_key"] = self.settings.openai_api_key
        if self.settings.openai_base_url:
            kwargs["api_base"] = self.settings.openai_base_url
        try:
            response = completion(**kwargs)
            content = response.choices[0].message.content
            if isinstance(content, list):
                content = "".join(
                    str(part.get("text", "")) if isinstance(part, dict) else str(part)
                    for part in content
                )
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty response")
            return content.strip()
        except Exception as exc:
            logger.warning("LiteLLM request failed (%s)", type(exc).__name__)
            raise LLMGenerationError(f"LiteLLM 调用失败：{type(exc).__name__}") from exc

    @staticmethod
    def _parse(content: str, response_type: type[BaseModel]):
        cleaned = _FENCED_JSON.sub("", content.strip()).strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON") from exc
        return response_type.model_validate(payload)
