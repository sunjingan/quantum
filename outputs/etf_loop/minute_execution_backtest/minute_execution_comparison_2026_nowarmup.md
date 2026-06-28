# Minute Execution Comparison - 2026 Nowarmup

- signal source: daily ETF Loop candidate signals, unchanged.
- execution overlay: local 1-minute ETF data.
- window: `2025-10-01` warmup, trading `2026-01-02` to `2026-06-25`.
- constraints: minute turnover, max participation 10%, limit-up buy block, limit-down sell block, missing/no-turnover rejection.
- default execution assumption for practical review: `T+1 09:35-10:30 VWAP`, roundtrip cost `7bp`.

## Reproduce

```bash
source activate.sh
python runs/etf_loop/run_minute_execution_backtest.py --setting F2_CAP_MA60 --start 2025-10-01 --trading-start 2026-01-02 --end 2026-06-25
python runs/etf_loop/run_minute_execution_backtest.py --setting WideA --start 2025-10-01 --trading-start 2026-01-02 --end 2026-06-25
python runs/etf_loop/run_minute_execution_backtest.py --setting Exph_v3_exp_looser --start 2025-10-01 --trading-start 2026-01-02 --end 2026-06-25
```

## Default VWAP 7bp Capacity Curve

| setting | initial_cash | annual_return | sharpe | max_drawdown | failed_rate | capacity_limited_rate | no_minute_data_rate | no_turnover_rate | limit_block_rate | avg_slippage_bp | avg_participation | avg_abs_exposure_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F2_CAP_MA60 | 1000000 | 74.75% | 2.68 | -12.70% | 29.64% | 0.00% | 3.17% | 13.81% | 0.14% | 2.06 | 0.05% | 7.71% |
| F2_CAP_MA60 | 3000000 | 73.76% | 2.64 | -12.75% | 29.68% | 0.00% | 3.17% | 13.83% | 0.14% | 2.58 | 0.16% | 7.67% |
| F2_CAP_MA60 | 5000000 | 72.80% | 2.61 | -12.81% | 28.70% | 0.14% | 3.19% | 13.91% | 0.14% | 3.05 | 0.27% | 7.66% |
| F2_CAP_MA60 | 10000000 | 71.84% | 2.57 | -12.91% | 27.55% | 0.15% | 3.21% | 13.99% | 0.15% | 3.98 | 0.52% | 7.70% |
| F2_CAP_MA60 | 30000000 | 64.68% | 2.32 | -13.25% | 26.74% | 3.70% | 3.13% | 15.08% | 0.14% | 6.57 | 1.39% | 7.95% |
| WideA | 1000000 | 76.79% | 2.44 | -13.25% | 26.89% | 0.00% | 2.65% | 16.48% | 0.19% | 2.30 | 0.08% | 9.11% |
| WideA | 3000000 | 75.36% | 2.39 | -13.28% | 26.89% | 0.19% | 2.65% | 16.48% | 0.19% | 3.06 | 0.24% | 9.09% |
| WideA | 5000000 | 76.88% | 2.44 | -13.33% | 27.08% | 0.38% | 2.65% | 16.48% | 0.19% | 3.51 | 0.39% | 9.19% |
| WideA | 10000000 | 76.60% | 2.42 | -13.42% | 26.83% | 1.69% | 2.63% | 16.51% | 0.19% | 4.67 | 0.74% | 9.36% |
| WideA | 30000000 | 72.73% | 2.29 | -13.69% | 25.70% | 6.52% | 2.61% | 16.39% | 0.19% | 7.42 | 1.67% | 10.17% |
| Exph_v3_exp_looser | 1000000 | 84.54% | 3.35 | -10.34% | 21.21% | 0.00% | 2.36% | 14.65% | 0.17% | 2.06 | 0.05% | 13.04% |
| Exph_v3_exp_looser | 3000000 | 83.65% | 3.31 | -10.36% | 20.17% | 0.00% | 2.37% | 14.92% | 0.17% | 2.48 | 0.16% | 13.07% |
| Exph_v3_exp_looser | 5000000 | 82.75% | 3.27 | -10.39% | 19.43% | 0.00% | 2.36% | 14.86% | 0.17% | 2.93 | 0.27% | 13.08% |
| Exph_v3_exp_looser | 10000000 | 82.42% | 3.25 | -10.44% | 18.92% | 0.17% | 2.36% | 14.86% | 0.17% | 3.78 | 0.52% | 13.04% |
| Exph_v3_exp_looser | 30000000 | 78.87% | 3.10 | -10.67% | 18.49% | 2.86% | 2.35% | 14.79% | 0.17% | 6.31 | 1.41% | 13.10% |

## Execution Mode Sensitivity - 1M capital, 7bp roundtrip

