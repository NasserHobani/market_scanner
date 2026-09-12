# AIA-10 Snapshot Audit

## Summary

| Metric | Value |
|--------|-------|
| Legacy `fs_*` snapshots (flat store) | ~2500 rows in `data/features/snapshots.jsonl` |
| Closed trades with `feature_snapshot_id` | ~3/203 (~1.5%) historically |
| PIT V3 snapshots (`pit_*`) | Runtime-created on each scan (post-deploy) |
| Historical reconstruction | From legacy `fs_*` only when ID exists |

## Status Codes

- `SNAPSHOT_CREATED` — full enough coverage
- `SNAPSHOT_PARTIAL` — coverage < 60%
- `SNAPSHOT_FAILED` — build/persist error
- `SNAPSHOT_REJECTED` — invariant violation (e.g. future timestamp)
- `HISTORICAL_RECONSTRUCTED` — upgraded from `fs_*`
- `HISTORICAL_SNAPSHOT_UNAVAILABLE` — no legacy data

## Observability

Events logged to `data/feature_snapshots/events.jsonl`:
`SNAPSHOT_STARTED`, `SNAPSHOT_CREATED`, `SNAPSHOT_PARTIAL`, `SNAPSHOT_FAILED`, `SNAPSHOT_REJECTED`, `LEAKAGE_DETECTED`

## Blockers

1. Historical trade linkage sparse (~1.5%) — honest reconstruction cannot invent missing `fs_*` IDs
2. Knowledge `components`/`context` often sparse in manual review path — partial V3 coverage expected until scan_source enrichment

## Next Improvement

Enrich `_build_scan_source()` with full scoring components and structure analysis so runtime PIT coverage approaches 80%+.
