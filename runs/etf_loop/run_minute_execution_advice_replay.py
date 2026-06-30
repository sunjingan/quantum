#!/usr/bin/env python3
"""Minute execution replay from ETF Loop advice logs.

Unlike `run_minute_execution_backtest.py`, this runner does not reconstruct a
daily target portfolio and rebalance to weights.  It replays the original
engine's BUY/SELL advice log, then applies minute-level execution prices,
capacity limits and slippage.  This preserves the candidate strategy's actual
trading semantics.
"""
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

from run_minute_execution_backtest import (  # noqa: E402
    EXECUTION_MODES,
    OUT,
    FillContext,
    LocalMinuteStore,
    SlippageConfig,
    execute_order,
    generate_daily_signal_logs,
    impact_slippage_bp,
    pct,
    summarize,
)


def _suffix(setting: str, start: str, end: str) -> str:
    exp_tag = f"MINEXEC_SIGNAL_{setting}_{start.replace('-', '')}_{end.replace('-', '')}"
    return f"{exp_tag}_h5_{start.replace('-', '')}_{end.replace('-', '')}"


def load_logs(setting: str, start: str, trading_start: str, end: str, force_signals: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    account_path, _, _ = generate_daily_signal_logs(setting, start, trading_start, end, force_signals)
    suffix = _suffix(setting, start, end)
    advice_path = account_path.parent / f"etf_loop_advice_{suffix}.csv"
    positions_path = account_path.parent / f"etf_loop_positions_{suffix}.csv"
    if not advice_path.exists():
        raise FileNotFoundError(advice_path)
    account = pd.read_csv(account_path)
    advice = pd.read_csv(advice_path)
    positions = pd.read_csv(positions_path) if positions_path.exists() else pd.DataFrame()
    for df in [account, advice, positions]:
        for col in ["signal_date", "trade_date", "date"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
    return account, advice, positions


def infer_base_cash(account: pd.DataFrame) -> float:
    vals = account["portfolio_value"].dropna()
    if vals.empty:
        return 500000.0
    return float(vals.iloc[0])


def get_codes(advice: pd.DataFrame, positions: pd.DataFrame) -> list[str]:
    codes = set(str(x) for x in advice["ts_code"].dropna().unique() if str(x) not in {"CASH", "nan"})
    if not positions.empty and "ts_code" in positions.columns:
        codes |= set(str(x) for x in positions["ts_code"].dropna().unique() if str(x) not in {"CASH", "nan"})
    return sorted(codes)


def slippage_config(roundtrip_cost_bp: float, slippage_model: str, sqrt_k: float, commission_bp: float = 1.5) -> SlippageConfig:
    base_slippage_bp = max(0.0, roundtrip_cost_bp / 2.0 - commission_bp)
    return SlippageConfig(
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


def intended_value(row: Any, scale: float, ctx: FillContext | None) -> float:
    action = str(row.action)
    if action == "BUY":
        val = getattr(row, "gross_cost", np.nan)
    else:
        val = getattr(row, "gross_proceeds", np.nan)
    if pd.notna(val) and float(val) > 0:
        return float(val) * scale
    shares = float(getattr(row, "shares", 0) or 0)
    px = ctx.raw_price if ctx is not None else float(getattr(row, "price", np.nan))
    if pd.isna(px) or px <= 0 or shares <= 0:
        return 0.0
    return shares * scale * px


def _fallback_context(row: Any, exec_date: pd.Timestamp, execution_mode: str, price: float) -> FillContext | None:
    if pd.isna(price) or price <= 0:
        return None
    spec = EXECUTION_MODES[execution_mode]
    return FillContext(
        price=float(price),
        raw_price=float(price),
        date=exec_date,
        start_time=spec["start"],
        end_time=spec["end"],
        window_turnover=1e18,
        daily_turnover=1e18,
        window_volume=1e18 / float(price),
        limit_up=np.nan,
        limit_down=np.nan,
        is_limit_up=False,
        is_limit_down=False,
        is_suspended=False,
        spread_proxy_bp=0.0,
        window_range_bp=0.0,
        source="advice_price_fallback",
    )


def execute_share_order(
    *,
    cash: float,
    shares: dict[str, int],
    code: str,
    side: str,
    requested_shares: int,
    ctx: FillContext | None,
    slippage_config: SlippageConfig,
    max_participation: float,
    ignore_liquidity_blocks: bool,
) -> tuple[float, dict[str, int], dict[str, Any]]:
    desired_value = float(requested_shares) * (ctx.raw_price if ctx is not None else np.nan)
    record: dict[str, Any] = {
        "ts_code": code,
        "side": side,
        "order_value": desired_value,
        "filled_value": 0.0,
        "unfilled_value": desired_value,
        "fill_ratio": 0.0,
        "shares": 0,
        "raw_price": np.nan if ctx is None else ctx.raw_price,
        "actual_fill_price": np.nan,
        "commission": 0.0,
        "slippage_bp": np.nan,
        "slippage_model": slippage_config.model,
        "base_slippage_bp": slippage_config.base_slippage_bp,
        "commission_bp": slippage_config.commission_bp,
        "impact_component_bp": np.nan,
        "extra_penalty_bp": np.nan,
        "cross_border_penalty_bp": 0.0,
        "commodity_penalty_bp": 0.0,
        "open_penalty_bp": 0.0,
        "spread_penalty_bp": 0.0,
        "spread_proxy_bp": np.nan if ctx is None else ctx.spread_proxy_bp,
        "window_range_bp": np.nan if ctx is None else ctx.window_range_bp,
        "is_cross_border": False,
        "is_commodity": False,
        "near_limit": False,
        "near_limit_distance_bp": np.nan,
        "capacity_multiplier": 1.0,
        "participation_rate_requested": np.nan,
        "participation_rate": np.nan,
        "daily_turnover": np.nan if ctx is None else ctx.daily_turnover,
        "execution_window_turnover": np.nan if ctx is None else ctx.window_turnover,
        "is_limit_up": False if ctx is None else ctx.is_limit_up,
        "is_limit_down": False if ctx is None else ctx.is_limit_down,
        "is_suspended": False if ctx is None else ctx.is_suspended,
        "reject_reason": "",
    }
    if requested_shares <= 0:
        record["reject_reason"] = "NO_ORDER"
        return cash, shares, record
    if ctx is None:
        record["reject_reason"] = "NO_MINUTE_DATA"
        return cash, shares, record
    if not ignore_liquidity_blocks:
        if ctx.is_suspended:
            record["reject_reason"] = "SUSPENDED_OR_NO_TURNOVER"
            return cash, shares, record
        if side == "BUY" and ctx.is_limit_up:
            record["reject_reason"] = "LIMIT_UP_BUY_BLOCKED"
            return cash, shares, record
        if side == "SELL" and ctx.is_limit_down:
            record["reject_reason"] = "LIMIT_DOWN_SELL_BLOCKED"
            return cash, shares, record
    order_value = requested_shares * ctx.raw_price
    if ignore_liquidity_blocks:
        slip_bp = slippage_config.base_slippage_bp
        too_large = False
        slip_details = {
            "participation_rate_requested": np.nan,
            "impact_component_bp": 0.0,
            "extra_penalty_bp": 0.0,
        }
    else:
        slip_bp, too_large, slip_details = impact_slippage_bp(code, order_value, ctx, slippage_config)
    record.update(slip_details)
    if (not ignore_liquidity_blocks) and too_large and order_value > ctx.window_turnover * max_participation:
        record["reject_reason"] = "PARTIAL_CAPACITY"
    trade_price = ctx.raw_price * (1.0 + slip_bp / 10000.0) if side == "BUY" else ctx.raw_price * (1.0 - slip_bp / 10000.0)
    qty = int(requested_shares // 100) * 100
    if side == "SELL":
        qty = min(qty, shares.get(code, 0))
    else:
        max_cash_qty = int((cash / (trade_price * (1.0 + slippage_config.commission_bp / 10000.0))) // 100) * 100
        qty = min(qty, max_cash_qty)
    if qty <= 0:
        record["reject_reason"] = record["reject_reason"] or "LOT_TOO_SMALL"
        return cash, shares, record
    gross = qty * trade_price
    commission = gross * slippage_config.commission_bp / 10000.0
    if side == "BUY":
        cash -= gross + commission
        shares[code] = shares.get(code, 0) + qty
    else:
        cash += gross - commission
        shares[code] = shares.get(code, 0) - qty
        if shares[code] <= 0:
            shares.pop(code, None)
    record.update({
        "filled_value": gross,
        "unfilled_value": max(0.0, order_value - gross),
        "fill_ratio": gross / order_value if order_value > 0 else 0.0,
        "shares": qty,
        "actual_fill_price": trade_price,
        "commission": commission,
        "slippage_bp": slip_bp,
        "participation_rate": gross / ctx.window_turnover if ctx.window_turnover > 0 else np.nan,
    })
    if qty < requested_shares and not record["reject_reason"]:
        record["reject_reason"] = "PARTIAL_LOT_OR_CASH"
    return cash, shares, record


def mark_value(cash: float, shares: dict[str, int], store: LocalMinuteStore, date: pd.Timestamp, fallback: dict[str, FillContext | None]) -> tuple[float, float]:
    mv = 0.0
    for code, qty in list(shares.items()):
        px = store.valuation_close_price(code, date)
        if pd.isna(px) or px <= 0:
            ctx = fallback.get(code)
            px = ctx.raw_price if ctx is not None else np.nan
        if pd.notna(px) and px > 0:
            mv += qty * px
    return cash + mv, mv


def run_replay(
    *,
    setting: str,
    start: str,
    trading_start: str,
    end: str,
    initial_cash: float,
    execution_mode: str,
    roundtrip_cost_bp: float,
    max_participation: float,
    slippage_model: str,
    sqrt_k: float,
    commission_bp: float,
    price_adjustment: str,
    replay_mode: str,
    ignore_liquidity_blocks: bool,
    missing_price_policy: str,
    account: pd.DataFrame,
    advice: pd.DataFrame,
    store: LocalMinuteStore,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    cfg = slippage_config(roundtrip_cost_bp, slippage_model, sqrt_k, commission_bp)
    base_cash = infer_base_cash(account)
    scale = initial_cash / base_cash if base_cash > 0 else 1.0
    cash = initial_cash
    shares: dict[str, int] = {}
    equity_rows: list[dict[str, Any]] = []
    order_rows: list[dict[str, Any]] = []
    advice = advice[advice["signal_date"] >= pd.Timestamp(trading_start)].copy()
    grouped = {k: v.sort_values(["action", "ts_code"]) for k, v in advice.groupby("signal_date")}
    extra_delay = max(0, int(EXECUTION_MODES[execution_mode].get("delay", "1")) - 1)
    account_trade_dates = (
        pd.to_datetime(account.loc[account["signal_date"] >= pd.Timestamp(trading_start), "trade_date"], errors="coerce")
        .dropna()
        .drop_duplicates()
        .sort_values()
        .tolist()
    )
    delayed_trade_date = {
        account_trade_dates[i]: account_trade_dates[i + extra_delay]
        for i in range(0, max(0, len(account_trade_dates) - extra_delay))
    }

    for acc in account.itertuples():
        signal_date = pd.Timestamp(acc.signal_date)
        if signal_date < pd.Timestamp(trading_start):
            continue
        base_exec_date = pd.Timestamp(acc.trade_date)
        exec_date = delayed_trade_date.get(base_exec_date)
        if exec_date is None:
            continue
        day = grouped.get(signal_date, pd.DataFrame())
        trade_rows = day[day["action"].isin(["BUY", "SELL"])].copy() if not day.empty else pd.DataFrame()
        codes = sorted(set(shares) | set(trade_rows["ts_code"].dropna().astype(str).tolist()))
        contexts = {code: store.fill_context(code, exec_date, execution_mode) for code in codes}

        for side in ["SELL", "BUY"]:
            side_rows = trade_rows[trade_rows["action"].eq(side)] if not trade_rows.empty else pd.DataFrame()
            for row in side_rows.itertuples():
                code = str(row.ts_code)
                if code == "CASH":
                    continue
                ctx = contexts.get(code)
                if ctx is None and missing_price_policy == "advice":
                    ctx = _fallback_context(row, exec_date, execution_mode, float(getattr(row, "price", np.nan)))
                if replay_mode == "shares":
                    requested_shares = int((float(getattr(row, "shares", 0) or 0) * scale) // 100) * 100
                    if requested_shares <= 0:
                        continue
                    cash, shares, rec = execute_share_order(
                        cash=cash,
                        shares=shares,
                        code=code,
                        side=side,
                        requested_shares=requested_shares,
                        ctx=ctx,
                        slippage_config=cfg,
                        max_participation=max_participation,
                        ignore_liquidity_blocks=ignore_liquidity_blocks,
                    )
                    desired = rec.get("order_value", np.nan)
                else:
                    desired = intended_value(row, scale, ctx)
                    if desired <= 0:
                        continue
                    cash, shares, rec = execute_order(
                        cash=cash,
                        shares=shares,
                        code=code,
                        side=side,
                        desired_value=desired,
                        ctx=ctx,
                        slippage_config=cfg,
                        max_participation=max_participation,
                    )
                rec.update({
                    "setting": setting,
                    "signal_date": signal_date,
                    "trade_date": exec_date,
                    "execution_mode": execution_mode,
                    "roundtrip_cost_bp": roundtrip_cost_bp,
                    "price_adjustment": price_adjustment,
                    "replay_mode": replay_mode,
                    "ignore_liquidity_blocks": ignore_liquidity_blocks,
                    "missing_price_policy": missing_price_policy,
                    "advice_reason": getattr(row, "reason", ""),
                    "advice_bucket": getattr(row, "bucket", ""),
                    "advice_shares": getattr(row, "shares", np.nan),
                    "advice_price": getattr(row, "price", np.nan),
                    "scale": scale,
                    "target_exposure": float(getattr(acc, "target_exposure", 1.0)),
                    "execution_start_time": EXECUTION_MODES[execution_mode]["start"],
                    "execution_end_time": EXECUTION_MODES[execution_mode]["end"],
                })
                order_rows.append(rec)

        portfolio_value, market_value = mark_value(cash, shares, store, exec_date, contexts)
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
            "position_count": sum(1 for qty in shares.values() if qty > 0),
            "execution_mode": execution_mode,
            "roundtrip_cost_bp": roundtrip_cost_bp,
            "price_adjustment": price_adjustment,
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
        })
    return equity, orders, stats


def write_report(summary: pd.DataFrame, path: Path) -> None:
    lines = [
        "# ETF Loop Advice Replay Minute Execution",
        "",
        "## 1. 口径",
        "",
        "- 信号和交易动作来自原引擎 `etf_loop_advice_*.csv`。",
        "- 不按每日 target_weight 强制再平衡，只重放原引擎实际 BUY/SELL。",
        "- 成交价格、容量、滑点、涨跌停和停牌约束用本地分钟数据重新计算。",
        "",
        "## 2. 结果",
        "",
        "| setting | 资金 | 执行 | 双边bp | 年化 | CAGR | Sharpe | DD | 订单数 | 失败率 | 容量受限 | 均滑点 | 均参与率 | 仓位偏离 |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in summary.sort_values(["setting", "initial_cash", "execution_mode", "roundtrip_cost_bp"]).itertuples():
        lines.append(
            f"| `{r.setting}` | {r.initial_cash:,.0f} | `{r.execution_mode}` | {r.roundtrip_cost_bp:.0f} | "
            f"{pct(r.annual_return)} | {pct(r.cagr)} | {r.sharpe:.2f} | {pct(r.max_drawdown)} | "
            f"{r.orders:.0f} | {pct(r.failed_rate)} | {pct(r.capacity_limited_rate)} | "
            f"{r.avg_slippage_bp:.2f}bp | {pct(r.avg_participation)} | {pct(r.avg_abs_exposure_gap)} |"
        )
    lines += [
        "",
        "## 3. 复现命令",
        "",
        "```bash",
        "source activate.sh && python runs/etf_loop/run_minute_execution_advice_replay.py --settings WideA,F2_CAP_MA60 --start 2013-07-01 --trading-start 2013-07-01 --end 2026-06-25 --capitals 1000000,3000000,5000000,10000000,30000000 --execution-modes vwap_0935_1030 --roundtrip-cost-bps 5,7,10,15,20",
        "```",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay ETF Loop advice with minute execution constraints")
    parser.add_argument("--settings", default="WideA,F2_CAP_MA60")
    parser.add_argument("--start", default="2013-07-01")
    parser.add_argument("--trading-start", default="2013-07-01")
    parser.add_argument("--end", default="2026-06-25")
    parser.add_argument("--capitals", default="1000000")
    parser.add_argument("--execution-modes", default="vwap_0935_1030")
    parser.add_argument("--roundtrip-cost-bps", default="7")
    parser.add_argument("--max-participation", type=float, default=0.10)
    parser.add_argument("--slippage-model", choices=["tiered", "sqrt"], default="tiered")
    parser.add_argument("--sqrt-k", type=float, default=40.0)
    parser.add_argument("--commission-bp", type=float, default=1.5)
    parser.add_argument("--price-adjustment", choices=["engine", "none"], default="engine")
    parser.add_argument("--replay-mode", choices=["value", "shares"], default="value")
    parser.add_argument("--ignore-liquidity-blocks", action="store_true")
    parser.add_argument("--missing-price-policy", choices=["skip", "advice"], default="skip")
    parser.add_argument("--tag-suffix", default="advice_replay")
    parser.add_argument("--force-signals", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    settings = [x.strip() for x in args.settings.split(",") if x.strip()]
    capitals = [float(x) for x in args.capitals.split(",") if x.strip()]
    modes = [x.strip() for x in args.execution_modes.split(",") if x.strip()]
    costs = [float(x) for x in args.roundtrip_cost_bps.split(",") if x.strip()]
    rows: list[dict[str, Any]] = []
    summary_path = OUT / f"advice_replay_summary_{args.tag_suffix}_{args.start.replace('-', '')}_{args.end.replace('-', '')}.csv"
    report_path = OUT / f"advice_replay_report_{args.tag_suffix}_{args.start.replace('-', '')}_{args.end.replace('-', '')}.md"

    for setting in settings:
        account, advice, positions = load_logs(setting, args.start, args.trading_start, args.end, args.force_signals)
        codes = get_codes(advice, positions)
        store = LocalMinuteStore(codes, args.start, args.end, "1min", price_adjustment=args.price_adjustment)
        for capital in capitals:
            for mode in modes:
                for cost in costs:
                    equity, orders, stats = run_replay(
                        setting=setting,
                        start=args.start,
                        trading_start=args.trading_start,
                        end=args.end,
                        initial_cash=capital,
                        execution_mode=mode,
                        roundtrip_cost_bp=cost,
                        max_participation=args.max_participation,
                        slippage_model=args.slippage_model,
                        sqrt_k=args.sqrt_k,
                        commission_bp=args.commission_bp,
                        price_adjustment=args.price_adjustment,
                        replay_mode=args.replay_mode,
                        ignore_liquidity_blocks=args.ignore_liquidity_blocks,
                        missing_price_policy=args.missing_price_policy,
                        account=account,
                        advice=advice,
                        store=store,
                    )
                    tag = (
                        f"{setting}_{mode}_COST{int(cost)}BP_CAP{int(capital)}_{args.tag_suffix}_"
                        f"{args.start.replace('-', '')}_{args.end.replace('-', '')}"
                    )
                    equity.to_csv(OUT / f"advice_replay_equity_{tag}.csv", index=False)
                    orders.to_csv(OUT / f"advice_replay_orders_{tag}.csv", index=False)
                    row = {
                        "setting": setting,
                        "start": args.start,
                        "trading_start": args.trading_start,
                        "end": args.end,
                        "initial_cash": capital,
                        "execution_mode": mode,
                        "roundtrip_cost_bp": cost,
                        "max_participation": args.max_participation,
                        "slippage_model": args.slippage_model,
                        **stats,
                    }
                    rows.append(row)
                    print(
                        f"{setting:<12s} cap={capital:>10.0f} mode={mode:<16s} cost={cost:>4.0f}bp "
                        f"ann={pct(row['annual_return'])} sharpe={row['sharpe']:.2f} dd={pct(row['max_drawdown'])} "
                        f"failed={pct(row.get('failed_rate', np.nan))}"
                    )
                    summary = pd.DataFrame(rows)
                    summary.to_csv(summary_path, index=False)
                    write_report(summary, report_path)
    summary = pd.DataFrame(rows)
    summary.to_csv(summary_path, index=False)
    write_report(summary, report_path)
    print("Saved:", summary_path)
    print("Saved:", report_path)


if __name__ == "__main__":
    main()