| setting | execution_mode | annual_return | sharpe | max_drawdown | failed_rate | avg_abs_exposure_gap |
| --- | --- | --- | --- | --- | --- | --- |
| F2_CAP_MA60 | open_0935 | 60.69% | 2.17 | -13.91% | 28.75% | 8.23% |
| F2_CAP_MA60 | vwap_0935_1030 | 74.75% | 2.68 | -12.70% | 29.64% | 7.71% |
| F2_CAP_MA60 | twap_0935_1030 | 75.22% | 2.70 | -12.68% | 29.52% | 7.69% |
| F2_CAP_MA60 | tail_vwap_1430_1455 | 126.97% | 3.79 | -14.18% | 12.39% | 3.70% |
| F2_CAP_MA60 | t2_open_0935 | 63.70% | 2.15 | -10.43% | 26.52% | 7.47% |
| WideA | open_0935 | 77.64% | 2.42 | -14.30% | 25.37% | 10.55% |
| WideA | vwap_0935_1030 | 76.79% | 2.44 | -13.25% | 26.89% | 9.11% |
| WideA | twap_0935_1030 | 75.59% | 2.40 | -13.18% | 26.86% | 9.10% |
| WideA | tail_vwap_1430_1455 | 134.93% | 3.37 | -15.87% | 6.81% | 3.62% |
| WideA | t2_open_0935 | 51.05% | 1.58 | -14.48% | 23.23% | 10.52% |
| Exph_v3_exp_looser | open_0935 | 77.62% | 3.05 | -11.24% | 20.53% | 13.04% |
| Exph_v3_exp_looser | vwap_0935_1030 | 84.54% | 3.35 | -10.34% | 21.21% | 13.04% |
| Exph_v3_exp_looser | twap_0935_1030 | 84.10% | 3.33 | -10.28% | 21.53% | 13.07% |
| Exph_v3_exp_looser | tail_vwap_1430_1455 | 119.61% | 4.08 | -10.93% | 7.78% | 3.32% |
| Exph_v3_exp_looser | t2_open_0935 | 72.45% | 2.71 | -8.54% | 20.53% | 13.45% |

## Cost Sensitivity - 1M capital, T+1 09:35-10:30 VWAP

| setting | roundtrip_cost_bp | annual_return | sharpe | max_drawdown |
| --- | --- | --- | --- | --- |
| F2_CAP_MA60 | 5 | 75.85% | 2.72 | -12.64% |
| F2_CAP_MA60 | 7 | 74.75% | 2.68 | -12.70% |
| F2_CAP_MA60 | 10 | 73.16% | 2.62 | -12.80% |
| F2_CAP_MA60 | 15 | 70.42% | 2.52 | -12.96% |
| F2_CAP_MA60 | 20 | 67.57% | 2.42 | -13.12% |
| WideA | 5 | 77.92% | 2.47 | -13.18% |
| WideA | 7 | 76.79% | 2.44 | -13.25% |
| WideA | 10 | 75.09% | 2.38 | -13.34% |
| WideA | 15 | 72.14% | 2.29 | -13.49% |
| WideA | 20 | 69.04% | 2.19 | -13.65% |
| Exph_v3_exp_looser | 5 | 85.46% | 3.38 | -10.29% |
| Exph_v3_exp_looser | 7 | 84.54% | 3.35 | -10.34% |
| Exph_v3_exp_looser | 10 | 83.00% | 3.28 | -10.42% |
| Exph_v3_exp_looser | 15 | 80.38% | 3.17 | -10.55% |
| Exph_v3_exp_looser | 20 | 77.76% | 3.07 | -10.67% |

## Initial Findings

- Under the default `T+1 09:35-10:30 VWAP / 7bp roundtrip` assumption, all three candidates remain profitable in the 2026 nowarmup window after minute execution constraints.
- `Exph_v3_exp_looser` has the best default minute-execution profile in this short 2026 window: higher Sharpe, smaller drawdown, and lower failed-rate than `F2_CAP_MA60` and `WideA`.
- Capacity pressure is modest through 10M in this window. At 30M, capacity-limited orders begin to appear: `F2_CAP_MA60` 3.70%, `WideA` 6.52%, `Exph_v3_exp_looser` 2.86%.
- Missing or zero-turnover minute windows are currently a larger issue than pure participation-rate capacity. This must be audited by ETF/date before drawing live-capacity conclusions.
- Tail VWAP looks very strong in this 2026 sample, but it is an execution timing sensitivity result, not a signal improvement. Treat it as evidence that same-day intraday path matters, not as a default execution rule without further out-of-sample checks.
- The average absolute exposure gap is non-trivial, especially for `Exph_v3_exp_looser`; this is partly expected because it intentionally targets lower exposure, but the gap still needs per-day review before paper trading.