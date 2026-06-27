#!/usr/bin/env python3
"""Run 2026 standalone backtest WITHOUT warm-up delay.
Uses data_start=2025-10-01 for context, trading_start=2026-01-02 for first trade.
"""
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

EXP_TAG = "VAL_YR26_NOWARMUP_F2_CAP_MA60"
START = "2025-10-01"      # data context from Oct 2025
TRADING_START = "2026-01-02"  # first trade on first trading day of 2026
END = "2026-06-25"

def main():
    pit = load_pit_pool()
    f2 = load_f2_pool()
    orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    f2_orig = sorted(set(f2) | set(orig38))

    # Build config using existing make_config, then override start/trading_start
    params = make_config("F2_CAP_MA60", pit, f2, f2_orig, EXP_TAG, {}, START, END)
    params = EngineParams(
        **{**params.__dict__,
           "start": START,
           "trading_start": TRADING_START,
           "end": END,
           "exp_tag": EXP_TAG,
           "lookback_days": 25,  # keep warm-up for signal quality
        })

    print(f"→ Running {EXP_TAG}")
    print(f"  data_start: {START}")
    print(f"  trading_start: {TRADING_START}")
    print(f"  end: {END}")
    print(f"  lookback_days: {params.lookback_days}")

    equity, trades, audit = run_and_save(params, OUT)
    stats = audit["stats"]

    print(f"\n  Annual return: {stats.get('annual_return', 0)*100:.2f}%")
    print(f"  Sharpe: {stats.get('sharpe_ratio', 0):.2f}")
    print(f"  Max DD: {stats.get('max_drawdown', 0)*100:.2f}%")
    print(f"  Total return: {stats.get('total_return', 0)*100:.2f}%")
    print(f"  Final value: {stats.get('final_value', 0):,.0f}")
    print(f"  Equity days: {len(equity)}")
    print(f"  Trades: {len(trades)}")

    # Count trades in 2026 only
    trades['trade_date'] = pd.to_datetime(trades['trade_date'])
    trades_2026 = trades[trades['trade_date'] >= '2026-01-01']
    print(f"  Trades in 2026: {len(trades_2026)}")
    first_trade = trades_2026['trade_date'].min()
    print(f"  First 2026 trade: {first_trade}")
    
    # Print first 5 trade dates
    print(f"\n  First 5 trades in 2026:")
    for d in sorted(trades_2026['trade_date'].unique())[:5]:
        print(f"    {d}")

    print(f"\n  File: {OUT}/etf_loop_equity_{EXP_TAG}_h5_{START.replace('-','')}_{END.replace('-','')}.csv")

if __name__ == "__main__":
    main()
