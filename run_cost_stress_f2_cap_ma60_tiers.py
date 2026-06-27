#!/usr/bin/env python3
"""Run optimistic + conservative cost tiers for F2_CAP_MA60.
Baseline (万1+万2) already completed."""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from run_multi_setting_pressure_tests import make_config, load_pit_pool, load_f2_pool
from strategies.etf_loop_strategy import FULL_ETF_POOL_JQ, _jq_to_ts
from strategies.etf_loop_engine import EngineParams, run_and_save

OUT = BASE_DIR / "outputs" / "etf_loop"
COST_TAG_PREFIX = "COSTTIER_FIX1"

TIERS = {
    "original": {"open_cost": 0.00010, "close_cost": 0.00010, "slippage": 0.00010},  # 万1+万1
    "optimistic": {"open_cost": 0.00005, "close_cost": 0.00005, "slippage": 0.00010},  # 万0.5+万1
    "baseline":   {"open_cost": 0.00010, "close_cost": 0.00010, "slippage": 0.00020},  # 万1+万2 (已跑)
    "conservative": {"open_cost": 0.00020, "close_cost": 0.00020, "slippage": 0.00050},  # 万2+万5
}

def pct(x: float) -> str:
    if pd.isna(x): return "NA"
    return f"{x * 100:.2f}%"


def run_tier(label: str, cost: dict, start: str, end: str) -> dict:
    exp_tag = f"{COST_TAG_PREFIX}_F2_CAP_MA60_{label}_{start[:4]}_{end[:4]}"
    pit = load_pit_pool()
    f2 = load_f2_pool()
    orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    f2_orig = sorted(set(f2) | set(orig38))
    params = make_config("F2_CAP_MA60", pit, f2, f2_orig, exp_tag, {}, start, end)
    params = EngineParams(**{**params.__dict__, **cost, "exp_tag": exp_tag})

    eq_path = OUT / f"etf_loop_equity_{exp_tag}_h5_{start.replace('-','')}_{end.replace('-','')}.csv"
    sm_path = OUT / f"etf_loop_summary_{exp_tag}_h5_{start.replace('-','')}_{end.replace('-','')}.csv"

    if eq_path.exists() and sm_path.exists():
        stats = pd.read_csv(sm_path).iloc[0].to_dict()
        print(f"  {exp_tag}: skip existing")
    else:
        equity, trades, audit = run_and_save(params, OUT)
        stats = audit["stats"]
    return stats


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    windows = [
        ("2013-07-01", "2026-06-25"),
        ("2018-01-01", "2026-06-25"),
        ("2026-01-01", "2026-06-25"),
    ]
    results: dict[str, dict] = {}

    for tier_name, cost in TIERS.items():
        for sw, ew in windows:
            wlabel = f"{sw[:4]}_{ew[:4]}"
            key = f"{tier_name}_{wlabel}"
            print(f"→ {tier_name} ({sw[:4]}-{ew[:4]}): 佣金{cost['open_cost']*10000:.1f}bp+滑点{cost['slippage']*10000:.1f}bp")
            results[key] = run_tier(tier_name, cost, sw, ew)

    # Baseline already exists from previous run — read it
    for sw, ew in windows:
        blabel = f"COSTSTRESS_F2_CAP_MA60_full_{sw[:4]}_{ew[:4]}" if sw == "2013-07-01" else f"COSTSTRESS_F2_CAP_MA60_exec_{sw[:4]}_{ew[:4]}"
        sm = OUT / f"etf_loop_summary_{blabel}_h{sw.replace('-','')}_{ew.replace('-','')}.csv"
        if sm.exists():
            results[f"baseline_{sw[:4]}_{ew[:4]}"] = pd.read_csv(sm).iloc[0].to_dict()

    # Print summary
    for sw, ew in windows:
        wlabel = f"{sw[:4]}_{ew[:4]}"
        print(f"\n{'='*70}")
        print(f"  {sw[:4]}-{ew[:4]}")
        print(f"{'='*70}")
        print(f"  {'档位':12s} {'佣金':>6s} {'滑点':>6s} {'单边':>6s} {'年化':>8s} {'Sharpe':>7s} {'DD':>8s} {'最终资产':>14s}")
        print(f"  {'-'*65}")
        for tier_name, cost, orig_key in [
            ("原始(1+1)bp", TIERS["original"], f"original_{wlabel}"),
            ("乐观(0.5+1)", TIERS["optimistic"], f"optimistic_{wlabel}"),
            ("基准(1+2)", TIERS["baseline"], f"baseline_{wlabel}"),
            ("保守(2+5)", TIERS["conservative"], f"conservative_{wlabel}"),
        ]:
            d = results.get(orig_key, {})
            if not d:
                continue
            ann = d.get("annual_return", 0)
            sharpe = d.get("sharpe_ratio", 0)
            dd = d.get("max_drawdown", 0)
            final = d.get("final_value", 0)
            oc = cost["open_cost"] * 10000
            sl = cost["slippage"] * 10000
            oneway = oc + sl
            print(f"  {tier_name:12s} {oc:4.1f}bp {sl:4.1f}bp {oneway:4.1f}bp {pct(ann):>8s} {sharpe:6.2f} {pct(dd):>8s} ¥{final:>13,.0f}")

    print("\nDone.")

if __name__ == "__main__":
    main()
