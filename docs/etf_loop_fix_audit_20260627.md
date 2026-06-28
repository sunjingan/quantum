# ETF Loop Fix Audit 2026-06-27

## Fixes Applied

- Disabled `friend_mode` in the daily-bar engine. It requires intraday signal/fill data; using a future/open price inside same-price execution is not a tradeable backtest.
- Re-applied `dynamic_max_total_weight` after `use_vol_weighting` and `use_score_weighting`, so custom sizing can no longer silently break the capped dynamic-pool budget.
- Moved Wyckoff score adjustments after the base momentum score is computed. Enabling Wyckoff filters no longer references `score` before assignment or gets overwritten by later score calculation.
- Fixed cost-stress output path checks from `_h...` to `_h5...`, avoiding unnecessary reruns or stale file detection.
- Versioned cost-tier reruns with `COSTTIER_FIX1_*` and regenerated all four cost tiers across 2013-2026, 2018-2026, and 2026 standalone.
- Updated `analysis/etf_loop/analyze_2026_comprehensive.py` to read only 2026 standalone `COSTTIER_FIX1` results for its 2026 cost table.
- Updated `runs/etf_loop/run_2026_nowarmup.py` to print both full-record metrics and 2026 active-window metrics.
- Updated `archive/etf_loop/replicate_friend_baseline.py` to skip unsafe `friend_mode` cases instead of reading/generating contaminated outputs.

## Outputs Regenerated

- `outputs/etf_loop/F2_CAP_MA60_deep_dive/2026_comprehensive_report.md`
- `outputs/etf_loop/F2_CAP_MA60_deep_dive/2026_nowarmup_report.md` core metrics section
- `outputs/etf_loop/etf_loop_summary_COSTTIER_FIX1_F2_CAP_MA60_*`
- `outputs/etf_loop/etf_loop_equity_COSTTIER_FIX1_F2_CAP_MA60_*`
- `outputs/etf_loop/etf_loop_targets_COSTTIER_FIX1_F2_CAP_MA60_*`

## Important Invalidated Or Limited Results

- Any `FR_2_FriendMode_*` or `FR_3_FriendMode_*` outputs are deprecated. They should not be used as evidence until intraday 9:50 signal data and realistic intraday execution are implemented.
- Old `COSTTIER_F2_CAP_MA60_*` outputs are superseded by `COSTTIER_FIX1_F2_CAP_MA60_*`.
- `2026_nowarmup_report.md` sections 3-4 still contain older derived attribution/crash tables. Use only the updated core/monthly metrics until those attribution tables are regenerated under FIX1.
- `annual_return` in engine summaries is arithmetic annualization (`mean(daily_return) * 252`), not CAGR. For partial-year windows, also inspect total return and active-window CAGR-like annualization.

## Verification Commands

```bash
source activate.sh
python -m py_compile strategies/etf_loop_engine.py strategies/etf_loop_strategy.py runs/etf_loop/run_2026_nowarmup.py analysis/etf_loop/analyze_2026_comprehensive.py archive/etf_loop/replicate_friend_baseline.py runs/etf_loop/run_cost_stress_f2_cap_ma60.py runs/etf_loop/run_cost_stress_f2_cap_ma60_tiers.py archive/etf_loop/run_2026_static_comparison.py
python runs/etf_loop/run_cost_stress_f2_cap_ma60_tiers.py
python analysis/etf_loop/analyze_2026_comprehensive.py
python runs/etf_loop/run_2026_nowarmup.py
python archive/etf_loop/replicate_friend_baseline.py
```

## Current Interpretation

- `F2_CAP_MA60_SW05` is not static-only. It uses F2 as a static core plus capped PIT dynamic supplement.
- The dynamic supplement remains capped after FIX1 even if custom weighting is enabled.
- The safest current production-study branch remains the non-`friend_mode` daily execution model: signal at close, trade on the next available execution date, no signal-date fallback.
