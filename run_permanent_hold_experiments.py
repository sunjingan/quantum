#!/usr/bin/env python3
"""Run permanent-hold plus dip-add experiments for ETF Loop."""
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


START = "2013-07-01"
END = "2026-06-25"
OUT = BASE_DIR / "outputs" / "etf_loop"

ASSETS = {
    "NASDAQ100": ("513100.SH", "国泰纳斯达克100ETF(QDII)"),
    "SP500": ("513500.SH", "博时标普500ETF(QDII)"),
    "GOLD": ("518880.SH", "华安易富黄金ETF"),
    "NIKKEI225": ("513520.SH", "华夏野村日经225ETF(QDII)"),
    "HSTECH": ("513180.SH", "华夏恒生科技ETF(QDII)"),
}

COMBOS = {
    "US_GOLD": ("513100.SH", "513500.SH", "518880.SH"),
}


def load_pit_pool() -> dict[pd.Timestamp, list[str]]:
    path = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity" / "etf_pool_G2_PIT_monthly.pkl"
    with open(path, "rb") as f:
        pools = pickle.load(f)
    return {pd.Timestamp(k): list(v) for k, v in pools.items()}


def load_f2_pool() -> list[str]:
    path = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity" / "etf_pool_F2_v3.csv"
    return sorted(pd.read_csv(path, dtype={"ts_code": str})["ts_code"].astype(str).tolist())


def load_fund_names() -> dict[str, str]:
    path = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity" / "fund_basic_etf.csv"
    df = pd.read_csv(path, dtype={"ts_code": str})
    return dict(zip(df["ts_code"].astype(str), df["name"].astype(str), strict=False))


def paths(tag: str, holdings: int = 5) -> tuple[Path, Path, Path]:
    suffix = f"{tag}_h{holdings}_{START.replace('-', '')}_{END.replace('-', '')}"
    return (
        OUT / f"etf_loop_equity_{suffix}.csv",
        OUT / f"etf_loop_targets_{suffix}.csv",
        OUT / f"etf_loop_summary_{suffix}.csv",
    )


def benchmark_stats(equity: pd.DataFrame) -> dict[str, float]:
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


def asset_diagnostics(trades: pd.DataFrame, codes: tuple[str, ...]) -> dict[str, Any]:
    if trades.empty:
        return {
            "asset_first_buy": "",
            "asset_buy_count": 0,
            "asset_sell_count": 0,
            "dip_add_count": 0,
            "asset_gross_buy": 0.0,
            "asset_net_sell": 0.0,
        }
    code_mask = trades["ts_code"].astype(str).isin(codes)
    action = trades.get("action", pd.Series("", index=trades.index)).astype(str)
    buys = code_mask & action.eq("BUY")
    sells = code_mask & action.eq("SELL")
    dip = trades.get("permanent_dip_add", pd.Series(False, index=trades.index)).astype("boolean").fillna(False)
    first_buy = ""
    if buys.any():
        first_buy = str(pd.to_datetime(trades.loc[buys, "trade_date"]).min().date())
    gross_buy = pd.to_numeric(trades.get("gross_cost", pd.Series(0.0, index=trades.index)), errors="coerce").fillna(0.0)
    net_sell = pd.to_numeric(trades.get("net_proceeds", pd.Series(0.0, index=trades.index)), errors="coerce").fillna(0.0)
    return {
        "asset_first_buy": first_buy,
        "asset_buy_count": int(buys.sum()),
        "asset_sell_count": int(sells.sum()),
        "dip_add_count": int((buys & dip).sum()),
        "asset_gross_buy": float(gross_buy[buys].sum()),
        "asset_net_sell": float(net_sell[sells].sum()),
    }


def run_case(rows: list[dict], params: EngineParams, group: str, codes: tuple[str, ...], notes: str, force: bool = False) -> None:
    equity_path, trades_path, summary_path = paths(params.exp_tag, params.holdings_num)
    if not force and equity_path.exists() and trades_path.exists() and summary_path.exists():
        equity = pd.read_csv(equity_path, parse_dates=["date"]).set_index("date")
        trades = pd.read_csv(trades_path)
        stats = pd.read_csv(summary_path).iloc[0].to_dict()
        print(f"{params.exp_tag}: skip existing")
    else:
        equity, trades, audit = run_and_save(params, OUT)
        stats = audit["stats"]
    bench = benchmark_stats(equity)
    row = {
        "tag": params.exp_tag,
        "group": group,
        "codes": ",".join(codes),
        "notes": notes,
        "annual_return": stats.get("annual_return"),
        "sharpe_ratio": stats.get("sharpe_ratio"),
        "max_drawdown": stats.get("max_drawdown"),
        "annual_volatility": stats.get("annual_volatility"),
        "total_return": stats.get("total_return"),
        "final_value": stats.get("final_value"),
        **bench,
        **asset_diagnostics(trades, codes),
        "permanent_dip_add_enabled": params.permanent_dip_add_enabled,
        "permanent_dip_threshold": params.permanent_dip_threshold,
        "permanent_dip_add_weight": params.permanent_dip_add_weight,
        "permanent_max_weight": params.permanent_max_weight,
    }
    row["alpha_vs_hs300"] = row["annual_return"] - row["benchmark_annual"]
    rows.append(row)


