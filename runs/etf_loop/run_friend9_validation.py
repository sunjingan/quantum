#!/usr/bin/env python3
"""Execution and capacity validation for the friend9 intraday candidate."""
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


FILL_WINDOW = {
    "same_0950_close": ("09:35", "10:30"),
    "same_0951_open": ("09:35", "10:30"),
    "same_0955_open": ("09:35", "10:30"),
    "next_day_open": ("09:35", "10:30"),
}


def _trade_window_amount(
    store: LocalETFIntradayStore,
    code: str,
    date: pd.Timestamp,
    start_time: str,
    end_time: str,
) -> float:
    df = store.frames.get(code)
    if df is None or df.empty:
        return np.nan
    day = df[(df["date"].eq(pd.Timestamp(date))) & (df["time"].ge(start_time)) & (df["time"].le(end_time))]
    if day.empty or "amount" not in day.columns:
        return np.nan
    return float(pd.to_numeric(day["amount"], errors="coerce").fillna(0.0).sum())


def _trade_minute_amount(store: LocalETFIntradayStore, code: str, date: pd.Timestamp, fill_mode: str) -> float:
    if fill_mode == "same_0950_close":
        row = store._minute_row_at_or_before(code, date, "09:50")
    elif fill_mode == "same_0951_open":
        row = store._minute_row_at_or_after(code, date, "09:51")
    elif fill_mode == "same_0955_open":
        row = store._minute_row_at_or_after(code, date, "09:55")
    elif fill_mode == "next_day_open":
        row = store._minute_row_at_or_after(code, date, "09:35")
    else:
        row = None
    if row is None or "amount" not in row:
        return np.nan
    return float(pd.to_numeric(row.get("amount", np.nan), errors="coerce"))


def _prev_close(store: LocalETFIntradayStore, code: str, date: pd.Timestamp) -> float:
    if code not in store.close.columns:
        return np.nan
    col = store.close[code].loc[store.close.index < pd.Timestamp(date)].dropna()
    return float(col.iloc[-1]) if not col.empty else np.nan


def _premium_rate(store: LocalETFIntradayStore, code: str, signal_date: pd.Timestamp) -> float:
    if code not in store.close.columns:
        return np.nan
    prev_dates = store.close.index[store.close.index < pd.Timestamp(signal_date)]
    if len(prev_dates) == 0:
        return np.nan
    prev_date = prev_dates[-1]
    prev_close = float(store.close[code].loc[prev_date])
    unit_nav = store.unit_nav(code, prev_date)
    if not unit_nav or unit_nav <= 0 or np.isnan(unit_nav):
        return np.nan
    return (prev_close - unit_nav) / unit_nav * 100.0


