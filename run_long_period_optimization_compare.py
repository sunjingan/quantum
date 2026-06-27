#!/usr/bin/env python3
"""Long-period optimization comparison: 2013-2026 across 3 pool configs × 4 variants."""
from __future__ import annotations
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import pandas as pd
from run_multi_setting_pressure_tests import make_config, load_pit_pool, load_f2_pool
from strategies.etf_loop_strategy import FULL_ETF_POOL_JQ, _jq_to_ts
from strategies.etf_loop_engine import EngineParams, run_and_save

OUT = BASE_DIR / "outputs" / "etf_loop"
OUT.mkdir(parents=True, exist_ok=True)

START = "2013-07-01"
END = "2026-06-25"

pit = load_pit_pool()
f2_pool = load_f2_pool()
orig38_pool = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
f2_orig = sorted(set(f2_pool) | set(orig38_pool))

# ── Configuration definitions ──
# (name, pool_type, override_params)
# pool_type: "F2_CAP_MA60", "F2_STATIC", "ORIG38_STATIC"
POOL_CONFIGS = {
    "F2_CAP_MA60": {
        "pit": pit, "f2": f2_pool, "f2_orig": f2_orig,
        "base_extra": {},
    },
    "F2_STATIC": {
        "pit": None, "f2": f2_pool, "f2_orig": f2_orig,
        "base_extra": {"etf_pool_ts": f2_pool, "use_dynamic_pool": False,
                       "mr_ma_period": 0, "mr_penalty": 0},
    },
    "ORIG38_STATIC": {
        "pit": None, "f2": f2_pool, "f2_orig": f2_orig,
        "base_extra": {"etf_pool_ts": orig38_pool, "use_dynamic_pool": False,
                       "mr_ma_period": 0, "mr_penalty": 0},
    },
}

VARIANTS = {
    "Baseline": {},
    "Premium(soft)": {"use_premium_penalty": True, "premium_penalty": 0.8, "premium_threshold": 0.08},
    "Premium(soft)+VolW": {"use_premium_penalty": True, "premium_penalty": 0.8, "premium_threshold": 0.08,
                           "use_vol_weighting": True},
}

def run_one(pool_name, variant_name, variant_extra, pool_cfg):
    tag = f"LONGPERIOD_{pool_name}_{variant_name.replace(' ','').replace('(','').replace(')','').replace('+','_')}"
    extra = {**pool_cfg["base_extra"], **variant_extra}
    
    params = make_config("F2_CAP_MA60" if pool_name == "F2_CAP_MA60" else "F2_STATIC",
                         pool_cfg["pit"], pool_cfg["f2"], pool_cfg["f2_orig"],
                         tag, extra, START, END)
    params_dict = {**params.__dict__, **extra, "start": START, "end": END, "exp_tag": tag,
                   "lookback_days": 25}
    
    # For static pools, need to set etf_pool_ts explicitly
    if pool_name == "F2_STATIC":
        params_dict["etf_pool_ts"] = f2_pool
        params_dict["pit_pools"] = None
        params_dict["core_pool"] = None
    elif pool_name == "ORIG38_STATIC":
        params_dict["etf_pool_ts"] = orig38_pool
        params_dict["pit_pools"] = None
        params_dict["core_pool"] = None
    
    params = EngineParams(**params_dict)
    
    sm = OUT / f"etf_loop_summary_{tag}_h5_{START.replace('-','')}_{END.replace('-','')}.csv"
    if sm.exists():
        print(f"  {tag}: skip existing")
        return pd.read_csv(sm).iloc[0].to_dict()
    else:
        print(f"  {tag}: running...")
        equity, trades, audit = run_and_save(params, OUT)
        return audit["stats"]

def main():
    print("=" * 90)
    print("  Long-Period Optimization Comparison: 2013-07-01 → 2026-06-25")
    print("=" * 90)
    
    results = {}
    for pool_name, pool_cfg in POOL_CONFIGS.items():
        print(f"\n── {pool_name} ──")
        for var_name, var_extra in VARIANTS.items():
            key = f"{pool_name}|{var_name}"
            results[key] = run_one(pool_name, var_name, var_extra, pool_cfg)
    
    # ── Print comparison table ──
    for pool_name in POOL_CONFIGS:
        print(f"\n{'=' * 90}")
        print(f"  {pool_name}")
        print(f"{'=' * 90}")
        header = f"  {'Variant':<25s} {'Ann':>8s} {'Sharpe':>7s} {'DD':>8s} {'TotalRet':>10s} {'FinalVal':>14s}"
        print(header)
        print("  " + "-" * 80)
        for var_name in VARIANTS:
            key = f"{pool_name}|{var_name}"
            s = results.get(key, {})
            if not s:
                print(f"  {var_name:<25s} {'N/A':>8s}")
                continue
            ann = s.get('annual_return', 0)
            sharpe = s.get('sharpe_ratio', 0)
            dd = s.get('max_drawdown', 0)
            total = s.get('total_return', 0)
            final = s.get('final_value', 0)
            print(f"  {var_name:<25s} {ann*100:7.2f}% {sharpe:6.2f} {dd*100:7.2f}% {total*100:9.2f}% {final:>13,.0f}¥")
        
        # Delta vs baseline
        base = results.get(f"{pool_name}|Baseline", {})
        if base:
            print(f"\n  {'Delta vs Baseline':<25s} {'ΔAnn':>8s} {'ΔSharpe':>7s} {'ΔDD':>8s}")
            print("  " + "-" * 55)
            for var_name in [v for v in VARIANTS if v != "Baseline"]:
                key = f"{pool_name}|{var_name}"
                s = results.get(key, {})
                if not s: continue
                dann = s.get('annual_return', 0) - base.get('annual_return', 0)
                dsharpe = s.get('sharpe_ratio', 0) - base.get('sharpe_ratio', 0)
                ddd = s.get('max_drawdown', 0) - base.get('max_drawdown', 0)
                print(f"  {var_name:<25s} {dann*100:+7.2f}% {dsharpe:+6.2f} {ddd*100:+7.2f}%")
    
    print(f"\nDone. Results saved in {OUT}")

if __name__ == "__main__":
    main()
