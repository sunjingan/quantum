# ETF Loop Signal-Layer OOS / Walk-Forward Validation

## Scope

- This rerun validates signal/parameter robustness only.
- Execution is fixed to `T close signal -> T+1 open fill`.
- Cost is fixed at `commission 1.5bp + slippage 2bp per side`.
- Excluded: minute VWAP/TWAP, order-book penalties, split orders, participation caps, capacity pressure.

## Reproduce

```bash
source activate.sh
python runs/etf_loop/run_signal_oos_walkforward_validation.py
```

## Fixed OOS

| variant | window | annual | sharpe | dd | calmar | win | alpha | trades |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Exph_v3_exp_looser | train_2018_2021 | 14.98% | 0.83 | -17.30% | 0.87 | 47.89% | 8.05% | 2900 |
| Exph_v3_exp_looser | valid_2022 | -0.13% | -0.01 | -13.51% | -0.01 | 33.33% | 21.82% | 608 |
| Exph_v3_exp_looser | test_2023_2026 | 52.64% | 2.36 | -15.66% | 3.36 | 54.61% | 44.00% | 2753 |
| Exph_v3_exp_looser | long_2013_2026 | 27.33% | 1.51 | -17.30% | 1.58 | 53.46% | 23.14% | 8387 |
| F2_CAP_MA60 | train_2018_2021 | 16.28% | 0.82 | -17.20% | 0.95 | 50.46% | 9.35% | 2452 |
| F2_CAP_MA60 | valid_2022 | 1.99% | 0.11 | -14.71% | 0.14 | 37.08% | 23.94% | 573 |
| F2_CAP_MA60 | test_2023_2026 | 58.38% | 2.37 | -19.11% | 3.06 | 56.17% | 49.74% | 2323 |
| F2_CAP_MA60 | long_2013_2026 | 29.01% | 1.47 | -18.98% | 1.53 | 55.14% | 24.83% | 7562 |
| WideA | train_2018_2021 | 26.83% | 1.07 | -21.49% | 1.25 | 49.43% | 19.90% | 1789 |
| WideA | valid_2022 | -1.33% | -0.06 | -17.54% | -0.08 | 32.92% | 20.61% | 404 |
| WideA | test_2023_2026 | 69.92% | 2.35 | -19.84% | 3.52 | 53.05% | 61.28% | 1735 |
| WideA | long_2013_2026 | 35.87% | 1.51 | -21.83% | 1.64 | 53.81% | 31.68% | 5805 |

## Yearly Breakdown

