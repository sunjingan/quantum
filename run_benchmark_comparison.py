#!/usr/bin/env python3
"""Benchmark comparisons for ETF Loop."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from strategies._utils import QlibDailyReader
from strategies.etf_loop_strategy import ETFDailyStore, SectorProsperityCache


BASE_DIR = Path(__file__).resolve().parent
OUT = BASE_DIR / "outputs" / "etf_loop"
START = "2018-01-01"
END = "2026-06-25"
INITIAL_CASH = 500_000.0


INDEX_BENCHMARKS = {
    "HS300": "sh000300",
    "CSI500": "sh000905",
    "CSI1000": "sh000852",
    "CHINEXT": "sz399006",
}

ETF_HOLDS = {
    "CSI300_ETF_510300": "510300.SH",
    "CHINEXT_ETF_159915": "159915.SZ",
    "NASDAQ100_513100": "513100.SH",
    "SP500_513500": "513500.SH",
    "GOLD_518880": "518880.SH",
    "MONEY_511880": "511880.SH",
}


def load_f2_pool() -> list[str]:
    path = BASE_DIR / "data/tushare_cache/sector_prosperity/etf_pool_F2_v3.csv"
    return sorted(pd.read_csv(path, dtype={"ts_code": str})["ts_code"].astype(str).tolist())


def perf(nav: pd.Series) -> dict[str, float]:
    nav = nav.dropna()
    daily = nav.pct_change().dropna()
    if len(daily) < 2:
        return {}
    ann = daily.mean() * 252.0
    vol = daily.std() * np.sqrt(252.0)
    return {
        "annual_return": float(ann),
        "annual_volatility": float(vol),
        "sharpe_ratio": float(ann / vol) if vol > 0 else 0.0,
        "max_drawdown": float((nav / nav.cummax() - 1.0).min()),
        "total_return": float(nav.iloc[-1] / nav.iloc[0] - 1.0),
        "final_value": float(nav.iloc[-1]),
    }


def qlib_index_nav(reader: QlibDailyReader, symbol: str) -> pd.Series:
    close = reader.read_field(symbol, "close").loc[pd.Timestamp(START):pd.Timestamp(END)].dropna()
    if close.empty:
        return pd.Series(dtype=float)
    return INITIAL_CASH * close / close.iloc[0]


def etf_buy_hold(store: ETFDailyStore, code: str) -> pd.Series:
    adjusted = adjusted_nav_matrix([code])
    if code not in adjusted.columns:
        return pd.Series(dtype=float)
    return INITIAL_CASH * adjusted[code].dropna()


def adjusted_nav_matrix(codes: list[str]) -> pd.DataFrame:
    wanted = set(codes)
    rows = []
    for path in sorted((BASE_DIR / "data/tushare_cache/sector_prosperity").glob("fund_daily_*.csv")):
        date = pd.Timestamp(path.stem.replace("fund_daily_", ""))
        if date < pd.Timestamp(START) or date > pd.Timestamp(END):
            continue
        df = pd.read_csv(path, dtype={"ts_code": str}, usecols=["ts_code", "trade_date", "pct_chg"])
        df = df[df["ts_code"].isin(wanted)].copy()
        if df.empty:
            continue
        df["date"] = date
        rows.append(df[["date", "ts_code", "pct_chg"]])
    if not rows:
        return pd.DataFrame()
    raw = pd.concat(rows, ignore_index=True)
    ret = raw.pivot_table(index="date", columns="ts_code", values="pct_chg", aggfunc="last").sort_index() / 100.0
    nav = (1.0 + ret.fillna(0.0)).cumprod()
    # Start each ETF at 1 on first valid return, leaving pre-listing gaps as NaN.
    for code in nav.columns:
        first = ret[code].first_valid_index()
        if first is None:
            nav[code] = np.nan
            continue
        first_pos = nav.index.get_loc(first)
        if first_pos > 0:
            nav.iloc[:first_pos, nav.columns.get_loc(code)] = np.nan
        nav.loc[first:, code] = nav.loc[first:, code] / nav.loc[first, code]
    return nav


def equal_weight_nav(store: ETFDailyStore, codes: list[str]) -> pd.Series:
    close = adjusted_nav_matrix(codes).dropna(how="all")
    ret = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    daily = ret.mean(axis=1, skipna=True).fillna(0.0)
    nav = INITIAL_CASH * (1.0 + daily).cumprod()
    return nav


def simple_momentum_nav(store: ETFDailyStore, codes: list[str], top_n: int = 1, lookback: int = 20) -> pd.Series:
    close = adjusted_nav_matrix(codes).copy()
    calendar = close.index
    nav = INITIAL_CASH
    holdings: set[str] = set()
    rows = []
    one_way_cost = 0.0002
    for i, date in enumerate(calendar[:-1]):
        if i < lookback:
            rows.append({"date": calendar[i + 1], "nav": nav})
            continue
        next_date = calendar[i + 1]
        hist = close.loc[:date].tail(lookback + 1)
        mom = hist.iloc[-1] / hist.iloc[0] - 1.0
        targets = set(mom.dropna().sort_values(ascending=False).head(top_n).index.astype(str))
        turnover = len(holdings.symmetric_difference(targets)) / max(1, top_n)
        holdings = targets
        if holdings:
            day_ret = (close.loc[next_date, list(holdings)] / close.loc[date, list(holdings)] - 1.0).replace([np.inf, -np.inf], np.nan).mean()
            nav *= 1.0 + (0.0 if pd.isna(day_ret) else float(day_ret))
            nav *= max(0.0, 1.0 - one_way_cost * turnover)
        rows.append({"date": next_date, "nav": nav})
    return pd.DataFrame(rows).drop_duplicates("date").set_index("date")["nav"]


def strategy_nav(tag: str) -> pd.Series:
    files = sorted(OUT.glob(f"etf_loop_equity_{tag}_h*_20180101_20260625.csv"))
    if not files:
        return pd.Series(dtype=float)
    df = pd.read_csv(files[0], parse_dates=["date"]).set_index("date")
    return df["portfolio_value"]


def pct(x: float) -> str:
    return "" if pd.isna(x) else f"{x * 100:.2f}%"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    navs = {}
    reader = QlibDailyReader(BASE_DIR / "data/a_share_qlib")
    for name, symbol in INDEX_BENCHMARKS.items():
        nav = qlib_index_nav(reader, symbol)
        if not nav.empty:
            navs[name] = nav
            rows.append({"name": name, "type": "index", **perf(nav)})

    f2 = load_f2_pool()
    all_etf = sorted(set(f2) | set(ETF_HOLDS.values()))
    cache = SectorProsperityCache(BASE_DIR / "config/tushare_token.txt", BASE_DIR / "data/tushare_cache")
    store = ETFDailyStore(cache, all_etf, START, END)
    for name, code in ETF_HOLDS.items():
        nav = etf_buy_hold(store, code)
        if not nav.empty:
            navs[name] = nav
            rows.append({"name": name, "type": "buy_hold_etf", **perf(nav)})

    for name, nav in {
        "F2_EQUAL_WEIGHT": equal_weight_nav(store, f2),
        "F2_MOM20_TOP1": simple_momentum_nav(store, f2, top_n=1, lookback=20),
        "F2_MOM20_TOP3": simple_momentum_nav(store, f2, top_n=3, lookback=20),
        "STRATEGY_F2_CAP_MA60_NEUTRAL_COST": strategy_nav("VAL_COST_cost_neutral"),
    }.items():
        if not nav.empty:
            navs[name] = nav
            rows.append({"name": name, "type": "strategy_or_baseline", **perf(nav)})

    result = pd.DataFrame(rows).sort_values(["sharpe_ratio", "annual_return"], ascending=False)
    manifest = OUT / "benchmark_comparison_manifest.csv"
    report = OUT / "benchmark_comparison_report.md"
    result.to_csv(manifest, index=False)
    lines = [
        "# ETF Loop Benchmark Comparison",
        "",
        f"- window: `{START}` to `{END}`",
        "",
        "| rank | name | type | ann | sharpe | dd | total | final |",
        "|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for i, r in enumerate(result.to_dict("records"), start=1):
        lines.append(
            f"| {i} | {r['name']} | {r['type']} | {pct(r['annual_return'])} | {r['sharpe_ratio']:.2f} | "
            f"{pct(r['max_drawdown'])} | {pct(r['total_return'])} | {r['final_value']:.0f} |"
        )
    report.write_text("\n".join(lines), encoding="utf-8")
    print("Saved:", manifest)
    print("Saved:", report)
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
