#!/usr/bin/env python3
"""Adaptive holdings v2: corrected cost, broader benchmarks, window sensitivity, position diagnostics."""
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

# CORRECTED cost: 1.5bp commission + 2bp slippage = 3.5bp/side, 7bp round-trip
COST = {"open_cost": 0.00015, "close_cost": 0.00015, "slippage": 0.0002}

# ── Test: different benchmarks for 20dRet mode ──
BENCHMARKS = {
    "HS300": "sh000300",       # 沪深300 (original, narrow large-cap)
    "ZZ500": "sh000905",       # 中证500 (broader mid-cap)
    "CYB": "sz399006",         # 创业板指 (growth/tech tilted)
}

# ── Test: 20dRet window sensitivity ──
RET_WINDOWS = [10, 15, 20, 30, 40]

def run_adaptive_config(tag, benchmark_code, ret_window, extra):
    """Run a single adaptive config."""
    p = EngineParams(
        start="2013-07-01", end="2026-06-25", exp_tag=tag,
        lookback_days=25, adaptive_window=ret_window, **COST,
        use_market_adaptive_holdings=True, adaptive_mode="bench_20d_ret",
        benchmark=benchmark_code,
        **extra
    )
    # Build full params via make_config for pool setup
    params = make_config("F2_CAP_MA60", pit, f2, f2o, tag, {}, "2013-07-01", "2026-06-25")
    params = EngineParams(**{**params.__dict__, **p.__dict__, "start": "2013-07-01", "end": "2026-06-25",
                            "exp_tag": tag, "lookback_days": 25, **COST, **extra,
                            "use_market_adaptive_holdings": True, "adaptive_mode": "bench_20d_ret",
                            "benchmark": benchmark_code, "adaptive_window": ret_window})
    
    sm = OUT / f"etf_loop_summary_{tag}_h5_20130701_20260625.csv"
    if sm.exists():
        return pd.read_csv(sm).iloc[0].to_dict()
    eq, tr, audit = run_and_save(params, OUT)
    return audit["stats"]

print("=" * 90)
print("  Adaptive Holdings V2: Corrected Cost + Benchmark Comparison")
print(f"  Cost: 3.5bp/side, 7bp round-trip (FIXED)")
print("=" * 90)

# ── Part A: Benchmark comparison (20d ret, no ScoreW) ──
print(f"\n{'='*60}")
print(f"  A. Benchmark Comparison (20dRet, no ScoreW, 2013-2026)")
print(f"{'='*60}")
print(f"  {'Benchmark':<10s} {'Ann':>8s} {'Sharpe':>7s} {'DD':>8s} {'Final':>14s}")
for bname, bcode in BENCHMARKS.items():
    tag = f"ADAPTV2_BENCH_{bname}_20d"
    s = run_adaptive_config(tag, bcode, 20, {})
    print(f"  {bname:<10s} {s.get('annual_return',0)*100:7.2f}% {s.get('sharpe_ratio',0):6.2f} {s.get('max_drawdown',0)*100:7.2f}% {s.get('final_value',0):>13,.0f}")

# ── Part B: Window sensitivity (HS300 benchmark, no ScoreW) ──
print(f"\n{'='*60}")
print(f"  B. Window Sensitivity (HS300, no ScoreW, 2013-2026)")
print(f"{'='*60}")
print(f"  {'Window':<10s} {'Ann':>8s} {'Sharpe':>7s} {'DD':>8s} {'Final':>14s}")
for w in RET_WINDOWS:
    tag = f"ADAPTV2_WIN_{w}d"
    s = run_adaptive_config(tag, "sh000300", w, {})
    print(f"  {w}d{'':>7s} {s.get('annual_return',0)*100:7.2f}% {s.get('sharpe_ratio',0):6.2f} {s.get('max_drawdown',0)*100:7.2f}% {s.get('final_value',0):>13,.0f}")

# ── Part C: Best combo (best benchmark + best window + ScoreW) ──
print(f"\n{'='*60}")
print(f"  C. Best Combo (ZZ500 + 15d + ScoreW, 2013-2026)")
print(f"{'='*60}")
tag = "ADAPTV2_BEST_COMBO"
s = run_adaptive_config(tag, "sh000905", 15, {"use_score_weighting": True})
print(f"  ZZ500 15d+SW: ann={s.get('annual_return',0)*100:.2f}%, sharpe={s.get('sharpe_ratio',0):.2f}, DD={s.get('max_drawdown',0)*100:.2f}%, final={s.get('final_value',0):,.0f}")

# Baselines
bs_tag = "ADAPTV2_BASELINE_FIXED5"
bs_s = run_adaptive_config(bs_tag, "sh000300", 20, {"use_market_adaptive_holdings": False, "use_score_weighting": False})
print(f"  Baseline fixed5 HS300: ann={bs_s.get('annual_return',0)*100:.2f}%")
print(f"  Δ vs Baseline: {(s.get('annual_return',0)-bs_s.get('annual_return',0))*100:+.2f}%")

print("\nDone.")