| variant | year | annual | sharpe | dd | win | alpha | trades |
|---|---:|---:|---:|---:|---:|---:|---:|
| Exph_v3_exp_looser | 2018 | -12.65% | -1.08 | -12.40% | 36.51% | 17.61% | 549 |
| Exph_v3_exp_looser | 2019 | 17.46% | 1.47 | -6.81% | 41.32% | -18.20% | 644 |
| Exph_v3_exp_looser | 2020 | 22.30% | 1.15 | -17.30% | 41.91% | -4.26% | 633 |
| Exph_v3_exp_looser | 2021 | 9.78% | 0.69 | -9.74% | 40.66% | 16.75% | 641 |
| Exph_v3_exp_looser | 2022 | -0.13% | -0.01 | -13.51% | 33.33% | 21.82% | 608 |
| Exph_v3_exp_looser | 2023 | 17.18% | 1.43 | -5.45% | 44.17% | 29.53% | 654 |
| Exph_v3_exp_looser | 2024 | 28.81% | 1.23 | -15.65% | 43.33% | 10.53% | 753 |
| Exph_v3_exp_looser | 2025 | 56.36% | 2.67 | -12.33% | 49.38% | 33.88% | 633 |
| Exph_v3_exp_looser | 2026 | 65.72% | 2.71 | -12.30% | 34.26% | 57.16% | 205 |
| F2_CAP_MA60 | 2018 | -11.39% | -0.83 | -12.79% | 41.91% | 18.87% | 458 |
| F2_CAP_MA60 | 2019 | 7.62% | 0.60 | -11.05% | 40.50% | -28.03% | 512 |
| F2_CAP_MA60 | 2020 | 28.04% | 1.36 | -12.19% | 45.64% | 1.48% | 524 |
| F2_CAP_MA60 | 2021 | 10.93% | 0.62 | -10.34% | 41.91% | 17.91% | 541 |
| F2_CAP_MA60 | 2022 | 1.99% | 0.11 | -14.71% | 37.08% | 23.94% | 573 |
| F2_CAP_MA60 | 2023 | 25.81% | 1.82 | -5.95% | 46.67% | 38.16% | 485 |
| F2_CAP_MA60 | 2024 | 27.01% | 1.08 | -19.08% | 42.08% | 8.72% | 617 |
| F2_CAP_MA60 | 2025 | 65.36% | 2.74 | -13.91% | 50.21% | 42.88% | 559 |
| F2_CAP_MA60 | 2026 | 62.61% | 2.30 | -15.74% | 35.19% | 54.05% | 182 |
| WideA | 2018 | -14.74% | -0.88 | -17.21% | 39.00% | 15.53% | 263 |
| WideA | 2019 | 24.29% | 1.48 | -10.81% | 44.21% | -11.36% | 366 |
| WideA | 2020 | 35.23% | 1.39 | -16.11% | 41.49% | 8.67% | 465 |
| WideA | 2021 | 12.86% | 0.51 | -15.93% | 40.25% | 19.83% | 366 |
| WideA | 2022 | -1.33% | -0.06 | -17.54% | 32.92% | 20.61% | 404 |
| WideA | 2023 | 20.42% | 1.08 | -8.91% | 44.58% | 32.77% | 322 |
| WideA | 2024 | 20.43% | 0.76 | -19.80% | 40.83% | 2.15% | 463 |
| WideA | 2025 | 98.86% | 3.25 | -15.60% | 48.96% | 76.39% | 455 |
| WideA | 2026 | 81.87% | 2.60 | -16.34% | 33.33% | 73.31% | 150 |

## Robustness Summary

| section | axis | count | annual min/median/max | dd min/median/max | sharpe min/median/max |
|---|---|---:|---:|---:|---:|
| robust_f2 | atr_multiplier | 5 | 28.87% / 29.03% / 29.04% | -19.05% / -18.96% / -18.96% | 1.46 / 1.47 / 1.47 |
| robust_f2 | dynamic_max_total_weight | 4 | 28.99% / 29.01% / 29.03% | -19.16% / -19.02% / -18.92% | 1.46 / 1.46 / 1.47 |
| robust_f2 | dynamic_overheat_penalty | 4 | 29.01% / 29.12% / 29.16% | -18.98% / -18.82% / -18.25% | 1.47 / 1.47 / 1.48 |
| robust_f2 | dynamic_overheat_threshold | 4 | 28.63% / 29.11% / 29.37% | -18.98% / -18.91% / -18.78% | 1.45 / 1.47 / 1.48 |
| robust_f2 | dynamic_score_margin | 4 | 28.85% / 29.03% / 29.24% | -19.27% / -19.06% / -18.94% | 1.46 / 1.47 / 1.48 |
| robust_f2 | holdings_num | 5 | 25.58% / 32.76% / 35.62% | -51.54% / -28.10% / -17.58% | 1.03 / 1.39 / 1.47 |
| robust_f2 | lookback_days | 7 | 15.90% / 22.49% / 29.55% | -38.55% / -21.44% / -16.61% | 0.86 / 1.15 / 1.49 |
| robust_f2 | mr_ma_period | 3 | 28.50% / 28.86% / 29.01% | -19.00% / -18.98% / -18.87% | 1.44 / 1.45 / 1.47 |
| robust_f2 | mr_penalty | 4 | 28.24% / 28.74% / 29.01% | -18.99% / -18.92% / -18.85% | 1.41 / 1.45 / 1.48 |
| robust_f2 | mr_threshold | 4 | 28.19% / 28.87% / 29.15% | -18.98% / -18.87% / -18.77% | 1.42 / 1.45 / 1.47 |
| robust_f2 | stop_loss | 5 | 28.87% / 29.02% / 29.03% | -19.01% / -18.98% / -18.98% | 1.46 / 1.47 / 1.47 |
| robust_widea | adaptive_tiers | 5 | 31.76% / 35.87% / 39.81% | -25.51% / -24.11% / -21.83% | 1.46 / 1.51 / 1.57 |
| robust_widea | adaptive_window | 6 | 25.44% / 32.49% / 35.87% | -31.60% / -25.15% / -21.83% | 1.15 / 1.38 / 1.51 |