def base_params(core_pool: list[str], pit: dict[pd.Timestamp, list[str]], tag: str, **kwargs: Any) -> EngineParams:
    params = {
        "pit_pools": pit,
        "core_pool": core_pool,
        "holdings_num": 5,
        "start": START,
        "end": END,
        "exp_tag": tag,
        "dynamic_fusion_mode": "capped",
        "dynamic_max_slots": 1,
        "dynamic_max_total_weight": 0.20,
        "dynamic_score_margin": 0.10,
        "dynamic_overheat_threshold": 0.10,
        "dynamic_overheat_penalty": 0.50,
    }
    params.update(kwargs)
    return EngineParams(**params)


def pct(x: float) -> str:
    return "" if pd.isna(x) else f"{x * 100:.2f}%"


def write_report(manifest: pd.DataFrame, names: dict[str, str]) -> Path:
    path = OUT / "permanent_hold_report.md"
    lines = [
        "# ETF Loop Permanent Hold Experiments",
        "",
        f"- window: `{START}` to `{END}`",
        "- base pool: `F2_v3 + ORIG38 + tested long assets`",
        "- dynamic overlay: capped G2 PIT, max 1 dynamic slot, max 20% weight, 10% score margin, 20d overheat penalty",
        "- permanent rule: after the strategy first buys a listed permanent asset, rank-out and stops are ignored",
        "- dip-add rule: add only when drawdown from holding high exceeds threshold; no next-open fallback is allowed",
        "",
        "## Results",
        "",
        "| tag | group | asset | ann | sharpe | dd | alpha | first buy | buys | sells | dip adds | final |",
        "|---|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|",
    ]
    for r in manifest.sort_values(["sharpe_ratio", "annual_return"], ascending=False).to_dict("records"):
        asset_names = ", ".join(names.get(c, c) for c in str(r["codes"]).split(",") if c)
        lines.append(
            f"| `{r['tag']}` | {r['group']} | {asset_names} | {pct(r['annual_return'])} | "
            f"{r['sharpe_ratio']:.2f} | {pct(r['max_drawdown'])} | {pct(r['alpha_vs_hs300'])} | "
            f"{r['asset_first_buy']} | {int(r['asset_buy_count'])} | {int(r['asset_sell_count'])} | "
            f"{int(r['dip_add_count'])} | {r['final_value']:.0f} |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pit = load_pit_pool()
    f2 = load_f2_pool()
    orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    tested_codes = sorted({code for code, _ in ASSETS.values()} | {c for combo in COMBOS.values() for c in combo})
    core_pool = sorted(set(f2) | set(orig38) | set(tested_codes))
    names = load_fund_names()

    rows: list[dict] = []
    run_case(rows, base_params(core_pool, pit, "PERMHOLD_BASE_EXPANDED"), "BASE", tuple(tested_codes), "expanded-pool baseline")

    variants = [
        ("HOLDONLY", {"permanent_dip_add_enabled": False}, "permanent hold, no dip add"),
        ("DIP10_ADD5_MAX35", {"permanent_dip_add_enabled": True, "permanent_dip_threshold": 0.10, "permanent_dip_add_weight": 0.05, "permanent_max_weight": 0.35}, "drawdown >=10%, add 5%, max 35%"),
        ("DIP15_ADD5_MAX40", {"permanent_dip_add_enabled": True, "permanent_dip_threshold": 0.15, "permanent_dip_add_weight": 0.05, "permanent_max_weight": 0.40}, "drawdown >=15%, add 5%, max 40%"),
        ("DIP20_ADD10_MAX50", {"permanent_dip_add_enabled": True, "permanent_dip_threshold": 0.20, "permanent_dip_add_weight": 0.10, "permanent_max_weight": 0.50}, "drawdown >=20%, add 10%, max 50%"),
    ]

    for group, (code, _name) in ASSETS.items():
        for suffix, kwargs, notes in variants:
            run_case(rows, base_params(
                core_pool,
                pit,
                f"PERMHOLD_{group}_{suffix}",
                permanent_hold_codes=(code,),
                **kwargs,
            ), group, (code,), notes)

    for group, codes in COMBOS.items():
        for suffix, kwargs, notes in variants:
            run_case(rows, base_params(
                core_pool,
                pit,
                f"PERMHOLD_{group}_{suffix}",
                permanent_hold_codes=tuple(codes),
                **kwargs,
            ), group, tuple(codes), notes)

    manifest = pd.DataFrame(rows)
    manifest_path = OUT / "permanent_hold_manifest.csv"
    manifest.to_csv(manifest_path, index=False)
    report_path = write_report(manifest, names)
    print("\nSaved:", manifest_path)
    print("Saved:", report_path)
    print(manifest.sort_values(["sharpe_ratio", "annual_return"], ascending=False)[[
        "tag", "annual_return", "sharpe_ratio", "max_drawdown", "alpha_vs_hs300",
        "asset_first_buy", "asset_buy_count", "asset_sell_count", "dip_add_count", "final_value",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()
