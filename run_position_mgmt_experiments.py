#!/usr/bin/env python3
"""Position management experiments: score-weighted, Kelly-vol, dynamic holdings."""
from __future__ import annotations
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import numpy as np
import pandas as pd
from strategies.etf_loop_engine import EngineParams, run_and_save
from run_multi_setting_pressure_tests import make_config, load_pit_pool, load_f2_pool
from strategies.etf_loop_strategy import _jq_to_ts, FULL_ETF_POOL_JQ

OUT = BASE_DIR / "outputs" / "etf_loop"
OUT.mkdir(parents=True, exist_ok=True)

pit = load_pit_pool()
f2 = load_f2_pool()
orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
f2_orig = sorted(set(f2) | set(orig38))

VARIANTS = {
    "Baseline (equal-weight 5)": {},
    "Score-weighted": {"use_score_weighting": True},
    "Score+Vol (Kelly-style)": {"use_score_weighting": True, "use_vol_weighting": True},
    "Dynamic holdings (3-8)": {"use_dynamic_holdings": True},
    "DynHold + ScoreW": {"use_dynamic_holdings": True, "use_score_weighting": True},
}

def run_period(label, start, end, trading_start=""):
    results = {}
    for var_name, extra in VARIANTS.items():
        tag = f"POSMGT_{label}_{var_name[:20].replace(' ','_').replace('(','').replace(')','').replace('+','_').replace('-','')}"
        base_extra = {"start": start, "end": end, "lookback_days": 25}
        if trading_start:
            base_extra["trading_start"] = trading_start
        params = make_config("F2_CAP_MA60", pit, f2, f2_orig, tag, extra, start, end)
        params = EngineParams(**{
            **params.__dict__, **base_extra, **extra,
            "exp_tag": tag, "start": start, "end": end, "lookback_days": 25,
        })
        if trading_start:
            params = EngineParams(**{**params.__dict__, "trading_start": trading_start})
        
        sm = OUT / f"etf_loop_summary_{tag}_h5_{start.replace('-','')}_{end.replace('-','')}.csv"
        if sm.exists():
            s = pd.read_csv(sm).iloc[0].to_dict()
        else:
            eq, tr, audit = run_and_save(params, OUT)
            s = audit["stats"]
        results[var_name] = s
    return results

# ── Run both periods ──
for period_label, start, end, ts in [
    ("LONG_2013_2026", "2013-07-01", "2026-06-25", ""),
    ("2026_NOWARMUP", "2025-10-01", "2026-06-25", "2026-01-02"),
]:
    print(f"\n{'='*80}")
    print(f"  {period_label}")
    print(f"{'='*80}")
    results = run_period(period_label, start, end, ts)
    
    print(f"  {'Variant':<35s} {'Ann':>8s} {'Sharpe':>7s} {'DD':>8s} {'Final':>14s}")
    print(f"  {'-'*75}")
    base_ann = results.get("Baseline (equal-weight 5)", {}).get("annual_return", 0)
    for var_name in VARIANTS:
        s = results.get(var_name, {})
        if not s: continue
        ann = s.get('annual_return', 0)
        print(f"  {var_name:<35s} {ann*100:7.2f}% {s.get('sharpe_ratio',0):6.2f} {s.get('max_drawdown',0)*100:7.2f}% {s.get('final_value',0):>13,.0f}")
    
    # Delta
    print(f"\n  {'Delta vs Baseline':<35s} {'ΔAnn':>8s} {'ΔDD':>8s}")
    print(f"  {'-'*55}")
    for var_name in [v for v in VARIANTS if v != "Baseline (equal-weight 5)"]:
        s = results.get(var_name, {})
        if not s: continue
        dann = s.get('annual_return', 0) - base_ann
        ddd = s.get('max_drawdown', 0) - results["Baseline (equal-weight 5)"].get('max_drawdown', 0)
        print(f"  {var_name:<35s} {dann*100:+7.2f}% {ddd*100:+7.2f}%")

print("\nDone.")