## Robustness Detail

| section | axis | label | annual | sharpe | dd | calmar | win | trades |
|---|---|---|---:|---:|---:|---:|---:|---:|
| robust_f2 | atr_multiplier | atr=1.5 | 28.87% | 1.46 | -19.05% | 1.52 | 55.11% | 7628 |
| robust_f2 | atr_multiplier | atr=2.0 | 29.01% | 1.47 | -18.98% | 1.53 | 55.14% | 7562 |
| robust_f2 | atr_multiplier | atr=2.5 | 29.03% | 1.47 | -18.96% | 1.53 | 55.20% | 7545 |
| robust_f2 | atr_multiplier | atr=3.0 | 29.04% | 1.47 | -18.96% | 1.53 | 55.23% | 7539 |
| robust_f2 | atr_multiplier | atr=off | 29.04% | 1.47 | -18.96% | 1.53 | 55.23% | 7539 |
| robust_f2 | dynamic_max_total_weight | dyn_weight=0.00 | 29.03% | 1.46 | -19.16% | 1.52 | 55.58% | 6410 |
| robust_f2 | dynamic_max_total_weight | dyn_weight=0.05 | 29.01% | 1.47 | -19.06% | 1.52 | 55.04% | 7536 |
| robust_f2 | dynamic_max_total_weight | dyn_weight=0.10 | 29.01% | 1.47 | -18.98% | 1.53 | 55.14% | 7562 |
| robust_f2 | dynamic_max_total_weight | dyn_weight=0.20 | 28.99% | 1.46 | -18.92% | 1.53 | 55.11% | 7485 |
| robust_f2 | dynamic_overheat_penalty | dyn_penalty=0.25 | 29.14% | 1.48 | -18.25% | 1.60 | 55.04% | 7545 |
| robust_f2 | dynamic_overheat_penalty | dyn_penalty=0.50 | 29.01% | 1.47 | -18.98% | 1.53 | 55.14% | 7562 |
| robust_f2 | dynamic_overheat_penalty | dyn_penalty=0.75 | 29.16% | 1.47 | -18.89% | 1.54 | 55.20% | 7469 |
| robust_f2 | dynamic_overheat_penalty | dyn_penalty=1.00 | 29.09% | 1.47 | -18.75% | 1.55 | 55.17% | 7451 |
| robust_f2 | dynamic_overheat_threshold | dyn_hot=0.05 | 28.63% | 1.45 | -18.97% | 1.51 | 55.20% | 7517 |
| robust_f2 | dynamic_overheat_threshold | dyn_hot=0.10 | 29.01% | 1.47 | -18.98% | 1.53 | 55.14% | 7562 |
| robust_f2 | dynamic_overheat_threshold | dyn_hot=0.15 | 29.37% | 1.48 | -18.84% | 1.56 | 55.20% | 7544 |
| robust_f2 | dynamic_overheat_threshold | dyn_hot=0.20 | 29.20% | 1.47 | -18.78% | 1.56 | 55.20% | 7495 |
| robust_f2 | dynamic_score_margin | dyn_margin=0.00 | 28.85% | 1.46 | -18.94% | 1.52 | 55.23% | 7556 |
| robust_f2 | dynamic_score_margin | dyn_margin=0.05 | 29.01% | 1.47 | -18.98% | 1.53 | 55.14% | 7562 |
| robust_f2 | dynamic_score_margin | dyn_margin=0.10 | 29.05% | 1.47 | -19.14% | 1.52 | 55.17% | 7557 |
| robust_f2 | dynamic_score_margin | dyn_margin=0.20 | 29.24% | 1.48 | -19.27% | 1.52 | 55.17% | 7539 |
| robust_f2 | holdings_num | holdings=1 | 35.62% | 1.03 | -51.54% | 0.69 | 51.97% | 2103 |
| robust_f2 | holdings_num | holdings=2 | 32.91% | 1.17 | -32.78% | 1.00 | 53.17% | 3876 |
| robust_f2 | holdings_num | holdings=3 | 32.76% | 1.39 | -28.10% | 1.17 | 54.63% | 5346 |
| robust_f2 | holdings_num | holdings=5 | 29.01% | 1.47 | -18.98% | 1.53 | 55.14% | 7562 |
| robust_f2 | holdings_num | holdings=7 | 25.58% | 1.43 | -17.58% | 1.46 | 55.71% | 8917 |
| robust_f2 | lookback_days | lookback=10 | 18.74% | 0.92 | -38.55% | 0.49 | 52.19% | 8674 |
| robust_f2 | lookback_days | lookback=15 | 22.49% | 1.10 | -32.45% | 0.69 | 54.00% | 7661 |
| robust_f2 | lookback_days | lookback=20 | 25.69% | 1.28 | -16.61% | 1.55 | 55.01% | 7369 |
| robust_f2 | lookback_days | lookback=25 | 29.01% | 1.47 | -18.98% | 1.53 | 55.14% | 7562 |
| robust_f2 | lookback_days | lookback=30 | 29.55% | 1.49 | -21.44% | 1.38 | 56.12% | 7615 |
| robust_f2 | lookback_days | lookback=40 | 21.91% | 1.15 | -18.80% | 1.17 | 55.65% | 7425 |
| robust_f2 | lookback_days | lookback=60 | 15.90% | 0.86 | -34.89% | 0.46 | 55.39% | 7330 |
| robust_f2 | mr_ma_period | ma=40 | 28.50% | 1.44 | -18.87% | 1.51 | 55.08% | 7529 |
| robust_f2 | mr_ma_period | ma=60 | 29.01% | 1.47 | -18.98% | 1.53 | 55.14% | 7562 |
| robust_f2 | mr_ma_period | ma=80 | 28.86% | 1.45 | -19.00% | 1.52 | 55.20% | 7578 |
| robust_f2 | mr_penalty | mr_penalty=0.30 | 28.86% | 1.48 | -18.86% | 1.53 | 55.52% | 7719 |
| robust_f2 | mr_penalty | mr_penalty=0.50 | 29.01% | 1.47 | -18.98% | 1.53 | 55.14% | 7562 |
| robust_f2 | mr_penalty | mr_penalty=0.70 | 28.62% | 1.43 | -18.99% | 1.51 | 55.20% | 7460 |
| robust_f2 | mr_penalty | mr_penalty=1.00 | 28.24% | 1.41 | -18.85% | 1.50 | 55.33% | 7412 |
| robust_f2 | mr_threshold | mr_threshold=1.10 | 28.19% | 1.42 | -18.77% | 1.50 | 55.33% | 7630 |
| robust_f2 | mr_threshold | mr_threshold=1.14 | 29.01% | 1.47 | -18.98% | 1.53 | 55.14% | 7562 |
| robust_f2 | mr_threshold | mr_threshold=1.18 | 29.15% | 1.47 | -18.86% | 1.55 | 55.39% | 7463 |
| robust_f2 | mr_threshold | mr_threshold=1.22 | 28.74% | 1.44 | -18.88% | 1.52 | 55.11% | 7493 |
| robust_f2 | stop_loss | stop=0.00 | 29.03% | 1.47 | -18.98% | 1.53 | 55.14% | 7547 |
| robust_f2 | stop_loss | stop=0.90 | 29.02% | 1.47 | -18.98% | 1.53 | 55.14% | 7549 |
| robust_f2 | stop_loss | stop=0.93 | 29.02% | 1.47 | -18.98% | 1.53 | 55.14% | 7551 |
| robust_f2 | stop_loss | stop=0.95 | 29.01% | 1.47 | -18.98% | 1.53 | 55.14% | 7562 |
| robust_f2 | stop_loss | stop=0.97 | 28.87% | 1.46 | -19.01% | 1.52 | 55.17% | 7609 |
| robust_widea | adaptive_tiers | current | 39.81% | 1.57 | -25.44% | 1.56 | 52.89% | 5041 |
| robust_widea | adaptive_tiers | wideA_base | 35.87% | 1.51 | -21.83% | 1.64 | 53.81% | 5805 |
| robust_widea | adaptive_tiers | wideA_looser | 34.43% | 1.50 | -25.51% | 1.35 | 54.31% | 6142 |
| robust_widea | adaptive_tiers | wideA_tighter | 38.71% | 1.57 | -23.31% | 1.66 | 53.33% | 5361 |
| robust_widea | adaptive_tiers | wideB | 31.76% | 1.46 | -24.11% | 1.32 | 54.35% | 6583 |
| robust_widea | adaptive_window | adaptive_window=10 | 32.53% | 1.37 | -26.15% | 1.24 | 53.71% | 5682 |
| robust_widea | adaptive_window | adaptive_window=15 | 35.87% | 1.51 | -21.83% | 1.64 | 53.81% | 5805 |
| robust_widea | adaptive_window | adaptive_window=20 | 32.46% | 1.39 | -31.60% | 1.03 | 53.11% | 5807 |
| robust_widea | adaptive_window | adaptive_window=30 | 32.22% | 1.37 | -22.88% | 1.41 | 52.60% | 5768 |
| robust_widea | adaptive_window | adaptive_window=5 | 32.75% | 1.40 | -24.15% | 1.36 | 54.38% | 5678 |
| robust_widea | adaptive_window | adaptive_window=60 | 25.44% | 1.15 | -26.62% | 0.96 | 49.49% | 5434 |

