# AIA-12 Automation Report

## Background responsibilities

| Concern | Owner |
|---------|--------|
| Market sync | MD-01 worker (independent of scan) |
| PIT capture | Every scan/recommendation |
| Trade linkage | `open_from_reco` / breakout |
| Readiness | `dataset_readiness.build_readiness` |
| Training trigger | Settlement → `schedule_if_ready_async` |

## Manual-only actions

1. Explicit model promotion (`CANDIDATE` → `ACTIVE`)
2. Optional manual retrain

User should **not** need to repeatedly Scan/Sync/rebuild dataset/trigger train every 20 trades.

## Monitoring

- `scripts/monitor_aia12.py`
- `scripts/verify_aia12.py`
- Dashboard: Dataset Readiness + «دورة التنبؤ»

## Alerts

Warnings for: runtime coverage &lt;70%, stalled eligible rows, linkage orphans, stuck training, leakage.

No alert for expected `NOT_PROMOTED`.
