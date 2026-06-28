#!/usr/bin/env python3
"""Multi-setting execution and cost stress tests for ETF Loop."""
from __future__ import annotations

import pickle
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from strategies.etf_loop_engine import EngineParams, run_and_save  # noqa: E402
from strategies.etf_loop_strategy import FULL_ETF_POOL_JQ, _jq_to_ts  # noqa: E402


OUT = PROJECT_ROOT / "outputs" / "etf_loop"
START = "2018-01-01"
END = "2026-06-25"


def load_pit_pool() -> dict[pd.Timestamp, list[str]]:
    path = PROJECT_ROOT / "data/tushare_cache/sector_prosperity/etf_pool_G2_PIT_monthly.pkl"
    with open(path, "rb") as f:
        pools = pickle.load(f)
    return {pd.Timestamp(k): list(v) for k, v in pools.items()}


def load_f2_pool() -> list[str]:
    path = PROJECT_ROOT / "data/tushare_cache/sector_prosperity/etf_pool_F2_v3.csv"
    return sorted(pd.read_csv(path, dtype={"ts_code": str})["ts_code"].astype(str).tolist())


def path_triplet(params: EngineParams) -> tuple[Path, Path, Path]:
    suffix = f"{params.exp_tag}_h{params.holdings_num}_{params.start.replace('-', '')}_{params.end.replace('-', '')}"
    return (
        OUT / f"etf_loop_equity_{suffix}.csv",
        OUT / f"etf_loop_targets_{suffix}.csv",
        OUT / f"etf_loop_summary_{suffix}.csv",
    )


def bench_stats(equity: pd.DataFrame) -> dict[str, float]:
    if "benchmark_value" not in equity.columns:
        return {"benchmark_annual": np.nan, "benchmark_drawdown": np.nan}
    b = equity["benchmark_value"].dropna()
    daily = b.pct_change().dropna()
    if len(daily) < 2:
        return {"benchmark_annual": np.nan, "benchmark_drawdown": np.nan}
    return {
        "benchmark_annual": float(daily.mean() * 252.0),
        "benchmark_drawdown": float((b / b.cummax() - 1.0).min()),
    }


def trade_stats(trades: pd.DataFrame) -> dict[str, int]:
    if trades.empty:
        return {"trade_count": 0, "dynamic_buy_count": 0, "partial_count": 0}
    action = trades.get("action", pd.Series("", index=trades.index)).astype(str)
    dyn = trades.get("is_dynamic_only", pd.Series(False, index=trades.index)).astype("boolean").fillna(False)
    partial = trades.get("partial", pd.Series(False, index=trades.index)).astype("boolean").fillna(False)
    return {
        "trade_count": int(len(trades)),
        "dynamic_buy_count": int((action.eq("BUY") & dyn).sum()),
        "partial_count": int(partial.sum()),
    }


def pct(x: float) -> str:
    return "" if pd.isna(x) else f"{x * 100:.2f}%"


def make_config(
    name: str,
    pit: dict[pd.Timestamp, list[str]],
    f2: list[str],
    f2_orig: list[str],
    tag: str,
    overrides: dict[str, Any],
    start: str = START,
    end: str = END,
) -> EngineParams:
    common = {
        "holdings_num": 5,
        "start": start,
        "end": end,
        "exp_tag": tag,
    }
    if name == "F2_STATIC_BASE":
        params = {**common, "etf_pool_ts": f2}
    elif name == "F2_STATIC_MA60":
        params = {**common, "etf_pool_ts": f2, "mr_ma_period": 60, "mr_threshold": 1.14, "mr_penalty": 0.50}
    elif name == "G2_PIT_PURE":
        params = {**common, "pit_pools": pit}
    elif name == "F2_CAP_BASE":
        params = {
            **common,
            "pit_pools": pit,
            "core_pool": f2,
            "dynamic_fusion_mode": "capped",
            "dynamic_max_slots": 1,
            "dynamic_max_total_weight": 0.10,
            "dynamic_score_margin": 0.05,
            "dynamic_overheat_threshold": 0.10,
            "dynamic_overheat_penalty": 0.50,
        }
    elif name == "F2_CAP_MA60":
        params = {
            **make_config("F2_CAP_BASE", pit, f2, f2_orig, tag, {}, start, end).__dict__,
            "mr_ma_period": 60,
            "mr_threshold": 1.14,
            "mr_penalty": 0.50,
        }
    elif name == "F2_CAP_MA60_SW05":
        params = {
            **make_config("F2_CAP_MA60", pit, f2, f2_orig, tag, {}, start, end).__dict__,
            "switch_score_margin": 0.05,
        }
    elif name == "F2O_CAP_BASE":
        params = {
            **make_config("F2_CAP_BASE", pit, f2, f2_orig, tag, {}, start, end).__dict__,
            "core_pool": f2_orig,
            "dynamic_max_total_weight": 0.20,
            "dynamic_score_margin": 0.10,
        }
    elif name == "F2O_SM025":
        params = {
            **make_config("F2O_CAP_BASE", pit, f2, f2_orig, tag, {}, start, end).__dict__,
            "short_momentum_threshold": 0.25,
        }
    elif name == "F2O_SM025_SW05":
        params = {
            **make_config("F2O_SM025", pit, f2, f2_orig, tag, {}, start, end).__dict__,
            "switch_score_margin": 0.05,
        }
    else:
        raise ValueError(name)
    params.update(overrides)
    return EngineParams(**params)


