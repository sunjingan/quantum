#!/usr/bin/env python3
"""Strict replication of friend's 9-ETF single-position strategy with friend_mode."""
from __future__ import annotations
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import pandas as pd
from strategies.etf_loop_engine import EngineParams, run_and_save

OUT = BASE_DIR / "outputs" / "etf_loop"
OUT.mkdir(parents=True, exist_ok=True)

POOL = ["513100.SH","513520.SH","513030.SH","518880.SH","159980.SZ","501018.SH","511090.SH","512890.SH","159915.SZ"]

COMMON = {
    "start": "2020-01-01", "end": "2025-12-31",
    "etf_pool_ts": POOL, "holdings_num": 1,
    "use_dynamic_pool": False, "mr_ma_period": 0, "mr_penalty": 0,
    "use_atr_stop_loss": True, "atr_multiplier": 2.0,
    "execution_price_mode": "open", "execution_delay_days": 1,
}

configs = [
    ("FR_1_Simple25d_FriendCost", "1. Simple 25d (friend cost)",
     {**COMMON, "lookback_days": 25, "open_cost": 0.0002, "close_cost": 0.0002, "slippage": 0.001}),
    
    ("FR_2_FriendMode_NoFilters", "2. friend_mode only, no filters",
     {**COMMON, "lookback_days": 25, "friend_mode": True,
      "open_cost": 0.0002, "close_cost": 0.0002, "slippage": 0.001}),
    
    ("FR_3_FriendMode_Full", "3. friend_mode + all friend logic (strict rep)",
     {**COMMON, "lookback_days": 25, "friend_mode": True,
      "use_dynamic_lookback": True, "dyn_lookback_min": 20, "dyn_lookback_max": 60,
      "dyn_lookback_vol_ratio_cap": 0.9, "dyn_lookback_use_atr": True,
      "use_drawdown_filter": True, "dd_use_enhanced": True,
      "min_score_threshold": 0.001, "max_score_threshold": 6.0,
      "use_premium_penalty": True, "premium_penalty": 1.0, "premium_threshold": 0.05,
      "open_cost": 0.0002, "close_cost": 0.0002, "slippage": 0.001}),
    
    ("FR_4_NoFriendMode_Full", "4. NO friend_mode, all friend logic (compare)",
     {**COMMON, "lookback_days": 25, "friend_mode": False,
      "use_dynamic_lookback": True, "dyn_lookback_min": 20, "dyn_lookback_max": 60,
      "dyn_lookback_vol_ratio_cap": 0.9, "dyn_lookback_use_atr": True,
      "use_drawdown_filter": True, "dd_use_enhanced": True,
      "min_score_threshold": 0.001, "max_score_threshold": 6.0,
      "use_premium_penalty": True, "premium_penalty": 0.5, "premium_threshold": 0.05,
      "open_cost": 0.0002, "close_cost": 0.0002, "slippage": 0.001}),
]

print(f"{'Config':<45s} {'Ann':>8s} {'Sharpe':>7s} {'DD':>8s} {'Final':>12s}")
print("-" * 85)
for tag, name, params_dict in configs:
    p = EngineParams(exp_tag=tag, **params_dict)
    sm = OUT / f"etf_loop_summary_{tag}_h5_20200101_20251231.csv"
    if sm.exists():
        s = pd.read_csv(sm).iloc[0].to_dict()
    else:
        eq, tr, audit = run_and_save(p, OUT); s = audit["stats"]
    print(f"{name:<45s} {s.get('annual_return',0)*100:7.2f}% {s.get('sharpe_ratio',0):6.2f} {s.get('max_drawdown',0)*100:7.2f}% {s.get('final_value',0):>11,.0f}")

print(f"\nFriend's claimed (2020-2025): ann=66.04%, DD=-16.53%")
