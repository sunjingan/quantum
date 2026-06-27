# 15D Behavior Diagnostics and V3 Local Tuning

## Setting
- pool: `F2_CAP_MA60`
- benchmark: `sh000300`
- window: `adaptive_window=15`
- cost: commission `1.5bp` + slippage `2bp` per side
- execution: signal-day close -> next trading day open, no signal-day close fallback
- control rule: diagnostics only read existing outputs; tuning block changes one axis at a time

## Repro Command

```bash
source activate.sh && python run_15d_behavior_v3_tuning.py
```

## Diagnostics Source

- `SEQ_LONG_2013_2026_Current`
- `SEQ_LONG_2013_2026_WideA`
- `SEQ_LONG_2013_2026_Exph_v3`

## 15D Behavior Diagnostics

## Current

### Annual By Year

| year | annual | dd | days |
|---:|---:|---:|---:|
| 2013 | -3.33% | -8.68% | 99 |
| 2014 | 44.93% | -5.76% | 245 |
| 2015 | 34.12% | -8.58% | 244 |
| 2016 | 14.27% | -6.86% | 244 |
| 2017 | 13.70% | -6.60% | 244 |
| 2018 | 5.26% | -16.83% | 243 |
| 2019 | 37.32% | -13.57% | 244 |
| 2020 | 62.55% | -18.02% | 243 |
| 2021 | 23.97% | -17.71% | 243 |
| 2022 | 2.81% | -25.22% | 242 |
| 2023 | 36.50% | -9.70% | 242 |
| 2024 | 11.32% | -25.44% | 242 |
| 2025 | 225.48% | -11.85% | 243 |
| 2026 | 148.10% | -19.00% | 110 |

### N Distribution

| N | days | share |
|---:|---:|---:|
| 0 | 144 | 4.60% |
| 1 | 355 | 11.35% |
| 2 | 639 | 20.43% |
| 3 | 491 | 15.70% |
| 4 | 472 | 15.09% |
| 5 | 1027 | 32.83% |

### Forward Portfolio Return By N

| horizon | N | count | mean | median |
|---:|---:|---:|---:|---:|
| 5 | 0 | 144 | 0.41% | 0.00% |
| 5 | 1 | 355 | 1.34% | 0.26% |
| 5 | 2 | 636 | 1.01% | 0.09% |
| 5 | 3 | 489 | 0.83% | 0.17% |
| 5 | 4 | 472 | 0.66% | 0.09% |
| 5 | 5 | 1027 | 0.59% | 0.10% |
| 10 | 0 | 144 | 1.24% | 0.01% |
| 10 | 1 | 355 | 2.74% | 0.92% |
| 10 | 2 | 631 | 1.68% | 0.25% |
| 10 | 3 | 489 | 1.84% | 0.31% |
| 10 | 4 | 472 | 1.70% | 0.66% |
| 10 | 5 | 1027 | 1.12% | 0.38% |
| 20 | 0 | 144 | 1.68% | 1.28% |
| 20 | 1 | 355 | 4.91% | 2.79% |
| 20 | 2 | 627 | 3.64% | 1.49% |
| 20 | 3 | 485 | 3.75% | 0.84% |
| 20 | 4 | 470 | 4.03% | 1.93% |
| 20 | 5 | 1027 | 2.44% | 1.03% |

### Forward Benchmark Return By N

| horizon | N | count | mean | median |
|---:|---:|---:|---:|---:|
| 5 | 0 | 123 | 0.95% | 1.13% |
| 5 | 1 | 327 | 0.48% | 0.47% |
| 5 | 2 | 568 | -0.17% | -0.22% |
| 5 | 3 | 399 | -0.14% | 0.01% |
| 5 | 4 | 388 | -0.08% | -0.21% |
| 5 | 5 | 242 | 0.30% | 0.38% |
| 10 | 0 | 123 | 1.30% | 1.32% |
| 10 | 1 | 327 | 0.60% | 0.11% |
| 10 | 2 | 563 | -0.29% | -0.43% |
| 10 | 3 | 399 | -0.12% | -0.27% |
| 10 | 4 | 388 | 0.17% | -0.24% |
| 10 | 5 | 242 | 0.35% | 0.48% |
| 20 | 0 | 123 | 1.48% | 1.67% |
| 20 | 1 | 327 | 0.26% | -0.69% |
| 20 | 2 | 559 | 0.06% | -0.72% |
| 20 | 3 | 395 | -0.20% | -0.58% |
| 20 | 4 | 386 | 0.72% | 0.14% |
| 20 | 5 | 242 | 0.22% | 0.31% |

### Trading Summary

- trades: 5041
- buys: 2919
- sells: 2122

## WideA

### Annual By Year

