# Adaptive Holdings Re-Audit

## Common Setting
- pool: `F2_CAP_MA60`
- benchmark: `sh000300`
- costs: commission `1.5bp` + slippage `2bp` per side
- adaptive window: `20`
- control rule: one market-adaptive axis at a time, fixed baseline as `Baseline fixed 5`

## Repro Command

```bash
source activate.sh && python run_adaptive_holdings_reaudit.py
```

## Source Notes

- `20dRet` rows are loaded from the refreshed `adaptive_holdings_fix2_report.md` / `adaptive_holdings_fix2_results.csv`.
- `MA60`, `Vol`, and `DD` rows are rerun under the current engine in this pass.

## LONG_2013_2026

| label | source | adaptive_mode | scoreW | thresh | annual | sharpe | dd | calmar | avg actual exp | avg cash | trades |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline fixed 5 | load | bench_20d_ret | False | — | 29.01% | 1.47 | -18.98% | 1.53 | 98.37% | 1.63% | 7562 |
| 20dRet | load | bench_20d_ret | nan | — | 35.83% | 1.45 | -23.58% | 1.52 | 92.66% | 7.34% | 5074 |
| 20dRet + ScoreW | load | bench_20d_ret | True | — | 36.81% | 1.40 | -23.99% | 1.53 | 92.70% | 7.30% | 4886 |
| 20dRet + ScoreW + Thresh0.1 | load | bench_20d_ret | True | 0.10 | 36.09% | 1.37 | -23.35% | 1.55 | 90.14% | 9.86% | 4628 |
| MA60 | run | bench_ma60 | nan | — | 29.17% | 1.28 | -25.96% | 1.12 | 97.86% | 2.14% | 5972 |
| MA60 + ScoreW | run | bench_ma60 | True | — | 34.17% | 1.34 | -27.56% | 1.24 | 97.92% | 2.08% | 5700 |
| MA60 + ScoreW + Thresh0.1 | run | bench_ma60 | True | 0.10 | 33.39% | 1.29 | -29.44% | 1.13 | 94.51% | 5.49% | 5246 |
| Vol | run | bench_vol | nan | — | 30.19% | 1.40 | -20.70% | 1.46 | 96.51% | 3.49% | 6427 |
| Vol + ScoreW | run | bench_vol | True | — | 32.74% | 1.35 | -27.52% | 1.19 | 96.56% | 3.44% | 6071 |
| Vol + ScoreW + Thresh0.1 | run | bench_vol | True | 0.10 | 30.83% | 1.24 | -27.68% | 1.11 | 93.12% | 6.88% | 5527 |
| DD | run | portfolio_dd | nan | — | 30.81% | 1.47 | -21.15% | 1.46 | 98.40% | 1.60% | 6799 |
| DD + ScoreW | run | portfolio_dd | True | — | 11.61% | 0.79 | -25.74% | 0.45 | 51.63% | 48.37% | 2333 |
| DD + ScoreW + Thresh0.1 | run | portfolio_dd | True | 0.10 | 12.62% | 0.79 | -25.46% | 0.50 | 44.36% | 55.64% | 1774 |

### Settings

- Long-period comparisons use `2013-07-01` to `2026-06-25` with no trading start cutoff.

## 2026_NOWARMUP

| label | source | adaptive_mode | scoreW | thresh | annual | sharpe | dd | calmar | avg actual exp | avg cash | trades |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline fixed 5 | load | bench_20d_ret | False | — | 91.86% | 3.30 | -15.76% | 5.83 | 64.16% | 35.84% | 347 |
| 20dRet | load | bench_20d_ret | nan | — | 116.98% | 3.04 | -19.72% | 5.93 | 64.34% | 35.66% | 244 |
| 20dRet + ScoreW | load | bench_20d_ret | True | — | 102.95% | 2.67 | -20.51% | 5.02 | 64.41% | 35.59% | 244 |
| 20dRet + ScoreW + Thresh0.1 | load | bench_20d_ret | True | 0.10 | 99.94% | 2.58 | -21.76% | 4.59 | 60.30% | 39.70% | 219 |
| MA60 | run | bench_ma60 | nan | — | 107.75% | 3.41 | -16.75% | 6.43 | 64.25% | 35.75% | 308 |
| MA60 + ScoreW | run | bench_ma60 | True | — | 110.57% | 3.05 | -18.33% | 6.03 | 64.30% | 35.70% | 291 |
| MA60 + ScoreW + Thresh0.1 | run | bench_ma60 | True | 0.10 | 98.17% | 2.63 | -22.18% | 4.43 | 60.27% | 39.73% | 245 |
| Vol | run | bench_vol | nan | — | 94.67% | 3.31 | -16.45% | 5.76 | 64.23% | 35.77% | 327 |
| Vol + ScoreW | run | bench_vol | True | — | 83.71% | 2.47 | -18.94% | 4.42 | 64.34% | 35.66% | 291 |
| Vol + ScoreW + Thresh0.1 | run | bench_vol | True | 0.10 | 64.33% | 1.84 | -22.00% | 2.92 | 60.82% | 39.18% | 256 |
| DD | run | portfolio_dd | nan | — | 96.29% | 3.39 | -14.81% | 6.50 | 64.24% | 35.76% | 320 |
| DD + ScoreW | run | portfolio_dd | True | — | 93.58% | 2.77 | -16.81% | 5.57 | 64.33% | 35.67% | 286 |
| DD + ScoreW + Thresh0.1 | run | portfolio_dd | True | 0.10 | 79.46% | 2.25 | -21.23% | 3.74 | 60.86% | 39.14% | 248 |

### Settings

- 2026 nowarmup comparisons use `2025-10-01` to `2026-06-25` and `trading_start=2026-01-02`.
