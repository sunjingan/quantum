#!/usr/bin/env python3
"""Monthly ETF attribution for the 2026 no-warmup baseline backtest."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from strategies.etf_loop_strategy import ETFDailyStore, SectorProsperityCache


OUT = BASE_DIR / "outputs" / "etf_loop"
REPORT_DIR = OUT / "F2_CAP_MA60_deep_dive"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

TAG = "VAL_YR26_NOWARMUP_F2_CAP_MA60"
DATA_START = "2025-10-01"
END = "2026-06-25"
ACTIVE_START = "2026-01-01"
HIGH_RANK_THRESHOLD = 0.8
LOW_RANK_THRESHOLD = 0.2


def load_names() -> dict[str, str]:
    path = BASE_DIR / "data" / "tushare_cache" / "sector_prosperity" / "fund_basic_etf.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype={"ts_code": str})
    return dict(zip(df["ts_code"].astype(str), df["name"].astype(str), strict=False))


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    equity = pd.read_csv(
        OUT / f"etf_loop_equity_{TAG}_h5_20251001_20260625.csv",
        parse_dates=["date"],
    ).sort_values("date")
    trades = pd.read_csv(
        OUT / f"etf_loop_targets_{TAG}_h5_20251001_20260625.csv",
        parse_dates=["date", "trade_date"],
        dtype={"ts_code": str},
    ).sort_values(["trade_date", "date"])
    return equity, trades


def build_store(codes: list[str]) -> ETFDailyStore:
    cache = SectorProsperityCache(
        BASE_DIR / "config" / "tushare_token.txt",
        BASE_DIR / "data" / "tushare_cache",
    )
    return ETFDailyStore(cache, codes, DATA_START, "2026-06-27")


def month_return_table(equity: pd.DataFrame) -> pd.DataFrame:
    active = equity[equity["date"] >= pd.Timestamp(ACTIVE_START)].copy()
    active["month"] = active["date"].dt.to_period("M").astype(str)
    rows: list[dict[str, float | str]] = []
    for month, g in active.groupby("month", sort=True):
        start_value = float(g["portfolio_value"].iloc[0])
        end_value = float(g["portfolio_value"].iloc[-1])
        first_prev = active.loc[active["date"] < g["date"].iloc[0], "portfolio_value"]
        month_base = float(first_prev.iloc[-1]) if not first_prev.empty else start_value
        rows.append(
            {
                "month": month,
                "month_start_value": month_base,
                "month_first_value": start_value,
                "month_end_value": end_value,
                "month_pnl": end_value - month_base,
                "month_return": end_value / month_base - 1.0,
                "days": int(len(g)),
            }
        )
    return pd.DataFrame(rows)


def compute_daily_contributions(
    equity: pd.DataFrame, trades: pd.DataFrame, store: ETFDailyStore
) -> pd.DataFrame:
    active_eq = equity[equity["date"] >= pd.Timestamp(ACTIVE_START)].copy().sort_values("date")
    codes = sorted(trades["ts_code"].dropna().astype(str).unique())
    closes = store.signal_close.reindex(active_eq["date"]).ffill()

    shares = {code: 0.0 for code in codes}
    prev_market_value = {code: 0.0 for code in codes}
    rows: list[dict[str, object]] = []

    prev_portfolio_value: float | None = None
    for date in active_eq["date"]:
        day_trades = trades[trades["trade_date"] == date]
        buy_cost = day_trades[day_trades["action"] == "BUY"].groupby("ts_code")["net_cost"].sum().to_dict()
        sell_proceeds = (
            day_trades[day_trades["action"] == "SELL"].groupby("ts_code")["net_proceeds"].sum().to_dict()
        )
        buy_count = day_trades[day_trades["action"] == "BUY"].groupby("ts_code").size().to_dict()
        sell_count = day_trades[day_trades["action"] == "SELL"].groupby("ts_code").size().to_dict()
        buy_shares = day_trades[day_trades["action"] == "BUY"].groupby("ts_code")["shares"].sum().to_dict()
        sell_shares = day_trades[day_trades["action"] == "SELL"].groupby("ts_code")["shares"].sum().to_dict()

        for _, trade in day_trades.iterrows():
            code = str(trade["ts_code"])
            traded_shares = float(trade["shares"])
            if trade["action"] == "BUY":
                shares[code] = shares.get(code, 0.0) + traded_shares
            else:
                shares[code] = shares.get(code, 0.0) - traded_shares

        total_contrib = 0.0
        for code in codes:
            px = closes.at[date, code] if code in closes.columns else np.nan
            market_value = shares[code] * float(px) if pd.notna(px) and float(px) > 0 else 0.0
            contrib = (
                market_value
                - prev_market_value.get(code, 0.0)
                + float(sell_proceeds.get(code, 0.0))
                - float(buy_cost.get(code, 0.0))
            )
            if (
                abs(contrib) > 1e-9
                or prev_market_value.get(code, 0.0) != 0.0
                or shares[code] != 0.0
                or code in buy_cost
                or code in sell_proceeds
            ):
                rows.append(
                    {
                        "date": date,
                        "month": date.to_period("M").strftime("%Y-%m"),
                        "ts_code": code,
                        "contribution": contrib,
                        "end_market_value": market_value,
                        "prev_market_value": prev_market_value.get(code, 0.0),
                        "end_shares": shares[code],
                        "buy_cost": float(buy_cost.get(code, 0.0)),
                        "sell_proceeds": float(sell_proceeds.get(code, 0.0)),
                        "buy_trades": int(buy_count.get(code, 0)),
                        "sell_trades": int(sell_count.get(code, 0)),
                        "buy_shares": float(buy_shares.get(code, 0.0)),
                        "sell_shares": float(sell_shares.get(code, 0.0)),
                    }
                )
            prev_market_value[code] = market_value
            total_contrib += contrib

        portfolio_value = float(active_eq.loc[active_eq["date"] == date, "portfolio_value"].iloc[0])
        if prev_portfolio_value is not None:
            nav_delta = portfolio_value - prev_portfolio_value
            if abs(total_contrib - nav_delta) > 1.0:
                raise RuntimeError(
                    f"Contribution mismatch on {date.date()}: model={total_contrib:.4f}, nav={nav_delta:.4f}"
                )
        prev_portfolio_value = portfolio_value

    return pd.DataFrame(rows)


def trade_rank_context(
    store: ETFDailyStore, code: str, signal_date: pd.Timestamp, price: float, window: int = 20
) -> dict[str, object]:
    if code not in store.signal_close.columns:
        return {"window_low": np.nan, "window_high": np.nan, "price_rank": np.nan, "near_high": False, "near_low": False}
    series = store.signal_close[code].dropna().loc[:signal_date]
    if series.empty:
        return {"window_low": np.nan, "window_high": np.nan, "price_rank": np.nan, "near_high": False, "near_low": False}
    hist = series.tail(window)
    window_low = float(hist.min())
    window_high = float(hist.max())
    if window_high <= window_low:
        price_rank = np.nan
    else:
        price_rank = float((price - window_low) / (window_high - window_low))
    return {
        "window_low": window_low,
        "window_high": window_high,
        "price_rank": price_rank,
        "near_high": bool(pd.notna(price_rank) and price_rank >= HIGH_RANK_THRESHOLD),
        "near_low": bool(pd.notna(price_rank) and price_rank <= LOW_RANK_THRESHOLD),
    }


def build_trade_context_table(
    trades: pd.DataFrame, store: ETFDailyStore, selected: pd.DataFrame
) -> pd.DataFrame:
    selected_keys = {(str(r["month"]), str(r["ts_code"])) for _, r in selected.iterrows()}
    rows: list[dict[str, object]] = []
    for _, trade in trades.iterrows():
        month = pd.Timestamp(trade["trade_date"]).to_period("M").strftime("%Y-%m")
        key = (month, str(trade["ts_code"]))
        if key not in selected_keys:
            continue
        context = trade_rank_context(store, str(trade["ts_code"]), pd.Timestamp(trade["date"]), float(trade["price"]))
        rows.append(
            {
                "month": month,
                "ts_code": str(trade["ts_code"]),
                "action": str(trade["action"]),
                "date": pd.Timestamp(trade["date"]).date().isoformat(),
                "trade_date": pd.Timestamp(trade["trade_date"]).date().isoformat(),
                "price": float(trade["price"]),
                "shares": float(trade["shares"]),
                "reason": str(trade.get("reason", "")),
                **context,
            }
        )
    return pd.DataFrame(rows)


def build_fifo_round_trips(trades: pd.DataFrame, store: ETFDailyStore) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for code, g in trades.sort_values(["trade_date", "date"]).groupby("ts_code"):
        lots: list[dict[str, object]] = []
        for _, trade in g.iterrows():
            action = str(trade["action"])
            shares = float(trade["shares"])
            trade_date = pd.Timestamp(trade["trade_date"])
            signal_date = pd.Timestamp(trade["date"])
            price = float(trade["price"])
            net_cost = float(trade.get("net_cost", 0.0) or 0.0)
            net_proceeds = float(trade.get("net_proceeds", 0.0) or 0.0)
            context = trade_rank_context(store, code, signal_date, price)

            if action == "BUY":
                lots.append(
                    {
                        "shares": shares,
                        "trade_date": trade_date,
                        "signal_date": signal_date,
                        "price": price,
                        "net_cost": net_cost,
                        "reason": str(trade.get("reason", "")),
                        "rank": context["price_rank"],
                    }
                )
                continue

            remaining = shares
            sell_alloc_cost = net_proceeds / shares if shares > 0 else 0.0
            while remaining > 0 and lots:
                lot = lots[0]
                take = min(remaining, float(lot["shares"]))
                buy_alloc_cost = float(lot["net_cost"]) / float(lot["shares"]) if float(lot["shares"]) > 0 else 0.0
                rows.append(
                    {
                        "ts_code": code,
                        "buy_signal_date": lot["signal_date"].date().isoformat(),
                        "buy_trade_date": lot["trade_date"].date().isoformat(),
                        "buy_price": float(lot["price"]),
                        "buy_rank20": float(lot["rank"]) if pd.notna(lot["rank"]) else np.nan,
                        "buy_reason": lot["reason"],
                        "sell_signal_date": signal_date.date().isoformat(),
                        "sell_trade_date": trade_date.date().isoformat(),
                        "sell_price": price,
                        "sell_rank20": context["price_rank"],
                        "sell_reason": str(trade.get("reason", "")),
                        "shares": float(take),
                        "holding_days": int((trade_date - pd.Timestamp(lot["trade_date"])).days),
                        "gross_pnl": (price - float(lot["price"])) * float(take),
                        "net_pnl": (sell_alloc_cost - buy_alloc_cost) * float(take),
                        "buy_near_high": bool(pd.notna(lot["rank"]) and float(lot["rank"]) >= HIGH_RANK_THRESHOLD),
                        "sell_near_low": bool(pd.notna(context["price_rank"]) and context["price_rank"] <= LOW_RANK_THRESHOLD),
                    }
                )
                lot["shares"] = float(lot["shares"]) - float(take)
                remaining -= float(take)
                if float(lot["shares"]) <= 0:
                    lots.pop(0)
    return pd.DataFrame(rows)


def summarize_monthly(
    daily_contrib: pd.DataFrame, month_returns: pd.DataFrame, names: dict[str, str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    monthly_code = (
        daily_contrib.groupby(["month", "ts_code"], as_index=False)
        .agg(
            contribution=("contribution", "sum"),
            buy_cost=("buy_cost", "sum"),
            sell_proceeds=("sell_proceeds", "sum"),
            buy_trades=("buy_trades", "sum"),
            sell_trades=("sell_trades", "sum"),
            buy_shares=("buy_shares", "sum"),
            sell_shares=("sell_shares", "sum"),
            end_market_value=("end_market_value", "last"),
            end_shares=("end_shares", "last"),
        )
        .sort_values(["month", "contribution"], ascending=[True, False])
    )
    monthly_code["name"] = monthly_code["ts_code"].map(names).fillna(monthly_code["ts_code"])

    summary_rows: list[dict[str, object]] = []
    for _, month_row in month_returns.iterrows():
        month = str(month_row["month"])
        month_df = monthly_code[monthly_code["month"] == month].copy()
        top_pos = month_df.sort_values("contribution", ascending=False).head(5)
        top_neg = month_df.sort_values("contribution", ascending=True).head(5)
        summary_rows.append(
            {
                "month": month,
                "month_pnl": float(month_row["month_pnl"]),
                "month_return": float(month_row["month_return"]),
                "month_start_value": float(month_row["month_start_value"]),
                "month_end_value": float(month_row["month_end_value"]),
                "top_positive": " | ".join(
                    f"{r['name']}({r['ts_code']}): {r['contribution']:.0f}" for _, r in top_pos.iterrows()
                ),
                "top_negative": " | ".join(
                    f"{r['name']}({r['ts_code']}): {r['contribution']:.0f}" for _, r in top_neg.iterrows()
                ),
            }
        )
    return pd.DataFrame(summary_rows), monthly_code


def write_report(
    summary: pd.DataFrame,
    monthly_code: pd.DataFrame,
    trade_context: pd.DataFrame,
    june_round_trips: pd.DataFrame,
) -> None:
    report_path = REPORT_DIR / "2026_nowarmup_monthly_etf_attribution.md"
    lines = [
        "# 2026 No-Warmup Monthly ETF Attribution",
        "",
        f"- tag: `{TAG}`",
        "- portfolio: F2_CAP_MA60 baseline, next-day execution, no signal-date price fallback",
        "- window: 2026-01 to 2026-06",
        "- attribution method: close-to-close daily contribution aligned to engine equity; each ETF contribution = end-of-day market value change + sell proceeds - buy cost",
        "",
        "## Monthly Summary",
        "",
        "| Month | Return | PnL | Start | End |",
        "|---|---:|---:|---:|---:|",
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"| {row['month']} | {row['month_return']*100:+.2f}% | "
            f"{row['month_pnl']:,.0f} | {row['month_start_value']:,.0f} | {row['month_end_value']:,.0f} |"
        )

    for _, row in summary.iterrows():
        month = row["month"]
        month_losers = monthly_code[(monthly_code["month"] == month) & (monthly_code["contribution"] < 0)]
        month_losers = month_losers.sort_values("contribution", ascending=True).head(3)
        lines.extend(
            [
                "",
                f"## {month}",
                "",
                f"- Month return: {row['month_return']*100:+.2f}%",
                f"- Month PnL: {row['month_pnl']:,.0f}",
                f"- Start -> End: {row['month_start_value']:,.0f} -> {row['month_end_value']:,.0f}",
                "",
                "### Top Losers With Entry/Exit Context",
                "",
                "| ETF | Code | Contribution | Buy avg rank | Sell avg rank | Buy near-high | Sell near-low |",
                "|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for _, r in month_losers.iterrows():
            month_trades = trade_context[(trade_context["month"] == month) & (trade_context["ts_code"] == r["ts_code"])]
            buy_mask = month_trades["action"] == "BUY"
            sell_mask = month_trades["action"] == "SELL"
            buy_avg = float(month_trades.loc[buy_mask, "price_rank"].mean()) if buy_mask.any() else np.nan
            sell_avg = float(month_trades.loc[sell_mask, "price_rank"].mean()) if sell_mask.any() else np.nan
            buy_high = float(month_trades.loc[buy_mask, "near_high"].mean()) if buy_mask.any() else np.nan
            sell_low = float(month_trades.loc[sell_mask, "near_low"].mean()) if sell_mask.any() else np.nan
            lines.append(
                f"| {r['name']} | {r['ts_code']} | {r['contribution']:,.0f} | {buy_avg:.2f} | {sell_avg:.2f} | "
                f"{buy_high:.0%} | {sell_low:.0%} |"
            )

        for _, r in month_losers.iterrows():
            month_trades = trade_context[(trade_context["month"] == month) & (trade_context["ts_code"] == r["ts_code"])]
            lines.extend(
                [
                    "",
                    f"#### {r['name']} ({r['ts_code']})",
                    f"- Month contribution: {r['contribution']:,.0f}",
                    f"- Buys: {int((month_trades['action'] == 'BUY').sum())}, Sells: {int((month_trades['action'] == 'SELL').sum())}",
                    "",
                    "| Type | Signal Date | Exec Date | Price | Shares | Rank20 | Near High | Near Low | Reason |",
                    "|---|---|---|---:|---:|---:|---|---|---|",
                ]
            )
            for _, t in month_trades.sort_values(["trade_date", "date"]).iterrows():
                lines.append(
                    f"| {t['action']} | {t['date']} | {t['trade_date']} | {t['price']:.4f} | {t['shares']:.0f} | "
                    f"{t['price_rank']:.2f} | {str(bool(t['near_high']))} | {str(bool(t['near_low']))} | {t['reason']} |"
                )

        lines.extend(
            [
                "",
                "### Top Winners",
                "",
                "| ETF | Code | Contribution | Buy Trades | Sell Trades | Buy Cost | Sell Proceeds | End MV |",
                "|---|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        month_df = monthly_code[monthly_code["month"] == month]
        for _, r in month_df.sort_values("contribution", ascending=False).head(8).iterrows():
            lines.append(
                f"| {r['name']} | {r['ts_code']} | {r['contribution']:,.0f} | {int(r['buy_trades'])} | "
                f"{int(r['sell_trades'])} | {r['buy_cost']:,.0f} | {r['sell_proceeds']:,.0f} | {r['end_market_value']:,.0f} |"
            )

    lines.extend(
        [
            "",
            "## 2026-06 Round Trips",
            "",
            "| ETF | Buy signal | Buy exec | Buy px | Buy rank20 | Sell signal | Sell exec | Sell px | Sell rank20 | Shares | Hold days | Gross PnL | Net PnL | Buy high? | Sell low? | Sell reason |",
            "|---|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---|---|---|",
        ]
    )
    june = june_round_trips.copy().sort_values(["sell_trade_date", "ts_code", "buy_trade_date"])
    for _, r in june.iterrows():
        name = monthly_code.loc[monthly_code["ts_code"] == r["ts_code"], "name"]
        label = name.iloc[0] if not name.empty else r["ts_code"]
        lines.append(
            f"| {label} | {r['buy_signal_date']} | {r['buy_trade_date']} | {r['buy_price']:.4f} | {r['buy_rank20']:.2f} | "
            f"{r['sell_signal_date']} | {r['sell_trade_date']} | {r['sell_price']:.4f} | {r['sell_rank20']:.2f} | "
            f"{r['shares']:.0f} | {int(r['holding_days'])} | {r['gross_pnl']:,.0f} | {r['net_pnl']:,.0f} | "
            f"{str(bool(r['buy_near_high']))} | {str(bool(r['sell_near_low']))} | {r['sell_reason']} |"
        )

    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    names = load_names()
    equity, trades = load_inputs()
    store = build_store(sorted(trades["ts_code"].dropna().astype(str).unique()))
    month_returns = month_return_table(equity)
    daily_contrib = compute_daily_contributions(equity, trades, store)
    summary, monthly_code = summarize_monthly(daily_contrib, month_returns, names)
    trade_context = build_trade_context_table(trades, store, monthly_code[monthly_code["contribution"] < 0])
    round_trips = build_fifo_round_trips(trades, store)
    june_round_trips = round_trips[round_trips["sell_trade_date"].astype(str).str.startswith("2026-06")].copy()

    daily_path = REPORT_DIR / "2026_nowarmup_daily_etf_contribution.csv"
    monthly_path = REPORT_DIR / "2026_nowarmup_monthly_etf_contribution.csv"
    summary_path = REPORT_DIR / "2026_nowarmup_monthly_summary.csv"
    context_path = REPORT_DIR / "2026_nowarmup_monthly_loser_trade_context.csv"
    june_roundtrip_path = REPORT_DIR / "2026_nowarmup_june_round_trips.csv"
    daily_contrib.to_csv(daily_path, index=False)
    monthly_code.to_csv(monthly_path, index=False)
    summary.to_csv(summary_path, index=False)
    trade_context.to_csv(context_path, index=False)
    june_round_trips.to_csv(june_roundtrip_path, index=False)
    write_report(summary, monthly_code, trade_context, june_round_trips)

    print(f"Saved: {daily_path}")
    print(f"Saved: {monthly_path}")
    print(f"Saved: {summary_path}")
    print(f"Saved: {context_path}")
    print(f"Saved: {june_roundtrip_path}")
    print(f"Saved: {REPORT_DIR / '2026_nowarmup_monthly_etf_attribution.md'}")


if __name__ == "__main__":
    main()
