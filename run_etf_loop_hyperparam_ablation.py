#!/usr/bin/env python3
"""Hyperparameter ablation runner for ETF Loop.

The runner intentionally uses the unified engine so execution semantics stay
identical to the strategy backtests: signal at close, execute at next open, and
skip orders with missing next-open prices.
"""
from __future__ import annotations

import argparse
import pickle
import sys
from dataclasses import asdict
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
PIT_NAME = "etf_pool_G2_PIT_monthly.pkl"


def load_pit_pool() -> dict[pd.Timestamp, list[str]]:
    path = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity" / PIT_NAME
    with open(path, "rb") as f:
        pools = pickle.load(f)
    return {pd.Timestamp(k): list(v) for k, v in pools.items()}


def load_f2_pool() -> list[str]:
    path = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity" / "etf_pool_F2_v3.csv"
    return sorted(pd.read_csv(path, dtype={"ts_code": str})["ts_code"].astype(str).tolist())


def summary_paths(tag: str, holdings: int) -> tuple[Path, Path, Path]:
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
    if len(bench) < 3:
        return {"benchmark_annual": np.nan, "benchmark_sharpe": np.nan, "benchmark_drawdown": np.nan}
    daily = bench.pct_change().dropna()
    ann = daily.mean() * 252.0
    vol = daily.std() * np.sqrt(252.0)
    peak = bench.cummax()
    dd = (bench / peak - 1.0).min()
    return {
        "benchmark_annual": float(ann),
        "benchmark_sharpe": float(ann / vol) if vol > 0 else 0.0,
        "benchmark_drawdown": float(dd),
    }


def trade_diagnostics(trades: pd.DataFrame) -> dict[str, Any]:
    if trades.empty:
        return {
            "trade_count": 0,
            "buy_count": 0,
            "sell_count": 0,
            "win_rate": np.nan,
            "dynamic_buys": 0,
            "penalized_dynamic_buys": 0,
        }

    action = trades.get("action", pd.Series("", index=trades.index)).astype(str)
    buys = action.eq("BUY")
    sells = action.eq("SELL")
    dyn = trades.get("is_dynamic_only", pd.Series(False, index=trades.index)).astype("boolean").fillna(False)
    penalized = trades.get("dynamic_overheat_penalized", pd.Series(False, index=trades.index)).astype("boolean").fillna(False)

    # FIFO round-trip win rate on sells. Partial fills are handled by share lots.
    lots: dict[str, list[dict[str, float]]] = {}
    sell_pnls: list[float] = []
    for _, row in trades.iterrows():
        code = str(row.get("ts_code", ""))
        shares = int(pd.to_numeric(row.get("shares", 0), errors="coerce") or 0)
        if shares <= 0:
            continue
        if row.get("action") == "BUY":
            cost = float(pd.to_numeric(row.get("net_cost", row.get("gross_cost", 0.0)), errors="coerce") or 0.0)
            lots.setdefault(code, []).append({"shares": shares, "cost_per_share": cost / shares if shares else 0.0})
        elif row.get("action") == "SELL":
            proceeds = float(pd.to_numeric(row.get("net_proceeds", row.get("gross_proceeds", 0.0)), errors="coerce") or 0.0)
            sell_shares = shares
            cost_basis = 0.0
            while sell_shares > 0 and lots.get(code):
                lot = lots[code][0]
                matched = min(sell_shares, int(lot["shares"]))
                cost_basis += matched * float(lot["cost_per_share"])
                lot["shares"] -= matched
                sell_shares -= matched
                if lot["shares"] <= 0:
                    lots[code].pop(0)
            matched_shares = shares - sell_shares
            if matched_shares > 0:
                matched_proceeds = proceeds * matched_shares / shares
                sell_pnls.append(matched_proceeds - cost_basis)

    return {
        "trade_count": int(len(trades)),
        "buy_count": int(buys.sum()),
        "sell_count": int(sells.sum()),
        "win_rate": float(np.mean([p > 0 for p in sell_pnls])) if sell_pnls else np.nan,
        "dynamic_buys": int((dyn & buys).sum()),
        "penalized_dynamic_buys": int((dyn & buys & penalized).sum()),
    }


def param_snapshot(params: EngineParams) -> dict[str, Any]:
    keys = [
        "holdings_num", "lookback_days", "stop_loss", "use_atr_stop_loss",
        "atr_multiplier", "use_short_momentum_filter", "short_lookback_days",
        "short_momentum_threshold", "mr_ma_period", "mr_threshold",
        "mr_penalty", "rebalance_interval", "dynamic_fusion_mode",
        "dynamic_max_slots", "dynamic_max_total_weight", "dynamic_score_margin",
        "dynamic_overheat_lookback", "dynamic_overheat_threshold",
        "dynamic_overheat_penalty",
    ]
    raw = asdict(params)
    return {k: raw.get(k) for k in keys}


