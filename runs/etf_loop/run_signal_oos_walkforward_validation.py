#!/usr/bin/env python3
"""Signal-layer OOS, robustness, and walk-forward validation for ETF Loop.

This deliberately excludes minute execution, order book penalties, split
orders, and participation caps.  The goal is to test whether the signal and
parameter choices survive out-of-sample checks before execution-layer work.
"""
from __future__ import annotations

import pickle
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from strategies.etf_loop_engine import EngineParams, run_backtest  # noqa: E402


OUT = PROJECT_ROOT / "outputs" / "etf_loop" / "signal_oos_walkforward_20260629"
START_ALL = "2013-07-01"
END_ALL = "2026-06-25"
BASE_COST = {
    "open_cost": 0.00015,
    "close_cost": 0.00015,
    "slippage": 0.0002,
    "use_dynamic_cost": False,
    "participation_cap": None,
    "execution_price_mode": "open",
    "execution_delay_days": 1,
}


def load_pit_pool() -> dict[pd.Timestamp, list[str]]:
    path = PROJECT_ROOT / "data" / "tushare_cache" / "sector_prosperity" / "etf_pool_G2_PIT_monthly.pkl"
    with open(path, "rb") as f:
        pools = pickle.load(f)
    return {pd.Timestamp(k): list(v) for k, v in pools.items()}


def load_f2_pool() -> list[str]:
    path = PROJECT_ROOT / "data" / "tushare_cache" / "sector_prosperity" / "etf_pool_F2_v3.csv"
    return sorted(pd.read_csv(path, dtype={"ts_code": str})["ts_code"].astype(str).tolist())


def base_params(pit: dict[pd.Timestamp, list[str]], f2: list[str], start: str, end: str, tag: str) -> dict[str, Any]:
    return {
        **BASE_COST,
        "pit_pools": pit,
        "core_pool": f2,
        "holdings_num": 5,
        "lookback_days": 25,
        "start": start,
        "end": end,
        "exp_tag": tag,
        "initial_cash": 500_000.0,
        "dynamic_fusion_mode": "capped",
        "dynamic_max_slots": 1,
        "dynamic_max_total_weight": 0.10,
        "dynamic_score_margin": 0.05,
        "dynamic_overheat_lookback": 20,
        "dynamic_overheat_threshold": 0.10,
        "dynamic_overheat_penalty": 0.50,
        "mr_ma_period": 60,
        "mr_threshold": 1.14,
        "mr_penalty": 0.50,
        "use_atr_stop_loss": True,
        "atr_multiplier": 2.0,
        "stop_loss": 0.95,
    }


def variant_overrides(name: str) -> dict[str, Any]:
    if name == "F2_CAP_MA60":
        return {}
    if name == "WideA":
        return {
            "use_market_adaptive_holdings": True,
            "adaptive_mode": "bench_20d_ret",
            "adaptive_window": 15,
            "adaptive_tiers_ret": "0.06,0.03,0.00,-0.02,-0.05,-0.08",
            "adaptive_tiers_n": "5,5,4,3,2,1,0",
            "adaptive_tiers_exposure": "1,1,1,1,1,1,0",
        }
    if name == "Exph_v3_exp_looser":
        return {
            "use_market_adaptive_holdings": True,
            "adaptive_mode": "bench_20d_ret",
            "adaptive_window": 15,
            "adaptive_tiers_ret": "0.05,0.02,0.00,-0.03,-0.06",
            "adaptive_tiers_n": "5,5,4,4,3,0",
            "adaptive_tiers_exposure": "1,1,0.85,0.65,0.45,0",
        }
    raise ValueError(name)


def make_params(
    pit: dict[pd.Timestamp, list[str]],
    f2: list[str],
    start: str,
    end: str,
    tag: str,
    variant: str,
    overrides: dict[str, Any] | None = None,
) -> EngineParams:
    payload = base_params(pit, f2, start, end, tag)
    payload.update(variant_overrides(variant))
    if overrides:
        payload.update(overrides)
    return EngineParams(**payload)