## Walk-Forward

- months: `60`
- final value: `2,657,518`
- chained total return: `431.50%`
- approximate chained CAGR: `41.86%`
- positive test months: `56.67%`

| month | selected | train annual | train sharpe | train dd | test return | test annual | test sharpe | test dd | trades |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021-07 | WideA_base | 38.92% | 1.55 | -21.48% | 1.96% | 29.48% | 0.82 | -7.50% | 38 |
| 2021-08 | WideA_base | 37.77% | 1.47 | -21.47% | -2.25% | -24.43% | -1.00 | -6.12% | 55 |
| 2021-09 | WideA_base | 34.73% | 1.33 | -21.50% | 11.68% | 152.14% | 4.59 | -4.39% | 31 |
| 2021-10 | WideA_base | 40.76% | 1.54 | -21.48% | 2.39% | 42.46% | 1.74 | -3.81% | 22 |
| 2021-11 | WideA_base | 42.11% | 1.56 | -21.48% | -0.97% | -10.84% | -0.80 | -3.20% | 51 |
| 2021-12 | WideA_base | 41.30% | 1.53 | -21.48% | -3.77% | -43.29% | -3.47 | -4.58% | 67 |
| 2022-01 | WideA_base | 33.12% | 1.27 | -21.50% | 8.15% | 112.01% | 5.30 | -1.78% | 12 |
| 2022-02 | WideA_base | 34.38% | 1.32 | -21.50% | 6.99% | 119.80% | 3.30 | -3.82% | 29 |
| 2022-03 | WideA_base | 39.39% | 1.47 | -21.48% | -0.70% | -2.19% | -0.06 | -8.72% | 34 |
| 2022-04 | WideA_base | 39.73% | 1.44 | -21.49% | -3.57% | -49.43% | -2.92 | -3.57% | 32 |
| 2022-05 | WideA_base | 36.76% | 1.33 | -21.49% | -2.73% | -33.98% | -1.08 | -10.51% | 32 |
| 2022-06 | WideA_base | 37.47% | 1.34 | -21.48% | 13.27% | 161.56% | 5.55 | -3.46% | 60 |
| 2022-07 | WideA_base | 36.14% | 1.29 | -21.50% | 1.99% | 26.91% | 1.28 | -5.44% | 52 |
| 2022-08 | WideA_base | 38.23% | 1.37 | -21.49% | -3.28% | -35.87% | -1.62 | -8.26% | 40 |
| 2022-09 | WideA_base | 36.68% | 1.30 | -21.47% | -7.31% | -93.74% | -4.86 | -10.65% | 33 |
| 2022-10 | WideA_base | 34.15% | 1.21 | -21.47% | -1.39% | -22.66% | -1.69 | -2.73% | 10 |
| 2022-11 | WideA_base | 29.69% | 1.05 | -21.50% | 2.49% | 33.81% | 1.13 | -8.44% | 66 |
| 2022-12 | WideA_base | 27.58% | 1.00 | -19.81% | -0.39% | -1.63% | -0.06 | -5.67% | 65 |
| 2023-01 | F2_LB30 | 20.95% | 1.04 | -15.53% | 0.80% | 15.68% | 0.71 | -3.74% | 49 |
| 2023-02 | WideA_base | 28.09% | 1.07 | -19.81% | -5.42% | -72.86% | -5.14 | -5.79% | 56 |
| 2023-03 | WideA_base | 25.22% | 0.96 | -19.81% | -2.44% | -26.39% | -1.34 | -4.99% | 39 |
| 2023-04 | F2_H7 | 16.41% | 0.90 | -15.26% | -0.07% | 1.41% | 0.06 | -6.05% | 68 |
| 2023-05 | WideA_base | 17.86% | 0.68 | -19.80% | -0.86% | -9.11% | -0.41 | -8.34% | 48 |
| 2023-06 | F2_LB30 | 12.26% | 0.64 | -15.57% | 4.50% | 60.14% | 3.16 | -3.82% | 37 |
| 2023-07 | F2_LB30 | 13.45% | 0.70 | -15.82% | 2.87% | 36.18% | 3.45 | -1.52% | 35 |
| 2023-08 | F2_base | 16.78% | 0.87 | -15.40% | -1.49% | -16.05% | -1.07 | -5.35% | 59 |
| 2023-09 | F2_base | 18.86% | 0.99 | -15.31% | 1.04% | 14.24% | 1.40 | -2.41% | 29 |
| 2023-10 | F2_base | 17.41% | 0.92 | -15.42% | 2.13% | 33.96% | 2.66 | -1.73% | 57 |
| 2023-11 | Exph_v3_exp_looser | 13.16% | 0.84 | -13.51% | -2.77% | -33.16% | -3.33 | -3.56% | 81 |
| 2023-12 | Exph_v3_exp_looser | 13.35% | 0.88 | -13.51% | 1.52% | 19.27% | 2.60 | -1.23% | 64 |
| 2024-01 | F2_LB30 | 17.70% | 0.98 | -15.77% | 2.79% | 33.85% | 2.66 | -1.70% | 53 |
| 2024-02 | F2_LB30 | 18.41% | 1.02 | -15.77% | 4.45% | 79.12% | 7.22 | -1.56% | 23 |
| 2024-03 | F2_LB30 | 19.16% | 1.07 | -15.75% | 0.12% | 2.79% | 0.17 | -5.30% | 59 |
| 2024-04 | F2_LB30 | 18.52% | 1.03 | -15.74% | -1.07% | -12.94% | -0.77 | -4.41% | 66 |
| 2024-05 | F2_LB30 | 17.94% | 1.01 | -15.81% | -2.72% | -34.39% | -1.60 | -7.44% | 45 |
| 2024-06 | F2_LB30 | 17.80% | 1.01 | -15.78% | -0.40% | -4.18% | -0.24 | -5.04% | 47 |
| 2024-07 | F2_base | 15.54% | 0.87 | -15.38% | -3.29% | -36.84% | -2.11 | -6.64% | 76 |
| 2024-08 | F2_LB30 | 14.28% | 0.83 | -15.81% | -3.96% | -48.06% | -5.43 | -3.96% | 59 |
| 2024-09 | F2_LB30 | 12.05% | 0.70 | -15.74% | 26.92% | 343.29% | 8.52 | -2.09% | 72 |
| 2024-10 | F2_LB30 | 21.06% | 1.15 | -15.87% | 3.91% | 68.08% | 1.38 | -5.81% | 88 |
| 2024-11 | F2_LB30 | 24.60% | 1.23 | -15.94% | 8.24% | 104.28% | 3.42 | -7.07% | 84 |
| 2024-12 | F2_LB30 | 24.51% | 1.20 | -15.93% | 1.56% | 19.29% | 1.53 | -2.51% | 52 |
| 2025-01 | F2_LB30 | 23.60% | 1.19 | -15.98% | -0.57% | -7.96% | -0.73 | -3.50% | 52 |
| 2025-02 | F2_LB30 | 24.69% | 1.24 | -16.00% | 7.22% | 110.39% | 2.88 | -6.01% | 44 |
| 2025-03 | F2_LB30 | 26.61% | 1.30 | -15.93% | -0.92% | -9.86% | -0.52 | -5.31% | 96 |
| 2025-04 | F2_LB30 | 22.63% | 1.11 | -15.94% | -8.27% | -103.56% | -3.26 | -10.86% | 37 |
| 2025-05 | F2_LB30 | 21.16% | 1.02 | -15.94% | -2.03% | -27.75% | -1.94 | -3.89% | 65 |
| 2025-06 | F2_LB30 | 19.65% | 0.95 | -16.44% | 7.03% | 92.15% | 4.56 | -3.54% | 52 |
| 2025-07 | F2_LB30 | 23.72% | 1.14 | -16.43% | 10.97% | 121.32% | 6.20 | -3.55% | 44 |
| 2025-08 | F2_LB30 | 29.26% | 1.40 | -16.40% | 26.05% | 298.48% | 8.99 | -2.21% | 76 |
| 2025-09 | F2_LB30 | 37.15% | 1.72 | -16.44% | 2.84% | 38.51% | 1.20 | -9.04% | 54 |
| 2025-10 | F2_LB30 | 38.15% | 1.76 | -16.40% | 3.06% | 49.81% | 2.28 | -5.35% | 63 |
| 2025-11 | F2_LB30 | 37.30% | 1.70 | -16.44% | -4.41% | -58.05% | -3.15 | -7.10% | 76 |
| 2025-12 | F2_LB30 | 38.36% | 1.75 | -16.45% | 20.40% | 217.05% | 7.94 | -2.47% | 57 |
| 2026-01 | F2_LB30 | 46.90% | 2.08 | -16.46% | 25.16% | 303.21% | 10.71 | -2.81% | 50 |
| 2026-02 | F2_LB30 | 53.17% | 2.34 | -16.42% | 3.44% | 66.59% | 4.73 | -1.55% | 61 |
| 2026-03 | F2_LB30 | 51.95% | 2.22 | -16.39% | 8.31% | 99.82% | 3.53 | -5.39% | 73 |
| 2026-04 | WideA_base | 68.69% | 2.33 | -19.83% | 12.75% | 154.26% | 6.64 | -3.28% | 42 |
| 2026-05 | F2_LB30 | 59.46% | 2.46 | -16.43% | 14.50% | 211.53% | 4.59 | -6.91% | 54 |
| 2026-06 | F2_LB30 | 65.68% | 2.61 | -16.44% | 0.65% | 16.94% | 0.50 | -9.78% | 65 |