def run_case(rows: list[dict], config: str, case_label: str, params: EngineParams) -> None:
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
        "case": case_label,
        "tag": params.exp_tag,
        "execution_price_mode": params.execution_price_mode,
        "execution_delay_days": params.execution_delay_days,
        "slippage": params.slippage,
        "open_cost": params.open_cost,
        "close_cost": params.close_cost,
        "switch_score_margin": params.switch_score_margin,
        "annual_return": stats.get("annual_return"),
        "sharpe_ratio": stats.get("sharpe_ratio"),
        "max_drawdown": stats.get("max_drawdown"),
        "annual_volatility": stats.get("annual_volatility"),
        "total_return": stats.get("total_return"),
        "final_value": stats.get("final_value"),
        **bench_stats(equity),
        **trade_stats(trades),
    }
    row["alpha_vs_hs300"] = row["annual_return"] - row["benchmark_annual"]
    rows.append(row)


def write_report(df: pd.DataFrame) -> Path:
    path = OUT / "multi_setting_pressure_report.md"
    lines = [
        "# ETF Loop Multi-Setting Pressure Tests",
        "",
        f"- window: `{START}` to `{END}`",
        "- prices: continuous adjusted OHLC/VWAP for signal, execution, and valuation",
        "- execution: signal on day T close, trade on configured future trading day; no signal-day fallback",
        "",
        "## Base Results",
        "",
        "| config | ann | sharpe | dd | alpha | trades | dynamic_buys | final |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    base = df[df["case"].eq("open_d1")].sort_values("annual_return", ascending=False)
    for r in base.to_dict("records"):
        lines.append(
            f"| {r['config']} | {pct(r['annual_return'])} | {r['sharpe_ratio']:.2f} | "
            f"{pct(r['max_drawdown'])} | {pct(r['alpha_vs_hs300'])} | {int(r['trade_count'])} | "
            f"{int(r['dynamic_buy_count'])} | {r['final_value']:.0f} |"
        )

    lines += [
        "",
        "## Stress Delta Vs open_d1",
        "",
        "| config | stress | ann | ann_delta | sharpe | dd | trades |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    base_ann = base.set_index("config")["annual_return"].to_dict()
    stress = df[~df["case"].eq("open_d1")].sort_values(["config", "case"])
    for r in stress.to_dict("records"):
        delta = r["annual_return"] - base_ann.get(r["config"], np.nan)
        lines.append(
            f"| {r['config']} | {r['case']} | {pct(r['annual_return'])} | {pct(delta)} | "
            f"{r['sharpe_ratio']:.2f} | {pct(r['max_drawdown'])} | {int(r['trade_count'])} |"
        )

    lines += [
        "",
        "## Notes",
        "",
        "- `F2_STATIC_*`: static F2_v3 pool only.",
        "- `G2_PIT_PURE`: point-in-time monthly dynamic pool only.",
        "- `F2_CAP_*`: F2_v3 core plus capped PIT dynamic supplement.",
        "- `F2O_*`: F2_v3 plus original 38 ETF core, with capped PIT dynamic supplement.",
        "- `SW05`: keep current holding unless replacement score is at least 5% better.",
    ]
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
    cases = [
        ("open_d1", {"execution_price_mode": "open", "execution_delay_days": 1, "slippage": 0.0001}),
        ("vwap_d1", {"execution_price_mode": "vwap", "execution_delay_days": 1, "slippage": 0.0001}),
        ("close_d1", {"execution_price_mode": "close", "execution_delay_days": 1, "slippage": 0.0001}),
        ("open_d2", {"execution_price_mode": "open", "execution_delay_days": 2, "slippage": 0.0001}),
        ("open_d1_adverse_20bp", {"execution_price_mode": "open", "execution_delay_days": 1, "slippage": 0.0020}),
    ]
    rows: list[dict] = []
    for config in configs:
        for case_label, overrides in cases:
            tag = f"ADJPRS_{config}_{case_label.upper()}"
            params = make_config(config, pit, f2, f2_orig, tag, overrides)
            run_case(rows, config, case_label, params)

    df = pd.DataFrame(rows)
    manifest = OUT / "multi_setting_pressure_manifest.csv"
    df.to_csv(manifest, index=False)
    report = write_report(df)
    print("Saved:", manifest)
    print("Saved:", report)
    print(df.sort_values(["config", "case"])[[
        "config", "case", "annual_return", "sharpe_ratio", "max_drawdown",
        "alpha_vs_hs300", "trade_count", "dynamic_buy_count",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()
