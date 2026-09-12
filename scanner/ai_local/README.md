# Local AI (AIA-06)

Additive local inference layer via Ollama + Qwen3, integrated with the existing AI Advisor provider abstraction.

## Execution Modes

| Mode | Behavior |
|------|----------|
| `claude_only` | Default — Claude only (production unchanged) |
| `local_only` | Qwen via Ollama only |
| `local_first` | Qwen first, escalate to Claude on failure/low confidence |
| `compare` | Same `UnifiedDecisionPackage` to both — observational only |

## Configuration (Settings)

- `ai_local_enabled` — must be explicitly enabled
- `ai_ollama_enabled`
- `ai_ollama_base_url` — default `http://127.0.0.1:11434`
- `ai_local_model` — `qwen3:4b` or `qwen3:8b`
- `ai_execution_mode`

## API

- `GET /api/ai/local/health/`
- `POST /api/ai/local/test/`
- `GET /api/ai/local/models/`
- `GET /api/ai/local/status/`
- `GET /api/ai/local/leaderboard/`
- `GET /api/ai/local/comparisons/`

## Ollama Setup

```bash
# Install Ollama: https://ollama.com
ollama pull qwen3:4b
# or
ollama pull qwen3:8b

# Verify
ollama list
curl http://127.0.0.1:11434/api/tags
```

## Verification

```bash
python scripts/verify_local_ai.py
```

## Data Files

- `data/local_ai_history.jsonl` — append-only local reviews
- `data/local_ai_comparisons.jsonl` — compare mode records

## Shadow Mode

Local AI never modifies BUY/SELL/NONE/STOP/TARGET. Platform decisions remain authoritative.
