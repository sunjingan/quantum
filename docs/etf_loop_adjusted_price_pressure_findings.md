# ETF Loop Adjusted-Price Pressure Findings

Date: 2026-06-26

## What Changed

- Fixed signal/valuation price pollution from raw Tushare `fund_daily.close` adjustment jumps.
- `ETFDailyStore` now builds continuous adjusted close from `pct_chg`, and adjusts open/high/low/VWAP onto the same price scale.
- Signal ranking, MA/ATR/stop logic, execution prices, and portfolio valuation now use the same continuous adjusted price system.
- Execution still requires an exact future execution-date price. There is no fallback to signal-date close.
- Added `EngineParams.execution_price_mode`: `open`, `vwap`, `close`.
- Added `EngineParams.execution_delay_days`: `1` means next trading day, `2` means two trading days later.
- Added `EngineParams.switch_score_margin`: keep existing holding unless the replacement score is sufficiently better.
- Fixed a defense-ordering bug: portfolio defense now clears targets after all score penalties and target selection, so mean-reversion re-selection cannot override defense.

## Reproduction

Run from repo root:

```bash
source activate.sh
python run_multi_setting_pressure_tests.py
python run_adjusted_core_setting_comparison.py
```

Outputs:

- `outputs/etf_loop/multi_setting_pressure_manifest.csv`
- `outputs/etf_loop/multi_setting_pressure_report.md`
- `outputs/etf_loop/adjusted_core_setting_comparison_manifest.csv`
- `outputs/etf_loop/adjusted_core_setting_comparison_report.md`

## Core 13-Year Results

Window: `2013-07-01` to `2026-06-25`.

| config | ann | sharpe | max_dd | alpha_vs_hs300 | trades | dynamic_buys |
|---|---:|---:|---:|---:|---:|---:|
| F2O_SM025 | 36.57% | 1.50 | -23.10% | 32.38% | 6502 | 341 |
| F2O_SM025_SW05 | 36.07% | 1.48 | -23.60% | 31.88% | 6305 | 331 |
| F2_CAP_MA60_SW05 | 31.68% | 1.59 | -18.76% | 27.49% | 6617 | 487 |
| F2_CAP_MA60 | 31.53% | 1.59 | -18.34% | 27.35% | 6744 | 515 |
| F2_CAP_BASE | 30.62% | 1.52 | -18.23% | 26.43% | 6631 | 520 |
| F2_STATIC_MA60 | 30.52% | 1.58 | -18.35% | 26.33% | 6047 | 0 |
| F2_STATIC_BASE | 29.99% | 1.54 | -18.36% | 25.80% | 5944 | 0 |
| F2O_CAP_BASE | 27.55% | 1.35 | -20.90% | 23.37% | 7190 | 370 |
| G2_PIT_PURE | 13.00% | 0.80 | -20.15% | 8.81% | 4139 | 0 |

## Multi-Setting Pressure Results

Window: `2018-01-01` to `2026-06-25`.

Base `open_d1`:

| config | ann | sharpe | max_dd | trades | dynamic_buys |
|---|---:|---:|---:|---:|---:|
| F2O_SM025 | 37.85% | 1.44 | -23.09% | 4722 | 306 |
| F2O_SM025_SW05 | 37.23% | 1.43 | -23.48% | 4584 | 301 |
| F2_CAP_MA60_SW05 | 37.12% | 1.66 | -18.79% | 5112 | 458 |
| F2_CAP_MA60 | 36.66% | 1.64 | -18.40% | 5191 | 476 |
| F2_CAP_BASE | 35.33% | 1.55 | -18.24% | 5097 | 478 |
| F2_STATIC_MA60 | 35.13% | 1.63 | -17.03% | 4492 | 0 |
| F2_STATIC_BASE | 34.32% | 1.57 | -17.00% | 4373 | 0 |
| F2O_CAP_BASE | 32.79% | 1.43 | -20.89% | 5258 | 349 |
| G2_PIT_PURE | 19.97% | 0.99 | -20.16% | 4161 | 0 |

Adverse cost: `open_d1_adverse_20bp`.

| config | ann | ann_delta | sharpe | max_dd |
|---|---:|---:|---:|---:|
| F2_CAP_MA60_SW05 | 17.39% | -19.73% | 0.78 | -28.76% |
| F2_STATIC_MA60 | 16.36% | -18.77% | 0.76 | -33.89% |
| F2_CAP_MA60 | 16.22% | -20.44% | 0.73 | -32.74% |
| F2_STATIC_BASE | 15.89% | -18.43% | 0.72 | -35.00% |
| F2_CAP_BASE | 15.28% | -20.04% | 0.67 | -34.15% |
| F2O_SM025_SW05 | 15.27% | -21.95% | 0.58 | -51.48% |
| F2O_SM025 | 15.14% | -22.71% | 0.58 | -53.61% |
| F2O_CAP_BASE | 10.62% | -22.17% | 0.46 | -45.07% |
| G2_PIT_PURE | 2.40% | -17.57% | 0.12 | -49.83% |

## Conclusions

- Pure dynamic PIT pool is not suitable as the main strategy. It has much lower long-horizon return and Sharpe, and under adverse 20 bp slippage it nearly collapses to cash-like return with about -50% drawdown.
- Dynamic pool as a capped supplement is acceptable, but not a clear free lunch. `F2_CAP_MA60` improves annual return versus static F2, but adds more trades and dynamic buys.
- `F2_CAP_MA60_SW05` is currently the most balanced production candidate. It slightly improves return and Sharpe versus `F2_CAP_MA60`, reduces trades and dynamic buys, and has the best adverse-cost drawdown among dynamic settings.
- `F2O_SM025` has the highest 13-year annual return, but its drawdown and cost sensitivity are worse. Under adverse 20 bp slippage, max drawdown reaches about -54%, which is too fragile for a first live candidate.
- The dynamic-pool degradation is mostly a cost/churn and fragility issue, not simply “dynamic is bad”. When constrained as a capped supplement and combined with score-gap no-switch, it remains useful. When treated as a larger expanded opportunity set, it can pick more aggressive themes and become much more sensitive to slippage and regime reversal.
- For paper trading, prefer `F2_CAP_MA60_SW05` over `F2O_SM025` unless the objective is explicitly maximum return with materially higher drawdown tolerance.

## Remaining Work

- Run walk-forward selection last, using only past windows for parameter choice.
- Re-run attribution and trade-point visualizations on the adjusted-price result tags.
- Add live/paper reconciliation once real paper logs exist.
