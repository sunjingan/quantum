#!/usr/bin/env python3
"""Single-factor scan for ETF Loop rebalance_interval."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from run_multi_setting_pressure_tests import load_f2_pool, load_pit_pool, make_config  # noqa: E402
from strategies.etf_loop_engine import EngineParams, run_and_save  # noqa: E402
from strategies.etf_loop_strategy import FULL_ETF_POOL_JQ, _jq_to_ts  # noqa: E402


OUT = PROJECT_ROOT / "outputs" / "etf_loop" / "rebalance_interval_scan"
LONG_START = "2013-07-01"
NOWARMUP_START = "2025-10-01"
NOWARMUP_TRADING_START = "2026-01-02"
END = "2026-06-25"
INTERVALS = [1, 2, 3, 5, 7, 10, 15, 20]
COST = {"open_cost": 0.00015, "close_cost": 0.00015, "slippage": 0.00020}


def pct(x: float) -> str:
    return "" if pd.isna(x) else f"{x * 100:.2f}%"


def summarize_active_2026(equity: pd.DataFrame) -> dict[str, float]:
    nav = equity.loc[equity.index >= pd.Timestamp("2026-01-01"), "portfolio_value"].dropna()
    if len(nav) < 2:
        return {"active_total_return": np.nan, "active_annual_return": np.nan, "active_sharpe": np.nan, "active_max_drawdown": np.nan}
    daily = nav.pct_change().dropna()
    ann = float(daily.mean() * 252.0)
    vol = float(daily.std() * np.sqrt(252.0)) if len(daily) > 1 else 0.0
    return {
        "active_total_return": float(nav.iloc[-1] / nav.iloc[0] - 1.0),
        "active_annual_return": ann,
        "active_sharpe": ann / vol if vol > 0 else np.nan,
        "active_max_drawdown": float((nav / nav.cummax() - 1.0).min()),
    }


def build_params(
    setting: str,
    pit: dict[pd.Timestamp, list[str]],
    f2: list[str],
    f2_orig: list[str],
    tag: str,
    start: str,
    end: str,
    interval: int,
) -> EngineParams:
    params = make_config("F2_CAP_MA60", pit, f2, f2_orig, tag, {}, start, end)
    extra: dict[str, Any] = {
        **COST,
        "benchmark": "sh000300",
        "start": start,
        "end": end,
        "exp_tag": tag,
        "lookback_days": 25,
        "rebalance_interval": interval,
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
    else:
        raise ValueError(setting)
    return EngineParams(**{**params.__dict__, **extra})


def run_case(
    rows: list[dict],
    setting: str,
    horizon: str,
    interval: int,
    pit: dict[pd.Timestamp, list[str]],
    f2: list[str],
    f2_orig: list[str],
) -> None:
    start = LONG_START if horizon == "LONG_2013_2026" else NOWARMUP_START
    tag = f"RIS_{horizon}_{setting}_RI{interval}"
    params = build_params(setting, pit, f2, f2_orig, tag, start, END, interval)
    if horizon == "NOWARMUP_2026":
        params.trading_start = NOWARMUP_TRADING_START

    equity, trades, audit = run_and_save(params, OUT)
    stats = audit["stats"]
    row = {
        "setting": setting,
        "horizon": horizon,
        "rebalance_interval": interval,
        "tag": tag,
        "annual_return": stats.get("annual_return"),
        "sharpe_ratio": stats.get("sharpe_ratio"),
        "max_drawdown": stats.get("max_drawdown"),
        "total_return": stats.get("total_return"),
        "final_value": stats.get("final_value"),
        "trade_count": int(len(trades)),
        "buy_count": int((trades.get("action", pd.Series(dtype=str)).astype(str) == "BUY").sum()) if not trades.empty else 0,
        "sell_count": int((trades.get("action", pd.Series(dtype=str)).astype(str) == "SELL").sum()) if not trades.empty else 0,
    }
    if horizon == "NOWARMUP_2026":
        row.update(summarize_active_2026(equity))
    rows.append(row)


def write_report(df: pd.DataFrame) -> Path:
    path = OUT / "rebalance_interval_scan_report.md"
    lines = [
        "# Rebalance Interval Scan",
        "",
        "## Reproduce",
        "",
        "```bash",
        "source activate.sh",
        "python runs/etf_loop/run_rebalance_interval_scan.py",
        "```",
        "",
        "## Control Rule",
        "",
        "- This is a single-factor scan: only `rebalance_interval` changes inside each setting.",
        "- `F2_CAP_MA60` uses the project baseline structure: F2_v3 core + capped PIT supplement + MA60 mean-reversion penalty. This scan applies the same high-cost assumption to both settings, so its F2 numbers are not meant to equal the lower-cost baseline row in `docs/etf_loop_project_history.md`.",
        "- `WideA` matches `docs/etf_loop_project_history.md`: `adaptive_window=15`, `adaptive_tiers_ret=0.06,0.03,0.00,-0.02,-0.05,-0.08`, `adaptive_tiers_n=5,5,4,3,2,1,0`, no score weighting.",
        "- cost: `open_cost=0.00015`, `close_cost=0.00015`, `slippage=0.00020`.",
        "- execution: signal on T close, trade on next trading day open; no signal-day close fallback.",
        "",
    ]
    for horizon in ["LONG_2013_2026", "NOWARMUP_2026"]:
        lines += [
            f"## {horizon}",
            "",
            "| setting | interval | ann | sharpe | dd | total | final | trades |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        view = df[df["horizon"].eq(horizon)].sort_values(["setting", "rebalance_interval"])
        for r in view.to_dict("records"):
            lines.append(
                f"| {r['setting']} | {int(r['rebalance_interval'])} | {pct(r['annual_return'])} | "
                f"{r['sharpe_ratio']:.2f} | {pct(r['max_drawdown'])} | {pct(r['total_return'])} | "
                f"{r['final_value']:.0f} | {int(r['trade_count'])} |"
            )
        lines.append("")

    lines += [
        "## Best By Simple Criteria",
        "",
        "| setting | horizon | best annual | best sharpe | lowest dd |",
        "|---|---|---|---|---|",
    ]
    for (setting, horizon), g in df.groupby(["setting", "horizon"], sort=True):
        best_ann = g.loc[g["annual_return"].idxmax()]
        best_sharpe = g.loc[g["sharpe_ratio"].idxmax()]
        best_dd = g.loc[g["max_drawdown"].idxmax()]
        lines.append(
            f"| {setting} | {horizon} | RI{int(best_ann['rebalance_interval'])} {pct(best_ann['annual_return'])} | "
            f"RI{int(best_sharpe['rebalance_interval'])} {best_sharpe['sharpe_ratio']:.2f} | "
            f"RI{int(best_dd['rebalance_interval'])} {pct(best_dd['max_drawdown'])} |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pit = load_pit_pool()
    f2 = load_f2_pool()
    orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    f2_orig = sorted(set(f2) | set(orig38))

    rows: list[dict] = []
    for setting in ["F2_CAP_MA60", "WideA"]:
        for horizon in ["LONG_2013_2026", "NOWARMUP_2026"]:
            for interval in INTERVALS:
                run_case(rows, setting, horizon, interval, pit, f2, f2_orig)

    df = pd.DataFrame(rows)
    manifest = OUT / "rebalance_interval_scan_results.csv"
    df.to_csv(manifest, index=False)
    report = write_report(df)
    print("Saved:", manifest)
    print("Saved:", report)
    print(df[[
        "setting", "horizon", "rebalance_interval", "annual_return",
        "sharpe_ratio", "max_drawdown", "trade_count",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()
