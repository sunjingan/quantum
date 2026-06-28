# V3 Multi-Setting Diagnostics

## Setting
- benchmark: `sh000300`
- base window: `adaptive_window=15`
- cost: `open_cost=0.00015`, `close_cost=0.00015`, `slippage=0.0002`
- execution: signal-day close -> next trading day open, no signal-day fallback
- data source: current code + current engine, rerun in this pass
- control rule: each setting is a single coherent configuration, no mixed-axis tuning

## Repro Command

```bash
source activate.sh && python run_v3_attribution_tables.py
```

## Acceptance Snapshot

| setting | long ann | dd | calmar | 2013-2024 ann | 2018 | 2022 | 2024 | exposure gap max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Current | 39.81% | -25.44% | 1.56 | 25.07% | 5.26% | 2.81% | 11.32% | 100.00% |
| WideA | 37.12% | -19.66% | 1.89 | 25.38% | -0.62% | 31.21% | 29.58% | 100.00% |
| Exph_v3_base | 26.14% | -17.53% | 1.49 | 18.40% | -10.07% | 13.30% | 30.66% | 100.00% |
| Exph_v3_exp_looser | 27.33% | -17.30% | 1.58 | 19.24% | -9.31% | 14.53% | 31.20% | 100.00% |

## Table 1: Annual Returns By Year

| year | Current | WideA | Exph_v3_base | Exph_v3_exp_looser |
|---:|---:|---:|---:|---:|
| 2013 | -3.33% | -3.33% | -3.33% | -3.33% |
| 2014 | 44.93% | 44.93% | 44.93% | 44.93% |
| 2015 | 34.12% | 34.12% | 34.12% | 34.12% |
| 2016 | 14.27% | 14.27% | 14.27% | 14.27% |
| 2017 | 13.70% | 13.70% | 13.70% | 13.70% |
| 2018 | 5.26% | -0.62% | -10.07% | -9.31% |
| 2019 | 37.32% | 50.90% | 42.92% | 44.41% |
| 2020 | 62.55% | 38.52% | 14.30% | 16.56% |
| 2021 | 23.97% | 21.43% | 6.05% | 7.65% |
| 2022 | 2.81% | 31.21% | 13.30% | 14.53% |
| 2023 | 36.50% | 17.06% | 11.97% | 13.97% |
| 2024 | 11.32% | 29.58% | 30.66% | 31.20% |
| 2025 | 225.48% | 169.63% | 82.22% | 87.18% |
| 2026 | 148.10% | 109.76% | 77.99% | 82.49% |

## Table 2: N Distribution

| N | Current | WideA | Exph_v3_base | Exph_v3_exp_looser |
|---:|---:|---:|---:|---:|
| 0 | 4.60% | 2.56% | 4.60% | 4.60% |
| 1 | 11.35% | 5.24% | 0.93% | 0.93% |
| 2 | 20.43% | 16.24% | 2.30% | 2.30% |
| 3 | 15.70% | 15.25% | 13.46% | 13.46% |
| 4 | 15.09% | 19.79% | 33.50% | 33.50% |
| 5 | 32.83% | 40.92% | 45.20% | 45.20% |

## Table 3: Max Drawdown Path Summary

| setting | peak_date | trough_date | recover_date | max_dd | peak_n | trough_n | avg_n | avg_target_exp | avg_actual_exp | turnover | window_days |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Current | 2024-04-12 | 2024-09-23 | 2024-10-21 | -25.44% | 2 | 2 | 2.13 | 100.00% | 99.98% | 72.85 | 111 |
| WideA | 2020-02-25 | 2020-04-24 | 2020-07-06 | -19.66% | 5 | 5 | 2.95 | 100.00% | 67.13% | 22.96 | 43 |
| Exph_v3_base | 2020-07-13 | 2020-11-13 | 2021-07-08 | -17.53% | 5 | 5 | 4.30 | 79.05% | 80.62% | 43.87 | 84 |
| Exph_v3_exp_looser | 2020-07-13 | 2020-10-30 | 2021-07-05 | -17.30% | 5 | 5 | 4.28 | 81.15% | 82.65% | 39.98 | 74 |

## Exposure Audit

| setting | max gap | mean gap | corr |
|---|---:|---:|---:|
| Current | 100.00% | 5.50% | nan |
| WideA | 100.00% | 7.48% | nan |
| Exph_v3_base | 100.00% | 34.82% | 0.076 |
| Exph_v3_exp_looser | 100.00% | 34.84% | 0.084 |

## Notes

- `Current` and `WideA` are N-only controls.
- `Exph_v3_base` is the current Exp+Hold baseline.
- `Exph_v3_exp_looser` is the best one-axis local tuning found so far.
- If the acceptance gate is strict on 2018, none of the current settings pass that condition yet.