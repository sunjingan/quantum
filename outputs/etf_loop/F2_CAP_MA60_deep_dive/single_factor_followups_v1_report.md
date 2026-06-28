# Single-Factor Follow-Ups

## Common Setting
- pool: `F2_CAP_MA60`
- benchmark: `sh000300`
- period: `2013-07-01` to `2026-06-25`
- cost: `open_cost=0.00015`, `close_cost=0.00015`, `slippage=0.0002`
- execution: signal-day close -> next trading day open, no signal-day close fallback
- control rule: one axis changes at a time; all other strategy knobs stay fixed

## Repro Command

```bash
source activate.sh && python run_single_factor_followups_v1.py
```

You can also run a single group with `--group widea_window`, `--group widea_threshold`, `--group exph_exposure`, `--group exph_n`, or `--group current_score`.

## Baseline Sources

- `Current` and `WideA` baselines were refreshed in `outputs/etf_loop/F2_CAP_MA60_deep_dive/v3_multi_setting_diagnostics.md`.
- `Exph_v3_base`, `Exph_v3_n_up1`, `Exph_v3_n_down1` were refreshed in `outputs/etf_loop/F2_CAP_MA60_deep_dive/adaptive_15d_v3_tuning_report.md`.

## WideA Window Perturbation

- setting: Fix `adaptive_tiers_ret=0.06,0.03,0.00,-0.02,-0.05,-0.08` and `adaptive_tiers_n=5,5,4,3,2,1,0`; vary only `adaptive_window`.
- repro: `source activate.sh && python run_single_factor_followups_v1.py --group widea_window`
- source report: `v3_multi_setting_diagnostics.md`

| variant | tag | source | adaptive_window | adaptive_tiers_ret | adaptive_tiers_n | adaptive_tiers_exposure | use_score_weighting | switch_score_margin | annual_return | max_drawdown | sharpe_ratio | calmar | year_2018 | year_2022 | year_2024 | avg_actual_exp | avg_cash_ratio | trade_count |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| win_10 | SF_WIDEA_WIN_10 | run | 10 | 0.06,0.03,0.00,-0.02,-0.05,-0.08 | 5,5,4,3,2,1,0 | — | — | — | 32.08% | -21.79% | 1.41 | 1.47 | 5.39% | 14.40% | 30.99% | 94.51% | 5.49% | 5710 |
| win_15_baseline | SEQ_LONG_2013_2026_WideA | load | 15 | 0.06,0.03,0.00,-0.02,-0.05,-0.08 | 5,5,4,3,2,1,0 | — | — | — | 37.12% | -19.66% | 1.62 | 1.89 | -0.62% | 31.21% | 29.58% | 92.52% | 7.48% | 5877 |
| win_20 | SF_WIDEA_WIN_20 | run | 20 | 0.06,0.03,0.00,-0.02,-0.05,-0.08 | 5,5,4,3,2,1,0 | — | — | — | 32.14% | -25.46% | 1.45 | 1.26 | -1.85% | 29.66% | 20.03% | 90.42% | 9.58% | 5854 |
| win_30 | SF_WIDEA_WIN_30 | run | 30 | 0.06,0.03,0.00,-0.02,-0.05,-0.08 | 5,5,4,3,2,1,0 | — | — | — | 31.13% | -22.36% | 1.44 | 1.39 | 2.73% | 10.47% | 32.27% | 86.73% | 13.27% | 5707 |

### Notes

- This isolates the lookback window only; the threshold ladder and N ladder stay fixed.
- Baseline `win_15` is loaded from the refreshed diagnostics report.

## WideA Threshold Perturbation

- setting: Fix `adaptive_window=15` and `adaptive_tiers_n=5,5,4,3,2,1,0`; vary only `adaptive_tiers_ret` by one notch.
- repro: `source activate.sh && python run_single_factor_followups_v1.py --group widea_threshold`
- source report: `v3_multi_setting_diagnostics.md`

