#!/usr/bin/env python3
"""Run an ETF Loop candidate and emit detailed daily trading logs."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from run_multi_setting_pressure_tests import load_f2_pool, load_pit_pool, make_config  # noqa: E402
from strategies.etf_loop_engine import EngineParams, run_and_save  # noqa: E402
from strategies.etf_loop_strategy import FULL_ETF_POOL_JQ, _jq_to_ts  # noqa: E402


OUT = PROJECT_ROOT / "outputs" / "etf_loop" / "detailed_trade_logs"
COST = {"open_cost": 0.00015, "close_cost": 0.00015, "slippage": 0.00020}


def build_params(
    setting: str,
    start: str,
    end: str,
    trading_start: str,
    signal_top_n: int,
) -> EngineParams:
    pit = load_pit_pool()
    f2 = load_f2_pool()
    orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    f2_orig = sorted(set(f2) | set(orig38))
    tag = f"LOG_{setting}_{start.replace('-', '')}_{end.replace('-', '')}"
    base = make_config("F2_CAP_MA60", pit, f2, f2_orig, tag, {}, start, end)
    extra: dict[str, Any] = {
        **COST,
        "benchmark": "sh000300",
        "start": start,
        "end": end,
        "trading_start": trading_start,
        "exp_tag": tag,
        "lookback_days": 25,
        "write_detailed_logs": True,
        "log_signal_top_n": signal_top_n,
    }
    if setting == "F2_CAP_MA60":
        pass
    elif setting == "WideA":
        extra.update({
            "use_market_adaptive_holdings": True,
            "adaptive_mode": "bench_20d_ret",
            "adaptive_window": 15,
            "adaptive_tiers_ret": "0.06,0.03,0.00,-0.02,-0.05,-0.08",
            "adaptive_tiers_n": "5,5,4,3,2,1,0",
            "use_score_weighting": False,
            "switch_score_margin": 0.0,
        })
    elif setting == "Current":
        extra.update({
            "use_market_adaptive_holdings": True,
            "adaptive_mode": "bench_20d_ret",
            "adaptive_window": 15,
            "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06",
            "adaptive_tiers_n": "5,4,3,2,1,0",
            "use_score_weighting": False,
            "switch_score_margin": 0.0,
        })
    elif setting == "Exph_v3_exp_looser":
        extra.update({
            "use_market_adaptive_holdings": True,
            "adaptive_mode": "bench_20d_ret",
            "adaptive_window": 15,
            "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06",
            "adaptive_tiers_n": "5,5,4,4,3,0",
            "adaptive_tiers_exposure": "1,1,0.85,0.65,0.45,0",
            "use_score_weighting": False,
            "switch_score_margin": 0.0,
        })
    else:
        raise ValueError(f"Unsupported setting: {setting}")
    return EngineParams(**{**base.__dict__, **extra})


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ETF Loop detailed trading logs")
    parser.add_argument("--setting", choices=["F2_CAP_MA60", "WideA", "Current", "Exph_v3_exp_looser"], default="WideA")
    parser.add_argument("--start", default="2025-10-01")
    parser.add_argument("--end", default="2026-06-25")
    parser.add_argument("--trading-start", default="2026-01-02")
    parser.add_argument("--signal-top-n", type=int, default=20)
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    params = build_params(args.setting, args.start, args.end, args.trading_start, args.signal_top_n)
    equity, trades, audit = run_and_save(params, OUT)
    suffix = f"{params.exp_tag}_h{params.holdings_num}_{params.start.replace('-', '')}_{params.end.replace('-', '')}"
    print("Detailed logs:")
    for name in ["account", "positions", "signals", "advice", "daily_log"]:
        ext = "md" if name == "daily_log" else "csv"
        stem = "daily_log" if name == "daily_log" else name
        print(f"  {OUT / f'etf_loop_{stem}_{suffix}.{ext}'}")
    print(f"Rows: equity={len(equity)}, trades={len(trades)}, account={len(audit.get('account_log', pd.DataFrame()))}")


if __name__ == "__main__":
    main()
