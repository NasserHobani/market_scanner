# AIA-08 Feature Audit

- Dataset: `ds_d02224f6fdb54e82`
- Feature version: `2.0.0`
- Eligible rows: 203
- Active features: 20
- Useless/constant: market_enc, side_buy

| feature | source | availability | missing_rate | leakage_risk | type | status |
|---|---|---|---|---|---|---|
| score | trade.score | 1.0 | 0.0 | none | float | active |
| confidence | trade.confidence | 1.0 | 0.0 | none | float | active |
| rr | trade.rr | 1.0 | 0.0 | none | float | active |
| grade_enc | trade.grade | 1.0 | 0.0 | none | int | active |
| factor_htf | trade.factors | 1.0 | 0.0 | none | bool | active |
| factor_confluence | trade.factors | 1.0 | 0.0 | none | bool | active |
| factor_sweep | trade.factors | 1.0 | 0.0 | none | bool | active |
| factor_breakout | trade.factors | 1.0 | 0.0 | none | bool | active |
| market_enc | trade.market | 1.0 | 0.0 | low | int | constant |
| timeframe_enc | trade.timeframe | 1.0 | 0.0 | none | int | active |
| side_buy | trade.side | 1.0 | 0.0 | none | bool | constant |
| factor_count | trade.factors | 1.0 | 0.0 | none | int | active |
| snap_available | feature_snapshot | 1.0 | 0.0 | none | bool | active |
| snap_confluence | feature_snapshot.confluence | 1.0 | 0.0 | none | int | active |
| snap_htf | feature_snapshot.htf | 1.0 | 0.0 | none | int | active |
| snap_score | feature_snapshot.score | 1.0 | 0.0 | none | float | active |
| snap_quote_volume | feature_snapshot.quote_volume | 1.0 | 0.0 | none | float | active |
| liquidity_enc | feature_snapshot.liquidity | 1.0 | 0.0 | none | int | active |
| hist_win_rate_symbol | historical.prior_trades | 1.0 | 0.0 | none | float | active |
| hist_win_rate_tf | historical.prior_trades | 1.0 | 0.0 | none | float | active |
| hist_trade_count_symbol | historical.prior_trades | 1.0 | 0.0 | none | int | active |
| hist_expectancy_symbol | historical.prior_trades | 1.0 | 0.0 | none | float | active |