def run_case(rows: list[dict], params: EngineParams, profile: str, family: str, variant: str, notes: str, force: bool) -> None:
    equity_path, trades_path, summary_path = summary_paths(params.exp_tag, params.holdings_num)
    if not force and equity_path.exists() and trades_path.exists() and summary_path.exists():
        equity = pd.read_csv(equity_path, parse_dates=["date"]).set_index("date")
        trades = pd.read_csv(trades_path)
        stats = pd.read_csv(summary_path).iloc[0].to_dict()
        print(f"{params.exp_tag}: skip existing")
    else:
        equity, trades, audit = run_and_save(params, OUT)
        stats = audit["stats"]

    bench = benchmark_stats(equity)
    diag = trade_diagnostics(trades)
    row = {
        "tag": params.exp_tag,
        "profile": profile,
        "family": family,
        "variant": variant,
        "notes": notes,
        "start": params.start,
        "end": params.end,
        "annual_return": stats.get("annual_return"),
        "sharpe_ratio": stats.get("sharpe_ratio"),
        "max_drawdown": stats.get("max_drawdown"),
        "annual_volatility": stats.get("annual_volatility"),
        "total_return": stats.get("total_return"),
        "final_value": stats.get("final_value"),
        **bench,
        **diag,
        **param_snapshot(params),
    }
    row["alpha_vs_hs300"] = row["annual_return"] - row["benchmark_annual"]
    rows.append(row)


