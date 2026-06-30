#!/usr/bin/env python3
"""Child-order execution validation for ETF Loop candidates.

This runner keeps the daily signal layer unchanged and only replaces the
single-window fill approximation with a child-order state machine.  Each child
slice independently checks minute turnover, limit blocks, slippage and partial
fills.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from run_minute_execution_backtest import (  # noqa: E402
    FillContext,
    LocalMinuteStore,
    SlippageConfig,
    execute_order,
    generate_daily_signal_logs,
    load_target_schedule,
    pct,
    summarize,
)
from run_minute_execution_advice_replay import (  # noqa: E402
    get_codes,
    infer_base_cash,
    intended_value,
    load_logs,
    slippage_config,
)


OUT = PROJECT_ROOT / "outputs" / "etf_loop" / "minute_execution_backtest"


SCHEDULES: dict[str, list[tuple[str, str, float]]] = {
    "am_4x": [
        ("09:35", "09:40", 0.25),
        ("09:45", "09:50", 0.25),
        ("10:00", "10:05", 0.25),
        ("10:20", "10:25", 0.25),
    ],
    "am_tail_4x": [
        ("09:35", "09:45", 0.25),
        ("10:05", "10:15", 0.25),
        ("14:30", "14:42", 0.25),
        ("14:43", "14:55", 0.25),
    ],
    "midday_6x": [
        ("10:00", "10:20", 1 / 6),
        ("10:30", "10:50", 1 / 6),
        ("11:00", "11:20", 1 / 6),
        ("13:05", "13:25", 1 / 6),
        ("13:45", "14:05", 1 / 6),
        ("14:20", "14:40", 1 / 6),
    ],
}


def window_context(store: LocalMinuteStore, code: str, date: pd.Timestamp, start: str, end: str, kind: str) -> FillContext | None:
    day = store.day_rows(code, date)
    if day.empty:
        return None
    window = day[(day["time"] >= start) & (day["time"] <= end)].copy()
    if window.empty:
        return None
    window_turnover = float(window["amount"].fillna(0).sum())
    window_volume = float(window["volume"].fillna(0).sum())
    daily_turnover = float(day["amount"].fillna(0).sum())
    if kind == "vwap":
        if window_turnover > 0 and window_volume > 0:
            if store.price_adjustment == "engine":
                valid = window[["close", "volume"]].dropna()
                valid = valid[valid["volume"] > 0]
                if not valid.empty:
                    raw_price = float((valid["close"].astype(float) * valid["volume"].astype(float)).sum() / valid["volume"].astype(float).sum())
                else:
                    raw_price = np.nan
            else:
                raw_price = window_turnover / window_volume
        else:
            raw_price = float(window["close"].dropna().mean())
    elif kind == "twap":
        raw_price = float(window["close"].dropna().mean())
    elif kind == "open":
        raw_price = float(window["open"].dropna().iloc[0]) if window["open"].notna().any() else np.nan
    else:
        raise ValueError(f"Unsupported child kind: {kind}")
    if pd.isna(raw_price) or raw_price <= 0:
        return None
    limit_up = float(window["limit_up"].dropna().iloc[0]) if "limit_up" in window.columns and window["limit_up"].notna().any() else np.nan
    limit_down = float(window["limit_down"].dropna().iloc[0]) if "limit_down" in window.columns and window["limit_down"].notna().any() else np.nan
    is_limit_up = bool(pd.notna(limit_up) and raw_price >= limit_up * 0.999)
    is_limit_down = bool(pd.notna(limit_down) and raw_price <= limit_down * 1.001)
    is_suspended = bool(daily_turnover <= 0 or window_turnover <= 0)
    spread_parts = window[["high", "low", "close"]].dropna()
    spread_parts = spread_parts[spread_parts["close"] > 0]
    if spread_parts.empty:
        spread_proxy_bp = np.nan
    else:
        spread_proxy_bp = float(((spread_parts["high"] - spread_parts["low"]) / spread_parts["close"]).clip(lower=0).median() * 10000.0)
    high = window["high"].dropna().max()
    low = window["low"].dropna().min()
    window_range_bp = float((high / low - 1.0) * 10000.0) if pd.notna(high) and pd.notna(low) and low > 0 else np.nan
    return FillContext(
        price=raw_price,
        raw_price=raw_price,
        date=pd.Timestamp(date),
        start_time=start,
        end_time=end,
        window_turnover=window_turnover,
        daily_turnover=daily_turnover,
        window_volume=window_volume,
        limit_up=limit_up,
        limit_down=limit_down,
        is_limit_up=is_limit_up,
        is_limit_down=is_limit_down,
        is_suspended=is_suspended,
        spread_proxy_bp=spread_proxy_bp,
        window_range_bp=window_range_bp,
        source=f"{kind}_{start}_{end}",
    )


def mark_to_market(cash: float, shares: dict[str, int], store: LocalMinuteStore, date: pd.Timestamp, fallback_contexts: dict[str, FillContext | None]) -> tuple[float, float]:
    market_value = 0.0
    for code, qty in list(shares.items()):
        px = store.valuation_close_price(code, date)
        if pd.isna(px) or px <= 0:
            ctx = fallback_contexts.get(code)
            px = ctx.raw_price if ctx is not None else np.nan
        if pd.notna(px) and px > 0:
            market_value += qty * px
    return cash + market_value, market_value


def child_contexts(
    store: LocalMinuteStore,
    codes: list[str],
    exec_date: pd.Timestamp,
    start: str,
    end: str,
    child_kind: str,
    cache: dict[tuple[str, pd.Timestamp, str, str, str], FillContext | None],
) -> dict[str, FillContext | None]:
    out: dict[str, FillContext | None] = {}
    d = pd.Timestamp(exec_date)
    for code in codes:
        key = (code, d, start, end, child_kind)
        if key not in cache:
            cache[key] = window_context(store, code, d, start, end, child_kind)
        out[code] = cache[key]
    return out


def price_for_diff(store: LocalMinuteStore, code: str, exec_date: pd.Timestamp, ctx: FillContext | None) -> float:
    if ctx is not None and pd.notna(ctx.raw_price) and ctx.raw_price > 0:
        return float(ctx.raw_price)
    px = store.close_price(code, exec_date)
    return float(px) if pd.notna(px) and px > 0 else np.nan


def run_child_overlay(
    *,
    setting: str,
    trading_start: str,
    initial_cash: float,
    schedule_name: str,
    child_kind: str,
    roundtrip_cost_bp: float,
    max_participation: float,
    slippage_model: str,
    sqrt_k: float,
    account: pd.DataFrame,
    targets_by_signal: dict[pd.Timestamp, dict[str, float]],
    exposure_by_signal: dict[pd.Timestamp, float],
    store: LocalMinuteStore,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    commission_bp = 1.5
    base_slippage_bp = max(0.0, roundtrip_cost_bp / 2.0 - commission_bp)
    slippage_config = SlippageConfig(
        model=slippage_model,
        sqrt_k=sqrt_k,
        commission_bp=commission_bp,
        base_slippage_bp=base_slippage_bp,
        cross_border_penalty_bp=0.0,
        commodity_penalty_bp=0.0,
        open_penalty_bp=0.0,
        spread_penalty_mult=0.0,
        spread_penalty_cap_bp=10.0,
        max_slippage_bp=50.0,
        near_limit_threshold_bp=0.0,
        near_limit_capacity_mult=1.0,
    )

    children = SCHEDULES[schedule_name]
    cash = initial_cash
    shares: dict[str, int] = {}
    equity_rows: list[dict[str, Any]] = []
    order_rows: list[dict[str, Any]] = []
    context_cache: dict[tuple[str, pd.Timestamp, str, str, str], FillContext | None] = {}

    for row in account.itertuples():
        signal_date = pd.Timestamp(row.signal_date)
        if signal_date < pd.Timestamp(trading_start):
            continue
        exec_date = store.nth_trading_day_after(signal_date, 1)
        if exec_date is None:
            continue
        target = targets_by_signal.get(signal_date, {})
        target_exposure = exposure_by_signal.get(signal_date, 1.0)

        for idx, (start, end, child_weight) in enumerate(children):
            all_codes = sorted(set(shares) | set(target))
            contexts = child_contexts(store, all_codes, exec_date, start, end, child_kind, context_cache)
            prices = {c: price_for_diff(store, c, exec_date, contexts.get(c)) for c in all_codes}
            portfolio_before = cash + sum(
                shares.get(c, 0) * prices.get(c, np.nan)
                for c in shares
                if pd.notna(prices.get(c, np.nan))
            )
            if portfolio_before <= 0:
                continue
            investable = portfolio_before * target_exposure
            desired = {c: investable * target.get(c, 0.0) for c in all_codes}
            current = {c: shares.get(c, 0) * prices.get(c, 0.0) for c in all_codes}
            remaining_weight = sum(w for _, _, w in children[idx:])
            slice_ratio = child_weight / remaining_weight if remaining_weight > 0 else 1.0

            for code in all_codes:
                diff = current.get(code, 0.0) - desired.get(code, 0.0)
                if diff <= max(100.0, portfolio_before * 0.0005):
                    continue
                child_value = diff * slice_ratio
                cash, shares, rec = execute_order(
                    cash=cash,
                    shares=shares,
                    code=code,
                    side="SELL",
                    desired_value=child_value,
                    ctx=contexts.get(code),
                    slippage_config=slippage_config,
                    max_participation=max_participation,
                )
                rec.update({
                    "signal_date": signal_date,
                    "trade_date": exec_date,
                    "setting": setting,
                    "schedule_name": schedule_name,
                    "child_index": idx + 1,
                    "child_weight": child_weight,
                    "child_kind": child_kind,
                    "roundtrip_cost_bp": roundtrip_cost_bp,
                    "target_weight": target.get(code, 0.0),
                    "target_exposure": target_exposure,
                    "portfolio_before": portfolio_before,
                    "execution_start_time": start,
                    "execution_end_time": end,
                })
                order_rows.append(rec)

            all_codes = sorted(set(shares) | set(target))
            contexts = child_contexts(store, all_codes, exec_date, start, end, child_kind, context_cache)
            prices = {c: price_for_diff(store, c, exec_date, contexts.get(c)) for c in all_codes}
            portfolio_mid = cash + sum(
                shares.get(c, 0) * prices.get(c, np.nan)
                for c in shares
                if pd.notna(prices.get(c, np.nan))
            )
            if portfolio_mid <= 0:
                continue
            investable = portfolio_mid * target_exposure
            desired = {c: investable * target.get(c, 0.0) for c in all_codes}
            current = {c: shares.get(c, 0) * prices.get(c, 0.0) for c in all_codes}
            for code in sorted(target):
                diff = desired.get(code, 0.0) - current.get(code, 0.0)
                if diff <= max(100.0, portfolio_mid * 0.0005):
                    continue
                child_value = diff * slice_ratio
                cash, shares, rec = execute_order(
                    cash=cash,
                    shares=shares,
                    code=code,
                    side="BUY",
                    desired_value=child_value,
                    ctx=contexts.get(code),
                    slippage_config=slippage_config,
                    max_participation=max_participation,
                )
                rec.update({
                    "signal_date": signal_date,
                    "trade_date": exec_date,
                    "setting": setting,
                    "schedule_name": schedule_name,
                    "child_index": idx + 1,
                    "child_weight": child_weight,
                    "child_kind": child_kind,
                    "roundtrip_cost_bp": roundtrip_cost_bp,
                    "target_weight": target.get(code, 0.0),
                    "target_exposure": target_exposure,
                    "portfolio_before": portfolio_mid,
                    "execution_start_time": start,
                    "execution_end_time": end,
                })
                order_rows.append(rec)

        all_codes = sorted(set(shares) | set(target))
        final_contexts = child_contexts(store, all_codes, exec_date, children[-1][0], children[-1][1], child_kind, context_cache)
        portfolio_value, market_value = mark_to_market(cash, shares, store, exec_date, final_contexts)
        actual_exposure = market_value / portfolio_value if portfolio_value > 0 else np.nan
        equity_rows.append({
            "date": exec_date,
            "signal_date": signal_date,
            "portfolio_value": portfolio_value,
            "cash": cash,
            "market_value": market_value,
            "target_exposure": target_exposure,
            "actual_exposure": actual_exposure,
            "exposure_gap": actual_exposure - target_exposure if pd.notna(actual_exposure) else np.nan,
            "position_count": sum(1 for v in shares.values() if v > 0),
            "target_count": len(target),
            "schedule_name": schedule_name,
            "child_kind": child_kind,
            "roundtrip_cost_bp": roundtrip_cost_bp,
            "initial_cash": initial_cash,
        })

    equity = pd.DataFrame(equity_rows).drop_duplicates("date", keep="last").sort_values("date")
    orders = pd.DataFrame(order_rows)
    stats = summarize(equity)
    if not orders.empty:
        reasons = orders["reject_reason"].fillna("")
        stats.update({
            "orders": float(len(orders)),
            "partial_or_failed_rate": float((orders["fill_ratio"].fillna(0) < 0.999).mean()),
            "failed_rate": float((orders["filled_value"].fillna(0) <= 0).mean()),
            "capacity_limited_rate": float(reasons.eq("PARTIAL_CAPACITY").mean()),
            "lot_residual_rate": float(reasons.eq("PARTIAL_LOT_OR_CASH").mean()),
            "no_minute_data_rate": float(reasons.eq("NO_MINUTE_DATA").mean()),
            "no_turnover_rate": float(reasons.eq("SUSPENDED_OR_NO_TURNOVER").mean()),
            "limit_block_rate": float(reasons.isin(["LIMIT_UP_BUY_BLOCKED", "LIMIT_DOWN_SELL_BLOCKED"]).mean()),
            "avg_slippage_bp": float(orders["slippage_bp"].dropna().mean()) if orders["slippage_bp"].notna().any() else np.nan,
            "avg_participation": float(orders["participation_rate"].dropna().mean()) if orders["participation_rate"].notna().any() else np.nan,
            "avg_abs_exposure_gap": float(equity["exposure_gap"].abs().dropna().mean()) if "exposure_gap" in equity else np.nan,
            "avg_child_fill_ratio": float(orders["fill_ratio"].dropna().mean()),
        })
    return equity, orders, stats


def run_child_advice_replay(
    *,
    setting: str,
    trading_start: str,
    initial_cash: float,
    schedule_name: str,
    child_kind: str,
    roundtrip_cost_bp: float,
    max_participation: float,
    slippage_model: str,
    sqrt_k: float,
    commission_bp: float,
    account: pd.DataFrame,
    advice: pd.DataFrame,
    store: LocalMinuteStore,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    cfg = slippage_config(roundtrip_cost_bp, slippage_model, sqrt_k, commission_bp)
    base_cash = infer_base_cash(account)
    scale = initial_cash / base_cash if base_cash > 0 else 1.0
    children = SCHEDULES[schedule_name]
    cash = initial_cash
    shares: dict[str, int] = {}
    equity_rows: list[dict[str, Any]] = []
    order_rows: list[dict[str, Any]] = []
    context_cache: dict[tuple[str, pd.Timestamp, str, str, str], FillContext | None] = {}

    advice = advice[advice["signal_date"] >= pd.Timestamp(trading_start)].copy()
    grouped = {k: v[v["action"].isin(["BUY", "SELL"])].copy() for k, v in advice.groupby("signal_date")}

    for acc in account.itertuples():
        signal_date = pd.Timestamp(acc.signal_date)
        if signal_date < pd.Timestamp(trading_start):
            continue
        exec_date = pd.Timestamp(acc.trade_date)
        day = grouped.get(signal_date, pd.DataFrame())
        if day.empty:
            contexts = child_contexts(store, sorted(shares), exec_date, children[-1][0], children[-1][1], child_kind, context_cache)
            portfolio_value, market_value = mark_to_market(cash, shares, store, exec_date, contexts)
            target_exposure = float(getattr(acc, "target_exposure", 1.0))
            equity_rows.append({
                "date": exec_date,
                "signal_date": signal_date,
                "portfolio_value": portfolio_value,
                "cash": cash,
                "market_value": market_value,
                "target_exposure": target_exposure,
                "actual_exposure": market_value / portfolio_value if portfolio_value > 0 else np.nan,
                "exposure_gap": (market_value / portfolio_value - target_exposure) if portfolio_value > 0 else np.nan,
                "position_count": sum(1 for v in shares.values() if v > 0),
                "schedule_name": schedule_name,
                "child_kind": child_kind,
                "roundtrip_cost_bp": roundtrip_cost_bp,
                "initial_cash": initial_cash,
                "scale": scale,
            })
            continue

        day = day.reset_index(drop=True)
        remaining_value: dict[int, float] = {}
        for idx, row in day.iterrows():
            first_ctx = store.fill_context(str(row["ts_code"]), exec_date, "vwap_0935_1030")
            remaining_value[idx] = intended_value(row, scale, first_ctx)

        for child_idx, (start, end, child_weight) in enumerate(children):
            remaining_weight = sum(w for _, _, w in children[child_idx:])
            slice_ratio = child_weight / remaining_weight if remaining_weight > 0 else 1.0
            codes = sorted(set(shares) | set(day["ts_code"].dropna().astype(str).tolist()))
            contexts = child_contexts(store, codes, exec_date, start, end, child_kind, context_cache)

            for side in ["SELL", "BUY"]:
                side_rows = day[day["action"].eq(side)]
                for idx, row in side_rows.iterrows():
                    code = str(row["ts_code"])
                    if code == "CASH":
                        continue
                    rem = remaining_value.get(idx, 0.0)
                    if rem <= 0:
                        continue
                    desired = rem * slice_ratio
                    cash, shares, rec = execute_order(
                        cash=cash,
                        shares=shares,
                        code=code,
                        side=side,
                        desired_value=desired,
                        ctx=contexts.get(code),
                        slippage_config=cfg,
                        max_participation=max_participation,
                    )
                    remaining_value[idx] = max(0.0, rem - float(rec.get("filled_value", 0.0) or 0.0))
                    rec.update({
                        "signal_date": signal_date,
                        "trade_date": exec_date,
                        "setting": setting,
                        "schedule_name": schedule_name,
                        "child_index": child_idx + 1,
                        "child_weight": child_weight,
                        "child_kind": child_kind,
                        "roundtrip_cost_bp": roundtrip_cost_bp,
                        "target_exposure": float(getattr(acc, "target_exposure", 1.0)),
                        "advice_reason": row.get("reason", ""),
                        "advice_bucket": row.get("bucket", ""),
                        "advice_action": side,
                        "advice_price": row.get("price", np.nan),
                        "advice_shares": row.get("shares", np.nan),
                        "remaining_order_value": remaining_value[idx],
                        "scale": scale,
                        "execution_start_time": start,
                        "execution_end_time": end,
                    })
                    order_rows.append(rec)

        contexts = child_contexts(store, sorted(set(shares) | set(day["ts_code"].dropna().astype(str).tolist())), exec_date, children[-1][0], children[-1][1], child_kind, context_cache)
        portfolio_value, market_value = mark_to_market(cash, shares, store, exec_date, contexts)
        target_exposure = float(getattr(acc, "target_exposure", 1.0))
        actual_exposure = market_value / portfolio_value if portfolio_value > 0 else np.nan
        equity_rows.append({
            "date": exec_date,
            "signal_date": signal_date,
            "portfolio_value": portfolio_value,
            "cash": cash,
            "market_value": market_value,
            "target_exposure": target_exposure,
            "actual_exposure": actual_exposure,
            "exposure_gap": actual_exposure - target_exposure if pd.notna(actual_exposure) else np.nan,
            "position_count": sum(1 for v in shares.values() if v > 0),
            "target_count": int(day[day["action"].eq("BUY")]["ts_code"].nunique()),
            "schedule_name": schedule_name,
            "child_kind": child_kind,
            "roundtrip_cost_bp": roundtrip_cost_bp,
            "initial_cash": initial_cash,
            "scale": scale,
        })

    equity = pd.DataFrame(equity_rows).drop_duplicates("date", keep="last").sort_values("date")
    orders = pd.DataFrame(order_rows)
    stats = summarize(equity)
    if not orders.empty:
        reasons = orders["reject_reason"].fillna("")
        stats.update({
            "orders": float(len(orders)),
            "partial_or_failed_rate": float((orders["fill_ratio"].fillna(0) < 0.999).mean()),
            "failed_rate": float((orders["filled_value"].fillna(0) <= 0).mean()),
            "capacity_limited_rate": float(reasons.eq("PARTIAL_CAPACITY").mean()),
            "lot_residual_rate": float(reasons.eq("PARTIAL_LOT_OR_CASH").mean()),
            "no_minute_data_rate": float(reasons.eq("NO_MINUTE_DATA").mean()),
            "no_turnover_rate": float(reasons.eq("SUSPENDED_OR_NO_TURNOVER").mean()),
            "limit_block_rate": float(reasons.isin(["LIMIT_UP_BUY_BLOCKED", "LIMIT_DOWN_SELL_BLOCKED"]).mean()),
            "avg_slippage_bp": float(orders["slippage_bp"].dropna().mean()) if orders["slippage_bp"].notna().any() else np.nan,
            "avg_participation": float(orders["participation_rate"].dropna().mean()) if orders["participation_rate"].notna().any() else np.nan,
            "avg_abs_exposure_gap": float(equity["exposure_gap"].abs().dropna().mean()) if "exposure_gap" in equity else np.nan,
            "avg_child_fill_ratio": float(orders["fill_ratio"].dropna().mean()),
        })
    return equity, orders, stats


def write_report(summary: pd.DataFrame, out_path: Path) -> None:
    start = str(summary["start"].iloc[0]) if "start" in summary.columns and len(summary) else "2013-07-01"
    trading_start = str(summary["trading_start"].iloc[0]) if "trading_start" in summary.columns and len(summary) else start
    end = str(summary["end"].iloc[0]) if "end" in summary.columns and len(summary) else "2026-06-25"
    settings = ",".join(summary["setting"].drop_duplicates().astype(str).tolist()) if "setting" in summary.columns else "WideA,F2_CAP_MA60"
    capitals = ",".join(f"{x:.0f}" for x in summary["initial_cash"].drop_duplicates().tolist()) if "initial_cash" in summary.columns else "50000,1000000"
    schedules = ",".join(summary["schedule_name"].drop_duplicates().astype(str).tolist()) if "schedule_name" in summary.columns else "am_4x,am_tail_4x,midday_6x"
    cost = float(summary["roundtrip_cost_bp"].iloc[0]) if "roundtrip_cost_bp" in summary.columns and len(summary) else 7.0
    lines = [
        "# ETF Loop 候选策略拆单执行验证",
        "",
        "## 1. 口径",
        "",
        f"- 回测区间：`{start}` 到 `{end}`，交易起点 `{trading_start}`。",
        "- 信号层不变：仍由 ETF Loop 日线候选策略在 T 日收盘后生成 BUY/SELL advice。",
        "- 执行层变化：只拆分原引擎 advice 中真实出现的 BUY/SELL，不按每日 target_weight 强制再平衡。",
        "- 每个子单独立检查分钟成交额、参与率、涨跌停、停牌/无成交、滑点和整百份残差。",
        "- 卖出优先，买入其次；未成交部分会自动滚入后续子窗口，但最后一个子窗口仍不强行追价。",
        "- 价格口径：默认 `--price-adjustment engine`，分钟价格缩放到 ETF Loop 日线 advice 的复权口径，仅用于回放账户一致性；实盘挂单仍应使用原始盘口价格。",
        "",
        "## 2. 拆单方案",
        "",
        "| 方案 | 子窗口 | 含义 |",
        "|---|---|---|",
        "| `am_4x` | 09:35-09:40 / 09:45-09:50 / 10:00-10:05 / 10:20-10:25 | 早盘快速四段执行 |",
        "| `am_tail_4x` | 09:35-09:45 / 10:05-10:15 / 14:30-14:42 / 14:43-14:55 | 早盘一半、尾盘一半 |",
        "| `midday_6x` | 10:00-10:20 / 10:30-10:50 / 11:00-11:20 / 13:05-13:25 / 13:45-14:05 / 14:20-14:40 | 避开开盘噪声，全天中段分散执行 |",
        "",
        "## 3. 复现命令",
        "",
        "```bash",
        (
            "source activate.sh && python runs/etf_loop/run_split_order_execution_validation.py "
            f"--settings {settings} --start {start} --trading-start {trading_start} --end {end} "
            f"--capitals {capitals} --schedules {schedules} --roundtrip-cost-bp {cost:g} --price-adjustment engine"
        ),
        "```",
        "",
        "## 4. 结果总表",
        "",
        "| setting | 资金 | 拆单方案 | 年化 | Sharpe | DD | 订单数 | 部分/失败 | 失败率 | 容量受限 | 均滑点 | 均参与率 | 仓位偏离 |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in summary.sort_values(["setting", "initial_cash", "annual_return"], ascending=[True, True, False]).itertuples():
        lines.append(
            f"| `{r.setting}` | {r.initial_cash:,.0f} | `{r.schedule_name}` | {pct(r.annual_return)} | {r.sharpe:.2f} | "
            f"{pct(r.max_drawdown)} | {r.orders:.0f} | {pct(r.partial_or_failed_rate)} | {pct(r.failed_rate)} | "
            f"{pct(r.capacity_limited_rate)} | {r.avg_slippage_bp:.2f}bp | {pct(r.avg_participation)} | {pct(r.avg_abs_exposure_gap)} |"
        )
    lines += [
        "",
        "## 5. 初步结论",
        "",
        "- 拆单验证是 advice replay 执行层压力测试，不改变策略 Alpha，也不制造原策略没有的每日再平衡订单。",
        "- 如果拆单后的年化显著低于单窗口 VWAP/TWAP，说明原先的窗口均价成交仍偏乐观。",
        "- `am_tail_4x` 和 `midday_6x` 更接近实盘可执行方式；`am_4x` 更适合小资金快速跟随。",
        "- 模拟盘默认不应强行把最后未成交部分补齐，未成交应保留为现金或旧仓，并写入 reconciliation 日志。",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run child-order execution validation for ETF Loop candidates")
    parser.add_argument("--settings", default="WideA,F2_CAP_MA60")
    parser.add_argument("--start", default="2013-07-01")
    parser.add_argument("--trading-start", default="2013-07-01")
    parser.add_argument("--end", default="2026-06-25")
    parser.add_argument("--capitals", default="50000,1000000")
    parser.add_argument("--schedules", default="am_4x,am_tail_4x,midday_6x")
    parser.add_argument("--roundtrip-cost-bp", type=float, default=7.0)
    parser.add_argument("--max-participation", type=float, default=0.10)
    parser.add_argument("--child-kind", choices=["vwap", "twap", "open"], default="vwap")
    parser.add_argument("--slippage-model", choices=["tiered", "sqrt"], default="tiered")
    parser.add_argument("--sqrt-k", type=float, default=40.0)
    parser.add_argument("--price-adjustment", choices=["engine", "none"], default="engine")
    parser.add_argument("--force-signals", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    settings = [x.strip() for x in args.settings.split(",") if x.strip()]
    capitals = [float(x) for x in args.capitals.split(",") if x.strip()]
    schedules = [x.strip() for x in args.schedules.split(",") if x.strip()]
    for schedule in schedules:
        if schedule not in SCHEDULES:
            raise ValueError(f"Unknown schedule: {schedule}")

    rows: list[dict[str, Any]] = []
    for setting in settings:
        account, advice, positions = load_logs(setting, args.start, args.trading_start, args.end, args.force_signals)
        codes = get_codes(advice, positions)
        store = LocalMinuteStore(codes, args.start, args.end, "1min", price_adjustment=args.price_adjustment)
        for capital in capitals:
            for schedule in schedules:
                equity, orders, stats = run_child_advice_replay(
                    setting=setting,
                    trading_start=args.trading_start,
                    initial_cash=capital,
                    schedule_name=schedule,
                    child_kind=args.child_kind,
                    roundtrip_cost_bp=args.roundtrip_cost_bp,
                    max_participation=args.max_participation,
                    slippage_model=args.slippage_model,
                    sqrt_k=args.sqrt_k,
                    commission_bp=1.5,
                    account=account,
                    advice=advice,
                    store=store,
                )
                tag = (
                    f"{setting}_{schedule}_{args.child_kind}_ADVICE_COST{int(args.roundtrip_cost_bp)}BP_"
                    f"CAP{int(capital)}_{args.start.replace('-', '')}_{args.end.replace('-', '')}"
                )
                equity.to_csv(OUT / f"split_child_equity_{tag}.csv", index=False)
                orders.to_csv(OUT / f"split_child_orders_{tag}.csv", index=False)
                row = {
                    "setting": setting,
                    "start": args.start,
                    "trading_start": args.trading_start,
                    "end": args.end,
                    "initial_cash": capital,
                    "schedule_name": schedule,
                    "child_kind": args.child_kind,
                    "roundtrip_cost_bp": args.roundtrip_cost_bp,
                    "max_participation": args.max_participation,
                    "slippage_model": args.slippage_model,
                    "sqrt_k": args.sqrt_k,
                    **stats,
                }
                rows.append(row)
                print(
                    f"{setting:<12s} cap={capital:>10.0f} schedule={schedule:<12s} "
                    f"ann={pct(row['annual_return'])} sharpe={row['sharpe']:.2f} "
                    f"dd={pct(row['max_drawdown'])} failed={pct(row['failed_rate'])}"
                )
    summary = pd.DataFrame(rows)
    summary_path = OUT / f"split_child_execution_summary_{args.start.replace('-', '')}_{args.end.replace('-', '')}.csv"
    report_path = OUT / "split_child_execution_report.md"
    summary.to_csv(summary_path, index=False)
    write_report(summary, report_path)
    print("Saved:", summary_path)
    print("Saved:", report_path)


if __name__ == "__main__":
    main()
