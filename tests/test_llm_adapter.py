from types import SimpleNamespace

import pytest

from src.config import Settings
from src.llm.adapter import LLMGenerationError, LLMNotConfiguredError
from src.llm.litellm_adapter import LiteLLMAdapter
from src.schemas.report import MatchReport


VALID_REPORT = """{
  "summary": "候选人有相关项目经历。",
  "match_score": 76,
  "recommendation": "match",
  "matched_points": ["有 Python 项目经历"],
  "missing_points": ["未说明到岗天数"],
  "risk_points": [],
  "next_actions": ["查看岗位来源确认最新要求"]
}"""


def llm_response(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_litellm_adapter_parses_markdown_fenced_json():
    adapter = LiteLLMAdapter(
        Settings(litellm_model="test/mock"),
        completion_fn=lambda **_: llm_response(f"```json\n{VALID_REPORT}\n```"),
    )

    report = adapter.generate_structured(prompt="test", response_type=MatchReport)

    assert report.match_score == 76
    assert report.recommendation == "match"


def test_litellm_adapter_repairs_invalid_structured_output_once():
    responses = iter([llm_response("{bad json"), llm_response(VALID_REPORT)])
    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        return next(responses)

    adapter = LiteLLMAdapter(Settings(litellm_model="test/mock"), completion_fn=completion)
    report = adapter.generate_structured(prompt="test", response_type=MatchReport)

    assert report.match_score == 76
    assert len(calls) == 2
    assert "修复" in calls[1]["messages"][0]["content"]


def test_litellm_provider_prefix_is_applied_and_credentials_are_passed():
    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        return llm_response(VALID_REPORT)

    adapter = LiteLLMAdapter(
        Settings(
            litellm_provider="OpenAI",
            litellm_model="deepseek-v4-flash",
            openai_api_key="test-key",
            openai_base_url="https://llm.example/v1",
        ),
        completion_fn=completion,
    )

    report = adapter.generate_structured(prompt="test", response_type=MatchReport)

    assert report.match_score == 76
    assert calls[0]["model"] == "openai/deepseek-v4-flash"
    assert calls[0]["api_key"] == "test-key"
    assert calls[0]["api_base"] == "https://llm.example/v1"


def test_litellm_provider_prefix_is_not_duplicated():
    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        return llm_response(VALID_REPORT)

    adapter = LiteLLMAdapter(
        Settings(litellm_provider="openai", litellm_model="openai/deepseek-v4-flash"),
        completion_fn=completion,
    )

    adapter.generate_structured(prompt="test", response_type=MatchReport)

    assert calls[0]["model"] == "openai/deepseek-v4-flash"


def test_litellm_native_stream_forwards_tools_and_provider_credentials():
    calls = []
    chunks = iter([{"choices": [{"delta": {"content": "hello"}, "finish_reason": "stop"}]}])

    def completion(**kwargs):
        calls.append(kwargs)
        return chunks

    tools = [{"type": "function", "function": {"name": "search_jobs", "parameters": {"type": "object"}}}]
    adapter = LiteLLMAdapter(
        Settings(
            litellm_provider="openai",
            litellm_model="chat-model",
            openai_api_key="test-key",
            openai_base_url="https://compatible.example/v1",
        ),
        completion_fn=completion,
    )

    stream = adapter.stream_chat(messages=[{"role": "user", "content": "find internships"}], tools=tools)

    assert next(stream)["choices"][0]["delta"]["content"] == "hello"
    assert calls[0]["model"] == "openai/chat-model"
    assert calls[0]["tools"] == tools
    assert calls[0]["tool_choice"] == "auto"
    assert calls[0]["stream"] is True
    assert calls[0]["api_key"] == "test-key"
    assert calls[0]["api_base"] == "https://compatible.example/v1"


def test_litellm_adapter_rejects_missing_model_and_persistent_invalid_json():
    adapter = LiteLLMAdapter(Settings(litellm_model=""), completion_fn=lambda **_: llm_response(VALID_REPORT))
    with pytest.raises(LLMNotConfiguredError):
        adapter.generate_structured(prompt="test", response_type=MatchReport)

    invalid = LiteLLMAdapter(Settings(litellm_model="test/mock"), completion_fn=lambda **_: llm_response("not json"))
    with pytest.raises(LLMGenerationError, match="结构化报告"):
        invalid.generate_structured(prompt="test", response_type=MatchReport)
