#!/usr/bin/env python3
"""Rerun corrected ETF Loop core experiments.

Outputs are written to outputs/etf_loop with tags that identify the
experiment family. This script assumes old outputs have already been archived.
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from strategies.etf_loop_engine import EngineParams, run_and_save
from strategies.etf_loop_strategy import FULL_ETF_POOL_JQ, _jq_to_ts


START = "2018-06-01"
END = "2026-06-25"
LONG_START = "2013-07-01"


def _load_pickle(path: Path):
    with open(path, "rb") as f:
        return pickle.load(f)


def load_pit_pool(name: str) -> dict:
    path = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity" / name
    pools = _load_pickle(path)
    return {pd.Timestamp(k): list(v) for k, v in pools.items()}


def load_f2_pool() -> list[str]:
    path = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity" / "etf_pool_F2_v3.csv"
    return sorted(pd.read_csv(path, dtype={"ts_code": str})["ts_code"].astype(str).tolist())


def summarize_outputs(rows: list[dict]) -> None:
    out = BASE_DIR / "outputs" / "etf_loop" / "rerun_manifest.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\nSaved manifest: {out}")


def run_case(rows: list[dict], params: EngineParams) -> None:
    out_dir = BASE_DIR / "outputs" / "etf_loop"
    suffix = f"{params.exp_tag}_h{params.holdings_num}"
    suffix += f"_{params.start.replace('-','')}_{params.end.replace('-','')}"
    equity_path = out_dir / f"etf_loop_equity_{suffix}.csv"
    trades_path = out_dir / f"etf_loop_targets_{suffix}.csv"
    summary_path = out_dir / f"etf_loop_summary_{suffix}.csv"

    if equity_path.exists() and trades_path.exists() and summary_path.exists():
        stats = pd.read_csv(summary_path).iloc[0].to_dict()
        try:
            n_trades = len(pd.read_csv(trades_path, usecols=["action"]))
        except Exception:
            n_trades = len(pd.read_csv(trades_path))
        print(f"{params.exp_tag}: skip existing, trades={n_trades}")
        rows.append({
            "tag": params.exp_tag,
            "start": params.start,
            "end": params.end,
            "holdings_num": params.holdings_num,
            "annual_return": stats.get("annual_return"),
            "sharpe_ratio": stats.get("sharpe_ratio"),
            "max_drawdown": stats.get("max_drawdown"),
            "total_return": stats.get("total_return"),
            "final_value": stats.get("final_value"),
            "trades": n_trades,
            "nav_error": None,
            "pool_mode": "pit" if params.pit_pools is not None else "static",
            "core_pool_size": len(params.core_pool or []),
            "static_pool_size": len(params.etf_pool_ts or []),
        })
        return

    equity, trades, audit = run_and_save(params, BASE_DIR / "outputs" / "etf_loop")
    stats = audit["stats"]
    rows.append({
        "tag": params.exp_tag,
        "start": params.start,
        "end": params.end,
        "holdings_num": params.holdings_num,
        "annual_return": stats.get("annual_return"),
        "sharpe_ratio": stats.get("sharpe_ratio"),
        "max_drawdown": stats.get("max_drawdown"),
        "total_return": stats.get("total_return"),
        "final_value": stats.get("final_value"),
        "trades": len(trades),
        "nav_error": audit.get("max_nav_error"),
        "pool_mode": "pit" if params.pit_pools is not None else "static",
        "core_pool_size": len(params.core_pool or []),
        "static_pool_size": len(params.etf_pool_ts or []),
    })


def main() -> None:
    g1_pit = load_pit_pool("etf_pool_G1_PIT_monthly.pkl")
    g2_pit = load_pit_pool("etf_pool_G2_PIT_monthly.pkl")
    orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    f2 = load_f2_pool()
    f2_orig = sorted(set(f2) | set(orig38))
    pool19 = sorted([
        "513100.SH", "513500.SH", "159509.SZ", "513520.SH", "513030.SH",
        "518880.SH", "159980.SZ", "159985.SZ", "159981.SZ", "501018.SH",
        "511090.SH", "511360.SH",
        "513130.SH", "513690.SH",
        "510180.SH", "159922.SZ", "159531.SZ", "159915.SZ", "588080.SH",
    ])

    rows: list[dict] = []

    # Core corrected experiment set.
    run_case(rows, EngineParams(pit_pools=g1_pit, holdings_num=5, start=START, end=END, exp_tag="G1R"))
    run_case(rows, EngineParams(pit_pools=g2_pit, holdings_num=5, start=START, end=END, exp_tag="G2R"))

    for slip in [0.0001, 0.0005, 0.0010, 0.0020]:
        tag = f"J1R_{int(slip * 10000):03d}"
        run_case(rows, EngineParams(
            pit_pools=g2_pit, holdings_num=5, start=START, end=END,
            slippage=slip, exp_tag=tag,
        ))

    run_case(rows, EngineParams(
        pit_pools=g2_pit, holdings_num=5, start=START, end=END,
        use_dynamic_cost=True, exp_tag="K2R",
    ))
    run_case(rows, EngineParams(
        pit_pools=g2_pit, holdings_num=5, start=START, end=END,
        use_dynamic_cost=True, cooldown_days=3, exp_tag="K3R",
    ))

    for tag, interval in [
        ("K4R_daily", 1),
        ("K4R_e2d", 2),
        ("K4R_e3d", 3),
        ("K4R_weekly", 5),
    ]:
        run_case(rows, EngineParams(
            pit_pools=g2_pit, holdings_num=5, start=START, end=END,
            rebalance_interval=interval, exp_tag=tag,
        ))

    for tag, cash in [
        ("K5_500K", 500_000),
        ("K5_2M", 2_000_000),
        ("K5_5M", 5_000_000),
        ("K5_10M", 10_000_000),
    ]:
        run_case(rows, EngineParams(
            pit_pools=g2_pit, holdings_num=5, start=START, end=END,
            initial_cash=cash, use_dynamic_cost=True,
            participation_cap=0.05, exp_tag=tag,
        ))

    # Final 13-year pool comparison. G2 PIT has no pool before its first
    # month-end, so pure G2 remains in cash until PIT data starts.
    final_cases = [
        ("FINAL13_ORIG38", {"etf_pool_ts": orig38}),
        ("FINAL13_F2v3", {"etf_pool_ts": f2}),
        ("FINAL13_F2v3_ORIG38", {"etf_pool_ts": f2_orig}),
        ("FINAL13_POOL19", {"etf_pool_ts": pool19}),
        ("FINAL13_G2PIT", {"pit_pools": g2_pit}),
        ("FINAL13_ORIG38_G2PIT", {"pit_pools": g2_pit, "core_pool": orig38}),
        ("FINAL13_F2v3_G2PIT", {"pit_pools": g2_pit, "core_pool": f2}),
        ("FINAL13_F2v3_ORIG38_G2PIT", {"pit_pools": g2_pit, "core_pool": f2_orig}),
    ]
    for tag, kwargs in final_cases:
        run_case(rows, EngineParams(
            holdings_num=5, start=LONG_START, end=END,
            exp_tag=tag, **kwargs,
        ))

    summarize_outputs(rows)


if __name__ == "__main__":
    main()
