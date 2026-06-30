#!/usr/bin/env python3
"""Run daily ETF Loop candidates under the friend's JoinQuant-style costs."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from run_detailed_trade_log import build_params  # noqa: E402
from strategies.etf_loop_engine import run_and_save  # noqa: E402


OUT = PROJECT_ROOT / "outputs" / "etf_loop" / "friend_cost_daily_candidates"


def pct(x: float) -> str:
    return "" if pd.isna(x) else f"{x * 100:.2f}%"


def trade_cost_stats(trades: pd.DataFrame) -> dict[str, float]:
    if trades.empty or "raw_price" not in trades.columns:
        return {
            "trade_count": float(len(trades)),
            "fixed_slip_bp_weighted": np.nan,
            "one_side_total_bp_weighted": np.nan,
        }
    df = trades.copy()
    df["raw_price"] = pd.to_numeric(df["raw_price"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["shares"] = pd.to_numeric(df["shares"], errors="coerce")
    df = df.dropna(subset=["raw_price", "price", "shares"])
    df = df[(df["raw_price"] > 0) & (df["shares"] > 0)]
    if df.empty:
        return {
            "trade_count": float(len(trades)),
            "fixed_slip_bp_weighted": np.nan,
            "one_side_total_bp_weighted": np.nan,
        }
    raw_notional = df["raw_price"] * df["shares"]
    fixed_slip_value = (df["raw_price"] - df["price"]).abs() * df["shares"]
    slip_bp = float(fixed_slip_value.sum() / raw_notional.sum() * 10000.0)
    return {
        "trade_count": float(len(trades)),
        "fixed_slip_bp_weighted": slip_bp,
        "one_side_total_bp_weighted": 2.0 + slip_bp,
    }


def run_case(setting: str, start: str, end: str, trading_start: str, force: bool) -> dict[str, Any]:
    params = build_params(setting, start, end, trading_start, signal_top_n=20)
    params.exp_tag = f"FRIENDCOST_{setting}_{start.replace('-', '')}_{end.replace('-', '')}"
    params.open_cost = 0.0002
    params.close_cost = 0.0002
    params.slippage = 0.0
    params.fixed_price_slippage = 0.001
    params.write_detailed_logs = True
    suffix = f"{params.exp_tag}_h{params.holdings_num}_{params.start.replace('-', '')}_{params.end.replace('-', '')}"
    summary_path = OUT / f"etf_loop_summary_{suffix}.csv"
    trades_path = OUT / f"etf_loop_targets_{suffix}.csv"
    if summary_path.exists() and trades_path.exists() and not force:
        stats = pd.read_csv(summary_path).iloc[0].to_dict()
        trades = pd.read_csv(trades_path)
    else:
        _, trades, audit = run_and_save(params, OUT)
        stats = audit["stats"]
    cost_stats = trade_cost_stats(trades)
    return {
        "setting": setting,
        "start": start,
        "end": end,
        "trading_start": trading_start,
        "cost_model": "friend_jq_fixed_slip",
        "commission_bp_side": 2.0,
        "fixed_price_slippage": 0.001,
        **stats,
        **cost_stats,
    }


def write_report(rows: list[dict[str, Any]]) -> Path:
    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "daily_candidates_friend_cost_results.csv", index=False)
    path = OUT / "daily_candidates_friend_cost_report.md"
    lines = [
        "# Daily Candidates Under Friend/JoinQuant Cost",
        "",
        "## Cost Model",
        "",
        "- Strategy logic is unchanged: daily close signal, next trading day open execution.",
        "- Changed only costs: `open_cost=0.0002`, `close_cost=0.0002`, `slippage=0`, `fixed_price_slippage=0.001` yuan/share.",
        "- This approximates JoinQuant `FixedSlippage(0.001)` plus fund commission 2bp/side.",
        "- The 1 yuan minimum commission is not modeled; impact is negligible for the tested portfolio size.",
        "- Fixed price slippage is embedded in execution price: buy at `open+0.001`, sell at `open-0.001`.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "source activate.sh && python runs/etf_loop/run_daily_candidate_friend_cost.py --force",
        "```",
        "",
        "## Results",
        "",
        "| setting | start | end | annual | sharpe | DD | total | final | trades | weighted fixed slip bp/side | weighted all-in bp/side |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in df.sort_values(["start", "setting"]).to_dict("records"):
        lines.append(
            f"| {r['setting']} | {r['start']} | {r['end']} | {pct(r['annual_return'])} | "
            f"{r['sharpe_ratio']:.2f} | {pct(r['max_drawdown'])} | {pct(r['total_return'])} | "
            f"{r['final_value']:.0f} | {int(r['trade_count'])} | "
            f"{r['fixed_slip_bp_weighted']:.2f} | {r['one_side_total_bp_weighted']:.2f} |"
        )
    lines += [
        "",
        "## Interpretation Notes",
        "",
        "- Friend's cost is price-dependent. For a 1 yuan ETF, 0.001 yuan is 10bp/side; for a 2 yuan ETF it is 5bp/side.",
        "- Compare these rows against the same setting and same period, not against the long-period candidate table directly.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run F2_CAP_MA60/WideA under friend costs")
    parser.add_argument("--settings", default="F2_CAP_MA60,WideA")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    periods = [
        ("2013-07-01", "2026-06-25", "2013-07-01"),
        ("2020-01-01", "2026-06-25", "2020-01-01"),
    ]
    for setting in [x.strip() for x in args.settings.split(",") if x.strip()]:
        for start, end, trading_start in periods:
            row = run_case(setting, start, end, trading_start, args.force)
            rows.append(row)
            print(
                f"{setting:<12s} {start}->{end} ann={pct(row['annual_return'])} "
                f"sharpe={row['sharpe_ratio']:.2f} dd={pct(row['max_drawdown'])} "
                f"all_in_bp_side={row['one_side_total_bp_weighted']:.2f}"
            )
    report = write_report(rows)
    print("Saved:", OUT / "daily_candidates_friend_cost_results.csv")
    print("Saved:", report)


if __name__ == "__main__":
    main()
