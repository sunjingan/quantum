#!/usr/bin/env python3
"""Diagnose why adding the G2 PIT dynamic pool changes performance."""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from strategies.etf_loop_strategy import ETFDailyStore, FULL_ETF_POOL_JQ, _jq_to_ts
from strategies.sector_prosperity import SectorProsperityCache


START = "2013-07-01"
END = "2026-06-25"
OUT = BASE_DIR / "outputs" / "etf_loop"


def load_f2_orig_pool() -> set[str]:
    f2_path = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity" / "etf_pool_F2_v3.csv"
    f2 = set(pd.read_csv(f2_path, dtype={"ts_code": str})["ts_code"].astype(str))
    orig = set(_jq_to_ts(c) for c in FULL_ETF_POOL_JQ)
    return f2 | orig


def load_g2_union() -> set[str]:
    path = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity" / "etf_pool_G2_PIT_monthly.pkl"
    with open(path, "rb") as f:
        pools = pickle.load(f)
    return set().union(*(set(v) for v in pools.values()))


def trade_path(tag: str) -> Path:
    return OUT / f"etf_loop_targets_{tag}_h5_{START.replace('-', '')}_{END.replace('-', '')}.csv"


def equity_path(tag: str) -> Path:
    return OUT / f"etf_loop_equity_{tag}_h5_{START.replace('-', '')}_{END.replace('-', '')}.csv"


