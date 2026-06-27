#!/usr/bin/env python3
"""Adjusted-price core setting comparison for ETF Loop."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from run_multi_setting_pressure_tests import (
    OUT,
    bench_stats,
    load_f2_pool,
    load_pit_pool,
    make_config,
    path_triplet,
    pct,
    trade_stats,
)
from strategies.etf_loop_engine import run_and_save
from strategies.etf_loop_strategy import FULL_ETF_POOL_JQ, _jq_to_ts


START = "2013-07-01"
END = "2026-06-25"


def run_case(rows: list[dict], config: str, params) -> None:
    eq_path, tr_path, sm_path = path_triplet(params)
    if eq_path.exists() and tr_path.exists() and sm_path.exists():
        equity = pd.read_csv(eq_path, parse_dates=["date"]).set_index("date")
        trades = pd.read_csv(tr_path)
        stats = pd.read_csv(sm_path).iloc[0].to_dict()
        print(f"{params.exp_tag}: skip existing")
    else:
        equity, trades, audit = run_and_save(params, OUT)
        stats = audit["stats"]
    row = {
        "config": config,
        "tag": params.exp_tag,
        "start": params.start,
        "end": params.end,
        "annual_return": stats.get("annual_return"),
        "sharpe_ratio": stats.get("sharpe_ratio"),
        "max_drawdown": stats.get("max_drawdown"),
        "annual_volatility": stats.get("annual_volatility"),
        "total_return": stats.get("total_return"),
        "final_value": stats.get("final_value"),
        "switch_score_margin": params.switch_score_margin,
        **bench_stats(equity),
        **trade_stats(trades),
    }
    row["alpha_vs_hs300"] = row["annual_return"] - row["benchmark_annual"]
    rows.append(row)


def write_report(df: pd.DataFrame) -> Path:
    path = OUT / "adjusted_core_setting_comparison_report.md"
    lines = [
        "# ETF Loop Adjusted Core Setting Comparison",
        "",
        f"- window: `{START}` to `{END}`",
        "- execution: signal day close, next trading day adjusted open",
        "- prices: continuous adjusted OHLC/VWAP for signal, execution, and valuation",
        "",
        "| config | ann | sharpe | dd | alpha | trades | dynamic_buys | final |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in df.sort_values("annual_return", ascending=False).to_dict("records"):
        lines.append(
            f"| {r['config']} | {pct(r['annual_return'])} | {r['sharpe_ratio']:.2f} | "
            f"{pct(r['max_drawdown'])} | {pct(r['alpha_vs_hs300'])} | {int(r['trade_count'])} | "
            f"{int(r['dynamic_buy_count'])} | {r['final_value']:.0f} |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pit = load_pit_pool()
    f2 = load_f2_pool()
    orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    f2_orig = sorted(set(f2) | set(orig38))
    configs = [
        "F2_STATIC_BASE",
        "F2_STATIC_MA60",
        "G2_PIT_PURE",
        "F2_CAP_BASE",
        "F2_CAP_MA60",
        "F2_CAP_MA60_SW05",
        "F2O_CAP_BASE",
        "F2O_SM025",
        "F2O_SM025_SW05",
    ]
    rows: list[dict] = []
    for config in configs:
        tag = f"ADJCORE_{config}_OPEN_D1"
        params = make_config(
            config,
            pit,
            f2,
            f2_orig,
            tag,
            {"execution_price_mode": "open", "execution_delay_days": 1, "slippage": 0.0001},
            START,
            END,
        )
        run_case(rows, config, params)

    df = pd.DataFrame(rows)
    manifest = OUT / "adjusted_core_setting_comparison_manifest.csv"
    df.to_csv(manifest, index=False)
    report = write_report(df)
    print("Saved:", manifest)
    print("Saved:", report)
    print(df.sort_values("annual_return", ascending=False)[[
        "config", "annual_return", "sharpe_ratio", "max_drawdown",
        "alpha_vs_hs300", "trade_count", "dynamic_buy_count",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()