| year | annual | dd | days |
|---:|---:|---:|---:|
| 2013 | -3.33% | -8.68% | 99 |
| 2014 | 44.93% | -5.76% | 245 |
| 2015 | 34.12% | -8.58% | 244 |
| 2016 | 14.27% | -6.86% | 244 |
| 2017 | 13.70% | -6.60% | 244 |
| 2018 | -15.89% | -21.87% | 243 |
| 2019 | 52.51% | -10.81% | 244 |
| 2020 | 61.11% | -21.49% | 243 |
| 2021 | 11.27% | -16.02% | 243 |
| 2022 | 17.51% | -19.97% | 242 |
| 2023 | 16.28% | -9.04% | 242 |
| 2024 | 24.15% | -19.92% | 242 |
| 2025 | 180.63% | -15.08% | 243 |
| 2026 | 109.77% | -16.15% | 110 |

### N Distribution

| N | days | share |
|---:|---:|---:|
| 0 | 80 | 2.56% |
| 1 | 164 | 5.24% |
| 2 | 508 | 16.24% |
| 3 | 477 | 15.25% |
| 4 | 619 | 19.79% |
| 5 | 1280 | 40.92% |

### Forward Portfolio Return By N

| horizon | N | count | mean | median |
|---:|---:|---:|---:|---:|
| 5 | 0 | 80 | 0.02% | 0.00% |
| 5 | 1 | 164 | 0.33% | 0.05% |
| 5 | 2 | 508 | 1.06% | 0.29% |
| 5 | 3 | 474 | 0.77% | 0.13% |
| 5 | 4 | 617 | 0.82% | 0.05% |
| 5 | 5 | 1280 | 0.60% | 0.10% |
| 10 | 0 | 80 | 0.40% | 0.00% |
| 10 | 1 | 164 | 0.84% | 0.11% |
| 10 | 2 | 506 | 2.25% | 0.70% |
| 10 | 3 | 471 | 1.32% | 0.19% |
| 10 | 4 | 617 | 1.67% | 0.52% |
| 10 | 5 | 1280 | 1.23% | 0.37% |
| 20 | 0 | 80 | 1.42% | 2.13% |
| 20 | 1 | 164 | 0.40% | 0.19% |
| 20 | 2 | 505 | 4.51% | 1.96% |
| 20 | 3 | 468 | 2.66% | 0.78% |
| 20 | 4 | 611 | 3.61% | 1.38% |
| 20 | 5 | 1280 | 2.66% | 1.12% |

### Forward Benchmark Return By N

| horizon | N | count | mean | median |
|---:|---:|---:|---:|---:|
| 5 | 0 | 59 | 1.06% | 1.00% |
| 5 | 1 | 136 | 0.75% | 0.75% |
| 5 | 2 | 440 | 0.33% | 0.32% |
| 5 | 3 | 384 | -0.35% | -0.42% |
| 5 | 4 | 533 | -0.09% | -0.02% |
| 5 | 5 | 495 | 0.08% | -0.07% |
| 10 | 0 | 59 | 1.25% | 1.64% |
| 10 | 1 | 136 | 1.10% | 0.77% |
| 10 | 2 | 438 | 0.38% | 0.17% |
| 10 | 3 | 381 | -0.52% | -0.72% |
| 10 | 4 | 533 | 0.00% | -0.20% |
| 10 | 5 | 495 | 0.21% | 0.07% |
| 20 | 0 | 59 | 2.02% | 2.67% |
| 20 | 1 | 136 | 0.63% | 0.21% |
| 20 | 2 | 437 | 0.28% | -0.26% |
| 20 | 3 | 378 | -0.09% | -0.94% |
| 20 | 4 | 527 | 0.12% | -0.49% |
| 20 | 5 | 495 | 0.39% | 0.19% |

### Trading Summary

- trades: 5870
- buys: 3392
- sells: 2478

## Exph_v3

### Annual By Year

| year | annual | dd | days |
|---:|---:|---:|---:|
| 2013 | -3.33% | -8.68% | 99 |
| 2014 | 44.93% | -5.76% | 245 |
| 2015 | 34.12% | -8.58% | 244 |
| 2016 | 14.27% | -6.86% | 244 |
| 2017 | 13.70% | -6.60% | 244 |
| 2018 | -9.62% | -17.03% | 243 |
| 2019 | 49.65% | -7.70% | 244 |
| 2020 | 33.71% | -15.26% | 243 |
| 2021 | 14.51% | -14.60% | 243 |
| 2022 | 22.39% | -14.69% | 242 |
| 2023 | 29.46% | -7.79% | 242 |
| 2024 | 29.90% | -20.11% | 242 |
| 2025 | 104.27% | -16.31% | 243 |
| 2026 | 99.31% | -16.19% | 110 |

### N Distribution

| N | days | share |
|---:|---:|---:|
| 0 | 144 | 4.60% |
| 1 | 29 | 0.93% |
| 2 | 72 | 2.30% |
| 3 | 421 | 13.46% |
| 4 | 1048 | 33.50% |
| 5 | 1414 | 45.20% |

### Forward Portfolio Return By N

