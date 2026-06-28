#!/usr/bin/env python3
"""Paper/live vs backtest reconciliation helper for ETF Loop."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PAPER = BASE_DIR / "outputs" / "etf_loop_paper"
DEFAULT_BACKTEST = BASE_DIR / "outputs" / "etf_loop"


def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile paper/live trades with backtest trades")
    parser.add_argument("--paper-dir", default=str(DEFAULT_PAPER))
    parser.add_argument("--backtest-trades", required=False, help="Backtest target/trade CSV to compare against")
    args = parser.parse_args()

    paper_dir = Path(args.paper_dir)
    orders = load_csv(paper_dir / "orders.csv")
    trades = load_csv(paper_dir / "trades.csv")
    nav = load_csv(paper_dir / "nav.csv")

    lines = [
        "# ETF Loop Paper/Live Reconciliation",
        "",
        f"- paper_dir: `{paper_dir}`",
        "",
    ]
    if orders.empty and trades.empty:
        lines += [
            "No paper/live orders or trades found yet.",
            "",
            "Required daily paper/live fields:",
            "",
            "- signal generation timestamp",
            "- data snapshot date and latest cached trade date",
            "- planned signal_date and trade_date",
            "- ts_code, name, action, target_weight, reason, score",
            "- theoretical execution price from backtest assumption",
            "- actual quote/open/VWAP/filled price",
            "- fill status, filled shares, rejected shares, reject reason",
            "- slippage vs theoretical price",
            "- post-trade cash, market value, NAV",
        ]
    else:
        lines += [
            f"- orders: `{len(orders)}`",
            f"- trades: `{len(trades)}`",
            f"- nav rows: `{len(nav)}`",
            "",
        ]
        if not trades.empty:
            filled = trades[trades.get("status", "").astype(str).eq("FILLED")] if "status" in trades.columns else trades
            lines += [
                "## Fill Summary",
                "",
                f"- filled rows: `{len(filled)}`",
            ]
            if "price" in filled.columns and "ts_code" in filled.columns:
                lines.append(f"- traded ETFs: `{filled['ts_code'].nunique()}`")

    if args.backtest_trades:
        bt = load_csv(Path(args.backtest_trades))
        lines += ["", "## Backtest Comparison", ""]
        if bt.empty or orders.empty:
            lines.append("Backtest or paper orders missing; cannot compare.")
        else:
            key_cols = ["signal_date", "trade_date", "ts_code", "action"]
            missing_cols = [c for c in key_cols if c not in orders.columns or c not in bt.columns]
            if missing_cols:
                lines.append(f"Missing comparable columns: `{missing_cols}`")
            else:
                p = orders[key_cols].drop_duplicates()
                b = bt.rename(columns={"date": "signal_date"})[key_cols].drop_duplicates()
                merged = p.merge(b, on=key_cols, how="outer", indicator=True)
                lines += [
                    f"- matched orders: `{int(merged['_merge'].eq('both').sum())}`",
                    f"- paper only: `{int(merged['_merge'].eq('left_only').sum())}`",
                    f"- backtest only: `{int(merged['_merge'].eq('right_only').sum())}`",
                ]

    out = paper_dir / "reconciliation_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print("Saved:", out)


if __name__ == "__main__":
    main()
