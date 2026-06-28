#!/usr/bin/env python3
"""Validation suite for ETF Loop before paper/live deployment.

This covers tests that can be run with the current daily-bar engine:
fixed OOS splits, yearly breakdown, and cost/capacity stress.  It does not
pretend to cover intraday VWAP, real broker fills, or live/backtest
reconciliation; those require paper/live trading logs.
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from strategies.etf_loop_engine import EngineParams, run_and_save  # noqa: E402
from strategies.etf_loop_strategy import FULL_ETF_POOL_JQ, _jq_to_ts  # noqa: E402


OUT = BASE_DIR / "outputs" / "etf_loop"


def load_pit_pool() -> dict[pd.Timestamp, list[str]]:
    path = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity" / "etf_pool_G2_PIT_monthly.pkl"
    with open(path, "rb") as f:
        pools = pickle.load(f)
    return {pd.Timestamp(k): list(v) for k, v in pools.items()}


def load_f2_pool() -> list[str]:
    path = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity" / "etf_pool_F2_v3.csv"
    return sorted(pd.read_csv(path, dtype={"ts_code": str})["ts_code"].astype(str).tolist())


def path_triplet(tag: str, holdings: int, start: str, end: str) -> tuple[Path, Path, Path]:
    suffix = f"{tag}_h{holdings}_{start.replace('-', '')}_{end.replace('-', '')}"
    return (
        OUT / f"etf_loop_equity_{suffix}.csv",
        OUT / f"etf_loop_targets_{suffix}.csv",
        OUT / f"etf_loop_summary_{suffix}.csv",
    )


def bench_stats(equity: pd.DataFrame) -> dict[str, float]:
    if "benchmark_value" not in equity.columns:
        return {"benchmark_annual": np.nan, "benchmark_sharpe": np.nan, "benchmark_drawdown": np.nan}
    bench = equity["benchmark_value"].dropna()
    daily = bench.pct_change().dropna()
    if len(daily) < 2:
        return {"benchmark_annual": np.nan, "benchmark_sharpe": np.nan, "benchmark_drawdown": np.nan}
    ann = daily.mean() * 252.0
    vol = daily.std() * np.sqrt(252.0)
    return {
        "benchmark_annual": float(ann),
        "benchmark_sharpe": float(ann / vol) if vol > 0 else 0.0,
        "benchmark_drawdown": float((bench / bench.cummax() - 1.0).min()),
    }


def trade_stats(trades: pd.DataFrame) -> dict[str, Any]:
    if trades.empty:
        return {"trade_count": 0, "buy_count": 0, "sell_count": 0, "partial_count": 0}
    action = trades.get("action", pd.Series("", index=trades.index)).astype(str)
    partial = trades.get("partial", pd.Series(False, index=trades.index)).astype("boolean").fillna(False)
    return {
        "trade_count": int(len(trades)),
        "buy_count": int(action.eq("BUY").sum()),
        "sell_count": int(action.eq("SELL").sum()),
        "partial_count": int(partial.sum()),
    }


def max_recovery_days(equity: pd.DataFrame) -> int:
    nav = equity["portfolio_value"].dropna()
    if nav.empty:
        return 0
    peak = nav.cummax()
    under = nav < peak
    max_days = 0
    current = 0
    for flag in under:
        if flag:
            current += 1
            max_days = max(max_days, current)
        else:
            current = 0
    return max_days


def common_base(start: str, end: str, tag: str, pit: dict, core_pool: list[str], **kwargs: Any) -> EngineParams:
    params = {
        "pit_pools": pit,
        "core_pool": core_pool,
        "holdings_num": 5,
        "start": start,
        "end": end,
        "exp_tag": tag,
        "dynamic_fusion_mode": "capped",
        "dynamic_max_slots": 1,
        "dynamic_max_total_weight": 0.10,
        "dynamic_score_margin": 0.05,
        "dynamic_overheat_threshold": 0.10,
        "dynamic_overheat_penalty": 0.50,
    }
    params.update(kwargs)
    return EngineParams(**params)


def config_params(name: str, start: str, end: str, pit: dict, f2: list[str], f2_orig: list[str], tag: str, **overrides: Any) -> EngineParams:
    if name == "F2_CAP_BASE":
        return common_base(start, end, tag, pit, f2, **overrides)
    if name == "F2_CAP_MA60":
        return common_base(start, end, tag, pit, f2, mr_ma_period=60, mr_threshold=1.14, mr_penalty=0.5, **overrides)
    if name == "F2_CAP_ATR3":
        return common_base(start, end, tag, pit, f2, atr_multiplier=3.0, **overrides)
    if name == "F2O_SM025":
        return common_base(
            start, end, tag, pit, f2_orig,
            dynamic_max_total_weight=0.20,
            dynamic_score_margin=0.10,
            short_momentum_threshold=0.25,
            **overrides,
        )
    raise ValueError(name)


def run_case(rows: list[dict], section: str, config: str, label: str, params: EngineParams) -> None:
    eq_path, tr_path, sm_path = path_triplet(params.exp_tag, params.holdings_num, params.start, params.end)
    if eq_path.exists() and tr_path.exists() and sm_path.exists():
        equity = pd.read_csv(eq_path, parse_dates=["date"]).set_index("date")
        trades = pd.read_csv(tr_path)
        stats = pd.read_csv(sm_path).iloc[0].to_dict()
        print(f"{params.exp_tag}: skip existing")
    else:
        equity, trades, audit = run_and_save(params, OUT)
        stats = audit["stats"]
    bench = bench_stats(equity)
    row = {
        "section": section,
        "config": config,
        "label": label,
        "tag": params.exp_tag,
        "start": params.start,
        "end": params.end,
        "annual_return": stats.get("annual_return"),
        "sharpe_ratio": stats.get("sharpe_ratio"),
        "max_drawdown": stats.get("max_drawdown"),
        "annual_volatility": stats.get("annual_volatility"),
        "total_return": stats.get("total_return"),
        "final_value": stats.get("final_value"),
        "max_recovery_days": max_recovery_days(equity),
        "initial_cash": params.initial_cash,
        "open_cost": params.open_cost,
        "close_cost": params.close_cost,
        "slippage": params.slippage,
        "participation_cap": params.participation_cap,
        **bench,
        **trade_stats(trades),
    }
    row["alpha_vs_hs300"] = row["annual_return"] - row["benchmark_annual"]
    rows.append(row)


def pct(x: float) -> str:
    return "" if pd.isna(x) else f"{x * 100:.2f}%"


def write_report(df: pd.DataFrame) -> Path:
    path = OUT / "validation_suite_report.md"
    lines = [
        "# ETF Loop Validation Suite",
        "",
        "This report covers tests runnable with the current daily-bar engine.",
        "",
        "## Fixed OOS",
        "",
        "| config | window | ann | sharpe | dd | alpha | trades | recovery_days |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in df[df["section"].eq("fixed_oos")].sort_values(["config", "label"]).to_dict("records"):
        lines.append(
            f"| {r['config']} | {r['label']} | {pct(r['annual_return'])} | {r['sharpe_ratio']:.2f} | "
            f"{pct(r['max_drawdown'])} | {pct(r['alpha_vs_hs300'])} | {int(r['trade_count'])} | {int(r['max_recovery_days'])} |"
        )

    lines += [
        "",
        "## Yearly Breakdown",
        "",
        "| config | year | ann | sharpe | dd | alpha | trades | recovery_days |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    yearly = df[df["section"].eq("yearly")].sort_values(["config", "label"])
    for r in yearly.to_dict("records"):
        lines.append(
            f"| {r['config']} | {r['label']} | {pct(r['annual_return'])} | {r['sharpe_ratio']:.2f} | "
            f"{pct(r['max_drawdown'])} | {pct(r['alpha_vs_hs300'])} | {int(r['trade_count'])} | {int(r['max_recovery_days'])} |"
        )

    lines += [
        "",
        "## Cost And Capacity",
        "",
        "| label | cash | one_side_cost_hint | participation_cap | ann | sharpe | dd | partials | final |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    cost = df[df["section"].eq("cost_capacity")].sort_values(["label", "initial_cash"])
    for r in cost.to_dict("records"):
        one_side = r["open_cost"] + r["slippage"]
        cap = "" if pd.isna(r["participation_cap"]) else f"{r['participation_cap'] * 100:.1f}%"
        lines.append(
            f"| {r['label']} | {r['initial_cash']:.0f} | {one_side * 100:.2f}% | {cap} | "
            f"{pct(r['annual_return'])} | {r['sharpe_ratio']:.2f} | {pct(r['max_drawdown'])} | "
            f"{int(r['partial_count'])} | {r['final_value']:.0f} |"
        )

    lines += [
        "",
        "## Not Covered Yet",
        "",
        "- Walk-forward rolling parameter selection: needs a selector loop that trains on rolling 3-year windows and tests future 1-month slices.",
        "- VWAP/close execution and 1-2 day execution delay: needs engine-level execution date/price mode support.",
        "- Intraday spread, real order book depth, actual broker fills, duplicate order handling: should be measured in paper/live logs.",
        "- Live/backtest reconciliation: requires shadow trading data generated at real signal time.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pit = load_pit_pool()
    f2 = load_f2_pool()
    orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    f2_orig = sorted(set(f2) | set(orig38))
    rows: list[dict] = []

    configs = ["F2_CAP_BASE", "F2_CAP_MA60", "F2_CAP_ATR3", "F2O_SM025"]
    windows = [
        ("train_2018_2021", "2018-01-01", "2021-12-31"),
        ("valid_2022", "2022-01-01", "2022-12-31"),
        ("test_2023_2026", "2023-01-01", "2026-06-25"),
    ]
    for config in configs:
        for label, start, end in windows:
            tag = f"VAL_OOS_{config}_{label}"
            params = config_params(config, start, end, pit, f2, f2_orig, tag)
            run_case(rows, "fixed_oos", config, label, params)

    yearly_configs = ["F2_CAP_BASE", "F2_CAP_MA60", "F2O_SM025"]
    for config in yearly_configs:
        for year in range(2018, 2027):
            start = f"{year}-01-01"
            end = "2026-06-25" if year == 2026 else f"{year}-12-31"
            tag = f"VAL_YEAR_{config}_{year}"
            params = config_params(config, start, end, pit, f2, f2_orig, tag)
            run_case(rows, "yearly", config, str(year), params)

    cost_tiers = [
        ("cost_optimistic", 0.0001, 0.0001, 0.0001),
        ("cost_neutral", 0.0002, 0.0002, 0.0005),
        ("cost_pessimistic", 0.0005, 0.0005, 0.0015),
    ]
    for label, open_cost, close_cost, slip in cost_tiers:
        tag = f"VAL_COST_{label}"
        params = config_params(
            "F2_CAP_MA60", "2018-01-01", "2026-06-25", pit, f2, f2_orig, tag,
            open_cost=open_cost, close_cost=close_cost, slippage=slip,
        )
        run_case(rows, "cost_capacity", "F2_CAP_MA60", label, params)

    for cash in [100_000, 1_000_000, 5_000_000, 10_000_000]:
        tag = f"VAL_CAPACITY_F2_CAP_MA60_{int(cash)}"
        params = config_params(
            "F2_CAP_MA60", "2018-01-01", "2026-06-25", pit, f2, f2_orig, tag,
            initial_cash=float(cash),
            open_cost=0.0002,
            close_cost=0.0002,
            slippage=0.0005,
            participation_cap=0.05,
        )
        run_case(rows, "cost_capacity", "F2_CAP_MA60", f"capacity_{int(cash)}", params)

    df = pd.DataFrame(rows)
    manifest = OUT / "validation_suite_manifest.csv"
    df.to_csv(manifest, index=False)
    report = write_report(df)
    print("Saved:", manifest)
    print("Saved:", report)
    print(df.sort_values(["section", "config", "label"])[[
        "section", "config", "label", "annual_return", "sharpe_ratio", "max_drawdown",
        "alpha_vs_hs300", "trade_count", "partial_count",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()