| variant | tag | source | adaptive_window | adaptive_tiers_ret | adaptive_tiers_n | adaptive_tiers_exposure | use_score_weighting | switch_score_margin | annual_return | max_drawdown | sharpe_ratio | calmar | year_2018 | year_2022 | year_2024 | avg_actual_exp | avg_cash_ratio | trade_count |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ret_tighter | SF_WIDEA_RET_TIGHTER | run | 15 | 0.07,0.04,0.01,-0.01,-0.04,-0.07 | 5,5,4,3,2,1,0 | — | — | — | 33.73% | -26.14% | 1.47 | 1.29 | 2.32% | 19.76% | 19.73% | 89.10% | 10.90% | 5420 |
| ret_base | SEQ_LONG_2013_2026_WideA | load | 15 | 0.06,0.03,0.00,-0.02,-0.05,-0.08 | 5,5,4,3,2,1,0 | — | — | — | 37.12% | -19.66% | 1.62 | 1.89 | -0.62% | 31.21% | 29.58% | 92.52% | 7.48% | 5877 |
| ret_looser | SF_WIDEA_RET_LOOSER | run | 15 | 0.05,0.02,-0.01,-0.03,-0.06,-0.09 | 5,5,4,3,2,1,0 | — | — | — | 37.01% | -18.90% | 1.65 | 1.96 | -4.00% | 26.84% | 38.81% | 94.67% | 5.33% | 6175 |

### Notes

- This isolates the return threshold ladder only; the window and N ladder stay fixed.
- `ret_tighter` shifts every breakpoint up by 1 percentage point; `ret_looser` shifts them down by 1 point.

## Exph_v3 Exposure Perturbation

- setting: Fix `adaptive_window=15`, `adaptive_tiers_ret=0.05,0.02,0.00,-0.03,-0.06`, `adaptive_tiers_n=5,5,4,4,3,0`; vary only `adaptive_tiers_exposure`.
- repro: `source activate.sh && python run_single_factor_followups_v1.py --group exph_exposure`
- source report: `v3_multi_setting_diagnostics.md`

| variant | tag | source | adaptive_window | adaptive_tiers_ret | adaptive_tiers_n | adaptive_tiers_exposure | use_score_weighting | switch_score_margin | annual_return | max_drawdown | sharpe_ratio | calmar | year_2018 | year_2022 | year_2024 | avg_actual_exp | avg_cash_ratio | trade_count |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| exp_conservative | SF_EXPH_EXP_CONSERVATIVE | run | 15 | 0.05,0.02,0.00,-0.03,-0.06 | 5,5,4,4,3,0 | 1,1,0.80,0.60,0.40,0 | — | — | 26.14% | -17.53% | 1.47 | 1.49 | -10.07% | 13.30% | 30.66% | 79.34% | 20.66% | 8332 |
| exp_looser_baseline | SEQ15D_LONG_2013_2026_Exph_v3_exp_looser | load | 15 | 0.05,0.02,0.00,-0.03,-0.06 | 5,5,4,4,3,0 | 1,1,0.85,0.65,0.45,0 | — | — | 27.33% | -17.30% | 1.51 | 1.58 | -9.31% | 14.53% | 31.20% | 81.43% | 18.57% | 8387 |
| exp_aggressive | SF_EXPH_EXP_AGGRESSIVE | run | 15 | 0.05,0.02,0.00,-0.03,-0.06 | 5,5,4,4,3,0 | 1,1,0.90,0.70,0.50,0 | — | — | 28.26% | -17.10% | 1.53 | 1.65 | -9.54% | 15.73% | 31.35% | 83.52% | 16.48% | 8339 |

### Notes

- This isolates the exposure ladder only; the N ladder stays fixed at `5,5,4,4,3,0`.
- `exp_conservative` is one notch below the current looser variant; `exp_aggressive` is one notch above it.

## Exph_v3 N Perturbation

