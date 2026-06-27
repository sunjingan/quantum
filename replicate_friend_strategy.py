#!/usr/bin/env python3
"""Replicate friend's ETF rotation strategy baseline + borrow improvements."""
from __future__ import annotations
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import numpy as np
import pandas as pd
from strategies.etf_loop_engine import EngineParams, run_and_save
from strategies.etf_loop_strategy import calculate_atr

OUT = BASE_DIR / "outputs" / "etf_loop"
OUT.mkdir(parents=True, exist_ok=True)

START, END = "2013-07-01", "2026-06-25"

# Friend's 9-ETF pool (TS codes)
FRIEND_POOL_9 = [
    "513100.SH",  # 纳指ETF
    "513520.SH",  # 日经ETF
    "513030.SH",  # 德国ETF
    "518880.SH",  # 黄金ETF
    "159980.SZ",  # 有色ETF
    "501018.SH",  # 南方原油
    "511090.SH",  # 30年国债ETF
    "512890.SH",  # 红利低波
    "159915.SZ",  # 创业板100
]

# Friend's cost: commission 2bp/side, slippage 10bp/side
FRIEND_COST = {"open_cost": 0.0002, "close_cost": 0.0002, "slippage": 0.001}

# Also test with our standard cost for comparison
OUR_COST = {"open_cost": 0.0001, "close_cost": 0.0001, "slippage": 0.0001}
OUR_COST_BASELINE = {"open_cost": 0.0001, "close_cost": 0.0001, "slippage": 0.0002}

def build_params(tag, holdings=1, pool=None, lookback=25, extra=None):
    """Build EngineParams for a given config."""
    extra = extra or {}
    p = EngineParams(
        start=START, end=END, exp_tag=tag,
        etf_pool_ts=pool or FRIEND_POOL_9,
        holdings_num=holdings,
        lookback_days=lookback,
        use_dynamic_pool=False,
        mr_ma_period=0, mr_penalty=0,
        use_atr_stop_loss=True, atr_multiplier=2.0,
        execution_price_mode="open", execution_delay_days=1,
        **extra
    )
    return p

def run_tag(tag, params):
    sm = OUT / f"etf_loop_summary_{tag}_h5_{START.replace('-','')}_{END.replace('-','')}.csv"
    if sm.exists():
        return pd.read_csv(sm).iloc[0].to_dict()
    eq, tr, audit = run_and_save(params, OUT)
    return audit["stats"]

# ── Configs ──
configs = [
    # 1. Friend baseline: 9 ETFs, 1 position, fixed 25d lookback, friend's cost
    ("Friend_Baseline_1ETF", 1, FRIEND_POOL_9, 25, FRIEND_COST),
    # 2. Friend baseline with our standard cost (fair comparison)
    ("Friend_Baseline_1ETF_OurCost", 1, FRIEND_POOL_9, 25, OUR_COST),
    # 3. Friend baseline with our baseline cost
    ("Friend_Baseline_1ETF_OurBaseCost", 1, FRIEND_POOL_9, 25, OUR_COST_BASELINE),
    # 4. 5-ETF version for comparison
    ("Friend_5ETF_OurCost", 5, FRIEND_POOL_9, 25, OUR_COST),
    # 5. Friend's ATR dynamic lookback
    ("Friend_ATR_DynLB_1ETF", 1, FRIEND_POOL_9, 25, {**OUR_COST, "use_dynamic_lookback": True}),
    # 6. Friend's ATR + Premium penalty (our version)
    ("Friend_ATR_Premium_1ETF", 1, FRIEND_POOL_9, 25, {**OUR_COST, "use_dynamic_lookback": True,
                                                       "use_premium_penalty": True, "premium_penalty": 0.8, "premium_threshold": 0.08}),
    # 7. Our F2_CAP_MA60 with 1 ETF for direct comparison
    ("Our_F2CAP_1ETF_OurCost", 1, "FULL", 25, OUR_COST),
]

print("=" * 90)
print("  Friend's Strategy Replication + Borrowed Improvements")
print("=" * 90)
print(f"  {START} → {END}")
print()

for name, h, pool, lb, cost in configs:
    tag = f"FRIEND_{name.replace(' ','_').replace('(','').replace(')','')}"
    
    extra = dict(cost)
    extra.setdefault("use_dynamic_lookback", False)
    extra.setdefault("use_premium_penalty", False)
    
    if pool == "FULL":
        # Use our full F2_CAP_MA60 config but with 1 ETF
        from run_multi_setting_pressure_tests import make_config, load_pit_pool, load_f2_pool
        from strategies.etf_loop_strategy import _jq_to_ts, FULL_ETF_POOL_JQ
        pit = load_pit_pool(); f2p = load_f2_pool()
        orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
        f2o = sorted(set(f2p) | set(orig38))
        params = make_config("F2_CAP_MA60", pit, f2p, f2o, tag, extra, START, END)
        params = EngineParams(**{**params.__dict__, "holdings_num": h, "start": START, "end": END,
                                "exp_tag": tag, **cost})
    else:
        params = build_params(tag, holdings=h, pool=pool, lookback=lb, extra=extra)
    
    s = run_tag(tag, params)
    ann = s.get('annual_return', 0)
    sharpe = s.get('sharpe_ratio', 0)
    dd = s.get('max_drawdown', 0)
    total = s.get('total_return', 0)
    final = s.get('final_value', 0)
    
    print(f"  {name:<35s} {ann*100:7.2f}% {sharpe:6.2f} {dd*100:7.2f}% {total*100:9.2f}% {final:>14,.0f}¥")

print("\nDone.")