def win_rate(equity: pd.DataFrame) -> float:
    daily = equity["portfolio_value"].pct_change().dropna()
    if daily.empty:
        return np.nan
    return float((daily > 0).mean())


def benchmark_stats(equity: pd.DataFrame) -> dict[str, float]:
    if "benchmark_value" not in equity.columns:
        return {"benchmark_annual": np.nan, "benchmark_drawdown": np.nan, "alpha_vs_hs300": np.nan}
    bench = equity["benchmark_value"].dropna()
    daily = bench.pct_change().dropna()
    if len(daily) < 2:
        return {"benchmark_annual": np.nan, "benchmark_drawdown": np.nan, "alpha_vs_hs300": np.nan}
    annual = float(daily.mean() * 252.0)
    dd = float((bench / bench.cummax() - 1.0).min())
    return {"benchmark_annual": annual, "benchmark_drawdown": dd}


def summarize_equity(equity: pd.DataFrame) -> dict[str, float]:
    if equity.empty or "portfolio_value" not in equity.columns:
        return {
            "annual_return": np.nan,
            "annual_volatility": np.nan,
            "sharpe_ratio": np.nan,
            "max_drawdown": np.nan,
            "total_return": np.nan,
            "final_value": np.nan,
        }
    nav = equity["portfolio_value"].astype(float).dropna()
    if len(nav) < 2:
        final_value = float(nav.iloc[-1]) if len(nav) else np.nan
        return {
            "annual_return": 0.0,
            "annual_volatility": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "total_return": 0.0,
            "final_value": final_value,
        }
    daily = nav.pct_change().dropna()
    annual = float(daily.mean() * 252.0)
    vol = float(daily.std() * np.sqrt(252.0)) if len(daily) > 1 else 0.0
    dd = float((nav / nav.cummax() - 1.0).min())
    return {
        "annual_return": annual,
        "annual_volatility": vol,
        "sharpe_ratio": float(annual / vol) if vol > 0 else 0.0,
        "max_drawdown": dd,
        "total_return": float(nav.iloc[-1] / nav.iloc[0] - 1.0),
        "final_value": float(nav.iloc[-1]),
    }


def metric_row(
    *,
    section: str,
    variant: str,
    label: str,
    params: EngineParams,
    equity: pd.DataFrame,
    trades: pd.DataFrame,
    stats: dict[str, float],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bench = benchmark_stats(equity)
    row = {
        "section": section,
        "variant": variant,
        "label": label,
        "tag": params.exp_tag,
        "start": params.start,
        "end": params.end,
        "annual_return": float(stats.get("annual_return", np.nan)),
        "annual_volatility": float(stats.get("annual_volatility", np.nan)),
        "sharpe_ratio": float(stats.get("sharpe_ratio", np.nan)),
        "max_drawdown": float(stats.get("max_drawdown", np.nan)),
        "calmar": np.nan,
        "total_return": float(stats.get("total_return", np.nan)),
        "final_value": float(stats.get("final_value", np.nan)),
        "win_rate": win_rate(equity),
        "trade_count": int(len(trades)),
        "buy_count": int(trades.get("action", pd.Series(dtype=str)).astype(str).eq("BUY").sum()) if not trades.empty else 0,
        "sell_count": int(trades.get("action", pd.Series(dtype=str)).astype(str).eq("SELL").sum()) if not trades.empty else 0,
        "benchmark_annual": bench.get("benchmark_annual", np.nan),
        "benchmark_drawdown": bench.get("benchmark_drawdown", np.nan),
    }
    dd = row["max_drawdown"]
    if np.isfinite(dd) and dd < 0:
        row["calmar"] = row["annual_return"] / abs(dd)
    row["alpha_vs_hs300"] = row["annual_return"] - row["benchmark_annual"]
    if extra:
        row.update(extra)
    return row


def run_case(
    pit: dict[pd.Timestamp, list[str]],
    f2: list[str],
    *,
    section: str,
    variant: str,
    label: str,
    start: str,
    end: str,
    overrides: dict[str, Any] | None = None,
    save_equity: bool = False,
) -> tuple[dict[str, Any], pd.DataFrame]:
    safe_label = label.replace(" ", "_").replace("/", "_").replace(".", "p").replace("%", "pct")
    tag = f"SIGVAL_{section}_{variant}_{safe_label}"[:100]
    params = make_params(pit, f2, start, end, tag, variant, overrides)
    equity, trades, audit = run_backtest(params)
    row = metric_row(
        section=section,
        variant=variant,
        label=label,
        params=params,
        equity=equity,
        trades=trades,
        stats=audit["stats"],
        extra=overrides or {},
    )
    if save_equity:
        equity.to_csv(OUT / f"equity_{tag}_{start.replace('-', '')}_{end.replace('-', '')}.csv")
    print(
        f"{section:14s} {variant:20s} {label:24s} "
        f"ann={row['annual_return']*100:7.2f}% sharpe={row['sharpe_ratio']:5.2f} "
        f"dd={row['max_drawdown']*100:7.2f}% trades={row['trade_count']}"
        ,
        flush=True,
    )
    return row, equity


def save_partial(rows: list[dict[str, Any]], name: str = "partial") -> None:
    if not rows:
        return
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT / f"signal_oos_walkforward_results_{name}.csv", index=False)


