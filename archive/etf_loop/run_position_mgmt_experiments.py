#!/usr/bin/env python3
"""Position management experiments: score-weighted, Kelly-vol, dynamic holdings."""
from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = PROJECT_ROOT
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from strategies.etf_loop_engine import EngineParams, run_and_save
from run_multi_setting_pressure_tests import make_config, load_pit_pool, load_f2_pool
from strategies.etf_loop_strategy import _jq_to_ts, FULL_ETF_POOL_JQ

OUT = BASE_DIR / "outputs" / "etf_loop"
OUT.mkdir(parents=True, exist_ok=True)
REPORT_DIR = OUT / "F2_CAP_MA60_deep_dive"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
TAG_PREFIX = "POSMGT_FIX1"

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
    rows = []
    for var_name, extra in VARIANTS.items():
        tag = f"{TAG_PREFIX}_{label}_{var_name[:20].replace(' ','_').replace('(','').replace(')','').replace('+','_').replace('-','')}"
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
        rows.append({
            "period": label,
            "variant": var_name,
            "tag": tag,
            "start": start,
            "end": end,
            "trading_start": trading_start,
            **s,
        })
    return results, rows

# ── Run both periods ──
all_rows = []
for period_label, start, end, ts in [
    ("LONG_2013_2026", "2013-07-01", "2026-06-25", ""),
    ("2026_NOWARMUP", "2025-10-01", "2026-06-25", "2026-01-02"),
]:
    print(f"\n{'='*80}")
    print(f"  {period_label}")
    print(f"{'='*80}")
    results, rows = run_period(period_label, start, end, ts)
    all_rows.extend(rows)
    
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

df = pd.DataFrame(all_rows)
csv_path = REPORT_DIR / "position_management_fix1.csv"
df.to_csv(csv_path, index=False)
md_path = REPORT_DIR / "position_management_fix1.md"
lines = [
    "# Position Management FIX1",
    "",
    "- engine: dynamic pool caps are re-applied after score/vol weighting",
    "- friend_mode: not used",
    "",
    "| period | variant | ann | sharpe | dd | final |",
    "|---|---|---:|---:|---:|---:|",
]
for _, r in df.sort_values(["period", "annual_return"], ascending=[True, False]).iterrows():
    lines.append(
        f"| {r['period']} | {r['variant']} | {r['annual_return']*100:.2f}% | "
        f"{r['sharpe_ratio']:.2f} | {r['max_drawdown']*100:.2f}% | {r['final_value']:.0f} |"
    )
md_path.write_text("\n".join(lines), encoding="utf-8")
print(f"\nSaved: {csv_path}")
print(f"Saved: {md_path}")
print("\nDone.")
