# AI Learning & Reflection Engine (AIA-02)

Transforms completed AI evaluations into structured lessons, proposals, and research hypotheses.

**Learning is advisory. Research validates. Humans approve. The platform never self-modifies.**

## Architecture

```
scanner/ai_learning/
├── __init__.py              # LearningService public API
├── interfaces.py            # Protocols
├── learning_engine.py       # Full learning cycle orchestrator
├── reflection.py            # Periodic reflection engine
├── pattern_detector.py      # Evidence-backed pattern detection
├── lesson_generator.py      # Structured lesson generation
├── knowledge_proposals.py   # Knowledge proposals (never writes to Knowledge)
├── hypothesis_generator.py  # Research hypotheses (never executes)
├── improvement_candidates.py # Ranked improvement candidates
├── reflection_report.py     # Daily/weekly/monthly reports
├── lesson_repository.py     # Lesson persistence
├── learning_history.py      # Proposals, hypotheses, reports history
├── README.md
└── ENGINEERING_REPORT.md
```

## Data Flow

```
AI Evaluations (read-only)
    ↓
Reflection Engine
    ↓
Pattern Detector
    ↓
Lesson Generator
    ↓
Knowledge Proposals + Hypotheses
    ↓
Improvement Ranking
    ↓
Reflection Report
    ↓
Persist (append-only)
```

## Usage

```python
from scanner.ai_learning import LearningService

svc = LearningService()

# Full learning cycle
result = svc.run_cycle(
    scope={"last_week": True, "market": "crypto"},
    trade_outcomes=[...],       # optional, read-only
    research_results=[...],     # optional, read-only
    optimization_results=[...], # optional, read-only
    period="weekly",
)

# Individual access
svc.reflect(scope={"provider": "claude"})
svc.lessons()
svc.proposals()
svc.hypotheses()
svc.reports()
svc.update_lesson_status("lesson_abc", "VALIDATED")

# UI model
ui = svc.to_ui_model()
```

## Lesson Status Lifecycle

`NEW` → `UNDER_REVIEW` → `VALIDATED` | `REJECTED` → `ARCHIVED`

No lesson becomes active automatically.

## API Endpoint

`GET /api/widgets/ai-learning/`

Returns: Lessons, Top Insights, Knowledge Proposals, Suggested Experiments, Reflection Timeline.

## Strict Rules

- Does NOT modify Knowledge, Prediction, Optimization, Decision, Trading, Research, or AI Advisor.
- Learning only proposes.
- All persistence is append-only and versioned.

## Tests

```bash
python tests_ai_learning.py
```
