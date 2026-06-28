#!/usr/bin/env python3
"""Attribution analysis for selected ETF Loop experiments."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
OUT = BASE_DIR / "outputs" / "etf_loop"
CACHE = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity"
START = "20130701"
END = "20260625"
TAGS = [
    "ABL_F2_CAP_MA_OVERHEAT_MR60_T114_P50",
    "ABL_F2O_CAP_SHORT_MOM_SM0p25",
    "EXEC_F2_CAP_MA60_OPEN_D1",
]


def find_file(kind: str, tag: str) -> Path:
    files = sorted(OUT.glob(f"etf_loop_{kind}_{tag}_h*_{START}_{END}.csv"))
    if not files:
        files = sorted(OUT.glob(f"etf_loop_{kind}_{tag}_h*_20180101_20260625.csv"))
    if not files:
        raise FileNotFoundError(f"{kind} for {tag}")
    return files[0]


def load_names() -> dict[str, str]:
    path = CACHE / "fund_basic_etf.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype={"ts_code": str})
    return dict(zip(df["ts_code"].astype(str), df["name"].astype(str), strict=False))


def fifo_pnl(trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    lots: dict[str, list[dict[str, float]]] = {}
    rows = []
    for _, row in trades.sort_values(["trade_date", "date"]).iterrows():
        code = str(row.get("ts_code", ""))
        shares = int(pd.to_numeric(row.get("shares", 0), errors="coerce") or 0)
        if shares <= 0:
            continue
        if row.get("action") == "BUY":
            cost = float(pd.to_numeric(row.get("net_cost", row.get("gross_cost", 0.0)), errors="coerce") or 0.0)
            lots.setdefault(code, []).append({
                "shares": shares,
                "cost_per_share": cost / shares if shares else 0.0,
                "entry_date": row.get("trade_date"),
            })
        elif row.get("action") == "SELL":
            proceeds = float(pd.to_numeric(row.get("net_proceeds", row.get("gross_proceeds", 0.0)), errors="coerce") or 0.0)
            remaining = shares
            matched_cost = 0.0
            matched_shares = 0
            first_entry = ""
            while remaining > 0 and lots.get(code):
                lot = lots[code][0]
                m = min(remaining, int(lot["shares"]))
                if not first_entry:
                    first_entry = str(lot.get("entry_date", ""))
                matched_cost += m * float(lot["cost_per_share"])
                matched_shares += m
                lot["shares"] -= m
                remaining -= m
                if lot["shares"] <= 0:
                    lots[code].pop(0)
            if matched_shares:
                matched_proceeds = proceeds * matched_shares / shares
                pnl = matched_proceeds - matched_cost
                rows.append({
                    "ts_code": code,
                    "entry_date": first_entry,
                    "exit_date": row.get("trade_date"),
                    "shares": matched_shares,
                    "cost": matched_cost,
                    "proceeds": matched_proceeds,
                    "pnl": pnl,
                    "return_on_cost": pnl / matched_cost if matched_cost > 0 else np.nan,
                    "reason": row.get("reason", ""),
                })
    trade_pnl = pd.DataFrame(rows)
    if trade_pnl.empty:
        return trade_pnl, pd.DataFrame()
    by_code = trade_pnl.groupby("ts_code").agg(
        pnl=("pnl", "sum"),
        trades=("pnl", "size"),
        wins=("pnl", lambda s: int((s > 0).sum())),
        gross_cost=("cost", "sum"),
    ).reset_index()
    by_code["win_rate"] = by_code["wins"] / by_code["trades"]
    by_code["pnl_per_cost"] = by_code["pnl"] / by_code["gross_cost"]
    return trade_pnl, by_code.sort_values("pnl", ascending=False)


def yearly(equity: pd.DataFrame) -> pd.DataFrame:
    nav = equity["portfolio_value"].copy()
    rows = []
    for year, g in nav.groupby(nav.index.year):
        if len(g) < 2:
            continue
        daily = g.pct_change().dropna()
        ann = daily.mean() * 252.0
        vol = daily.std() * np.sqrt(252.0)
        rows.append({
            "year": int(year),
            "return": float(g.iloc[-1] / g.iloc[0] - 1),
            "annual_return": float(ann),
            "sharpe": float(ann / vol) if vol > 0 else 0.0,
            "max_drawdown": float((g / g.cummax() - 1).min()),
        })
    return pd.DataFrame(rows)


def pct(x: float) -> str:
    return "" if pd.isna(x) else f"{x * 100:.2f}%"


def main() -> None:
    names = load_names()
    lines = ["# ETF Loop Attribution", ""]
    summary_rows = []
    for tag in TAGS:
        try:
            trades = pd.read_csv(find_file("targets", tag), dtype={"ts_code": str})
            equity = pd.read_csv(find_file("equity", tag), parse_dates=["date"]).set_index("date")
        except FileNotFoundError:
            continue
        trade_pnl, by_code = fifo_pnl(trades)
        yr = yearly(equity)
        if not by_code.empty:
            top_pnl = float(by_code["pnl"].head(5).sum())
            total_pnl = float(by_code["pnl"].sum())
            concentration = top_pnl / total_pnl if total_pnl > 0 else np.nan
        else:
            concentration = np.nan
        summary_rows.append({
            "tag": tag,
            "round_trips": len(trade_pnl),
            "positive_years": int((yr["return"] > 0).sum()) if not yr.empty else 0,
            "negative_years": int((yr["return"] <= 0).sum()) if not yr.empty else 0,
            "top5_etf_pnl_share": concentration,
        })

        lines += [f"## {tag}", ""]
        lines += ["### ETF Contribution", ""]
        lines.append("| rank | code | name | pnl | trades | win_rate | pnl/cost |")
        lines.append("|---:|---|---|---:|---:|---:|---:|")
        for i, r in enumerate(by_code.head(15).to_dict("records"), start=1):
            lines.append(
                f"| {i} | {r['ts_code']} | {names.get(r['ts_code'], '')} | {r['pnl']:.0f} | "
                f"{int(r['trades'])} | {pct(r['win_rate'])} | {pct(r['pnl_per_cost'])} |"
            )
        lines += ["", "### Year Contribution", ""]
        lines.append("| year | return | annual | sharpe | dd |")
        lines.append("|---:|---:|---:|---:|---:|")
        for r in yr.to_dict("records"):
            lines.append(
                f"| {int(r['year'])} | {pct(r['return'])} | {pct(r['annual_return'])} | "
                f"{r['sharpe']:.2f} | {pct(r['max_drawdown'])} |"
            )
        lines += ["", "### Top Winning Trades", ""]
        lines.append("| code | name | entry | exit | pnl | return_on_cost | reason |")
        lines.append("|---|---|---|---|---:|---:|---|")
        for r in trade_pnl.sort_values("pnl", ascending=False).head(15).to_dict("records"):
            lines.append(
                f"| {r['ts_code']} | {names.get(r['ts_code'], '')} | {r['entry_date']} | {r['exit_date']} | "
                f"{r['pnl']:.0f} | {pct(r['return_on_cost'])} | {r['reason']} |"
            )
        lines.append("")

    summary = pd.DataFrame(summary_rows)
    summary_path = OUT / "attribution_summary.csv"
    report_path = OUT / "attribution_report.md"
    summary.to_csv(summary_path, index=False)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print("Saved:", summary_path)
    print("Saved:", report_path)
    if not summary.empty:
        print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
