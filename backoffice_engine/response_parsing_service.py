"""
response_parsing_service.py
───────────────────────────
Shared helpers for safely parsing LLM JSON responses.
"""

import json
import re


_CODE_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
_INLINE_FENCE_PATTERN = re.compile(r"^`(?:json)?\s*(.*?)\s*`$", re.DOTALL | re.IGNORECASE)


def extract_json_candidate(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if not text:
        return ""

    code_fence_match = _CODE_FENCE_PATTERN.match(text)
    if code_fence_match:
        return code_fence_match.group(1).strip()

    inline_fence_match = _INLINE_FENCE_PATTERN.match(text)
    if inline_fence_match:
        return inline_fence_match.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1].strip()

    return text


def parse_json_dict(raw_text: str) -> dict | None:
    candidate = extract_json_candidate(raw_text)
    if not candidate:
        return None

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None

    if isinstance(payload, dict):
        return payload
    return None