def cashflow_pnl(trades: pd.DataFrame, store: ETFDailyStore, final_date: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for code, g in trades.groupby("ts_code"):
        buy_net = float(g.loc[g["action"] == "BUY", "net_cost"].fillna(0).sum())
        sell_net = float(g.loc[g["action"] == "SELL", "net_proceeds"].fillna(0).sum())
        shares = int(g.loc[g["action"] == "BUY", "shares"].fillna(0).sum()
                     - g.loc[g["action"] == "SELL", "shares"].fillna(0).sum())
        px = store.latest_price(code, final_date)
        final_mv = shares * px if shares > 0 and not np.isnan(px) else 0.0
        rows.append({
            "ts_code": code,
            "buy_net": buy_net,
            "sell_net": sell_net,
            "final_mv": final_mv,
            "ending_shares": shares,
            "pnl": sell_net + final_mv - buy_net,
            "turnover_buy": buy_net,
            "trades": len(g),
            "buys": int((g["action"] == "BUY").sum()),
            "sells": int((g["action"] == "SELL").sum()),
        })
    return pd.DataFrame(rows).sort_values("pnl")


def future_return(store: ETFDailyStore, code: str, date: pd.Timestamp, horizon: int) -> float:
    if code not in store.close.columns:
        return np.nan
    s = store.close[code].dropna()
    if s.empty:
        return np.nan
    pos = s.index.searchsorted(date, side="left")
    if pos >= len(s):
        return np.nan
    end = min(pos + horizon, len(s) - 1)
    if end <= pos:
        return np.nan
    return float(s.iloc[end] / s.iloc[pos] - 1.0)


def prior_return(store: ETFDailyStore, code: str, date: pd.Timestamp, horizon: int) -> float:
    if code not in store.close.columns:
        return np.nan
    s = store.close[code].dropna()
    pos = s.index.searchsorted(date, side="right") - 1
    start = pos - horizon
    if start < 0 or pos <= start:
        return np.nan
    return float(s.iloc[pos] / s.iloc[start] - 1.0)


def round_trips(trades: pd.DataFrame, store: ETFDailyStore, dynamic_only: set[str]) -> pd.DataFrame:
    rows = []
    for code, g in trades.sort_values("trade_date").groupby("ts_code"):
        lots: list[dict] = []
        for _, r in g.iterrows():
            action = r["action"]
            shares = int(r["shares"])
            if action == "BUY":
                lots.append({
                    "shares": shares,
                    "entry_date": pd.Timestamp(r["trade_date"]),
                    "entry_price": float(r["price"]),
                    "entry_score": float(r.get("score", np.nan)),
                })
                continue

            remaining = shares
            exit_date = pd.Timestamp(r["trade_date"])
            exit_price = float(r["price"])
            while remaining > 0 and lots:
                lot = lots[0]
                take = min(remaining, lot["shares"])
                entry_price = lot["entry_price"]
                rows.append({
                    "ts_code": code,
                    "is_dynamic_only": code in dynamic_only,
                    "entry_date": lot["entry_date"],
                    "exit_date": exit_date,
                    "holding_days": (exit_date - lot["entry_date"]).days,
                    "shares": take,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "gross_return": exit_price / entry_price - 1.0,
                    "entry_score": lot["entry_score"],
                    "prior_20d_return": prior_return(store, code, lot["entry_date"], 20),
                    "post_sell_20d_return": future_return(store, code, exit_date, 20),
                    "post_sell_60d_return": future_return(store, code, exit_date, 60),
                })
                lot["shares"] -= take
                remaining -= take
                if lot["shares"] <= 0:
                    lots.pop(0)
    return pd.DataFrame(rows)


def main() -> None:
    static_tag = "FINAL13_F2v3_ORIG38"
    fused_tag = "FINAL13_F2v3_ORIG38_G2PIT"
    static_pool = load_f2_orig_pool()
    dynamic_only = load_g2_union() - static_pool

    static_trades = pd.read_csv(trade_path(static_tag), parse_dates=["date", "trade_date"])
    fused_trades = pd.read_csv(trade_path(fused_tag), parse_dates=["date", "trade_date"])
    all_codes = sorted(set(static_trades["ts_code"]) | set(fused_trades["ts_code"]) | dynamic_only | static_pool)
    store = ETFDailyStore(
        SectorProsperityCache(BASE_DIR / "config" / "tushare_token.txt", BASE_DIR / "data" / "tushare_cache"),
        all_codes, START, END,
    )
    final_date = pd.read_csv(equity_path(fused_tag), parse_dates=["date"])["date"].max()

    static_pnl = cashflow_pnl(static_trades, store, final_date)
    static_pnl["strategy"] = static_tag
    static_pnl["is_dynamic_only"] = False

    fused_pnl = cashflow_pnl(fused_trades, store, final_date)
    fused_pnl["strategy"] = fused_tag
    fused_pnl["is_dynamic_only"] = fused_pnl["ts_code"].isin(dynamic_only)
    fused_pnl["is_static_pool"] = fused_pnl["ts_code"].isin(static_pool)

    rt = round_trips(fused_trades, store, dynamic_only)

    by_group = fused_pnl.groupby("is_dynamic_only").agg(
        n_codes=("ts_code", "nunique"),
        pnl=("pnl", "sum"),
        buy_net=("buy_net", "sum"),
        trades=("trades", "sum"),
        buys=("buys", "sum"),
    ).reset_index()
    rt_group = rt.groupby("is_dynamic_only").agg(
        round_trips=("gross_return", "size"),
        avg_return=("gross_return", "mean"),
        median_return=("gross_return", "median"),
        win_rate=("gross_return", lambda x: float((x > 0).mean())),
        avg_holding_days=("holding_days", "mean"),
        avg_prior_20d=("prior_20d_return", "mean"),
        avg_post_sell_20d=("post_sell_20d_return", "mean"),
        avg_post_sell_60d=("post_sell_60d_return", "mean"),
    ).reset_index()

    common = static_pnl[["ts_code", "pnl", "buy_net", "trades"]].merge(
        fused_pnl[["ts_code", "pnl", "buy_net", "trades", "is_dynamic_only"]],
        on="ts_code", how="outer", suffixes=("_static", "_fused"),
    ).fillna(0)
    common["pnl_delta_fused_minus_static"] = common["pnl_fused"] - common["pnl_static"]
    common["buy_delta_fused_minus_static"] = common["buy_net_fused"] - common["buy_net_static"]

    OUT.mkdir(parents=True, exist_ok=True)
    fused_pnl.to_csv(OUT / "dynamic_pool_fused_code_pnl.csv", index=False)
    static_pnl.to_csv(OUT / "dynamic_pool_static_code_pnl.csv", index=False)
    common.sort_values("pnl_delta_fused_minus_static").to_csv(OUT / "dynamic_pool_common_code_delta.csv", index=False)
    rt.to_csv(OUT / "dynamic_pool_round_trips.csv", index=False)
    by_group.to_csv(OUT / "dynamic_pool_group_pnl.csv", index=False)
    rt_group.to_csv(OUT / "dynamic_pool_roundtrip_summary.csv", index=False)

    print("Dynamic-only codes in G2 but not static64:", len(dynamic_only))
    print("\nCash-flow PnL by group in fused strategy:")
    print(by_group.to_string(index=False))
    print("\nRound-trip behavior:")
    print(rt_group.to_string(index=False))
    print("\nWorst fused-minus-static code deltas:")
    print(common.sort_values("pnl_delta_fused_minus_static").head(12).to_string(index=False))
    print("\nBest dynamic-only code PnL:")
    print(fused_pnl[fused_pnl["is_dynamic_only"]].sort_values("pnl", ascending=False).head(10).to_string(index=False))
    print("\nWorst dynamic-only code PnL:")
    print(fused_pnl[fused_pnl["is_dynamic_only"]].sort_values("pnl").head(10).to_string(index=False))


if __name__ == "__main__":
    main()
