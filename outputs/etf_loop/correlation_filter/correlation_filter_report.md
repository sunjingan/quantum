# ETF Loop Correlation Filter Experiments

## Setting

- Single-factor experiment: only add target correlation de-duplication.
- Filter: greedily keep high-score ETFs, skip a candidate if trailing return correlation with any selected ETF exceeds threshold.
- Scope: this does not permanently remove ETFs from the pool; it only reorders daily candidates before the existing target-selection rules.
- Data safety: correlation uses signal-date-visible price history only.
- `backfill=True`: if strict de-correlation cannot fill N, the engine backfills by original score order to avoid unintended cash bias.
- `backfill=False`: if strict de-correlation cannot fill N, the strategy holds fewer ETFs instead of buying lower-score low-correlation names.

## Reproduce

```bash
source activate.sh && python runs/etf_loop/run_correlation_filter_experiments.py
```

## Results

| setting | period | corr | lookback | backfill | ann | sharpe | DD | total | final | trades |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| F2_CAP_MA60 | 2026_nowarmup | OFF | 250 | False | 91.86% | 3.30 | -15.76% | 79.63% | 898160 | 347 |
| F2_CAP_MA60 | 2026_nowarmup | 0.85 | 250 | False | 0.00% | 0.00 | 0.00% | 0.00% | 500000 | 0 |
| F2_CAP_MA60 | 2026_nowarmup | 0.90 | 250 | False | 0.00% | 0.00 | 0.00% | 0.00% | 500000 | 0 |
| F2_CAP_MA60 | long | OFF | 250 | False | 29.01% | 1.47 | -18.98% | 2846.38% | 14731909 | 7562 |
| F2_CAP_MA60 | long | 0.85 | 250 | False | 20.61% | 1.22 | -22.36% | 1001.95% | 5509771 | 6854 |
| F2_CAP_MA60 | long | 0.90 | 250 | False | 22.55% | 1.26 | -22.77% | 1274.68% | 6873387 | 7187 |
| WideA | 2026_nowarmup | OFF | 250 | False | 115.15% | 3.39 | -16.33% | 107.13% | 1035666 | 288 |
| WideA | 2026_nowarmup | 0.85 | 250 | False | 0.00% | 0.00 | 0.00% | 0.00% | 500000 | 0 |
| WideA | 2026_nowarmup | 0.90 | 250 | False | 0.00% | 0.00 | 0.00% | 0.00% | 500000 | 0 |
| WideA | long | OFF | 250 | False | 37.12% | 1.62 | -19.66% | 7372.70% | 37363494 | 5877 |
| WideA | long | 0.85 | 250 | False | 29.68% | 1.45 | -26.74% | 3049.62% | 15748101 | 5357 |
| WideA | long | 0.90 | 250 | False | 30.35% | 1.44 | -26.89% | 3270.84% | 16854199 | 5589 |

## Interpretation

- F2_CAP_MA60: 0.70/0.80/0.90 thresholds all reduce long-period annualized return versus OFF. Drawdown improves by about 1.8-2.2 pct points, but the return trade-off is large.
- WideA: 0.70/0.80/0.90 thresholds also underperform OFF on the long period. 0.90 improves 2026-nowarmup Sharpe and annualized return slightly, but this is not enough to justify replacing the long-period candidate.
- Practical conclusion: correlation de-duplication can be kept as a defensive optional overlay, but current evidence does not support making it the default candidate rule.

## Notes

- This is not yet a candidate replacement; it tests whether reducing intra-pool correlation helps.
- Compare against `corr=OFF` within the same setting and period only.