### Walk-Forward Selection Counts

| candidate | count |
|---|---:|
| F2_LB30 | 31 |
| WideA_base | 22 |
| F2_base | 4 |
| Exph_v3_exp_looser | 2 |
| F2_H7 | 1 |

## Notes

- These results still use the frozen `F2_v3` static core pool, so they test parameter overfit under a frozen pool rather than a fully PIT core-pool research design.
- If this layer passes, execution-layer validation should be rerun afterward using minute data, capacity, split orders, and premium/slippage audits.

## Conclusion

### Current candidate ranking after this signal-layer rerun

| rank | candidate | role | reason | key risk |
|---:|---|---|---|---|
| 1 | `F2_CAP_MA60` / `F2_LB30` family | Default robust baseline | Long-run annual return is lower than WideA, but drawdown is more controlled and most single-parameter perturbations remain stable. Walk-forward selected `F2_LB30` most often. | 2024 H1 and 2025-04 still show regime-lag losses; lookback choice matters. |
| 2 | `WideA` | Aggressive/high-return candidate | Long-run and 2023-2026 return are strongest: long annual `35.87%`, test annual `69.92%`. | 2022 validation is worse than F2, long DD is larger, and returns are more back-loaded into 2025-2026. |
| 3 | `Exph_v3_exp_looser` | Defensive/risk-control candidate | Long DD `-17.30%`, 2024 DD `-15.65%`, 2026 DD `-12.30%`, lower than the other two. | Return is clearly lower than WideA and lower than F2 in most long windows. |

