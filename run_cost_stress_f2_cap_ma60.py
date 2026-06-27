#!/usr/bin/env python3
"""
Run F2_CAP_MA60 cost stress test:
  Commission: 万1 (0.01%) per side
  Slippage:   万2 (0.02%) per side
  Total:      单边 0.03%, 双边 0.06%

Windows: 2013-2026 (full) and 2018-2026 (comparable with EXEC tests)
"""
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
START_FULL = "2013-07-01"
END_FULL = "2026-06-25"
START_EXEC = "2018-01-01"
END_EXEC = "2026-06-25"

# User-specified cost parameters
COST = {
    "open_cost":  0.0001,   # 佣金 万1 = 0.01%
    "close_cost": 0.0001,   # 佣金 万1 = 0.01%
    "slippage":   0.0002,   # 滑点 万2 = 0.02%
}


def pct(x: float) -> str:
    if pd.isna(x): return "NA"
    return f"{x * 100:.2f}%"


def run_window(label: str, start: str, end: str) -> dict:
    exp_tag = f"COSTSTRESS_F2_CAP_MA60_{label}"
    pit = load_pit_pool()
    f2 = load_f2_pool()
    orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    f2_orig = sorted(set(f2) | set(orig38))

    params = make_config("F2_CAP_MA60", pit, f2, f2_orig, exp_tag, {}, start, end)
    params = EngineParams(**{**params.__dict__, **COST, "exp_tag": exp_tag})

    eq_path = OUT / f"etf_loop_equity_{exp_tag}_h5_{start.replace('-','')}_{end.replace('-','')}.csv"
    sm_path = OUT / f"etf_loop_summary_{exp_tag}_h5_{start.replace('-','')}_{end.replace('-','')}.csv"

    if eq_path.exists() and sm_path.exists():
        stats = pd.read_csv(sm_path).iloc[0].to_dict()
        print(f"{exp_tag}: skip existing")
    else:
        equity, trades, audit = run_and_save(params, OUT)
        stats = audit["stats"]

    return stats


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("=== F2_CAP_MA60 Cost Stress Test ===")
    print(f"  佣金: {COST['open_cost']*10000:.0f}bp 买 / {COST['close_cost']*10000:.0f}bp 卖")
    print(f"  滑点: {COST['slippage']*10000:.0f}bp 单边")
    print(f"  单边合计: {(COST['open_cost']+COST['slippage'])*10000:.0f}bp")
    print(f"  双边合计: {(COST['open_cost']+COST['close_cost']+2*COST['slippage'])*10000:.0f}bp")
    print()

    # 2013-2026 full window
    print("→ Running 2013-2026 full window...")
    s_full = run_window("full_2013_2026", START_FULL, END_FULL)

    # 2018-2026 (comparable with execution stress tests)
    print("→ Running 2018-2026 window...")
    s_exec = run_window("exec_2018_2026", START_EXEC, END_EXEC)

    # Baseline comparison (existing ADJCORE_F2_CAP_MA60_OPEN_D1)
    baseline_full = OUT / "etf_loop_summary_ADJCORE_F2_CAP_MA60_OPEN_D1_h5_20130701_20260625.csv"
    baseline_exec = OUT / "etf_loop_summary_EXEC_F2_CAP_MA60_OPEN_D1_h5_20180101_20260625.csv"

    b_full = pd.read_csv(baseline_full).iloc[0].to_dict() if baseline_full.exists() else {}
    b_exec = pd.read_csv(baseline_exec).iloc[0].to_dict() if baseline_exec.exists() else {}

    # Print comparison
    print()
    print("=" * 70)
    print("  2013-2026 全区间")
    print("=" * 70)
    for label, d, baseline in [("Baseline (滑点1bp)", b_full, None),
                                 ("Cost Stress (滑点2bp)", s_full, b_full)]:
        ann = d.get("annual_return", 0)
        sharpe = d.get("sharpe_ratio", 0)
        dd = d.get("max_drawdown", 0)
        final = d.get("final_value", 0)
        delta = ""
        if baseline:
            da = ann - baseline.get("annual_return", 0)
            dd_ = dd - baseline.get("max_drawdown", 0)
            delta = f"  Δann={pct(da)}  Δdd={pct(dd_)}"
        print(f"  {label}: ann={pct(ann)}  sharpe={sharpe:.2f}  dd={pct(dd)}  final=¥{final:,.0f}{delta}")

    print()
    print("=" * 70)
    print("  2018-2026 (可对比 EXEC)")
    print("=" * 70)
    for label, d, baseline in [("Baseline EXEC (滑点1bp)", b_exec, None),
                                 ("Cost Stress (滑点2bp)", s_exec, b_exec)]:
        ann = d.get("annual_return", 0)
        sharpe = d.get("sharpe_ratio", 0)
        dd = d.get("max_drawdown", 0)
        final = d.get("final_value", 0)
        delta = ""
        if baseline:
            da = ann - baseline.get("annual_return", 0)
            dd_ = dd - baseline.get("max_drawdown", 0)
            delta = f"  Δann={pct(da)}  Δdd={pct(dd_)}"
        print(f"  {label}: ann={pct(ann)}  sharpe={sharpe:.2f}  dd={pct(dd)}  final=¥{final:,.0f}{delta}")

    # Also print EXEC adverse 20bp for reference
    adverse = OUT / "etf_loop_summary_EXEC_F2_CAP_MA60_OPEN_D1_ADVERSE_20BP_h5_20180101_20260625.csv"
    if adverse.exists():
        a = pd.read_csv(adverse).iloc[0].to_dict()
        print()
        print("  --- Reference ---")
        print(f"  Adverse 20bp基线: ann={pct(a.get('annual_return',0))}  sharpe={a.get('sharpe_ratio',0):.2f}  dd={pct(a.get('max_drawdown',0))}")

    print()
    print("Done.")

if __name__ == "__main__":
    main()
