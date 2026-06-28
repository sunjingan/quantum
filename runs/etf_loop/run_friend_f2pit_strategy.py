#!/usr/bin/env python3
"""Friend-style intraday momentum strategy on F2_v3 core + PIT dynamic pool.

This runner is deliberately independent from the existing ETF Loop engine.
It reuses the friend's weighted log-linear momentum score, but uses our ETF
universe construction and explicit trading frictions/risk filters.
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

from run_friend_intraday_replication import (  # noqa: E402
    LOCAL_DATA,
    LocalETFIntradayStore,
    _weighted_regression_score,
    pct,
    summarize,
)
from run_multi_setting_pressure_tests import load_f2_pool, load_pit_pool  # noqa: E402
from strategies.etf_loop_strategy import _lot_floor, calculate_atr  # noqa: E402


OUT = PROJECT_ROOT / "outputs" / "etf_loop" / "friend_f2pit_strategy"


def latest_pit_pool(pit: dict[pd.Timestamp, list[str]], date: pd.Timestamp) -> list[str]:
    keys = [k for k in pit if k <= pd.Timestamp(date)]
    if not keys:
        return []
    return list(pit[max(keys)])


def max_recent_return(prices: np.ndarray, window: int) -> float:
    if len(prices) < window + 1:
        return np.nan
    return float(prices[-1] / prices[-window - 1] - 1.0)


def rank_friend_f2pit(
    store: LocalETFIntradayStore,
    current_date: pd.Timestamp,
    prev_date: pd.Timestamp,
    core_pool: set[str],
    dynamic_pool: set[str],
    *,
    min_days: int,
    max_days: int,
    use_dynamic_lookback: bool,
    dynamic_score_margin: float,
    dynamic_overheat_threshold: float,
    dynamic_overheat_penalty: float,
    use_drawdown_filter: bool,
    use_premium_penalty: bool,
    premium_threshold: float,
    premium_penalty: float,
    min_score: float,
    max_score: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    universe = sorted(core_pool | dynamic_pool)
    for code in universe:
        if code not in store.close.columns:
            continue
        close = store.close[code].loc[:prev_date].dropna().tail(max_days + 10)
        high = store.high[code].loc[:prev_date].dropna().tail(max_days + 10)
        low = store.low[code].loc[:prev_date].dropna().tail(max_days + 10)
        if len(close) < max_days + 10 or len(high) < max_days + 10 or len(low) < max_days + 10:
            continue
        current_px = store.signal_price(code, current_date)
        if np.isnan(current_px) or current_px <= 0:
            continue

        lookback = max_days
        long_atr = np.nan
        short_atr = np.nan
        if use_dynamic_lookback:
            long_atr = calculate_atr(high.values, low.values, close.values, max_days)
            short_atr = calculate_atr(high.values, low.values, close.values, min_days)
            if long_atr <= 0 or np.isnan(long_atr) or np.isnan(short_atr):
                continue
            lookback = int(min_days + (max_days - min_days) * (1.0 - min(0.9, short_atr / long_atr)))
        else:
            lookback = min_days

        prices = np.append(close.values, current_px)[-lookback:]
        metrics = _weighted_regression_score(prices)
        if metrics is None:
            continue
        raw_score = float(metrics["score"])
        score = raw_score

        # Friend-style short crash filters.  These use only previous closes and current 09:50 price.
        if len(prices) >= 5:
            con1 = min(prices[-1] / prices[-2], prices[-2] / prices[-3], prices[-3] / prices[-4]) < 0.95
            con2 = prices[-1] < prices[-2] < prices[-3] < prices[-4] and prices[-1] / prices[-4] < 0.95
            con3 = prices[-2] < prices[-3] < prices[-4] < prices[-5] and prices[-2] / prices[-5] < 0.95
            if con1 or con2 or con3:
                score = 0.0

        overheat_ret20 = max_recent_return(np.append(close.values, current_px), 20)
        is_core = code in core_pool
        is_dynamic = code in dynamic_pool and not is_core
        if is_dynamic and not np.isnan(overheat_ret20) and overheat_ret20 > dynamic_overheat_threshold:
            score *= max(0.0, 1.0 - dynamic_overheat_penalty)

        premium_rate = np.nan
        if use_premium_penalty:
            unit_nav = store.unit_nav(code, prev_date)
            prev_close = float(close.iloc[-1])
            if unit_nav and unit_nav > 0 and not np.isnan(unit_nav):
                premium_rate = (prev_close - unit_nav) / unit_nav
                if premium_rate >= premium_threshold:
                    score -= premium_penalty

        if use_drawdown_filter and len(prices) >= 10:
            recent_peak = float(np.max(prices[-10:]))
            if recent_peak > 0 and prices[-1] / recent_peak - 1.0 < -0.08:
                score = 0.0

        if min_score < score < max_score:
            rows.append({
                "ts_code": code,
                "score": score,
                "raw_score": raw_score,
                "current_price": current_px,
                "lookback": lookback,
                "long_atr": long_atr,
                "short_atr": short_atr,
                "premium_rate": premium_rate,
                "ret20": overheat_ret20,
                "is_core": is_core,
                "is_dynamic_only": is_dynamic,
                **metrics,
            })
    rows.sort(key=lambda x: x["score"], reverse=True)
    if dynamic_score_margin > 0:
        best_core = next((r for r in rows if r["is_core"]), None)
        if best_core is not None:
            filtered = []
            for r in rows:
                if r["is_dynamic_only"] and r["score"] < best_core["score"] + dynamic_score_margin:
                    continue
                filtered.append(r)
            rows = filtered
    return rows


def fill_price(store: LocalETFIntradayStore, code: str, signal_date: pd.Timestamp, mode: str):
    return store.fill_price(code, signal_date, mode)


def execute_price(raw_price: float, side: str, slippage_bp: float) -> float:
    if side == "BUY":
        return raw_price * (1.0 + slippage_bp / 10000.0)
    return raw_price * (1.0 - slippage_bp / 10000.0)


def run_backtest(
    *,
    store: LocalETFIntradayStore,
    pit: dict[pd.Timestamp, list[str]],
    core_pool: set[str],
    fill_mode: str,
    min_days: int,
    max_days: int,
    use_dynamic_lookback: bool,
    target_num: int,
    open_cost_bp: float,
    close_cost_bp: float,
    slippage_bp: float,
    dynamic_score_margin: float,
    dynamic_overheat_threshold: float,
    dynamic_overheat_penalty: float,
    use_drawdown_filter: bool,
    use_premium_penalty: bool,
    premium_threshold: float,
    premium_penalty: float,
    min_score: float,
    max_score: float,
    stop_loss: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, float]]:
    cash = 500000.0
    shares: dict[str, int] = {}
    entry_price: dict[str, float] = {}
    equity_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    signal_rows: list[dict[str, Any]] = []
    cal = list(store.calendar)

    for idx, current_date in enumerate(cal):
        prev_dates = store.close.index[store.close.index < current_date]
        if len(prev_dates) == 0:
            continue
        prev_date = prev_dates[-1]
        if len(store.close.loc[:prev_date]) < max_days + 30:
            continue
        store.set_signal_date(current_date)
        dyn_pool = set(latest_pit_pool(pit, current_date))
        ranked = rank_friend_f2pit(
            store,
            current_date,
            prev_date,
            core_pool,
            dyn_pool,
            min_days=min_days,
            max_days=max_days,
            use_dynamic_lookback=use_dynamic_lookback,
            dynamic_score_margin=dynamic_score_margin,
            dynamic_overheat_threshold=dynamic_overheat_threshold,
            dynamic_overheat_penalty=dynamic_overheat_penalty,
            use_drawdown_filter=use_drawdown_filter,
            use_premium_penalty=use_premium_penalty,
            premium_threshold=premium_threshold,
            premium_penalty=premium_penalty,
            min_score=min_score,
            max_score=max_score,
        )
        for rank, row in enumerate(ranked[:20], start=1):
            signal_rows.append({
                "signal_date": current_date,
                "prev_date": prev_date,
                "rank": rank,
                **row,
                "dynamic_pool_size": len(dyn_pool),
                "core_pool_size": len(core_pool),
            })
        target_codes = [r["ts_code"] for r in ranked[:target_num]]
        target_scores = {r["ts_code"]: r["score"] for r in ranked[:target_num]}
        target_is_dynamic = {r["ts_code"]: r["is_dynamic_only"] for r in ranked[:target_num]}

        # Sell rank-outs and stop-loss hits first.
        for code, qty in list(shares.items()):
            if qty <= 0:
                continue
            sig_px = store.signal_price(code, current_date)
            stop_hit = stop_loss > 0 and code in entry_price and not np.isnan(sig_px) and sig_px <= entry_price[code] * (1.0 - stop_loss)
            if code in target_codes and not stop_hit:
                continue
            fill = fill_price(store, code, current_date, fill_mode)
            if fill is None:
                continue
            trade_px = execute_price(fill.price, "SELL", slippage_bp)
            gross = qty * trade_px
            cost = gross * close_cost_bp / 10000.0
            cash += gross - cost
            shares[code] = 0
            entry_price.pop(code, None)
            trade_rows.append({
                "signal_date": current_date,
                "trade_date": fill.date,
                "ts_code": code,
                "action": "SELL",
                "reason": "STOP_LOSS" if stop_hit else "RANK_OUT",
                "shares": qty,
                "price": trade_px,
                "raw_price": fill.price,
                "gross": gross,
                "cost": cost,
                "cash_after": cash,
                "fill_source": fill.source,
                "score": target_scores.get(code, np.nan),
            })

        held_codes = [c for c, q in shares.items() if q > 0]
        buy_candidates = [c for c in target_codes if shares.get(c, 0) <= 0]
        slots = max(0, target_num - len(held_codes))
        if slots > 0 and buy_candidates:
            budget_each = cash / min(slots, len(buy_candidates))
            for code in buy_candidates[:slots]:
                fill = fill_price(store, code, current_date, fill_mode)
                if fill is None:
                    continue
                trade_px = execute_price(fill.price, "BUY", slippage_bp)
                qty = _lot_floor(budget_each / (trade_px * (1.0 + open_cost_bp / 10000.0)))
                if qty <= 0:
                    continue
                gross = qty * trade_px
                cost = gross * open_cost_bp / 10000.0
                if gross + cost > cash:
                    continue
                cash -= gross + cost
                shares[code] = shares.get(code, 0) + qty
                entry_price[code] = fill.price
                trade_rows.append({
                    "signal_date": current_date,
                    "trade_date": fill.date,
                    "ts_code": code,
                    "action": "BUY",
                    "reason": "RANK_IN_DYNAMIC" if target_is_dynamic.get(code, False) else "RANK_IN_CORE",
                    "shares": qty,
                    "price": trade_px,
                    "raw_price": fill.price,
                    "gross": gross,
                    "cost": cost,
                    "cash_after": cash,
                    "fill_source": fill.source,
                    "score": target_scores.get(code, np.nan),
                })

        value_date = current_date
        if fill_mode == "next_day_open" and idx + 1 < len(cal):
            value_date = cal[idx + 1]
        market_value = 0.0
        held = []
        for code, qty in shares.items():
            if qty <= 0:
                continue
            px = store.latest_price(code, value_date)
            if np.isnan(px):
                px = entry_price.get(code, np.nan)
            if not np.isnan(px):
                market_value += qty * px
                held.append(code)
        portfolio_value = cash + market_value
        equity_rows.append({
            "date": value_date,
            "signal_date": current_date,
            "portfolio_value": portfolio_value,
            "cash": cash,
            "market_value": market_value,
            "cash_ratio": cash / portfolio_value if portfolio_value > 0 else np.nan,
            "position_count": len(held),
            "holding": "|".join(held),
            "top_signal": target_codes[0] if target_codes else "CASH",
            "top_score": ranked[0]["score"] if ranked else np.nan,
        })

    equity = pd.DataFrame(equity_rows).drop_duplicates("date", keep="last").set_index("date").sort_index()
    trades = pd.DataFrame(trade_rows)
    signals = pd.DataFrame(signal_rows)
    stats = summarize(equity)
    return equity, trades, signals, stats


def write_report(rows: list[dict[str, Any]], out_dir: Path, start: str, end: str) -> Path:
    df = pd.DataFrame(rows)
    suffix = f"{start.replace('-', '')}_{end.replace('-', '')}"
    path = out_dir / f"friend_f2pit_strategy_report_{suffix}.md"
    lines = [
        "# Friend F2/PIT Intraday Strategy",
        "",
        f"- window: `{start}` to `{end}`",
        "- independent runner: does not modify ETF Loop engine or existing friend replication script",
        "- universe: F2_v3 static core + latest available G2 PIT monthly dynamic pool",
        "- signal: friend-style weighted log-linear momentum score using previous daily history + current intraday 09:50 price",
        "- default execution: same-day 09:55 open after 09:50 signal; `next_day_open` included as latency stress",
        "- costs: configurable commission bp and percentage slippage bp, applied on each side",
        "",
        "## Reproduce",
        "",
        "```bash",
        f"source activate.sh && python runs/etf_loop/run_friend_f2pit_strategy.py --start {start} --end {end}",
        "```",
        "",
        "## Results",
        "",
        "| variant | fill | N | dyn lb | cost/slip bp | dyn margin | overheat | premium | stop | ann | CAGR | Sharpe | DD | total | final | trades | dyn buys |",
        "|---|---|---:|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['variant']} | {r['fill_mode']} | {r['target_num']} | {r['use_dynamic_lookback']} | "
            f"{r['roundtrip_cost_bp']:.1f} | {r['dynamic_score_margin']:.2f} | "
            f"{r['dynamic_overheat_threshold']:.0%}/{r['dynamic_overheat_penalty']:.0%} | {r['use_premium_penalty']} | "
            f"{r['stop_loss']:.0%} | {pct(r['annual_return'])} | {pct(r['cagr'])} | {r['sharpe_ratio']:.2f} | "
            f"{pct(r['max_drawdown'])} | {pct(r['total_return'])} | {r['final_value']:.0f} | "
            f"{int(r['trade_count'])} | {int(r['dynamic_buy_count'])} |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "- This is not a replacement for the ETF Loop candidate; it is a separate friend-style strategy experiment.",
        "- Same-day execution assumes ETF T+0 trading and minute bars are available after the 09:50 signal.",
        "- If same-day performance collapses under `next_day_open`, the alpha is execution-timing sensitive.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    latest = out_dir / "friend_f2pit_strategy_report.md"
    latest.write_text("\n".join(lines), encoding="utf-8")
    df.to_csv(out_dir / f"friend_f2pit_strategy_summary_{suffix}.csv", index=False)
    df.to_csv(out_dir / "friend_f2pit_strategy_summary.csv", index=False)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Friend-style strategy on F2_v3 + PIT dynamic ETF universe")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2026-06-25")
    parser.add_argument("--signal-time", default="09:50")
    parser.add_argument("--frequency", choices=["1min", "5min"], default="5min")
    parser.add_argument("--fill-modes", default="same_0955_open,next_day_open")
    parser.add_argument("--target-nums", default="1,3")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    core_pool = set(load_f2_pool())
    pit = load_pit_pool()
    all_codes = sorted(core_pool | {c for codes in pit.values() for c in codes})
    store = LocalETFIntradayStore(
        LOCAL_DATA,
        all_codes,
        args.start,
        args.end,
        args.signal_time,
        adjust="none",
        frequency=args.frequency,
    )
    core_pool = core_pool & set(store.ts_codes)
    pit = {k: [c for c in v if c in store.ts_codes] for k, v in pit.items()}

    variants = [
        {
            "variant": "friend_f2pit_base",
            "use_dynamic_lookback": True,
            "dynamic_score_margin": 0.00,
            "dynamic_overheat_threshold": 0.10,
            "dynamic_overheat_penalty": 0.50,
            "use_drawdown_filter": True,
            "use_premium_penalty": True,
            "premium_threshold": 0.05,
            "premium_penalty": 1.0,
            "stop_loss": 0.0,
        },
        {
            "variant": "friend_f2pit_guarded",
            "use_dynamic_lookback": True,
            "dynamic_score_margin": 0.05,
            "dynamic_overheat_threshold": 0.10,
            "dynamic_overheat_penalty": 0.50,
            "use_drawdown_filter": True,
            "use_premium_penalty": True,
            "premium_threshold": 0.05,
            "premium_penalty": 1.0,
            "stop_loss": 0.08,
        },
        {
            "variant": "friend_f2pit_no_premium",
            "use_dynamic_lookback": True,
            "dynamic_score_margin": 0.05,
            "dynamic_overheat_threshold": 0.10,
            "dynamic_overheat_penalty": 0.50,
            "use_drawdown_filter": True,
            "use_premium_penalty": False,
            "premium_threshold": 0.05,
            "premium_penalty": 0.0,
            "stop_loss": 0.08,
        },
    ]
    rows: list[dict[str, Any]] = []
    for fill_mode in [x.strip() for x in args.fill_modes.split(",") if x.strip()]:
        for target_num in [int(x) for x in args.target_nums.split(",") if x.strip()]:
            for variant in variants:
                tag = f"{variant['variant']}_{args.frequency}_{fill_mode}_N{target_num}_{args.start.replace('-', '')}_{args.end.replace('-', '')}"
                equity_path = OUT / f"equity_{tag}.csv"
                trades_path = OUT / f"trades_{tag}.csv"
                signals_path = OUT / f"signals_{tag}.csv"
                if equity_path.exists() and trades_path.exists() and signals_path.exists() and not args.force:
                    equity = pd.read_csv(equity_path, parse_dates=["date"]).set_index("date")
                    trades = pd.read_csv(trades_path)
                    stats = summarize(equity)
                else:
                    equity, trades, signals, stats = run_backtest(
                        store=store,
                        pit=pit,
                        core_pool=core_pool,
                        fill_mode=fill_mode,
                        min_days=20,
                        max_days=60,
                        target_num=target_num,
                        open_cost_bp=1.5,
                        close_cost_bp=1.5,
                        slippage_bp=2.0,
                        min_score=0.0,
                        max_score=6.0,
                        **{k: v for k, v in variant.items() if k != "variant"},
                    )
                    equity.to_csv(equity_path)
                    trades.to_csv(trades_path, index=False)
                    signals.to_csv(signals_path, index=False)
                dyn_buys = int((trades.get("reason", pd.Series(dtype=str)).astype(str).eq("RANK_IN_DYNAMIC")).sum()) if not trades.empty else 0
                row = {
                    "variant": variant["variant"],
                    "frequency": args.frequency,
                    "fill_mode": fill_mode,
                    "target_num": target_num,
                    "roundtrip_cost_bp": 7.0,
                    **{k: v for k, v in variant.items() if k != "variant"},
                    **stats,
                    "trade_count": int(len(trades)),
                    "buy_count": int((trades.get("action", pd.Series(dtype=str)) == "BUY").sum()) if not trades.empty else 0,
                    "sell_count": int((trades.get("action", pd.Series(dtype=str)) == "SELL").sum()) if not trades.empty else 0,
                    "dynamic_buy_count": dyn_buys,
                }
                rows.append(row)
                print(
                    f"{row['variant']:<24s} fill={fill_mode:<14s} N={target_num} "
                    f"ann={pct(row['annual_return'])} sharpe={row['sharpe_ratio']:.2f} "
                    f"dd={pct(row['max_drawdown'])} trades={row['trade_count']} dyn_buys={dyn_buys}"
                )
    report = write_report(rows, OUT, args.start, args.end)
    print("Saved:", OUT / "friend_f2pit_strategy_summary.csv")
    print("Saved:", report)


if __name__ == "__main__":
    main()
