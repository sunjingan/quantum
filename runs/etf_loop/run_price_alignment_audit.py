#!/usr/bin/env python3
"""Audit price alignment between ETF Loop daily advice and local minute data."""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from run_minute_execution_advice_replay import get_codes, load_logs  # noqa: E402
from run_minute_execution_backtest import EXECUTION_MODES, LOCAL_DATA, LocalMinuteStore, pct  # noqa: E402
from strategies.etf_loop_strategy import ETFDailyStore, SectorProsperityCache  # noqa: E402


OUT = PROJECT_ROOT / "outputs" / "etf_loop" / "price_alignment_audit"


def _factor_file_key(ts_code: str) -> str:
    local = ts_code.split(".")[0]
    prefix = "sh" if ts_code.endswith(".SH") else "sz"
    return f"{prefix}{local}.csv"


class LocalFactorStore:
    def __init__(self, root: Path, end: str) -> None:
        self.root = root
        self.end = pd.Timestamp(end)
        self.cache: dict[str, pd.Series] = {}

    def load(self, ts_code: str) -> pd.Series:
        if ts_code in self.cache:
            return self.cache[ts_code]
        factor_zip = self.root / "全部复权因子" / "涨跌幅" / "全部复权因子.zip"
        key = _factor_file_key(ts_code)
        if not factor_zip.exists():
            self.cache[ts_code] = pd.Series(dtype=float)
            return self.cache[ts_code]
        with zipfile.ZipFile(factor_zip) as zf:
            names = [n for n in zf.namelist() if n.endswith("/" + key) or n.endswith(key)]
            if not names:
                self.cache[ts_code] = pd.Series(dtype=float)
                return self.cache[ts_code]
            with zf.open(names[0]) as fh:
                df = pd.read_csv(fh)
        if df.empty or "交易日期" not in df.columns or "复权因子" not in df.columns:
            self.cache[ts_code] = pd.Series(dtype=float)
            return self.cache[ts_code]
        df = df.copy()
        df["date"] = pd.to_datetime(df["交易日期"], errors="coerce")
        s = df.dropna(subset=["date"]).set_index("date")["复权因子"].astype(float).sort_index()
        self.cache[ts_code] = s
        return s

    def pre_adjust_scale(self, ts_code: str, date: pd.Timestamp) -> float:
        factor = self.load(ts_code)
        if factor.empty:
            return np.nan
        hist = factor.loc[: pd.Timestamp(date)]
        end_hist = factor.loc[: self.end]
        if hist.empty or end_hist.empty:
            return np.nan
        end_factor = float(end_hist.iloc[-1])
        if end_factor <= 0:
            return np.nan
        return float(hist.iloc[-1]) / end_factor


def build_daily_store(codes: list[str], start: str, end: str) -> ETFDailyStore:
    cache = SectorProsperityCache(PROJECT_ROOT / "config" / "tushare_token.txt", PROJECT_ROOT / "data" / "tushare_cache")
    return ETFDailyStore(cache, codes, start, end)


def daily_engine_price(store: ETFDailyStore, code: str, date: pd.Timestamp, mode: str) -> float:
    if mode in {"open_0935", "t2_open_0935"}:
        return store.execution_price(code, date, "open")
    if mode.startswith("tail_") or "vwap" in mode:
        return store.execution_price(code, date, "vwap")
    if "twap" in mode:
        return store.execution_price(code, date, "close")
    return store.execution_price(code, date, "open")