def fixed_oos_and_yearly(pit: dict[pd.Timestamp, list[str]], f2: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    variants = ["F2_CAP_MA60", "WideA", "Exph_v3_exp_looser"]
    windows = [
        ("train_2018_2021", "2018-01-01", "2021-12-31"),
        ("valid_2022", "2022-01-01", "2022-12-31"),
        ("test_2023_2026", "2023-01-01", END_ALL),
        ("long_2013_2026", START_ALL, END_ALL),
    ]
    for variant in variants:
        for label, start, end in windows:
            row, _ = run_case(pit, f2, section="fixed_oos", variant=variant, label=label, start=start, end=end)
            rows.append(row)
            save_partial(rows, "fixed_yearly_partial")

    for variant in variants:
        for year in range(2018, 2027):
            start = f"{year}-01-01"
            end = END_ALL if year == 2026 else f"{year}-12-31"
            row, _ = run_case(pit, f2, section="yearly", variant=variant, label=str(year), start=start, end=end)
            rows.append(row)
            save_partial(rows, "fixed_yearly_partial")
    return rows


def robustness_cases() -> list[tuple[str, str, dict[str, Any]]]:
    cases: list[tuple[str, str, dict[str, Any]]] = []
    for v in [10, 15, 20, 25, 30, 40, 60]:
        cases.append(("lookback_days", f"lookback={v}", {"lookback_days": v}))
    for v in [1, 2, 3, 5, 7]:
        cases.append(("holdings_num", f"holdings={v}", {"holdings_num": v}))
    for v in [0.0, 0.90, 0.93, 0.95, 0.97]:
        cases.append(("stop_loss", f"stop={v:.2f}", {"stop_loss": v}))
    for v in [1.5, 2.0, 2.5, 3.0]:
        cases.append(("atr_multiplier", f"atr={v:.1f}", {"use_atr_stop_loss": True, "atr_multiplier": v}))
    cases.append(("atr_multiplier", "atr=off", {"use_atr_stop_loss": False}))
    for v in [40, 60, 80]:
        cases.append(("mr_ma_period", f"ma={v}", {"mr_ma_period": v}))
    for v in [1.10, 1.14, 1.18, 1.22]:
        cases.append(("mr_threshold", f"mr_threshold={v:.2f}", {"mr_threshold": v}))
    for v in [0.30, 0.50, 0.70, 1.00]:
        cases.append(("mr_penalty", f"mr_penalty={v:.2f}", {"mr_penalty": v}))
    for v in [0.0, 0.05, 0.10, 0.20]:
        cases.append(("dynamic_max_total_weight", f"dyn_weight={v:.2f}", {"dynamic_max_total_weight": v}))
    for v in [0.00, 0.05, 0.10, 0.20]:
        cases.append(("dynamic_score_margin", f"dyn_margin={v:.2f}", {"dynamic_score_margin": v}))
    for v in [0.05, 0.10, 0.15, 0.20]:
        cases.append(("dynamic_overheat_threshold", f"dyn_hot={v:.2f}", {"dynamic_overheat_threshold": v}))
    for v in [0.25, 0.50, 0.75, 1.00]:
        cases.append(("dynamic_overheat_penalty", f"dyn_penalty={v:.2f}", {"dynamic_overheat_penalty": v}))
    return cases


def widea_robustness_cases() -> list[tuple[str, str, dict[str, Any]]]:
    cases: list[tuple[str, str, dict[str, Any]]] = []
    for v in [5, 10, 15, 20, 30, 60]:
        cases.append(("adaptive_window", f"adaptive_window={v}", {"adaptive_window": v}))
    tier_sets = {
        "wideA_base": ("0.06,0.03,0.00,-0.02,-0.05,-0.08", "5,5,4,3,2,1,0"),
        "wideA_tighter": ("0.07,0.04,0.01,-0.01,-0.04,-0.07", "5,5,4,3,2,1,0"),
        "wideA_looser": ("0.05,0.02,-0.01,-0.03,-0.06,-0.10", "5,5,4,3,2,1,0"),
        "current": ("0.05,0.02,0.00,-0.03,-0.06", "5,4,3,2,1,0"),
        "wideB": ("0.05,0.01,-0.02,-0.05,-0.08,-0.12", "5,5,4,3,2,1,0"),
    }
    for label, (ret, n) in tier_sets.items():
        cases.append(("adaptive_tiers", label, {"adaptive_window": 15, "adaptive_tiers_ret": ret, "adaptive_tiers_n": n}))
    return cases


def robustness(pit: dict[pd.Timestamp, list[str]], f2: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for axis, label, overrides in robustness_cases():
        row, _ = run_case(
            pit, f2, section="robust_f2", variant="F2_CAP_MA60", label=label,
            start=START_ALL, end=END_ALL, overrides=overrides,
        )
        row["axis"] = axis
        rows.append(row)
        save_partial(rows, "robust_partial")
    for axis, label, overrides in widea_robustness_cases():
        row, _ = run_case(
            pit, f2, section="robust_widea", variant="WideA", label=label,
            start=START_ALL, end=END_ALL, overrides=overrides,
        )
        row["axis"] = axis
        rows.append(row)
        save_partial(rows, "robust_partial")
    return rows


def wf_candidate_specs() -> list[tuple[str, str, dict[str, Any]]]:
    return [
        ("F2_CAP_MA60", "F2_base", {}),
        ("F2_CAP_MA60", "F2_LB30", {"lookback_days": 30}),
        ("F2_CAP_MA60", "F2_H7", {"holdings_num": 7}),
        ("WideA", "WideA_base", {}),
        ("Exph_v3_exp_looser", "Exph_v3_exp_looser", {}),
    ]


def selection_score(row: dict[str, Any]) -> float:
    ann = row["annual_return"]
    sharpe = row["sharpe_ratio"]
    dd = abs(row["max_drawdown"])
    if np.isnan(ann) or np.isnan(sharpe) or np.isnan(dd):
        return -1e9
    return float(sharpe + 0.50 * ann - 0.50 * dd)


def month_starts(start: str, end: str) -> list[pd.Timestamp]:
    starts = pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="MS")
    return [pd.Timestamp(x) for x in starts]


def filter_test_equity(equity: pd.DataFrame, test_start: str) -> pd.DataFrame:
    idx = pd.to_datetime(equity.index)
    return equity.loc[idx >= pd.Timestamp(test_start)].copy()


def filter_test_trades(trades: pd.DataFrame, test_start: str) -> pd.DataFrame:
    if trades.empty:
        return trades
    date_col = "trade_date" if "trade_date" in trades.columns else "date"
    if date_col not in trades.columns:
        return trades
    dates = pd.to_datetime(trades[date_col], errors="coerce")
    return trades.loc[dates >= pd.Timestamp(test_start)].copy()


def walk_forward(pit: dict[pd.Timestamp, list[str]], f2: list[str]) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    nav_parts: list[pd.DataFrame] = []
    candidates = wf_candidate_specs()
    current_nav = 500_000.0

    for test_start_ts in month_starts("2021-07-01", "2026-06-01"):
        test_end_ts = min(test_start_ts + pd.offsets.MonthEnd(0), pd.Timestamp(END_ALL))
        if test_start_ts > pd.Timestamp(END_ALL):
            break
        train_end_ts = test_start_ts - pd.Timedelta(days=1)
        train_start_ts = test_start_ts - pd.DateOffset(years=3)
        train_start = train_start_ts.strftime("%Y-%m-%d")
        train_end = train_end_ts.strftime("%Y-%m-%d")
        test_start = test_start_ts.strftime("%Y-%m-%d")
        test_end = test_end_ts.strftime("%Y-%m-%d")

        train_rows: list[dict[str, Any]] = []
        for variant, cand_name, overrides in candidates:
            row, _ = run_case(
                pit, f2, section="wf_train", variant=variant, label=f"{test_start}_{cand_name}",
                start=train_start, end=train_end, overrides=overrides,
            )
            row["candidate"] = cand_name
            row["test_month"] = test_start[:7]
            row["selection_score"] = selection_score(row)
            train_rows.append(row)
        rows.extend(train_rows)
        save_partial(rows, "walkforward_partial")
        best = max(train_rows, key=lambda r: r["selection_score"])
        spec = next((s for s in candidates if s[1] == best["candidate"]), None)
        if spec is None:
            raise RuntimeError(best)
        variant, cand_name, overrides = spec
        warmup_start = (test_start_ts - pd.DateOffset(days=260)).strftime("%Y-%m-%d")
        params = make_params(
            pit, f2, warmup_start, test_end,
            f"SIGVAL_wf_test_{test_start[:7]}_{cand_name}",
            variant, {**overrides, "initial_cash": current_nav, "trading_start": test_start},
        )
        equity, trades, audit = run_backtest(params)
        equity_test = filter_test_equity(equity, test_start)
        trades_test = filter_test_trades(trades, test_start)
        test_stats = summarize_equity(equity_test)
        row = metric_row(
            section="wf_test",
            variant=variant,
            label=test_start[:7],
            params=params,
            equity=equity_test,
            trades=trades_test,
            stats=test_stats,
            extra={
                "candidate": cand_name,
                "train_start": train_start,
                "train_end": train_end,
                "selection_score": best["selection_score"],
                "train_annual_return": best["annual_return"],
                "train_sharpe_ratio": best["sharpe_ratio"],
                "train_max_drawdown": best["max_drawdown"],
            },
        )
        row["start"] = test_start
        row["end"] = test_end
        rows.append(row)
        save_partial(rows, "walkforward_partial")
        eq = equity_test.reset_index().rename(columns={"index": "date"})
        if "date" not in eq.columns:
            eq = equity_test.reset_index()
        eq["test_month"] = test_start[:7]
        eq["candidate"] = cand_name
        nav_parts.append(eq)
        current_nav = float(equity_test["portfolio_value"].iloc[-1])
        print(
            f"wf selected {test_start[:7]} {cand_name} "
            f"train_score={best['selection_score']:.3f} test_ann={row['annual_return']*100:.2f}% "
            f"nav={current_nav:.0f}"
            ,
            flush=True,
        )
        if test_end_ts >= pd.Timestamp(END_ALL):
            break

    wf_nav = pd.concat(nav_parts, ignore_index=True) if nav_parts else pd.DataFrame()
    return rows, wf_nav


def pct(x: Any) -> str:
    try:
        if pd.isna(x):
            return ""
        return f"{float(x) * 100:.2f}%"
    except Exception:
        return ""


def fnum(x: Any, digits: int = 2) -> str:
    try:
        if pd.isna(x):
            return ""
        return f"{float(x):.{digits}f}"
    except Exception:
        return ""


def write_report(results: pd.DataFrame, wf_nav: pd.DataFrame) -> Path:
    report = OUT / "signal_oos_walkforward_report.md"
    lines: list[str] = [
        "# ETF Loop Signal-Layer OOS / Walk-Forward Validation",
        "",
        "## Scope",
        "",
        "- This rerun validates signal/parameter robustness only.",
        "- Execution is fixed to `T close signal -> T+1 open fill`.",
        "- Cost is fixed at `commission 1.5bp + slippage 2bp per side`.",
        "- Excluded: minute VWAP/TWAP, order-book penalties, split orders, participation caps, capacity pressure.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "source activate.sh",
        "python runs/etf_loop/run_signal_oos_walkforward_validation.py",
        "```",
        "",
        "## Fixed OOS",
        "",
        "| variant | window | annual | sharpe | dd | calmar | win | alpha | trades |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    fixed = results[results["section"].eq("fixed_oos")].copy()
    order = {"train_2018_2021": 0, "valid_2022": 1, "test_2023_2026": 2, "long_2013_2026": 3}
    fixed["_order"] = fixed["label"].map(order).fillna(99)
    for _, r in fixed.sort_values(["variant", "_order"]).iterrows():
        lines.append(
            f"| {r['variant']} | {r['label']} | {pct(r['annual_return'])} | {fnum(r['sharpe_ratio'])} | "
            f"{pct(r['max_drawdown'])} | {fnum(r['calmar'])} | {pct(r['win_rate'])} | {pct(r['alpha_vs_hs300'])} | {int(r['trade_count'])} |"
        )

    lines += [
        "",
        "## Yearly Breakdown",
        "",
        "| variant | year | annual | sharpe | dd | win | alpha | trades |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    yearly = results[results["section"].eq("yearly")].copy()
    for _, r in yearly.sort_values(["variant", "label"]).iterrows():
        lines.append(
            f"| {r['variant']} | {r['label']} | {pct(r['annual_return'])} | {fnum(r['sharpe_ratio'])} | "
            f"{pct(r['max_drawdown'])} | {pct(r['win_rate'])} | {pct(r['alpha_vs_hs300'])} | {int(r['trade_count'])} |"
        )

    lines += [
        "",
        "## Robustness Summary",
        "",
        "| section | axis | count | annual min/median/max | dd min/median/max | sharpe min/median/max |",
        "|---|---|---:|---:|---:|---:|",
    ]
    robust = results[results["section"].isin(["robust_f2", "robust_widea"])].copy()
    for (section, axis), g in robust.groupby(["section", "axis"], dropna=False):
        lines.append(
            f"| {section} | {axis} | {len(g)} | "
            f"{pct(g['annual_return'].min())} / {pct(g['annual_return'].median())} / {pct(g['annual_return'].max())} | "
            f"{pct(g['max_drawdown'].min())} / {pct(g['max_drawdown'].median())} / {pct(g['max_drawdown'].max())} | "
            f"{fnum(g['sharpe_ratio'].min())} / {fnum(g['sharpe_ratio'].median())} / {fnum(g['sharpe_ratio'].max())} |"
        )

    lines += [
        "",
        "## Robustness Detail",
        "",
        "| section | axis | label | annual | sharpe | dd | calmar | win | trades |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in robust.sort_values(["section", "axis", "label"]).iterrows():
        lines.append(
            f"| {r['section']} | {r.get('axis', '')} | {r['label']} | {pct(r['annual_return'])} | "
            f"{fnum(r['sharpe_ratio'])} | {pct(r['max_drawdown'])} | {fnum(r['calmar'])} | {pct(r['win_rate'])} | {int(r['trade_count'])} |"
        )

    wf_test = results[results["section"].eq("wf_test")].copy()
    if not wf_test.empty:
        month_returns = wf_test["total_return"].astype(float)
        total = float(wf_nav["portfolio_value"].iloc[-1] / 500_000.0 - 1.0) if not wf_nav.empty else np.nan
        days = max(1, len(pd.to_datetime(wf_nav["date"]).dt.date.unique())) if not wf_nav.empty and "date" in wf_nav.columns else np.nan
        cagr = (1.0 + total) ** (252.0 / days) - 1.0 if np.isfinite(total) and np.isfinite(days) else np.nan
        lines += [
            "",
            "## Walk-Forward",
            "",
            f"- months: `{len(wf_test)}`",
            f"- final value: `{wf_nav['portfolio_value'].iloc[-1]:,.0f}`" if not wf_nav.empty else "- final value: n/a",
            f"- chained total return: `{pct(total)}`",
            f"- approximate chained CAGR: `{pct(cagr)}`",
            f"- positive test months: `{(month_returns > 0).mean() * 100:.2f}%`",
            "",
            "| month | selected | train annual | train sharpe | train dd | test return | test annual | test sharpe | test dd | trades |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for _, r in wf_test.sort_values("label").iterrows():
            lines.append(
                f"| {r['label']} | {r.get('candidate', '')} | {pct(r.get('train_annual_return'))} | "
                f"{fnum(r.get('train_sharpe_ratio'))} | {pct(r.get('train_max_drawdown'))} | {pct(r['total_return'])} | "
                f"{pct(r['annual_return'])} | {fnum(r['sharpe_ratio'])} | {pct(r['max_drawdown'])} | {int(r['trade_count'])} |"
            )
        lines += [
            "",
            "### Walk-Forward Selection Counts",
            "",
            "| candidate | count |",
            "|---|---:|",
        ]
        for cand, cnt in wf_test["candidate"].value_counts().sort_values(ascending=False).items():
            lines.append(f"| {cand} | {cnt} |")

    lines += [
        "",
        "## Notes",
        "",
        "- These results still use the frozen `F2_v3` static core pool, so they test parameter overfit under a frozen pool rather than a fully PIT core-pool research design.",
        "- If this layer passes, execution-layer validation should be rerun afterward using minute data, capacity, split orders, and premium/slippage audits.",
    ]
    report.write_text("\n".join(lines), encoding="utf-8")
    return report


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pit = load_pit_pool()
    f2 = load_f2_pool()
    rows: list[dict[str, Any]] = []

    fixed_partial = OUT / "signal_oos_walkforward_results_fixed_yearly_partial.csv"
    robust_partial = OUT / "signal_oos_walkforward_results_robust_partial.csv"
    if fixed_partial.exists():
        fixed_df = pd.read_csv(fixed_partial)
        if len(fixed_df) == 39:
            rows.extend(fixed_df.to_dict("records"))
            print(f"loaded fixed/yearly partial: {fixed_partial}", flush=True)
        else:
            rows.extend(fixed_oos_and_yearly(pit, f2))
    else:
        rows.extend(fixed_oos_and_yearly(pit, f2))

    if robust_partial.exists():
        robust_df = pd.read_csv(robust_partial)
        if len(robust_df) == 60:
            rows.extend(robust_df.to_dict("records"))
            print(f"loaded robustness partial: {robust_partial}", flush=True)
        else:
            rows.extend(robustness(pit, f2))
    else:
        rows.extend(robustness(pit, f2))

    wf_rows, wf_nav = walk_forward(pit, f2)
    rows.extend(wf_rows)

    results = pd.DataFrame(rows)
    results.to_csv(OUT / "signal_oos_walkforward_results.csv", index=False)
    if not wf_nav.empty:
        wf_nav.to_csv(OUT / "walkforward_chained_equity.csv", index=False)

    # Compact parameter manifest for reproducibility.
    manifest_rows = []
    for variant in ["F2_CAP_MA60", "WideA", "Exph_v3_exp_looser"]:
        params = make_params(pit, f2, START_ALL, END_ALL, f"MANIFEST_{variant}", variant)
        manifest_rows.append({"variant": variant, **asdict(params)})
    pd.DataFrame(manifest_rows).to_csv(OUT / "candidate_parameter_manifest.csv", index=False)

    report = write_report(results, wf_nav)
    print(f"Saved: {OUT / 'signal_oos_walkforward_results.csv'}")
    print(f"Saved: {OUT / 'walkforward_chained_equity.csv'}")
    print(f"Saved: {OUT / 'candidate_parameter_manifest.csv'}")
    print(f"Saved: {report}")


if __name__ == "__main__":
    main()
