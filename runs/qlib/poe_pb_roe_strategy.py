"""
POE PB+ROE monthly strategy, local Qlib/Tushare version.

This script is intentionally non-ML:
  1. Monthly rebalance on the first trading day of each month
  2. Use data visible on the previous trading day
  3. Build a PB/ROE candidate pool from Tushare fundamentals
  4. Select targets with the POE V1 branch rules
  5. Run a simple equal-weight monthly backtest with transaction costs

Usage:
  source activate.sh
  python runs/qlib/poe_pb_roe_strategy.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tushare as ts

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = PROJECT_ROOT
PROVIDER_URI = Path(os.environ.get("QLIB_PROVIDER_URI", BASE_DIR / "data" / "a_share_qlib"))
TOKEN_PATH = BASE_DIR / "config" / "tushare_token.txt"
CACHE_DIR = BASE_DIR / "data" / "tushare_cache" / "poe_pb_roe"

BENCHMARK = "sh000300"

sys.path.insert(0, str(PROJECT_ROOT))

from lazy_tushare_loader import LazyTushareLoader, qlib_to_tushare, tushare_to_qlib


@dataclass
class StrategyParams:
    initial_cash: float = 500_000.0
    min_list_days: int = 250
    pb_min: float = 0.1
    pb_max: float = 20.0
    roe_min: float = 0.0
    market_cap_min: float = 20.0
    pe_min: float = 0.1
    pe_max: float = 200.0
    core_pb_low: float = 0.10
    core_pb_high: float = 0.30
    core_roe_low: float = 0.10
    core_roe_high: float = 0.30
    max_per_industry: int = 2
    strong_cycle_max_1: int = 1
    weak_top_n_25: int = 25
    weak_broad_industry_max: int = 3
    weak_broad_strong_cycle_max_25: int = 5
    weak_rank_spread_band_count: int = 4
    open_cost: float = 0.0005
    close_cost: float = 0.0015


class QlibDailyReader:
    def __init__(self, provider_uri: Path):
        self.provider_uri = provider_uri
        self.calendar = pd.to_datetime(pd.read_csv(provider_uri / "calendars" / "day.txt", header=None)[0])

    def read_field(self, code: str, field: str) -> pd.Series:
        path = self.provider_uri / "features" / code.lower() / f"{field}.day.bin"
        if not path.exists():
            return pd.Series(dtype=float)
        arr = np.fromfile(path, dtype="<f")
        if len(arr) <= 1:
            return pd.Series(dtype=float)
        start_idx = int(arr[0])
        values = arr[1:]
        idx = self.calendar.iloc[start_idx : start_idx + len(values)]
        return pd.Series(values, index=idx, name=code.lower())

    def close_frame(self, codes: list[str], start: str, end: str) -> pd.DataFrame:
        series = [self.read_field(code, "close") for code in codes]
        df = pd.concat(series, axis=1).sort_index() if series else pd.DataFrame()
        return df.loc[pd.Timestamp(start) : pd.Timestamp(end)]


class FundamentalCache:
    def __init__(self, token_path: Path, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.pro = ts.pro_api(token=token_path.read_text().strip())

    def stock_basic(self) -> pd.DataFrame:
        path = self.cache_dir / "stock_basic_all.csv"
        if path.exists():
            return pd.read_csv(path, dtype={"ts_code": str, "list_date": str})
        parts = []
        for status in ["L", "D"]:
            df = self.pro.stock_basic(
                exchange="",
                list_status=status,
                fields="ts_code,symbol,name,area,industry,list_date,delist_date",
            )
            if df is not None and not df.empty:
                df["list_status"] = status
                parts.append(df)
        result = pd.concat(parts, ignore_index=True)
        result.to_csv(path, index=False)
        return result

    def daily_basic(self, trade_date: pd.Timestamp) -> pd.DataFrame:
        ymd = trade_date.strftime("%Y%m%d")
        path = self.cache_dir / "daily_basic" / f"{ymd}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return pd.read_csv(path, dtype={"ts_code": str})
        df = self.pro.daily_basic(
            trade_date=ymd,
            fields="ts_code,trade_date,close,turnover_rate,volume_ratio,pe,pe_ttm,pb,total_mv,circ_mv",
        )
        if df is None:
            df = pd.DataFrame()
        df.to_csv(path, index=False)
        return df

    def fina_indicator(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        safe_name = ts_code.replace(".", "_")
        path = self.cache_dir / "fina_indicator" / f"{safe_name}.csv"
        through_path = self.cache_dir / "fina_indicator" / f"{safe_name}.through"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            df = pd.read_csv(path, dtype={"ts_code": str, "ann_date": str, "end_date": str})
            if through_path.exists() and through_path.read_text().strip() >= end_date:
                return df
        df = self.pro.fina_indicator(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            fields="ts_code,ann_date,end_date,roe,roa,netprofit_yoy,or_yoy",
        )
        if df is None:
            df = pd.DataFrame()
        if path.exists():
            old = pd.read_csv(path, dtype={"ts_code": str, "ann_date": str, "end_date": str})
            df = pd.concat([old, df], ignore_index=True)
            if not df.empty:
                df = df.drop_duplicates(["ts_code", "ann_date", "end_date"], keep="last")
        df.to_csv(path, index=False)
        through_path.write_text(end_date)
        return df

    def latest_fina_rows(self, ts_codes: list[str], data_date: pd.Timestamp) -> pd.DataFrame:
        end_date = data_date.strftime("%Y%m%d")
        start_date = (data_date - pd.DateOffset(years=3)).strftime("%Y%m%d")
        rows = []
        for ts_code in ts_codes:
            df = self.fina_indicator(ts_code, start_date, end_date)
            if df.empty or "ann_date" not in df:
                continue
            visible = df[df["ann_date"].astype(str) <= end_date].copy()
            visible = visible.dropna(subset=["roe"])
            if visible.empty:
                continue
            rows.append(visible.sort_values(["ann_date", "end_date"]).iloc[-1])
        return pd.DataFrame(rows)

    def prefetch_fina(self, ts_codes: list[str], start: str, end: str) -> None:
        start_date = pd.Timestamp(start).strftime("%Y%m%d")
        end_date = pd.Timestamp(end).strftime("%Y%m%d")
        total = len(ts_codes)
        for i, ts_code in enumerate(sorted(set(ts_codes)), start=1):
            self.fina_indicator(ts_code, start_date, end_date)
            if i % 50 == 0:
                print(f"fina_indicator cache: {i}/{total}")

    def fundamentals(self, qlib_codes: list[str], data_date: pd.Timestamp) -> pd.DataFrame:
        ts_codes = [qlib_to_tushare(code) for code in qlib_codes]
        basic = self.stock_basic()
        daily = self.daily_basic(data_date)
        fina = self.latest_fina_rows(ts_codes, data_date)
        if daily.empty or fina.empty:
            return pd.DataFrame()

        df = daily[daily["ts_code"].isin(ts_codes)].merge(fina, on="ts_code", how="inner")
        df = df.merge(basic, on="ts_code", how="left")
        if df.empty:
            return df
        df["code"] = df["ts_code"].map(lambda x: x.split(".")[1].lower() + x.split(".")[0])
        df = df.rename(
            columns={
                "pb": "pb_ratio",
                "pe_ttm": "pe_ratio",
                "total_mv": "market_cap",
                "industry": "industry_name",
                "netprofit_yoy": "inc_net_profit_year_on_year",
                "or_yoy": "inc_revenue_year_on_year",
            }
        )
        df["pe_ratio"] = df["pe_ratio"].fillna(df.get("pe", np.nan))
        df["market_cap"] = df["market_cap"] / 10000.0
        return df


def read_instrument_codes(provider_uri: Path, market: str) -> list[str]:
    path = provider_uri / "instruments" / f"{market}.txt"
    df = pd.read_csv(path, sep="\t", header=None, names=["code", "start", "end"])
    return df["code"].str.lower().tolist()


def load_hs300_weights(cache_dir: Path, start: str, end: str) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"index_weight_000300_{pd.Timestamp(start):%Y%m%d}_{pd.Timestamp(end):%Y%m%d}.csv"
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    if path.exists():
        df = pd.read_csv(path, dtype={"con_code": str, "trade_date": str})
        if not df.empty and pd.Timestamp(str(df["trade_date"].min())) <= start_ts:
            df["date"] = pd.to_datetime(df["trade_date"].astype(str))
            df["code"] = df["con_code"].map(tushare_to_qlib)
            return df.sort_values(["date", "code"])

    if True:
        pro = ts.pro_api(token=TOKEN_PATH.read_text().strip())
        parts = []
        cursor = start_ts
        while cursor <= end_ts:
            chunk_end = min(cursor + pd.DateOffset(months=3) - pd.DateOffset(days=1), end_ts)
            part = pro.index_weight(
                index_code="000300.SH",
                start_date=f"{cursor:%Y%m%d}",
                end_date=f"{chunk_end:%Y%m%d}",
            )
            if part is not None and not part.empty:
                parts.append(part)
            cursor = chunk_end + pd.DateOffset(days=1)
        if not parts:
            raise RuntimeError("Tushare returned no HS300 index_weight data")
        df = pd.concat(parts, ignore_index=True)
        df = df.drop_duplicates(["index_code", "con_code", "trade_date"], keep="last")
        df.to_csv(path, index=False)
    df["date"] = pd.to_datetime(df["trade_date"].astype(str))
    df["code"] = df["con_code"].map(tushare_to_qlib)
    return df.sort_values(["date", "code"])


class Hs300HistoryUniverse:
    def __init__(self, weights: pd.DataFrame):
        self.weights = weights.sort_values("date")

    def codes_for_date(self, data_date: pd.Timestamp) -> list[str]:
        dates = self.weights.loc[self.weights["date"] <= data_date, "date"]
        if dates.empty:
            return []
        latest = dates.max()
        return sorted(self.weights.loc[self.weights["date"] == latest, "code"].str.lower().unique().tolist())

    def first_needed_dates(self, global_start: str) -> dict[str, pd.Timestamp]:
        start = pd.Timestamp(global_start)
        first = self.weights.groupby("code")["date"].min()
        return {code.lower(): max(start, pd.Timestamp(date)) for code, date in first.items()}


def contains_any(text, words):
    return any(w in str(text) for w in words)


def is_real_estate_industry(industry_name):
    return contains_any(industry_name, ["房地产"])


def is_finance_industry(industry_name):
    return contains_any(industry_name, ["银行", "非银金融", "证券", "保险", "多元金融"])


def is_strong_cycle_industry(industry_name):
    return contains_any(industry_name, ["煤炭", "采掘", "有色金属", "钢铁", "基础化工", "化工", "石油石化", "交通运输"])


def classify_pb_bucket(p):
    if pd.isnull(p):
        return "PB_Q4_NOT_LOW"
    if p <= 0.1:
        return "PB_Q1_EXTREME_LOW"
    if p <= 0.3:
        return "PB_Q2_CORE_LOW"
    if p <= 0.5:
        return "PB_Q3_ACCEPT_LOW"
    return "PB_Q4_NOT_LOW"


def classify_roe_bucket(p):
    if pd.isnull(p):
        return "ROE_Q4_WEAK"
    if p <= 0.1:
        return "ROE_Q1_EXTREME_HIGH"
    if p <= 0.3:
        return "ROE_Q2_CORE_HIGH"
    if p <= 0.5:
        return "ROE_Q3_ACCEPT"
    return "ROE_Q4_WEAK"


def add_rank_bucket_score_fields(df: pd.DataFrame, params: StrategyParams) -> pd.DataFrame:
    df = df.copy()
    df["market_pb_rank_pct"] = df["pb_ratio"].rank(ascending=True, pct=True)
    df["industry_pb_rank_pct"] = df.groupby("industry_name")["pb_ratio"].rank(ascending=True, pct=True)
    df["roe_rank_pct"] = df["roe"].rank(ascending=False, pct=True)
    df["roa_rank_pct"] = df["roa"].rank(ascending=False, pct=True)
    df["score_b_ind_pb_roe"] = 0.25 * df["market_pb_rank_pct"] + 0.25 * df["industry_pb_rank_pct"] + 0.5 * df["roe_rank_pct"]
    df["pb_bucket"] = df["market_pb_rank_pct"].apply(classify_pb_bucket)
    df["roe_bucket"] = df["roe_rank_pct"].apply(classify_roe_bucket)
    df["pb_roe_cell"] = df["pb_bucket"] + "__" + df["roe_bucket"]
    df["is_static_core_cell"] = (
        (df["market_pb_rank_pct"] > params.core_pb_low)
        & (df["market_pb_rank_pct"] <= params.core_pb_high)
        & (df["roe_rank_pct"] > params.core_roe_low)
        & (df["roe_rank_pct"] <= params.core_roe_high)
    )
    df["score_regime_neutral_balanced"] = df["score_b_ind_pb_roe"]
    df["score_regime_weak_value_soft"] = 0.3 * df["market_pb_rank_pct"] + 0.3 * df["industry_pb_rank_pct"] + 0.4 * df["roe_rank_pct"]
    return df


def sort_pool(pool: pd.DataFrame, score_col: str) -> pd.DataFrame:
    pool = pool.copy()
    if score_col not in pool.columns:
        pool[score_col] = 0.5
    pool = pool.sort_values(
        [score_col, "industry_pb_rank_pct", "market_pb_rank_pct", "roe_rank_pct"],
        ascending=[True, True, True, True],
    ).reset_index(drop=True)
    pool["candidate_rank"] = pool.index + 1
    return pool


def reorder_pool_rank_spread(pool: pd.DataFrame, band_count: int) -> pd.DataFrame:
    if pool is None or len(pool) <= band_count:
        return pool
    pool = pool.reset_index(drop=True)
    bands = np.array_split(list(range(len(pool))), band_count)
    ordered = []
    for i in range(max(len(b) for b in bands)):
        for band in bands:
            if i < len(band):
                ordered.append(int(band[i]))
    return pool.iloc[ordered].reset_index(drop=True)


def select_targets(pool: pd.DataFrame, top_n: int, params: StrategyParams, strong_cycle_max: int | None, max_per_industry: int | None) -> list[str]:
    selected, industry_count, strong_count = [], {}, 0
    if pool is None or pool.empty:
        return selected
    for _, row in pool.iterrows():
        code = row["code"]
        ind = row.get("industry_name", "UNKNOWN")
        is_strong = bool(row.get("is_strong_cycle_fixed", False))
        if max_per_industry is not None and industry_count.get(ind, 0) >= max_per_industry:
            continue
        if strong_cycle_max is not None and is_strong and strong_count >= strong_cycle_max:
            continue
        selected.append(code)
        industry_count[ind] = industry_count.get(ind, 0) + 1
        strong_count += int(is_strong)
        if len(selected) >= top_n:
            break
    for code in list(pool["code"]):
        if len(selected) >= top_n:
            break
        if code not in selected:
            selected.append(code)
    return selected


def market_state(benchmark_close: pd.Series, data_date: pd.Timestamp) -> tuple[str, str]:
    close = benchmark_close.loc[:data_date].dropna()
    if len(close) < 121:
        return "UNKNOWN", "UNKNOWN"
    last = close.iloc[-1]
    ret60 = last / close.iloc[-61] - 1.0
    ma120 = close.iloc[-120:].mean()
    price_vs_ma120 = last / ma120 - 1.0
    drawdown_120 = last / close.iloc[-120:].max() - 1.0
    if ret60 > 0 and price_vs_ma120 > 0:
        state = "MARKET_STRONG"
    elif ret60 < 0 and price_vs_ma120 < 0:
        state = "MARKET_WEAK"
    else:
        state = "MARKET_NEUTRAL"
    if drawdown_120 <= -0.15:
        risk = "HIGH_DRAWDOWN"
    elif drawdown_120 <= -0.08:
        risk = "MID_DRAWDOWN"
    else:
        risk = "NORMAL_DRAWDOWN"
    return state, risk


def build_base_dataframe(fund: FundamentalCache, codes: list[str], data_date: pd.Timestamp, params: StrategyParams) -> pd.DataFrame:
    df = fund.fundamentals(codes, data_date)
    if df.empty:
        return df
    raw_code = df["code"].str[2:]
    list_days = (data_date - pd.to_datetime(df["list_date"].astype(str), errors="coerce")).dt.days
    keep = (
        (list_days >= params.min_list_days)
        & ~raw_code.str.startswith(("688", "689", "4", "8"))
        & ~df["name"].fillna("").str.contains("ST|退|\\*", regex=True)
        & (df["pb_ratio"] > params.pb_min)
        & (df["pb_ratio"] < params.pb_max)
        & (df["roe"] > params.roe_min)
        & (df["market_cap"] >= params.market_cap_min)
        & (df["pe_ratio"] > params.pe_min)
        & (df["pe_ratio"] < params.pe_max)
    )
    df = df[keep].dropna(subset=["code", "pb_ratio", "roe", "market_cap"]).copy()
    if df.empty:
        return df
    df["roa"] = df["roa"].fillna(0)
    df["industry_name"] = df["industry_name"].fillna("UNKNOWN")
    df["is_real_estate"] = df["industry_name"].apply(is_real_estate_industry)
    df["is_finance"] = df["industry_name"].apply(is_finance_industry)
    df["is_strong_cycle_fixed"] = df["industry_name"].apply(is_strong_cycle_industry)
    df = df[~df["is_real_estate"]].copy()
    return add_rank_bucket_score_fields(df, params)


def pick_targets(base_df: pd.DataFrame, m_state: str, risk_state: str, params: StrategyParams) -> tuple[list[str], pd.DataFrame, str]:
    core = base_df[base_df["is_static_core_cell"]].copy()
    if core.empty:
        core = base_df.copy()

    if m_state == "MARKET_STRONG":
        score_col, top_n, branch = "score_regime_neutral_balanced", 10, "STRONG_BALANCED_TOP10"
        pool = sort_pool(core, score_col)
        targets = select_targets(pool, top_n, params, params.strong_cycle_max_1, params.max_per_industry)
    elif m_state == "MARKET_WEAK" and risk_state == "HIGH_DRAWDOWN":
        score_col, top_n, branch = "score_regime_weak_value_soft", params.weak_top_n_25, "WEAK_HIGH_SOFT25_RANKSPREAD25"
        pool = reorder_pool_rank_spread(sort_pool(core, score_col), params.weak_rank_spread_band_count)
        targets = select_targets(pool, top_n, params, params.weak_broad_strong_cycle_max_25, params.weak_broad_industry_max)
    elif m_state == "MARKET_WEAK" and risk_state == "MID_DRAWDOWN":
        score_col, top_n, branch = "score_regime_neutral_balanced", params.weak_top_n_25, "WEAK_MID_BALANCED25_RANKSPREAD25"
        pool = reorder_pool_rank_spread(sort_pool(core, score_col), params.weak_rank_spread_band_count)
        targets = select_targets(pool, top_n, params, params.weak_broad_strong_cycle_max_25, params.weak_broad_industry_max)
    elif m_state == "MARKET_WEAK":
        score_col, top_n, branch = "score_regime_neutral_balanced", 10, "WEAK_NORMAL_BALANCED_TOP10"
        pool = sort_pool(core, score_col)
        targets = select_targets(pool, top_n, params, params.strong_cycle_max_1, params.max_per_industry)
    else:
        score_col, top_n, branch = "score_regime_neutral_balanced", 12, "NEUTRAL_BALANCED_TOP12"
        pool = sort_pool(core, score_col)
        targets = select_targets(pool, top_n, params, params.strong_cycle_max_1, params.max_per_industry)
    return targets, pool, branch


def monthly_rebalance_dates(calendar: pd.Series, start: str, end: str) -> list[pd.Timestamp]:
    cal = calendar[(calendar >= pd.Timestamp(start)) & (calendar <= pd.Timestamp(end))]
    return cal.groupby(cal.dt.to_period("M")).first().tolist()


def lot_floor(amount: float, lot_size: int = 100) -> int:
    if pd.isnull(amount) or amount < lot_size:
        return 0
    return int(amount // lot_size) * lot_size


def run_backtest(start: str, end: str, market: str, params: StrategyParams) -> tuple[pd.DataFrame, pd.DataFrame]:
    history_universe = None
    if market.lower() in {"hs300", "csi300_history", "000300"}:
        weights = load_hs300_weights(CACHE_DIR, start, end)
        history_universe = Hs300HistoryUniverse(weights)
        universe = sorted(weights["code"].str.lower().unique().tolist())
        ensure_instruments = history_universe.first_needed_dates(start)
        print(f"HS300 historical universe: {len(universe)} unique stocks")
    else:
        universe = read_instrument_codes(PROVIDER_URI, market)
        ensure_instruments = universe

    if os.environ.get("QLIB_LAZY_TUSHARE", "1") != "0":
        LazyTushareLoader.for_project(BASE_DIR, PROVIDER_URI).ensure(ensure_instruments, start, end, benchmark="SH000300")
    else:
        print("Lazy Tushare: skipped by QLIB_LAZY_TUSHARE=0")

    reader = QlibDailyReader(PROVIDER_URI)
    codes = sorted(set(universe + [BENCHMARK]))
    close = reader.close_frame(codes, start, end)
    stock_close = close[[c for c in universe if c in close.columns]]
    bench_close = close[BENCHMARK]
    fund = FundamentalCache(TOKEN_PATH, CACHE_DIR)
    fund.prefetch_fina([qlib_to_tushare(code) for code in universe], start, end)

    cash = params.initial_cash
    shares = pd.Series(0.0, index=stock_close.columns)
    records, target_rows = [], []
    rebal_dates = set(monthly_rebalance_dates(reader.calendar, start, end))

    for i, date in enumerate(stock_close.index[:-1]):
        next_date = stock_close.index[i + 1]
        prices = stock_close.loc[date]
        value = cash + float((shares * prices.fillna(0)).sum())

        if date in rebal_dates and i > 0:
            data_date = stock_close.index[i - 1]
            active_universe = history_universe.codes_for_date(data_date) if history_universe else universe
            base_df = build_base_dataframe(fund, active_universe, data_date, params)
            if not base_df.empty:
                m_state, risk_state = market_state(bench_close, data_date)
                targets, pool, branch = pick_targets(base_df, m_state, risk_state, params)
                target_set = set(targets)

                sell_codes = [c for c in shares.index if shares[c] > 0 and c not in target_set]
                for code in sell_codes:
                    if pd.notnull(prices.get(code, np.nan)):
                        cash += shares[code] * prices[code] * (1 - params.close_cost)
                        shares[code] = 0

                if targets:
                    target_value = (cash + float((shares * prices.fillna(0)).sum())) / len(targets)
                    for code in targets:
                        price = prices.get(code, np.nan)
                        if pd.isnull(price) or price <= 0:
                            continue
                        current_value = shares.get(code, 0.0) * price
                        diff_value = target_value - current_value
                        if diff_value < 0:
                            sell_shares = min(shares[code], lot_floor(abs(diff_value) / price))
                            cash += sell_shares * price * (1 - params.close_cost)
                            shares[code] -= sell_shares
                        elif diff_value > 0:
                            buy_cash = min(cash, diff_value)
                            buy_shares = lot_floor(buy_cash / (price * (1 + params.open_cost)))
                            cash -= buy_shares * price * (1 + params.open_cost)
                            shares[code] += buy_shares

                value = cash + float((shares * prices.fillna(0)).sum())
                for rank, code in enumerate(targets, start=1):
                    target_rows.append({"date": date, "rank": rank, "code": code, "branch": branch})
                print(f"{date.date()} rebalance {branch}: {len(targets)} targets")

        next_prices = stock_close.loc[next_date]
        next_value = cash + float((shares * next_prices.fillna(prices)).sum())
        records.append({"date": next_date, "portfolio_value": next_value, "cash": cash, "position_count": int((shares > 0).sum())})

    equity = pd.DataFrame(records).set_index("date")
    bench = bench_close.reindex(equity.index).ffill()
    equity["benchmark_value"] = params.initial_cash * bench / bench.iloc[0]
    equity["strategy_return"] = equity["portfolio_value"] / equity["portfolio_value"].iloc[0] - 1
    equity["benchmark_return"] = equity["benchmark_value"] / equity["benchmark_value"].iloc[0] - 1
    targets = pd.DataFrame(target_rows)
    return equity, targets


def summarize(equity: pd.DataFrame) -> dict[str, float]:
    ret = equity["portfolio_value"].pct_change().dropna()
    total_return = equity["portfolio_value"].iloc[-1] / equity["portfolio_value"].iloc[0] - 1
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    annual_return = (1 + total_return) ** (1 / years) - 1
    annual_vol = ret.std() * np.sqrt(252)
    max_dd = (equity["portfolio_value"] / equity["portfolio_value"].cummax() - 1).min()
    sharpe = annual_return / annual_vol if annual_vol > 0 else np.nan
    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "annual_vol": annual_vol,
        "max_drawdown": max_dd,
        "sharpe_like": sharpe,
    }


def plot_returns(equity: pd.DataFrame, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    (equity["strategy_return"] * 100).plot(ax=ax, label="POE PB+ROE strategy", linewidth=2)
    (equity["benchmark_return"] * 100).plot(ax=ax, label="CSI 300 benchmark", linewidth=1.8)
    ax.set_title("POE PB+ROE Strategy vs CSI 300")
    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative return (%)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default=dt.date.today().strftime("%Y-%m-%d"))
    parser.add_argument("--market", default="hs300")
    parser.add_argument("--initial-cash", type=float, default=500_000.0)
    args = parser.parse_args()

    params = StrategyParams(initial_cash=args.initial_cash)
    equity, targets = run_backtest(args.start, args.end, args.market, params)
    out_dir = BASE_DIR / "outputs"
    out_dir.mkdir(exist_ok=True)
    suffix = f"{args.market}_{pd.Timestamp(args.start):%Y%m%d}_{pd.Timestamp(args.end):%Y%m%d}"
    equity_path = out_dir / f"poe_pb_roe_equity_{suffix}.csv"
    targets_path = out_dir / f"poe_pb_roe_targets_{suffix}.csv"
    plot_path = out_dir / f"poe_pb_roe_returns_{suffix}.png"
    equity.to_csv(equity_path)
    targets.to_csv(targets_path, index=False)
    plot_returns(equity, plot_path)

    stats = summarize(equity)
    print("\nPOE PB+ROE backtest summary")
    for key, value in stats.items():
        print(f"{key}: {value:.4f}")
    print(f"equity: {equity_path}")
    print(f"targets: {targets_path}")
    print(f"return_plot: {plot_path}")


if __name__ == "__main__":
    main()