- setting: Already rerun under the current engine; fix `adaptive_window=15` and `adaptive_tiers_exposure=1,1,0.8,0.6,0.4,0`; vary only `adaptive_tiers_n`.
- repro: `source activate.sh && python run_single_factor_followups_v1.py --group exph_n`
- source report: `adaptive_15d_v3_tuning_report.md`

| variant | tag | source | adaptive_window | adaptive_tiers_ret | adaptive_tiers_n | adaptive_tiers_exposure | use_score_weighting | switch_score_margin | annual_return | max_drawdown | sharpe_ratio | calmar | year_2018 | year_2022 | year_2024 | avg_actual_exp | avg_cash_ratio | trade_count |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | SEQ15D_LONG_2013_2026_Exph_v3_base | load | 15 | 0.05,0.02,0.00,-0.03,-0.06 | 5,5,4,4,3,0 | 1,1,0.80,0.60,0.40,0 | — | — | 26.14% | -17.53% | 1.47 | 1.49 | -10.07% | 13.30% | 30.66% | 79.34% | 20.66% | 8332 |
| n_up1 | SEQ15D_LONG_2013_2026_Exph_v3_n_up1 | load | 15 | 0.05,0.02,0.00,-0.03,-0.06 | 5,5,5,4,3,0 | 1,1,0.80,0.60,0.40,0 | — | — | 24.96% | -18.26% | 1.42 | 1.37 | -11.68% | 12.98% | 26.62% | 79.38% | 20.62% | 8692 |
| n_down1 | SEQ15D_LONG_2013_2026_Exph_v3_n_down1 | load | 15 | 0.05,0.02,0.00,-0.03,-0.06 | 5,5,4,3,3,0 | 1,1,0.80,0.60,0.40,0 | — | — | 26.35% | -16.72% | 1.47 | 1.58 | -8.99% | 15.49% | 31.67% | 79.33% | 20.67% | 7702 |

### Notes

- This section is here for completeness because it was already rerun under the fixed engine.
- Compare these rows with `adaptive_15d_v3_tuning_report.md` if you need the full diagnostics.

## Current Score Management

- setting: Fix `adaptive_window=15`, `adaptive_tiers_ret=0.05,0.02,0.00,-0.03,-0.06`, `adaptive_tiers_n=5,4,3,2,1,0`; vary only `use_score_weighting` or `switch_score_margin`.
- repro: `source activate.sh && python run_single_factor_followups_v1.py --group current_score`
- source report: `v3_multi_setting_diagnostics.md`

| variant | tag | source | adaptive_window | adaptive_tiers_ret | adaptive_tiers_n | adaptive_tiers_exposure | use_score_weighting | switch_score_margin | annual_return | max_drawdown | sharpe_ratio | calmar | year_2018 | year_2022 | year_2024 | avg_actual_exp | avg_cash_ratio | trade_count |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | SEQ_LONG_2013_2026_Current | load | 15 | 0.05,0.02,0.00,-0.03,-0.06 | 5,4,3,2,1,0 | — | False | 0.0 | 39.81% | -25.44% | 1.57 | 1.56 | 5.26% | 2.81% | 11.32% | 94.50% | 5.50% | 5041 |
| score_weighted | SF_CURRENT_SCORE_WEIGHTED | run | 15 | 0.05,0.02,0.00,-0.03,-0.06 | 5,4,3,2,1,0 | — | True | — | 40.49% | -27.81% | 1.52 | 1.46 | 4.43% | -2.60% | 19.46% | 94.54% | 5.46% | 4819 |
| switch_margin_05 | SF_CURRENT_SWITCH_MARGIN_05 | run | 15 | 0.05,0.02,0.00,-0.03,-0.06 | 5,4,3,2,1,0 | — | — | 0.05 | 38.94% | -25.52% | 1.54 | 1.53 | 2.61% | -1.75% | 12.11% | 94.49% | 5.51% | 4917 |

### Notes

- `score_weighted` changes only the position sizing rule.
- `switch_margin_05` keeps the same equal-weight sizing but requires a new candidate to beat an existing holding by 5% before switching.
