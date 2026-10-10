"""LiteLLM adapter boundary."""

from __future__ import annotations

from typing import Protocol, TypeVar


ReportT = TypeVar("ReportT")


class LLMAdapter(Protocol):
    def generate_structured(
        self,
        *,
        prompt: str,
        response_type: type[ReportT],
        system_prompt: str | None = None,
    ) -> ReportT:
        """Generate and validate a structured response."""


class LLMNotConfiguredError(RuntimeError):
    """Raised when a model is not configured for an explicitly requested run."""


class LLMGenerationError(RuntimeError):
    """Raised when the configured model cannot return a valid structured result."""