### What passed

- The F2 baseline does not look like a single-point parameter island. ATR multiplier, stop loss, dynamic-pool cap, dynamic-score margin, MA overheat threshold/penalty all have small impact.
- F2 lookback has a usable plateau around `20/25/30` trading days. `25` and `30` are strongest; very short `10/15` and very long `60` degrade materially.
- Holding number confirms the earlier design choice: Top1/Top2 has higher annual return but much larger drawdown; Top5 is the more usable baseline.
- WideA adaptive window is not completely isolated: `5/10/15/20/30` all remain alive, but `15` is best in this sweep.
- Walk-forward chained result is positive: 60 monthly tests, final value `2,657,518` from `500,000`, chained total return `431.50%`, approximate CAGR `41.86%`.

### What did not fully pass

- 2022 remains a weak validation year for WideA. It was still selected by walk-forward for much of 2022 because trailing 3-year training performance lagged regime change.
- Walk-forward selector is regime-lagged. It over-selected WideA entering parts of 2022 and F2_LB30 entering some bad 2024/2025 months.
- This validation uses a frozen `F2_v3` core pool. It validates parameter robustness under the current pool assumption, not the full historical process of discovering the core pool without hindsight.
- These numbers intentionally exclude minute execution, split orders, premium/slippage audits, and capacity constraints. They should not be read as directly tradable returns.

### Next experiments before returning to minute execution

- Test `F2_CAP_MA60` versus `F2_LB30` directly in fixed OOS/yearly tables, because walk-forward selected `F2_LB30` most frequently.
- Add a conservative walk-forward selector: only switch from F2 to WideA if WideA beats by a margin and recent 3/6-month risk is not deteriorating.
- Re-run the minute execution layer only after the signal shortlist is frozen; otherwise execution results will mix signal changes and execution assumptions.
