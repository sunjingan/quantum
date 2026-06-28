#!/usr/bin/env python3
"""Adaptive holdings: bench_ma60, bench_20d_ret, bench_vol, portfolio_dd × score threshold"""
from __future__ import annotations
import sys; from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent; sys.path.insert(0, str(BASE_DIR))
import pandas as pd, numpy as np
from strategies.etf_loop_engine import EngineParams, run_and_save
from run_multi_setting_pressure_tests import make_config, load_pit_pool, load_f2_pool
from strategies.etf_loop_strategy import _jq_to_ts, FULL_ETF_POOL_JQ

OUT = BASE_DIR / "outputs" / "etf_loop"; OUT.mkdir(parents=True, exist_ok=True)
pit = load_pit_pool(); f2 = load_f2_pool()
orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ); f2o = sorted(set(f2) | set(orig38))
COST = {"open_cost": 0.00015, "close_cost": 0.00015, "slippage": 0.0002}

MODES = {
    "Baseline (fixed 5)": {},
    "MA60 (bench/MA60 ratio)": {"use_market_adaptive_holdings": True, "adaptive_mode": "bench_ma60"},
    "20dRet (bench 20d return)": {"use_market_adaptive_holdings": True, "adaptive_mode": "bench_20d_ret"},
    "Vol (bench 20d vol)": {"use_market_adaptive_holdings": True, "adaptive_mode": "bench_vol"},
    "DD (portfolio drawdown)": {"use_market_adaptive_holdings": True, "adaptive_mode": "portfolio_dd"},
}

# Add ScoreW + ScoreThreshold combos
COMBOS = {}
for mode_name, mode_extra in MODES.items():
    COMBOS[mode_name] = mode_extra
    if mode_name != "Baseline (fixed 5)":
        COMBOS[f"{mode_name} + ScoreW"] = {**mode_extra, "use_score_weighting": True}
        COMBOS[f"{mode_name} + ScoreW + Thresh0.1"] = {**mode_extra, "use_score_weighting": True, "adaptive_score_threshold": 0.1}

for period_label, start, end, ts in [
    ("2026_NOWARMUP", "2025-10-01", "2026-06-25", "2026-01-02"),
    ("LONG_2013_2026", "2013-07-01", "2026-06-25", ""),
]:
    print(f"\n{'='*90}")
    print(f"  {period_label}")
    print(f"{'='*90}")
    print(f"  {'Config':<45s} {'Ann':>8s} {'Sharpe':>7s} {'DD':>8s} {'Final':>14s}")
    print(f"  {'-'*85}")
    baseline_ann = None
    for name, extra in COMBOS.items():
        tag = f"ADAPT_{period_label}_{name[:35].replace(' ','_').replace('(','').replace(')','').replace('/','_')}"
        params = make_config("F2_CAP_MA60", pit, f2, f2o, tag, {}, start, end)
        p = EngineParams(**{**params.__dict__, **COST, "start": start, "end": end, "exp_tag": tag, "lookback_days": 25, **extra})
        if ts: p = EngineParams(**{**p.__dict__, "trading_start": ts})
        sm = OUT / f"etf_loop_summary_{tag}_h5_{start.replace('-','')}_{end.replace('-','')}.csv"
        if sm.exists():
            s = pd.read_csv(sm).iloc[0].to_dict()
        else:
            eq, tr, audit = run_and_save(p, OUT); s = audit["stats"]
        ann = s.get('annual_return', 0)
        if name == "Baseline (fixed 5)": baseline_ann = ann
        print(f"  {name:<45s} {ann*100:7.2f}% {s.get('sharpe_ratio',0):6.2f} {s.get('max_drawdown',0)*100:7.2f}% {s.get('final_value',0):>13,.0f}")
    
    if baseline_ann:
        print(f"\n  {'Delta vs Baseline':<45s} {'ΔAnn':>8s} {'ΔDD':>8s}")
        for name, extra in COMBOS.items():
            if name == "Baseline (fixed 5)": continue
            tag = f"ADAPT_{period_label}_{name[:35].replace(' ','_').replace('(','').replace(')','').replace('/','_')}"
            sm = OUT / f"etf_loop_summary_{tag}_h5_{start.replace('-','')}_{end.replace('-','')}.csv"
            if sm.exists():
                s = pd.read_csv(sm).iloc[0].to_dict()
                dann = s.get('annual_return', 0) - baseline_ann
                ddd = s.get('max_drawdown', 0) - s.get('max_drawdown', 0)  # placeholder
                print(f"  {name:<45s} {dann*100:+7.2f}%")
print("\nDone.")