def enrich_trades(
    trades: pd.DataFrame,
    store: LocalETFIntradayStore,
    fill_mode: str,
    initial_cash: float,
) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    out = trades.copy()
    out["signal_date"] = pd.to_datetime(out["signal_date"])
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    out["raw_price"] = pd.to_numeric(out.get("raw_price", out.get("price")), errors="coerce")
    out["price"] = pd.to_numeric(out["price"], errors="coerce")
    out["shares"] = pd.to_numeric(out["shares"], errors="coerce")
    out["order_value_raw"] = out["raw_price"] * out["shares"]
    out["fixed_slip_bp"] = (out["price"] - out["raw_price"]).abs() / out["raw_price"] * 10000.0
    out["commission_bp"] = pd.to_numeric(out.get("cost", np.nan), errors="coerce") / pd.to_numeric(out.get("gross", np.nan), errors="coerce") * 10000.0
    out["all_in_bp_side"] = out["fixed_slip_bp"] + out["commission_bp"]

    start_time, end_time = FILL_WINDOW.get(fill_mode, ("09:35", "10:30"))
    daily_amount = []
    window_amount = []
    minute_amount = []
    premium = []
    near_limit_up = []
    near_limit_down = []
    no_minute_liquidity = []
    for r in out.to_dict("records"):
        code = str(r["ts_code"])
        trade_date = pd.Timestamp(r["trade_date"])
        signal_date = pd.Timestamp(r["signal_date"])
        da = np.nan
        if code in store.amount.columns and trade_date in store.amount.index:
            da = float(store.amount.loc[trade_date, code])
        wa = _trade_window_amount(store, code, trade_date, start_time, end_time)
        ma = _trade_minute_amount(store, code, trade_date, fill_mode)
        pc = _prev_close(store, code, trade_date)
        raw_px = float(r.get("raw_price", np.nan))
        near_limit_up.append(bool(np.isfinite(raw_px) and np.isfinite(pc) and pc > 0 and raw_px / pc >= 1.095))
        near_limit_down.append(bool(np.isfinite(raw_px) and np.isfinite(pc) and pc > 0 and raw_px / pc <= 0.905))
        no_minute_liquidity.append(bool(not np.isfinite(ma) or ma <= 0))
        daily_amount.append(da)
        window_amount.append(wa)
        minute_amount.append(ma)
        premium.append(_premium_rate(store, code, signal_date))

    out["daily_amount"] = daily_amount
    out["window_amount_0935_1030"] = window_amount
    out["minute_amount"] = minute_amount
    out["participation_daily"] = out["order_value_raw"] / out["daily_amount"]
    out["participation_window"] = out["order_value_raw"] / out["window_amount_0935_1030"]
    out["participation_minute"] = out["order_value_raw"] / out["minute_amount"]
    out["premium_rate"] = premium
    out["premium_ge_5pct"] = out["premium_rate"] >= 5.0
    near_limit_up_s = pd.Series(near_limit_up, index=out.index)
    near_limit_down_s = pd.Series(near_limit_down, index=out.index)
    out["near_limit_up_buy"] = out["action"].astype(str).eq("BUY") & near_limit_up_s
    out["near_limit_down_sell"] = out["action"].astype(str).eq("SELL") & near_limit_down_s
    out["no_minute_liquidity"] = no_minute_liquidity
    out["no_window_liquidity"] = ~np.isfinite(out["window_amount_0935_1030"]) | (out["window_amount_0935_1030"] <= 0)
    out["daily_part_gt_3pct"] = out["participation_daily"] > 0.03
    out["window_part_gt_10pct"] = out["no_window_liquidity"] | (out["participation_window"] > 0.10)
    out["minute_part_gt_30pct"] = out["no_minute_liquidity"] | (out["participation_minute"] > 0.30)
    out["initial_cash"] = initial_cash

    last_buy_date: dict[str, pd.Timestamp] = {}
    same_day_roundtrip = []
    for r in out.to_dict("records"):
        code = str(r["ts_code"])
        date = pd.Timestamp(r["trade_date"])
        if r["action"] == "BUY":
            last_buy_date[code] = date
            same_day_roundtrip.append(False)
        elif r["action"] == "SELL":
            same_day_roundtrip.append(last_buy_date.get(code) == date)
        else:
            same_day_roundtrip.append(False)
    out["same_day_roundtrip_sell"] = same_day_roundtrip
    return out


