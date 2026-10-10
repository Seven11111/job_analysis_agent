"""Local-only sensitive text masking for future model context."""

from __future__ import annotations

import re


PATTERNS = (
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[手机号已脱敏]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[邮箱已脱敏]"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[身份证号已脱敏]"),
    (re.compile(r"(?:详细地址|住址|家庭住址)\s*[:：]?\s*[^，。;；\n]{4,}"), "[详细住址已脱敏]"),
)


def mask_sensitive_text(value: str) -> str:
    """Mask common contact and identity data before text enters an LLM prompt."""

    masked = value
    for pattern, replacement in PATTERNS:
        masked = pattern.sub(replacement, masked)
    return masked
