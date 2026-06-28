# Rebalance Interval Scan

## Reproduce

```bash
source activate.sh
python runs/etf_loop/run_rebalance_interval_scan.py
```

## Control Rule

- This is a single-factor scan: only `rebalance_interval` changes inside each setting.
- `F2_CAP_MA60` uses the project baseline structure: F2_v3 core + capped PIT supplement + MA60 mean-reversion penalty. This scan applies the same high-cost assumption to both settings, so its F2 numbers are not meant to equal the lower-cost baseline row in `docs/etf_loop_project_history.md`.
- `WideA` matches `docs/etf_loop_project_history.md`: `adaptive_window=15`, `adaptive_tiers_ret=0.06,0.03,0.00,-0.02,-0.05,-0.08`, `adaptive_tiers_n=5,5,4,3,2,1,0`, no score weighting.
- cost: `open_cost=0.00015`, `close_cost=0.00015`, `slippage=0.00020`.
- execution: signal on T close, trade on next trading day open; no signal-day close fallback.

## LONG_2013_2026

| setting | interval | ann | sharpe | dd | total | final | trades |
|---|---:|---:|---:|---:|---:|---:|---:|
| F2_CAP_MA60 | 1 | 29.01% | 1.47 | -18.98% | 2846.38% | 14731909 | 7562 |
| F2_CAP_MA60 | 2 | 27.47% | 1.37 | -19.75% | 2310.75% | 12053750 | 5190 |
| F2_CAP_MA60 | 3 | 26.32% | 1.33 | -19.64% | 2000.50% | 10502477 | 4072 |
| F2_CAP_MA60 | 5 | 25.57% | 1.29 | -24.55% | 1812.45% | 9562235 | 3047 |
| F2_CAP_MA60 | 7 | 21.16% | 1.07 | -25.00% | 1005.32% | 5526616 | 2366 |
| F2_CAP_MA60 | 10 | 16.77% | 0.87 | -25.83% | 544.16% | 3220809 | 1919 |
| F2_CAP_MA60 | 15 | 20.03% | 1.14 | -37.09% | 910.01% | 5050068 | 1359 |
| F2_CAP_MA60 | 20 | 10.24% | 0.59 | -47.25% | 197.29% | 1486455 | 1176 |
| WideA | 1 | 37.12% | 1.62 | -19.66% | 7372.70% | 37363494 | 5877 |
| WideA | 2 | 34.34% | 1.45 | -20.92% | 5047.61% | 25738056 | 4055 |
| WideA | 3 | 30.10% | 1.32 | -21.57% | 3011.52% | 15557587 | 3172 |
| WideA | 5 | 29.46% | 1.27 | -25.98% | 2742.76% | 14213815 | 2342 |
| WideA | 7 | 23.94% | 1.10 | -36.90% | 1384.33% | 7421648 | 1846 |
| WideA | 10 | 17.64% | 0.78 | -35.45% | 561.81% | 3309027 | 1470 |
| WideA | 15 | 22.38% | 1.13 | -38.15% | 1184.61% | 6423071 | 1030 |
| WideA | 20 | 11.99% | 0.57 | -55.57% | 239.16% | 1695777 | 918 |

## NOWARMUP_2026

| setting | interval | ann | sharpe | dd | total | final | trades |
|---|---:|---:|---:|---:|---:|---:|---:|
| F2_CAP_MA60 | 1 | 91.86% | 3.30 | -15.76% | 79.63% | 898160 | 347 |
| F2_CAP_MA60 | 2 | 84.10% | 3.00 | -11.47% | 70.53% | 852643 | 234 |
| F2_CAP_MA60 | 3 | 56.07% | 1.98 | -14.32% | 41.47% | 707354 | 187 |
| F2_CAP_MA60 | 5 | 59.15% | 2.15 | -11.90% | 44.60% | 722998 | 130 |
| F2_CAP_MA60 | 7 | 42.02% | 1.67 | -10.92% | 29.56% | 647822 | 109 |
| F2_CAP_MA60 | 10 | 26.26% | 1.11 | -14.39% | 16.94% | 584693 | 88 |
| F2_CAP_MA60 | 15 | 60.81% | 2.36 | -17.44% | 46.66% | 733311 | 66 |
| F2_CAP_MA60 | 20 | 5.72% | 0.27 | -16.17% | 2.31% | 511530 | 55 |
| WideA | 1 | 115.15% | 3.39 | -16.33% | 107.13% | 1035666 | 288 |
| WideA | 2 | 69.50% | 2.02 | -16.73% | 52.76% | 763818 | 193 |
| WideA | 3 | 55.34% | 1.69 | -15.17% | 39.55% | 697763 | 154 |
| WideA | 5 | 72.33% | 2.57 | -12.83% | 57.68% | 788412 | 109 |
| WideA | 7 | 58.86% | 2.00 | -12.85% | 43.79% | 718968 | 93 |
| WideA | 10 | 39.27% | 1.60 | -13.26% | 27.33% | 636669 | 69 |
| WideA | 15 | 65.00% | 2.46 | -18.18% | 50.62% | 753114 | 51 |
| WideA | 20 | 10.83% | 0.50 | -15.00% | 5.80% | 528992 | 38 |

## Best By Simple Criteria

| setting | horizon | best annual | best sharpe | lowest dd |
|---|---|---|---|---|
| F2_CAP_MA60 | LONG_2013_2026 | RI1 29.01% | RI1 1.47 | RI1 -18.98% |
| F2_CAP_MA60 | NOWARMUP_2026 | RI1 91.86% | RI1 3.30 | RI7 -10.92% |
| WideA | LONG_2013_2026 | RI1 37.12% | RI1 1.62 | RI1 -19.66% |
| WideA | NOWARMUP_2026 | RI1 115.15% | RI1 3.39 | RI5 -12.83% |
