# ETF Loop Execution Mode Stress

- window: `2018-01-01` to `2026-06-25`
- config: `F2_CAP_MA60`
- signal always uses signal-date close and prior data only

| label | mode | delay | slippage | ann | sharpe | dd | alpha | trades | final |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| close_d1 | close | 1 | 0.01% | 33.85% | 1.44 | -23.58% | 29.73% | 5229 | 6263719 |
| open_d1 | open | 1 | 0.01% | 37.02% | 1.60 | -21.58% | 32.90% | 5215 | 8167873 |
| open_d1_adverse_20bp | open | 1 | 0.20% | 16.62% | 0.72 | -39.85% | 12.51% | 5021 | 1554847 |
| vwap_d1 | vwap | 1 | 0.01% | 34.41% | 1.50 | -22.44% | 30.29% | 5212 | 6620544 |
| close_d2 | close | 2 | 0.01% | 28.63% | 1.23 | -19.93% | 24.56% | 5359 | 4115315 |
| open_d2 | open | 2 | 0.01% | 33.08% | 1.41 | -23.19% | 29.01% | 5280 | 5882354 |
| open_d2_adverse_20bp | open | 2 | 0.20% | 12.50% | 0.53 | -43.03% | 8.43% | 5062 | 1104441 |
| vwap_d2 | vwap | 2 | 0.01% | 27.80% | 1.20 | -20.82% | 23.73% | 5279 | 3854953 |