def make_profiles(selected: set[str]) -> dict[str, dict[str, Any]]:
    f2 = load_f2_pool()
    orig38 = sorted(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    f2_orig = sorted(set(f2) | set(orig38))
    pit = load_pit_pool()
    profiles: dict[str, dict[str, Any]] = {}
    if "F2_STATIC" in selected:
        profiles["F2_STATIC"] = {"etf_pool_ts": f2}
    if "F2_CAP" in selected:
        profiles["F2_CAP"] = {
            "pit_pools": pit,
            "core_pool": f2,
            "dynamic_fusion_mode": "capped",
            "dynamic_max_slots": 1,
            "dynamic_max_total_weight": 0.10,
            "dynamic_score_margin": 0.05,
            "dynamic_overheat_threshold": 0.10,
            "dynamic_overheat_penalty": 0.50,
        }
    if "F2O_CAP" in selected:
        profiles["F2O_CAP"] = {
            "pit_pools": pit,
            "core_pool": f2_orig,
            "dynamic_fusion_mode": "capped",
            "dynamic_max_slots": 1,
            "dynamic_max_total_weight": 0.20,
            "dynamic_score_margin": 0.10,
            "dynamic_overheat_threshold": 0.10,
            "dynamic_overheat_penalty": 0.50,
        }
    return profiles


def variants() -> list[tuple[str, str, dict[str, Any], str]]:
    out: list[tuple[str, str, dict[str, Any], str]] = []
    out.append(("BASE", "BASE", {}, "baseline"))

    for h in [3, 4, 5, 6, 8]:
        out.append(("HOLD", f"H{h}", {"holdings_num": h}, f"holdings_num={h}"))

    for sl in [0.90, 0.93, 0.95, 0.97, 0.99]:
        out.append(("STOP", f"SL{int(sl * 100)}", {"stop_loss": sl}, f"fixed stop loss={sl:.2f}"))
    out.append(("STOP", "SL_OFF", {"stop_loss": 0.0}, "disable fixed stop loss"))

    for mult in [1.5, 2.0, 2.5, 3.0]:
        out.append(("ATR", f"ATR{str(mult).replace('.', 'p')}", {"use_atr_stop_loss": True, "atr_multiplier": mult}, f"ATR multiplier={mult}"))
    out.append(("ATR", "ATR_OFF", {"use_atr_stop_loss": False}, "disable ATR stop"))

    out.append(("SHORT_MOM", "SM_OFF", {"use_short_momentum_filter": False}, "disable short momentum hard filter"))
    for th in [-0.50, -0.25, 0.0, 0.25, 0.50]:
        tag = f"SM{str(th).replace('-', 'N').replace('.', 'p')}"
        out.append(("SHORT_MOM", tag, {"use_short_momentum_filter": True, "short_momentum_threshold": th}, f"short annualized momentum threshold={th:.2f}"))

    for lb in [20, 25, 30, 40]:
        out.append(("LOOKBACK", f"LB{lb}", {"lookback_days": lb}, f"regression lookback={lb} trading days"))

    for interval in [1, 2, 3, 5]:
        out.append(("REBAL", f"RB{interval}", {"rebalance_interval": interval}, f"rebalance every {interval} trading day(s)"))

    ma_cases = [
        (20, 1.10, 0.50),
        (20, 1.15, 0.50),
        (20, 1.20, 0.50),
        (40, 1.15, 0.50),
        (60, 1.15, 0.50),
        (20, 1.15, 0.30),
        (20, 1.15, 0.70),
    ]
    for ma, threshold, penalty in ma_cases:
        tag = f"MR{ma}_T{int(threshold * 100)}_P{int(penalty * 100)}"
        out.append(("MA_OVERHEAT", tag, {
            "mr_ma_period": ma,
            "mr_threshold": threshold,
            "mr_penalty": penalty,
        }, f"penalize price/MA{ma}>={threshold:.2f} by x{penalty:.2f}"))

    return out


def build_report(manifest: pd.DataFrame, out_path: Path) -> None:
    def pct(x: float) -> str:
        return "" if pd.isna(x) else f"{x * 100:.2f}%"

    lines = [
        "# ETF Loop Hyperparameter Ablation",
        "",
        f"- window: `{START}` to `{END}`",
        "- execution: signal close -> next trading day open; missing next open is skipped",
        "- benchmark: HS300 (`sh000300`)",
        "- profiles: `F2_STATIC`, `F2_CAP`, `F2O_CAP` where selected",
        "",
        "## Best By Sharpe",
        "",
    ]
    best = manifest.sort_values(["sharpe_ratio", "annual_return"], ascending=False).head(20)
    lines.append("| rank | tag | profile | family | ann | sharpe | dd | win | alpha | trades |")
    lines.append("|---:|---|---|---|---:|---:|---:|---:|---:|---:|")
    for i, r in enumerate(best.to_dict("records"), start=1):
        lines.append(
            f"| {i} | `{r['tag']}` | {r['profile']} | {r['family']} | "
            f"{pct(r['annual_return'])} | {r['sharpe_ratio']:.2f} | {pct(r['max_drawdown'])} | "
            f"{pct(r['win_rate'])} | {pct(r['alpha_vs_hs300'])} | {int(r['trade_count'])} |"
        )

    lines += ["", "## Family Winners", ""]
    lines.append("| profile | family | tag | ann | sharpe | dd | alpha | notes |")
    lines.append("|---|---|---|---:|---:|---:|---:|---|")
    winners = (
        manifest.sort_values(["profile", "family", "sharpe_ratio", "annual_return"], ascending=[True, True, False, False])
        .groupby(["profile", "family"], as_index=False)
        .head(1)
    )
    for r in winners.to_dict("records"):
        lines.append(
            f"| {r['profile']} | {r['family']} | `{r['tag']}` | {pct(r['annual_return'])} | "
            f"{r['sharpe_ratio']:.2f} | {pct(r['max_drawdown'])} | {pct(r['alpha_vs_hs300'])} | {r['notes']} |"
        )

    lines += ["", "## Baselines", ""]
    base = manifest[manifest["family"].eq("BASE")].sort_values("profile")
    lines.append("| profile | tag | ann | sharpe | dd | final | hs300 ann | alpha |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for r in base.to_dict("records"):
        lines.append(
            f"| {r['profile']} | `{r['tag']}` | {pct(r['annual_return'])} | {r['sharpe_ratio']:.2f} | "
            f"{pct(r['max_drawdown'])} | {r['final_value']:.0f} | {pct(r['benchmark_annual'])} | {pct(r['alpha_vs_hs300'])} |"
        )

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ETF Loop hyperparameter ablation")
    parser.add_argument("--profiles", default="F2_STATIC,F2_CAP,F2O_CAP")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    selected_profiles = {p.strip() for p in args.profiles.split(",") if p.strip()}
    profiles = make_profiles(selected_profiles)
    rows: list[dict] = []

    for profile, profile_kwargs in profiles.items():
        for family, variant, kwargs, notes in variants():
            params_kwargs = dict(profile_kwargs)
            params_kwargs.update(kwargs)
            holdings = int(params_kwargs.get("holdings_num", 5))
            tag = f"ABL_{profile}_{family}_{variant}"
            params = EngineParams(
                start=START,
                end=END,
                holdings_num=holdings,
                exp_tag=tag,
                **{k: v for k, v in params_kwargs.items() if k != "holdings_num"},
            )
            run_case(rows, params, profile, family, variant, notes, args.force)

    manifest = pd.DataFrame(rows)
    manifest_path = OUT / "hyperparam_ablation_manifest.csv"
    report_path = OUT / "hyperparam_ablation_report.md"
    manifest.to_csv(manifest_path, index=False)
    build_report(manifest, report_path)

    print("\nSaved:", manifest_path)
    print("Saved:", report_path)
    cols = ["tag", "annual_return", "sharpe_ratio", "max_drawdown", "win_rate", "alpha_vs_hs300", "trade_count"]
    print(manifest.sort_values(["sharpe_ratio", "annual_return"], ascending=False)[cols].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