def ratio(a: Any, b: Any) -> float:
    try:
        a = float(a)
        b = float(b)
    except Exception:
        return np.nan
    if pd.isna(a) or pd.isna(b) or b <= 0:
        return np.nan
    return a / b


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in ["raw_ratio", "local_pre_ratio", "engine_scaled_ratio", "daily_engine_ratio"]:
        s = pd.to_numeric(df[col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if s.empty:
            continue
        rows.append({
            "method": col.replace("_ratio", ""),
            "count": int(len(s)),
            "median": float(s.median()),
            "p05": float(s.quantile(0.05)),
            "p95": float(s.quantile(0.95)),
            "p99_abs_log_error": float(np.quantile(np.abs(np.log(s)), 0.99)),
            "within_1pct": float(((s >= 0.99) & (s <= 1.01)).mean()),
            "within_5pct": float(((s >= 0.95) & (s <= 1.05)).mean()),
        })
    return pd.DataFrame(rows)


def summarize_by_code(df: pd.DataFrame, method: str, top_n: int = 30) -> pd.DataFrame:
    col = f"{method}_ratio"
    rows = []
    for code, g in df.groupby("ts_code"):
        s = pd.to_numeric(g[col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if len(s) < 3:
            continue
        rows.append({
            "ts_code": code,
            "count": int(len(s)),
            "median": float(s.median()),
            "p05": float(s.quantile(0.05)),
            "p95": float(s.quantile(0.95)),
            "within_5pct": float(((s >= 0.95) & (s <= 1.05)).mean()),
            "abs_log_error_median": float(np.abs(np.log(s)).median()),
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("abs_log_error_median", ascending=False).head(top_n)


def write_report(setting: str, start: str, trading_start: str, end: str, execution_mode: str, detail: pd.DataFrame, summary: pd.DataFrame, by_code: pd.DataFrame, out_path: Path) -> None:
    lines = [
        "# ETF Loop 分钟价格对齐审计",
        "",
        "## 1. 口径",
        "",
        f"- setting: `{setting}`",
        f"- period: `{start}` → `{end}`，trading_start=`{trading_start}`",
        f"- execution_mode: `{execution_mode}`",
        "- 比较对象：原日线引擎 advice 成交价 vs 本地分钟价不同调整口径。",
        "- 主审计建议使用 `open_0935`，因为原日线引擎的 advice price 是 T+1 adjusted open。",
        "",
        "## 2. 总体比例",
        "",
        "`ratio = advice_price / candidate_price`。越接近 1，价格体系越一致。",
        "",
        "| method | count | median | p05 | p95 | within 1% | within 5% | p99 abs log err |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in summary.to_dict("records"):
        lines.append(
            f"| `{r['method']}` | {int(r['count'])} | {r['median']:.4f} | {r['p05']:.4f} | {r['p95']:.4f} | "
            f"{pct(r['within_1pct'])} | {pct(r['within_5pct'])} | {r['p99_abs_log_error']:.4f} |"
        )
    lines += [
        "",
        "## 3. 偏差最大的 ETF",
        "",
        "| ts_code | count | median | p05 | p95 | within 5% | median abs log err |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in by_code.to_dict("records"):
        lines.append(
            f"| `{r['ts_code']}` | {int(r['count'])} | {r['median']:.4f} | {r['p05']:.4f} | {r['p95']:.4f} | "
            f"{pct(r['within_5pct'])} | {r['abs_log_error_median']:.4f} |"
        )
    lines += [
        "",
        "## 4. 典型异常样例",
        "",
    ]
    sample = detail.copy()
    sample["err"] = (np.log(pd.to_numeric(sample["daily_engine_ratio"], errors="coerce")).abs())
    sample = sample.sort_values("err", ascending=False).head(20)
    lines += [
        "| signal_date | trade_date | code | side | advice | raw | local_pre | engine_scaled | daily_engine | raw_ratio | local_pre_ratio | engine_ratio | daily_ratio |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in sample.to_dict("records"):
        lines.append(
            f"| {pd.Timestamp(r['signal_date']).date()} | {pd.Timestamp(r['trade_date']).date()} | `{r['ts_code']}` | {r['action']} | "
            f"{r['advice_price']:.4f} | {r['raw_price']:.4f} | {r['local_pre_price']:.4f} | {r['engine_scaled_price']:.4f} | {r['daily_engine_price']:.4f} | "
            f"{r['raw_ratio']:.4f} | {r['local_pre_ratio']:.4f} | {r['engine_scaled_ratio']:.4f} | {r['daily_engine_ratio']:.4f} |"
        )
    lines += [
        "",
        "## 5. 输出",
        "",
        f"- detail csv: `{out_path.with_suffix('.csv')}`",
        f"- summary csv: `{out_path.with_name(out_path.stem + '_summary.csv')}`",
        f"- by-code csv: `{out_path.with_name(out_path.stem + '_by_code.csv')}`",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit minute/daily adjusted price alignment")
    parser.add_argument("--setting", default="WideA")
    parser.add_argument("--start", default="2013-07-01")
    parser.add_argument("--trading-start", default="2013-07-01")
    parser.add_argument("--end", default="2026-06-25")
    parser.add_argument("--execution-mode", default="open_0935", choices=sorted(EXECUTION_MODES))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force-signals", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    account, advice, positions = load_logs(args.setting, args.start, args.trading_start, args.end, args.force_signals)
    advice = advice[advice["signal_date"] >= pd.Timestamp(args.trading_start)].copy()
    advice = advice[advice["action"].isin(["BUY", "SELL"])].copy()
    if args.limit > 0:
        advice = advice.tail(args.limit).copy()
    codes = get_codes(advice, positions)
    raw_store = LocalMinuteStore(codes, args.start, args.end, "1min", price_adjustment="none")
    engine_store = LocalMinuteStore(codes, args.start, args.end, "1min", price_adjustment="engine")
    daily_store = build_daily_store(codes, args.start, args.end)
    factor_store = LocalFactorStore(LOCAL_DATA, args.end)

    rows: list[dict[str, Any]] = []
    for r in advice.itertuples():
        code = str(r.ts_code)
        trade_date = pd.Timestamp(r.trade_date)
        raw_ctx = raw_store.fill_context(code, trade_date, args.execution_mode)
        engine_ctx = engine_store.fill_context(code, trade_date, args.execution_mode)
        raw_price = raw_ctx.raw_price if raw_ctx is not None else np.nan
        engine_scaled_price = engine_ctx.raw_price if engine_ctx is not None else np.nan
        local_scale = factor_store.pre_adjust_scale(code, trade_date)
        local_pre_price = raw_price * local_scale if pd.notna(raw_price) and pd.notna(local_scale) else np.nan
        daily_price = daily_engine_price(daily_store, code, trade_date, args.execution_mode)
        advice_price = float(getattr(r, "price", np.nan))
        rows.append({
            "signal_date": pd.Timestamp(r.signal_date),
            "trade_date": trade_date,
            "ts_code": code,
            "action": str(r.action),
            "advice_price": advice_price,
            "raw_price": raw_price,
            "local_pre_price": local_pre_price,
            "engine_scaled_price": engine_scaled_price,
            "daily_engine_price": daily_price,
            "raw_ratio": ratio(advice_price, raw_price),
            "local_pre_ratio": ratio(advice_price, local_pre_price),
            "engine_scaled_ratio": ratio(advice_price, engine_scaled_price),
            "daily_engine_ratio": ratio(advice_price, daily_price),
            "local_pre_scale": local_scale,
        })
    detail = pd.DataFrame(rows)
    summary = summarize(detail)
    by_code = summarize_by_code(detail, "daily_engine")
    tag = f"{args.setting}_{args.execution_mode}_{args.start.replace('-', '')}_{args.end.replace('-', '')}"
    detail_path = OUT / f"price_alignment_detail_{tag}.csv"
    report_path = OUT / f"price_alignment_report_{tag}.md"
    detail.to_csv(detail_path, index=False)
    summary.to_csv(OUT / f"price_alignment_detail_{tag}_summary.csv", index=False)
    by_code.to_csv(OUT / f"price_alignment_detail_{tag}_by_code.csv", index=False)
    write_report(args.setting, args.start, args.trading_start, args.end, args.execution_mode, detail, summary, by_code, report_path)
    print("Saved:", detail_path)
    print("Saved:", report_path)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
