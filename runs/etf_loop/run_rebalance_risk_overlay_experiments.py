#!/usr/bin/env python3
"""Controlled tests for fixed rebalance dates and position risk throttle overlay."""
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


OUT = PROJECT_ROOT / "outputs" / "etf_loop" / "rebalance_risk_overlay"
LONG_START = "2013-07-01"
NOWARMUP_START = "2025-10-01"
NOWARMUP_TRADING_START = "2026-01-02"
END = "2026-06-25"


def pct(x: float) -> str:
    return "" if pd.isna(x) else f"{x * 100:.2f}%"


def summarize_nav(nav: pd.Series) -> dict[str, float]:
    nav = nav.dropna()
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


def trade_stats(trades: pd.DataFrame) -> dict[str, int]:
    if trades.empty:
        return {
            "trade_count": 0,
            "buy_count": 0,
            "sell_count": 0,
            "risk_sell_count": 0,
            "risk_buy_count": 0,
            "partial_count": 0,
        }
    action = trades.get("action", pd.Series("", index=trades.index)).astype(str)
    reason = trades.get("reason", pd.Series("", index=trades.index)).astype(str)
    risk = trades.get("risk_throttled", pd.Series(False, index=trades.index)).astype("boolean").fillna(False)
    partial = trades.get("partial", pd.Series(False, index=trades.index)).astype("boolean").fillna(False)
    return {
        "trade_count": int(len(trades)),
        "buy_count": int(action.eq("BUY").sum()),
        "sell_count": int(action.eq("SELL").sum()),
        "risk_sell_count": int((action.eq("SELL") & reason.str.contains("RISK_THROTTLE", regex=False)).sum()),
        "risk_buy_count": int((action.eq("BUY") & risk).sum()),
        "partial_count": int(partial.sum()),
    }


def build_widea_score_weighted(
    pit: dict[pd.Timestamp, list[str]],
    f2: list[str],
    f2_orig: list[str],
    tag: str,
    start: str,
    end: str,
    overrides: dict[str, Any],
) -> EngineParams:
    """F2_CAP_MA60 + WideA adaptive N + score weighting, keeping all other controls fixed."""
    base_overrides: dict[str, Any] = {
        "lookback_days": 25,
        "open_cost": 0.00015,
        "close_cost": 0.00015,
        "slippage": 0.00020,
        "use_score_weighting": True,
        "use_market_adaptive_holdings": True,
        "adaptive_mode": "bench_20d_ret",
        "adaptive_window": 15,
        "adaptive_tiers_ret": "0.06,0.03,0.00,-0.02,-0.05,-0.08",
        "adaptive_tiers_n": "5,5,4,3,2,1,0",
        "adaptive_tiers_exposure": "1,1,1,1,1,1,0",
    }
    params = make_config(
        "F2_CAP_MA60",
        pit,
        f2,
        f2_orig,
        tag,
        {**base_overrides, **overrides},
        start,
        end,
    )
    return EngineParams(**params.__dict__)


def run_case(
    rows: list[dict],
    pit: dict[pd.Timestamp, list[str]],
    f2: list[str],
    f2_orig: list[str],
    horizon: str,
    variant: str,
    overrides: dict[str, Any],
) -> None:
    start = LONG_START if horizon == "LONG_2013_2026" else NOWARMUP_START
    tag = f"RRO_{horizon}_{variant}"
    params = build_widea_score_weighted(pit, f2, f2_orig, tag, start, END, overrides)
    if horizon == "NOWARMUP_2026":
        params.trading_start = NOWARMUP_TRADING_START

    equity, trades, audit = run_and_save(params, OUT)
    stats = audit["stats"]
    active = {}
    if horizon == "NOWARMUP_2026":
        active = summarize_nav(equity.loc[equity.index >= pd.Timestamp("2026-01-01"), "portfolio_value"])

    row = {
        "horizon": horizon,
        "variant": variant,
        "tag": tag,
        "rebalance_interval": params.rebalance_interval,
        "use_position_risk_throttle": params.use_position_risk_throttle,
        "risk_ret_std_threshold": params.risk_ret_std_threshold if params.use_position_risk_throttle else np.nan,
        "risk_amount_cv_threshold": params.risk_amount_cv_threshold if params.use_position_risk_throttle else np.nan,
        "risk_exposure_multiplier": params.risk_exposure_multiplier if params.use_position_risk_throttle else np.nan,
        "annual_return": stats.get("annual_return"),
        "sharpe_ratio": stats.get("sharpe_ratio"),
        "max_drawdown": stats.get("max_drawdown"),
        "total_return": stats.get("total_return"),
        "final_value": stats.get("final_value"),
        **trade_stats(trades),
        **active,
    }
    rows.append(row)


