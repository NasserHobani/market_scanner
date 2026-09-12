# -*- coding: utf-8 -*-
"""Parse LLM responses into structured advisor review dicts."""
from __future__ import annotations

import json
import re
from typing import Any


class ResponseParseError(Exception):
    def __init__(self, message: str, *, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw


class ResponseParser:
    """Extract JSON from LLM output — handles fences and trailing prose."""

    def parse(self, raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw

        text = str(raw).strip()
        if not text:
            raise ResponseParseError("Empty response", raw=text)

        # Strip markdown code fences if present
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1)

        # Find first JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ResponseParseError("No JSON object found", raw=text)

        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ResponseParseError(f"Invalid JSON: {exc}", raw=text) from exc
