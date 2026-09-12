#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Enable Local AI settings for AIA-06.1 verification."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(WEB))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from scanner import settings_schema as schema
from dashboard import appsettings


def main() -> int:
    current = appsettings.values(force=True)
    updates = dict(current)
    updates["ai_local_enabled"] = True
    updates["ai_ollama_enabled"] = True
    updates["ai_execution_mode"] = "compare"
    updates["ai_local_model"] = "qwen3:8b"
    updates["ai_ollama_base_url"] = "http://127.0.0.1:11434"
    # Keep Claude unchanged
    updates.setdefault("ai_default_provider", "claude")
    updates.setdefault("ai_claude_model", "claude-sonnet-4-6")
    if updates.get("ai_claude_model") != "claude-sonnet-4-6":
        updates["ai_claude_model"] = "claude-sonnet-4-6"

    clean, notes = appsettings.save(updates)
    print("Local AI settings saved:")
    for k in ("ai_local_enabled", "ai_ollama_enabled", "ai_execution_mode",
              "ai_local_model", "ai_ollama_base_url", "ai_default_provider",
              "ai_claude_model"):
        print(f"  {k} = {clean.get(k)}")
    if notes:
        print("Notes:", notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