def write_report(df: pd.DataFrame) -> Path:
    path = OUT / "rebalance_risk_overlay_report.md"
    lines = [
        "# Fixed Rebalance And Risk Overlay Experiment",
        "",
        "## Reproduce",
        "",
        "```bash",
        "source activate.sh",
        "python runs/etf_loop/run_rebalance_risk_overlay_experiments.py",
        "```",
        "",
        "## Common Setting",
        "",
        "- base: `F2_CAP_MA60` = F2_v3 static core pool + capped PIT dynamic supplement + MA60 mean-reversion overheat penalty.",
        "- sizing: `use_score_weighting=True`; this is `WideA + score weighting`, not the unweighted `WideA` candidate in `docs/etf_loop_project_history.md`.",
        "- important: `BASE_DAILY` in this report is only the local control for this overlay experiment. It should not be read as the project candidate `WideA`.",
        "- adaptive holdings: `adaptive_mode=bench_20d_ret`, `adaptive_window=15`, `adaptive_tiers_ret=0.06,0.03,0.00,-0.02,-0.05,-0.08`, `adaptive_tiers_n=5,5,4,3,2,1,0`, `adaptive_tiers_exposure=1,1,1,1,1,1,0`.",
        "- cost: `open_cost=0.00015`, `close_cost=0.00015`, `slippage=0.00020`; effective single-side cost is 3.5bp before liquidity/participation penalties.",
        "- execution: signal at T close, trade at next trading day open; no signal-day close fallback.",
        "- overlay risk score: `(20d return std + 5d return std) / 2`; amount CV: `20d amount std / 20d amount mean`, both computed only through signal date.",
        "- risk overlay setting when enabled: `risk_ret_std_threshold=0.035`, `risk_amount_cv_threshold=1.0`, `risk_exposure_multiplier=0.5`, `risk_check_on_non_rebalance=True`.",
        "",
        "## Variants",
        "",
        "| variant | isolated change |",
        "|---|---|",
        "| BASE_DAILY | daily rebalance, risk overlay off |",
        "| REB10 | only `rebalance_interval=10` |",
        "| RISK_HALF | only risk overlay on |",
        "| REB10_RISK_HALF | 10-day rebalance plus risk overlay; interaction test, not a single-factor result |",
        "",
        "## Long Window Results",
        "",
        "| variant | ann | sharpe | dd | total | final | trades | risk sells | risk buys |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in df[df["horizon"].eq("LONG_2013_2026")].to_dict("records"):
        lines.append(
            f"| {r['variant']} | {pct(r['annual_return'])} | {r['sharpe_ratio']:.2f} | {pct(r['max_drawdown'])} | "
            f"{pct(r['total_return'])} | {r['final_value']:.0f} | {int(r['trade_count'])} | "
            f"{int(r['risk_sell_count'])} | {int(r['risk_buy_count'])} |"
        )

    lines += [
        "",
        "## 2026 Nowarmup Results",
        "",
        "| variant | full ann | active ann | active total | sharpe | active sharpe | dd | active dd | trades | risk sells | risk buys |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in df[df["horizon"].eq("NOWARMUP_2026")].to_dict("records"):
        lines.append(
            f"| {r['variant']} | {pct(r['annual_return'])} | {pct(r.get('active_annual_return', np.nan))} | "
            f"{pct(r.get('active_total_return', np.nan))} | {r['sharpe_ratio']:.2f} | "
            f"{r.get('active_sharpe', np.nan):.2f} | {pct(r['max_drawdown'])} | "
            f"{pct(r.get('active_max_drawdown', np.nan))} | {int(r['trade_count'])} | "
            f"{int(r['risk_sell_count'])} | {int(r['risk_buy_count'])} |"
        )

    lines += [
        "",
        "## Interpretation Guide",
        "",
        "- `REB10` tests whether daily rank churn is hurting results. It should be compared only with `BASE_DAILY`.",
        "- `RISK_HALF` tests the non-rebalance risk reduction idea. It should be compared only with `BASE_DAILY`.",
        "- `REB10_RISK_HALF` is an interaction case; if it works, follow-up tests should tune thresholds and interval separately.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pit = load_pit_pool()
    f2 = load_f2_pool()
    orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    f2_orig = sorted(set(f2) | set(orig38))

    variants: list[tuple[str, dict[str, Any]]] = [
        ("BASE_DAILY", {"rebalance_interval": 1}),
        ("REB10", {"rebalance_interval": 10}),
        ("RISK_HALF", {
            "rebalance_interval": 1,
            "use_position_risk_throttle": True,
            "risk_ret_std_threshold": 0.035,
            "risk_amount_cv_threshold": 1.0,
            "risk_exposure_multiplier": 0.5,
            "risk_check_on_non_rebalance": True,
        }),
        ("REB10_RISK_HALF", {
            "rebalance_interval": 10,
            "use_position_risk_throttle": True,
            "risk_ret_std_threshold": 0.035,
            "risk_amount_cv_threshold": 1.0,
            "risk_exposure_multiplier": 0.5,
            "risk_check_on_non_rebalance": True,
        }),
    ]
    rows: list[dict] = []
    for horizon in ["LONG_2013_2026", "NOWARMUP_2026"]:
        for variant, overrides in variants:
            run_case(rows, pit, f2, f2_orig, horizon, variant, overrides)

    df = pd.DataFrame(rows)
    manifest = OUT / "rebalance_risk_overlay_results.csv"
    df.to_csv(manifest, index=False)
    report = write_report(df)
    print("Saved:", manifest)
    print("Saved:", report)
    print(df[[
        "horizon", "variant", "annual_return", "sharpe_ratio", "max_drawdown",
        "trade_count", "risk_sell_count", "risk_buy_count",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()
