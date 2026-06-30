#!/usr/bin/env python3
"""Stateful partial-fill replay for friend9 under window participation limits."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from run_friend_intraday_replication import (  # noqa: E402
    FRIEND_POOL_9,
    LOCAL_DATA,
    LocalETFIntradayStore,
    build_friend_params,
    pct,
    run_intraday_backtest,
)


OUT = PROJECT_ROOT / "outputs" / "etf_loop" / "friend9_validation"


def summarize(equity: pd.DataFrame) -> dict[str, float]:
    if equity.empty or "portfolio_value" not in equity:
        return {"annual_return": np.nan, "cagr": np.nan, "sharpe": np.nan, "max_drawdown": np.nan, "total_return": np.nan}
    nav = equity.set_index("date")["portfolio_value"].astype(float).sort_index()
    ret = nav.pct_change().dropna()
    total = nav.iloc[-1] / nav.iloc[0] - 1.0
    years = (pd.Timestamp(nav.index[-1]) - pd.Timestamp(nav.index[0])).days / 365.25
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1.0 / years) - 1.0 if years > 0 else np.nan
    ann = ret.mean() * 252 if len(ret) else np.nan
    sharpe = ret.mean() / ret.std(ddof=0) * np.sqrt(252) if len(ret) and ret.std(ddof=0) > 0 else np.nan
    dd = nav / nav.cummax() - 1.0
    return {
        "annual_return": float(ann),
        "cagr": float(cagr),
        "sharpe": float(sharpe),
        "max_drawdown": float(dd.min()),
        "total_return": float(total),
        "final_value": float(nav.iloc[-1]),
    }


def window_amount(store: LocalETFIntradayStore, code: str, date: pd.Timestamp, start: str = "09:35", end: str = "10:30") -> float:
    df = store.frames.get(code)
    if df is None or df.empty:
        return np.nan
    day = df[(df["date"].eq(pd.Timestamp(date))) & (df["time"].ge(start)) & (df["time"].le(end))]
    if day.empty or "amount" not in day:
        return np.nan
    return float(pd.to_numeric(day["amount"], errors="coerce").fillna(0.0).sum())


def lot_floor(value: float, price: float) -> int:
    if not np.isfinite(value) or not np.isfinite(price) or price <= 0:
        return 0
    return int(value / price // 100) * 100


def commission(gross: float) -> float:
    return max(1.0, gross * 0.0002) if gross > 0 else 0.0


def replay(
    *,
    store: LocalETFIntradayStore,
    equity_template: pd.DataFrame,
    trades: pd.DataFrame,
    initial_cash: float,
    max_participation: float,
    fill_mode: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    cash = initial_cash
    shares: dict[str, int] = {}
    orders: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    trades = trades.copy()
    trades["signal_date"] = pd.to_datetime(trades["signal_date"])
    trades["trade_date"] = pd.to_datetime(trades["trade_date"])
    grouped = {k: v.sort_values(["action", "ts_code"]) for k, v in trades.groupby("signal_date")}

    template = equity_template.copy()
    template["date"] = pd.to_datetime(template["date"])
    template["signal_date"] = pd.to_datetime(template["signal_date"])
    for r in template.itertuples():
        signal_date = pd.Timestamp(r.signal_date)
        trade_rows = grouped.get(signal_date, pd.DataFrame())
        if not trade_rows.empty:
            for side in ["SELL", "BUY"]:
                for tr in trade_rows[trade_rows["action"].eq(side)].itertuples():
                    code = str(tr.ts_code)
                    price = float(tr.price)
                    if not np.isfinite(price) or price <= 0:
                        continue
                    wa = window_amount(store, code, pd.Timestamp(tr.trade_date))
                    max_value = wa * max_participation if np.isfinite(wa) and wa > 0 else 0.0
                    if side == "SELL":
                        requested_qty = shares.get(code, 0)
                    else:
                        requested_qty = lot_floor(cash / 1.0002, price)
                    requested_value = requested_qty * price
                    fill_value = min(requested_value, max_value)
                    fill_qty = lot_floor(fill_value, price)
                    if side == "SELL":
                        fill_qty = min(fill_qty, shares.get(code, 0))
                    if side == "BUY":
                        fill_qty = min(fill_qty, lot_floor(cash / 1.0002, price))
                    gross = fill_qty * price
                    cost = commission(gross)
                    if fill_qty > 0:
                        if side == "BUY":
                            cash -= gross + cost
                            shares[code] = shares.get(code, 0) + fill_qty
                        else:
                            cash += gross - cost
                            shares[code] = shares.get(code, 0) - fill_qty
                            if shares[code] <= 0:
                                shares.pop(code, None)
                    orders.append({
                        "signal_date": signal_date,
                        "trade_date": pd.Timestamp(tr.trade_date),
                        "ts_code": code,
                        "side": side,
                        "price": price,
                        "requested_qty": requested_qty,
                        "filled_qty": fill_qty,
                        "requested_value": requested_value,
                        "filled_value": gross,
                        "unfilled_value": max(0.0, requested_value - gross),
                        "fill_ratio": gross / requested_value if requested_value > 0 else 0.0,
                        "window_amount": wa,
                        "max_participation": max_participation,
                        "participation": gross / wa if np.isfinite(wa) and wa > 0 else np.nan,
                        "reject_reason": "" if fill_qty > 0 else ("NO_WINDOW_LIQUIDITY" if not np.isfinite(wa) or wa <= 0 else "CAP_OR_LOT"),
                    })

        value_date = pd.Timestamp(r.date)
        market = 0.0
        held = []
        for code, qty in list(shares.items()):
            if qty <= 0:
                continue
            px = store.latest_price(code, value_date)
            if np.isfinite(px) and px > 0:
                market += qty * px
                held.append(code)
        pv = cash + market
        rows.append({
            "date": value_date,
            "signal_date": signal_date,
            "portfolio_value": pv,
            "cash": cash,
            "market_value": market,
            "cash_ratio": cash / pv if pv > 0 else np.nan,
            "position_count": len(held),
            "holding": "|".join(held),
            "fill_mode": fill_mode,
            "initial_cash": initial_cash,
            "max_participation": max_participation,
        })

    equity = pd.DataFrame(rows)
    orders_df = pd.DataFrame(orders)
    stats = summarize(equity)
    if not orders_df.empty:
        stats.update({
            "orders": float(len(orders_df)),
            "failed_rate": float(orders_df["filled_value"].le(0).mean()),
            "partial_or_failed_rate": float(orders_df["fill_ratio"].lt(0.999).mean()),
            "avg_participation": float(orders_df["participation"].dropna().mean()) if orders_df["participation"].notna().any() else np.nan,
            "avg_fill_ratio": float(orders_df["fill_ratio"].mean()),
        })
    return equity, orders_df, stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay friend9 with window partial fills")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2026-06-25")
    parser.add_argument("--capitals", default="50000,100000,500000,1000000")
    parser.add_argument("--fill-modes", default="same_0955_open,next_day_open")
    parser.add_argument("--max-participation", type=float, default=0.10)
    parser.add_argument("--force-signals", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    store = LocalETFIntradayStore(LOCAL_DATA, FRIEND_POOL_9, args.start, args.end, signal_time="09:50", adjust="none", frequency="1min")
    rows = []
    for fill_mode in [x.strip() for x in args.fill_modes.split(",") if x.strip()]:
        for capital in [float(x) for x in args.capitals.split(",") if x.strip()]:
            tag = f"FRIEND9PF_1min_{fill_mode}_{int(capital)}_{args.start.replace('-', '')}_{args.end.replace('-', '')}"
            raw_equity = OUT / f"equity_FRIEND9VAL_1min_{fill_mode}_{int(capital)}_{args.start.replace('-', '')}_{args.end.replace('-', '')}.csv"
            raw_trades = OUT / f"trades_raw_FRIEND9VAL_1min_{fill_mode}_{int(capital)}_{args.start.replace('-', '')}_{args.end.replace('-', '')}.csv"
            if args.force_signals or not raw_equity.exists() or not raw_trades.exists():
                params = build_friend_params(args.start, args.end, tag, True)
                params.initial_cash = capital
                equity, trades, signals, stats = run_intraday_backtest(store, params, fill_mode, "jq_auto", True)
                equity.reset_index().to_csv(raw_equity, index=False)
                trades.to_csv(raw_trades, index=False)
            equity_template = pd.read_csv(raw_equity)
            trades = pd.read_csv(raw_trades)
            equity, orders, stats = replay(
                store=store,
                equity_template=equity_template,
                trades=trades,
                initial_cash=capital,
                max_participation=args.max_participation,
                fill_mode=fill_mode,
            )
            equity.to_csv(OUT / f"partial_fill_equity_{tag}.csv", index=False)
            orders.to_csv(OUT / f"partial_fill_orders_{tag}.csv", index=False)
            row = {
                "fill_mode": fill_mode,
                "initial_cash": capital,
                "start": args.start,
                "end": args.end,
                "max_participation": args.max_participation,
                **stats,
            }
            rows.append(row)
            print(
                f"friend9 {fill_mode:<14s} cap={capital:>9.0f} ann={pct(row['annual_return'])} "
                f"sharpe={row['sharpe']:.2f} dd={pct(row['max_drawdown'])} failed={pct(row.get('failed_rate', np.nan))}"
            )
    summary = pd.DataFrame(rows)
    summary_path = OUT / f"friend9_partial_fill_summary_{args.start.replace('-', '')}_{args.end.replace('-', '')}.csv"
    summary.to_csv(summary_path, index=False)
    report = OUT / "friend9_partial_fill_report.md"
    lines = [
        "# friend9 同等窗口参与率 partial-fill replay",
        "",
        "## 1. 口径",
        "",
        "- 使用 friend9 原始 9-ETF、`jq_auto`、Top1 信号和理想交易日志。",
        "- 每笔订单最多成交 `09:35-10:30` 窗口成交额的 10%。",
        "- 未成交部分不强行补齐，卖不掉则保留旧仓，买不满则保留现金。",
        "- 这是和 WideA realistic replay 可比的 stateful 压力测试；不同于旧 friend9 报告中只做容量标记。",
        "",
        "## 2. 结果",
        "",
        "| fill_mode | 资金 | 年化 | Sharpe | DD | 失败率 | 部分/失败 | 均成交率 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in summary.sort_values(["fill_mode", "initial_cash"]).itertuples():
        lines.append(
            f"| `{r.fill_mode}` | {r.initial_cash:,.0f} | {pct(r.annual_return)} | {r.sharpe:.2f} | "
            f"{pct(r.max_drawdown)} | {pct(getattr(r, 'failed_rate', np.nan))} | "
            f"{pct(getattr(r, 'partial_or_failed_rate', np.nan))} | {pct(getattr(r, 'avg_fill_ratio', np.nan))} |"
        )
    lines += [
        "",
        "## 3. 复现命令",
        "",
        "```bash",
        f"source activate.sh && python runs/etf_loop/run_friend9_partial_fill_replay.py --start {args.start} --end {args.end} --capitals {args.capitals} --fill-modes {args.fill_modes} --max-participation {args.max_participation}",
        "```",
    ]
    report.write_text("\n".join(lines), encoding="utf-8")
    print("Saved:", summary_path)
    print("Saved:", report)


if __name__ == "__main__":
    main()