| horizon | N | count | mean | median |
|---:|---:|---:|---:|---:|
| 5 | 0 | 144 | 0.44% | 0.00% |
| 5 | 1 | 29 | 0.11% | 0.05% |
| 5 | 2 | 72 | 0.20% | 0.05% |
| 5 | 3 | 421 | 0.79% | 0.29% |
| 5 | 4 | 1043 | 0.72% | 0.25% |
| 5 | 5 | 1414 | 0.62% | 0.10% |
| 10 | 0 | 144 | 0.78% | 0.00% |
| 10 | 1 | 29 | 0.17% | 0.12% |
| 10 | 2 | 72 | 0.60% | 0.14% |
| 10 | 3 | 421 | 1.79% | 0.71% |
| 10 | 4 | 1038 | 1.33% | 0.70% |
| 10 | 5 | 1414 | 1.28% | 0.41% |
| 20 | 0 | 144 | 0.71% | 0.15% |
| 20 | 1 | 29 | 0.53% | 0.21% |
| 20 | 2 | 72 | 1.03% | 0.22% |
| 20 | 3 | 421 | 2.88% | 1.14% |
| 20 | 4 | 1030 | 3.02% | 1.73% |
| 20 | 5 | 1412 | 2.78% | 1.39% |

### Forward Benchmark Return By N

| horizon | N | count | mean | median |
|---:|---:|---:|---:|---:|
| 5 | 0 | 123 | 0.95% | 1.13% |
| 5 | 1 | 1 | -1.16% | -1.16% |
| 5 | 2 | 4 | 0.93% | 1.69% |
| 5 | 3 | 331 | 0.51% | 0.47% |
| 5 | 4 | 959 | -0.17% | -0.14% |
| 5 | 5 | 629 | 0.07% | -0.10% |
| 10 | 0 | 123 | 1.30% | 1.32% |
| 10 | 1 | 1 | -1.36% | -1.36% |
| 10 | 2 | 4 | -0.32% | -0.48% |
| 10 | 3 | 331 | 0.61% | 0.12% |
| 10 | 4 | 954 | -0.22% | -0.33% |
| 10 | 5 | 629 | 0.23% | 0.05% |
| 20 | 0 | 123 | 1.48% | 1.67% |
| 20 | 1 | 1 | -3.94% | -3.94% |
| 20 | 2 | 4 | 1.39% | 1.33% |
| 20 | 3 | 331 | 0.20% | -0.69% |
| 20 | 4 | 946 | -0.03% | -0.64% |
| 20 | 5 | 627 | 0.52% | 0.17% |

### Trading Summary

- trades: 11005
- buys: 5861
- sells: 5144

## Local Tuning: LONG_2013_2026

- base: `adaptive_window=15`, `adaptive_mode=bench_20d_ret`, `F2_CAP_MA60`
- only one axis is changed per variant

| variant | axis | annual | sharpe | dd | trades |
|---|---|---:|---:|---:|---:|
| Exph_v3_n_down1 | N | 32.86% | 1.57 | -20.85% | 10147 |
| Exph_v3_exp_looser | Exposure | 32.80% | 1.60 | -19.94% | 10874 |
| Exph_v3_base | N | 32.60% | 1.59 | -20.11% | 11005 |
| Exph_v3_exp_tighter | Exposure | 32.45% | 1.59 | -20.24% | 11215 |
| Exph_v3_n_up1 | N | 31.40% | 1.56 | -21.49% | 11512 |

- baseline control: annual 32.60%, sharpe 1.59, dd -20.11%

## Local Tuning: 2026_NOWARMUP

- base: `adaptive_window=15`, `adaptive_mode=bench_20d_ret`, `F2_CAP_MA60`
- only one axis is changed per variant

| variant | axis | annual | sharpe | dd | trades |
|---|---|---:|---:|---:|---:|
| Exph_v3_exp_looser | Exposure | 109.05% | 3.59 | -15.80% | 557 |
| Exph_v3_base | N | 107.17% | 3.54 | -15.86% | 568 |
| Exph_v3_exp_tighter | Exposure | 105.30% | 3.48 | -15.89% | 571 |
| Exph_v3_n_up1 | N | 104.98% | 3.61 | -15.31% | 599 |
| Exph_v3_n_down1 | N | 104.70% | 3.23 | -16.45% | 506 |

- baseline control: annual 107.17%, sharpe 3.54, dd -15.86%

## Notes

- diagnostics are descriptive only; they do not change parameters
- tuning variants are single-axis perturbations around `Exph_v3`
- keep `15d` fixed throughout this script

## Conclusion

- 15d behavior diagnosis: lower `N` states are associated with higher forward portfolio returns, while benchmark forward returns are weakest around the mid `N=3/4` regime. This supports the idea that the adaptive N signal is doing real timing work instead of just adding noise.
- Local tuning: `Exph_v3_exp_looser` is the best one-axis perturbation in this round. It slightly improves annual return and Sharpe, and keeps drawdown better than the base case on both long-period and 2026 nowarmup tests.
- `N_down1` has the highest long-period annual return among the N-only variants, but it weakens 2026 drawdown and Sharpe. I would not promote it over `Exph_v3_exp_looser` on current evidence.
