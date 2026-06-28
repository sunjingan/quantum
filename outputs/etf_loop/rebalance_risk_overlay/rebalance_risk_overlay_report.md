# Fixed Rebalance And Risk Overlay Experiment

## Reproduce

```bash
source activate.sh
python runs/etf_loop/run_rebalance_risk_overlay_experiments.py
```

## Common Setting

- base: `F2_CAP_MA60` = F2_v3 static core pool + capped PIT dynamic supplement + MA60 mean-reversion overheat penalty.
- sizing: `use_score_weighting=True`; this is `WideA + score weighting`, not the unweighted `WideA` candidate in `docs/etf_loop_project_history.md`.
- important: `BASE_DAILY` in this report is only the local control for this overlay experiment. It should not be read as the project candidate `WideA`.
- adaptive holdings: `adaptive_mode=bench_20d_ret`, `adaptive_window=15`, `adaptive_tiers_ret=0.06,0.03,0.00,-0.02,-0.05,-0.08`, `adaptive_tiers_n=5,5,4,3,2,1,0`, `adaptive_tiers_exposure=1,1,1,1,1,1,0`.
- cost: `open_cost=0.00015`, `close_cost=0.00015`, `slippage=0.00020`; effective single-side cost is 3.5bp before liquidity/participation penalties.
- execution: signal at T close, trade at next trading day open; no signal-day close fallback.
- overlay risk score: `(20d return std + 5d return std) / 2`; amount CV: `20d amount std / 20d amount mean`, both computed only through signal date.
- risk overlay setting when enabled: `risk_ret_std_threshold=0.035`, `risk_amount_cv_threshold=1.0`, `risk_exposure_multiplier=0.5`, `risk_check_on_non_rebalance=True`.

## Variants

| variant | isolated change |
|---|---|
| BASE_DAILY | daily rebalance, risk overlay off |
| REB10 | only `rebalance_interval=10` |
| RISK_HALF | only risk overlay on |
| REB10_RISK_HALF | 10-day rebalance plus risk overlay; interaction test, not a single-factor result |

## Long Window Results

| variant | ann | sharpe | dd | total | final | trades | risk sells | risk buys |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BASE_DAILY | 37.49% | 1.46 | -23.19% | 7089.02% | 35945120 | 5587 | 0 | 0 |
| REB10 | 20.60% | 0.79 | -38.64% | 761.00% | 4305006 | 1417 | 0 | 0 |
| RISK_HALF | 35.27% | 1.43 | -22.80% | 5525.29% | 28126474 | 6182 | 166 | 383 |
| REB10_RISK_HALF | 21.70% | 0.98 | -28.52% | 1013.64% | 5568180 | 1579 | 112 | 58 |

## 2026 Nowarmup Results

| variant | full ann | active ann | active total | sharpe | active sharpe | dd | active dd | trades | risk sells | risk buys |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BASE_DAILY | 115.99% | 178.77% | 107.47% | 3.25 | 4.07 | -17.42% | -17.42% | 281 | 0 | 0 |
| REB10 | 14.57% | 22.46% | 7.29% | 0.51 | 0.64 | -19.91% | -19.91% | 69 | 0 | 0 |
| RISK_HALF | 81.11% | 125.01% | 65.81% | 2.52 | 3.15 | -18.21% | -18.21% | 323 | 18 | 50 |
| REB10_RISK_HALF | 18.22% | 28.08% | 11.39% | 0.90 | 1.12 | -14.01% | -14.01% | 79 | 10 | 5 |

## Interpretation Guide

- `REB10` tests whether daily rank churn is hurting results. It should be compared only with `BASE_DAILY`.
- `RISK_HALF` tests the non-rebalance risk reduction idea. It should be compared only with `BASE_DAILY`.
- `REB10_RISK_HALF` is an interaction case; if it works, follow-up tests should tune thresholds and interval separately.