def summarize_validation(equity: pd.DataFrame, enriched: pd.DataFrame, stats: dict[str, float], setting: dict[str, Any]) -> dict[str, Any]:
    if enriched.empty:
        return {**setting, **stats, "trade_count": 0}
    notional = enriched["order_value_raw"].replace([np.inf, -np.inf], np.nan).dropna()
    weights = enriched["order_value_raw"].fillna(0.0)

    def weighted_mean(col: str) -> float:
        x = pd.to_numeric(enriched[col], errors="coerce")
        mask = x.notna() & weights.gt(0)
        if not mask.any():
            return np.nan
        return float((x[mask] * weights[mask]).sum() / weights[mask].sum())

    def finite_quantile(col: str, q: float) -> float:
        x = pd.to_numeric(enriched[col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        return float(x.quantile(q)) if len(x) else np.nan

    def finite_max(col: str) -> float:
        x = pd.to_numeric(enriched[col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        return float(x.max()) if len(x) else np.nan

    return {
        **setting,
        **stats,
        "trade_count": int(len(enriched)),
        "buy_count": int(enriched["action"].astype(str).eq("BUY").sum()),
        "sell_count": int(enriched["action"].astype(str).eq("SELL").sum()),
        "avg_order_value": float(notional.mean()) if len(notional) else np.nan,
        "max_order_value": float(notional.max()) if len(notional) else np.nan,
        "weighted_fixed_slip_bp": weighted_mean("fixed_slip_bp"),
        "weighted_all_in_bp_side": weighted_mean("all_in_bp_side"),
        "p95_daily_participation": finite_quantile("participation_daily", 0.95),
        "max_daily_participation": finite_max("participation_daily"),
        "p95_window_participation": finite_quantile("participation_window", 0.95),
        "max_window_participation": finite_max("participation_window"),
        "p95_minute_participation": finite_quantile("participation_minute", 0.95),
        "max_minute_participation": finite_max("participation_minute"),
        "daily_part_gt_3pct_rate": float(enriched["daily_part_gt_3pct"].mean()),
        "window_part_gt_10pct_rate": float(enriched["window_part_gt_10pct"].mean()),
        "minute_part_gt_30pct_rate": float(enriched["minute_part_gt_30pct"].mean()),
        "window_split_needed_rate": float(enriched["window_part_gt_10pct"].mean()),
        "p95_window_slices_10pct": finite_quantile("participation_window", 0.95) / 0.10,
        "max_window_slices_10pct": finite_max("participation_window") / 0.10,
        "premium_ge_5pct_count": int(enriched["premium_ge_5pct"].sum()),
        "near_limit_buy_count": int(enriched["near_limit_up_buy"].sum()),
        "near_limit_sell_count": int(enriched["near_limit_down_sell"].sum()),
        "no_minute_liquidity_count": int(enriched["no_minute_liquidity"].sum()),
        "no_window_liquidity_count": int(enriched.get("no_window_liquidity", pd.Series(False, index=enriched.index)).sum()),
        "same_day_roundtrip_sell_count": int(enriched["same_day_roundtrip_sell"].sum()),
        "avg_cash_ratio": float(equity["cash_ratio"].mean()) if "cash_ratio" in equity.columns and not equity.empty else np.nan,
    }


def write_report(df: pd.DataFrame, out_dir: Path, start: str, end: str) -> Path:
    path = out_dir / "friend9_validation_report.md"
    lines = [
        "# friend9 候选策略分钟级验证报告",
        "",
        "## 1. 验证范围",
        "",
        f"- 区间：`{start}` 到 `{end}`",
        "- 策略：friend 原始 9-ETF 池，`jq_auto` ATR 动态回溯窗口，Top1 持仓。",
        "- 成本：买卖各 2bp 佣金，叠加 JoinQuant 风格 `FixedSlippage(0.001)` 元/份，并直接体现在成交价里。",
        "- 验证项：分钟成交模式、容量、固定滑点折算 bp、溢价、涨跌停/停牌近似、同日买卖可行性、订单拆分需求。",
        "- 注意：本报告不修改 `F2_CAP_MA60` / `WideA` 等日线候选策略。",
        "",
        "## 2. 复现命令",
        "",
        "```bash",
        f"source activate.sh && python runs/etf_loop/run_friend9_validation.py --start {start} --end {end} --force",
        "```",
        "",
        "## 3. 不同执行方式和资金规模下的收益/成本",
        "",
        "| 资金 | 执行方式 | 年化 | CAGR | Sharpe | DD | 总收益 | 交易数 | 单边全成本bp | p95窗口参与率 | 最大窗口参与率 | p95分钟参与率 | 溢价>=5% | 同日卖出 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    show = df.sort_values(["initial_cash", "fill_mode"])
    for r in show.to_dict("records"):
        lines.append(
            f"| {r['initial_cash']:,.0f} | {r['fill_mode']} | {pct(r['annual_return'])} | {pct(r['cagr'])} | "
            f"{r['sharpe_ratio']:.2f} | {pct(r['max_drawdown'])} | {pct(r['total_return'])} | "
            f"{int(r['trade_count'])} | {r['weighted_all_in_bp_side']:.2f} | "
            f"{pct(r['p95_window_participation'])} | {pct(r['max_window_participation'])} | "
            f"{pct(r['p95_minute_participation'])} | {int(r['premium_ge_5pct_count'])} | "
            f"{int(r['same_day_roundtrip_sell_count'])} |"
        )

    lines += [
        "",
        "## 4. 容量风险标记",
        "",
        "| 资金 | 执行方式 | 日成交额>3% | 窗口>10% | 分钟>30% | 无窗口成交额 | 无分钟成交额 | 近涨停买入 | 近跌停卖出 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in show.to_dict("records"):
        lines.append(
            f"| {r['initial_cash']:,.0f} | {r['fill_mode']} | {pct(r['daily_part_gt_3pct_rate'])} | "
            f"{pct(r['window_part_gt_10pct_rate'])} | {pct(r['minute_part_gt_30pct_rate'])} | "
            f"{int(r.get('no_window_liquidity_count', 0))} | {int(r['no_minute_liquidity_count'])} | "
            f"{int(r['near_limit_buy_count'])} | {int(r['near_limit_sell_count'])} |"
        )

    lines += [
        "",
        "## 5. 订单拆分诊断",
        "",
        "规则口径：如果单笔订单最多吃掉 `09:35-10:30` 窗口成交额的 `10%`，则理论拆单份数为 `ceil(order_value / (window_turnover * 10%))`。下面的 `p95 拆单份数` 和 `最大拆单份数` 只对有限窗口成交额计算；无窗口成交额的订单在容量表里单独列出。",
        "",
        "| 资金 | 执行方式 | 需要拆单比例 | p95拆单份数 | 最大拆单份数 | 无窗口成交额 |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for r in show.to_dict("records"):
        lines.append(
            f"| {r['initial_cash']:,.0f} | {r['fill_mode']} | {pct(r['window_split_needed_rate'])} | "
            f"{r['p95_window_slices_10pct']:.1f} | {r['max_window_slices_10pct']:.1f} | "
            f"{int(r.get('no_window_liquidity_count', 0))} |"
        )

    lines += [
        "",
        "## 6. 结论",
        "",
        "- `same_0950_close` 偏乐观，因为信号和成交使用同一根 09:50 K 线；真实模拟盘更应优先看 `same_0951_open` 或 `same_0955_open`。",
        "- `FixedSlippage(0.001)` 不是固定 bp 成本；不同 ETF 价格不同，单边全成本应看表里的实测折算值。",
        "- `同日卖出=0` 说明当前实现不依赖卖出当天刚买入的 ETF；它主要是卖出隔夜旧仓，再买入新 Top1。",
        "- 容量判断主要看 `窗口>10%` 和 `分钟>30%`。这些比例升高时，影子盘仍可观察，但真金白银容量会明显受限。",
        "- 溢价标记表示前一日市场价相对单位净值溢价至少 5%，这些交易需要重点人工复核，尤其是跨境 ETF 和商品 ETF。",
        "- 当前证据支持 friend9 进入影子盘/小资金模拟盘观察，但不支持在未做真实订单拆分和部分成交对账前直接放大资金。",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate friend9 intraday candidate execution/capacity")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2026-06-25")
    parser.add_argument("--cash-levels", default="50000,100000,500000,1000000,3000000")
    parser.add_argument("--fill-modes", default="same_0950_close,same_0951_open,same_0955_open,next_day_open")
    parser.add_argument("--frequency", choices=["1min", "5min"], default="1min")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    cash_levels = [float(x) for x in args.cash_levels.split(",") if x.strip()]
    fill_modes = [x.strip() for x in args.fill_modes.split(",") if x.strip()]

    store = LocalETFIntradayStore(
        LOCAL_DATA,
        FRIEND_POOL_9,
        args.start,
        args.end,
        signal_time="09:50",
        adjust="none",
        frequency=args.frequency,
    )

    rows: list[dict[str, Any]] = []
    for cash in cash_levels:
        for fill_mode in fill_modes:
            tag = f"FRIEND9VAL_{args.frequency}_{fill_mode}_{int(cash)}_{args.start.replace('-', '')}_{args.end.replace('-', '')}"
            enriched_path = OUT / f"trades_enriched_{tag}.csv"
            equity_path = OUT / f"equity_{tag}.csv"
            summary_path = OUT / f"summary_{tag}.csv"
            if summary_path.exists() and enriched_path.exists() and equity_path.exists() and not args.force:
                row = pd.read_csv(summary_path).iloc[0].to_dict()
                rows.append(row)
                continue

            params = build_friend_params(args.start, args.end, tag, full_logic=True)
            params.initial_cash = cash
            equity, trades, signals, stats = run_intraday_backtest(
                store=store,
                params=params,
                fill_mode=fill_mode,
                ranking_mode="jq_auto",
                exact_jq_cost=True,
            )
            enriched = enrich_trades(trades, store, fill_mode, cash)
            setting = {
                "initial_cash": cash,
                "fill_mode": fill_mode,
                "frequency": args.frequency,
                "start": args.start,
                "end": args.end,
            }
            row = summarize_validation(equity, enriched, stats, setting)
            rows.append(row)
            equity.to_csv(equity_path)
            trades.to_csv(OUT / f"trades_raw_{tag}.csv", index=False)
            signals.to_csv(OUT / f"signals_{tag}.csv", index=False)
            enriched.to_csv(enriched_path, index=False)
            pd.DataFrame([row]).to_csv(summary_path, index=False)
            print(
                f"cash={cash:,.0f} fill={fill_mode:<16s} ann={pct(row['annual_return'])} "
                f"sharpe={row['sharpe_ratio']:.2f} dd={pct(row['max_drawdown'])} "
                f"win>10={pct(row['window_part_gt_10pct_rate'])}"
            )

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "friend9_validation_summary.csv", index=False)
    report = write_report(df, OUT, args.start, args.end)
    print("Saved:", OUT / "friend9_validation_summary.csv")
    print("Saved:", report)


if __name__ == "__main__":
    main()
