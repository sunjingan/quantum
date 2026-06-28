"""
Trend-Serenity Quant Strategy for A-shares.

This is a non-ML strategy distilled from the local a-share research framework
and trend-serenity investing method:

  research discipline -> explicit data gates
  trend-growth screen -> tradable candidate pool
  Serenity deep-dive dimensions -> quantitative proxies
  evidence gaps -> conservative penalties

It is a research/backtest tool, not financial advice.

Usage:
  source activate.sh
  python runs/qlib/trend_serenity_quant_strategy.py --market hs300 --start 2018-01-02 --end 2026-06-22
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
sys.path.insert(0, str(PROJECT_ROOT))

from lazy_tushare_loader import LazyTushareLoader, qlib_to_tushare, tushare_to_qlib
from poe_pb_roe_strategy import (
    BASE_DIR,
    PROVIDER_URI,
    TOKEN_PATH,
    CACHE_DIR,
    BENCHMARK,
    QlibDailyReader,
    Hs300HistoryUniverse,
    load_hs300_weights,
    read_instrument_codes,
    monthly_rebalance_dates,
    lot_floor,
)


@dataclass
class SerenityParams:
    initial_cash: float = 500_000.0
    target_num: int = 10
    min_list_days: int = 250
    min_profit: float = 0.0
    min_q_sales_yoy: float = 40.0
    min_bottleneck_q_sales_yoy: float = 15.0
    min_price_score: int = 1
    max_pe_ttm: float = 200.0
    max_debt_to_assets: float = 85.0
    max_per_industry: int = 3
    open_cost: float = 0.0005
    close_cost: float = 0.0015


class SerenityDataCache:
    def __init__(self, token_path: Path, cache_dir: Path):
        self.cache_dir = cache_dir / "trend_serenity"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.pro = ts.pro_api(token=token_path.read_text().strip())
        self._statement_cache: dict[tuple[str, str], pd.DataFrame] = {}

    def stock_basic(self) -> pd.DataFrame:
        path = self.cache_dir / "stock_basic_all.csv"
        if path.exists():
            return pd.read_csv(path, dtype={"ts_code": str, "list_date": str, "delist_date": str})
        rows = []
        for status in ["L", "D"]:
            df = self.pro.stock_basic(
                exchange="",
                list_status=status,
                fields="ts_code,symbol,name,area,industry,list_date,delist_date",
            )
            if df is not None and not df.empty:
                df["list_status"] = status
                rows.append(df)
        result = pd.concat(rows, ignore_index=True)
        result.to_csv(path, index=False)
        return result

    def daily_basic(self, trade_date: pd.Timestamp) -> pd.DataFrame:
        ymd = f"{trade_date:%Y%m%d}"
        path = self.cache_dir / "daily_basic" / f"{ymd}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return pd.read_csv(path, dtype={"ts_code": str})
        df = self.pro.daily_basic(
            trade_date=ymd,
            fields="ts_code,trade_date,close,turnover_rate,volume_ratio,pe_ttm,pb,ps_ttm,total_mv,circ_mv",
        )
        if df is None:
            df = pd.DataFrame()
        df.to_csv(path, index=False)
        return df

    def statement(self, endpoint: str, ts_code: str, start_date: str, end_date: str, fields: str) -> pd.DataFrame:
        safe = ts_code.replace(".", "_")
        path = self.cache_dir / endpoint / f"{safe}.csv"
        through = self.cache_dir / endpoint / f"{safe}.through"
        path.parent.mkdir(parents=True, exist_ok=True)
        cache_key = (endpoint, ts_code)
        if path.exists() and through.exists() and through.read_text().strip() >= end_date:
            if cache_key not in self._statement_cache:
                self._statement_cache[cache_key] = pd.read_csv(path, dtype={"ts_code": str, "ann_date": str, "end_date": str})
            return self._statement_cache[cache_key]
        func = getattr(self.pro, endpoint)
        df = func(ts_code=ts_code, start_date=start_date, end_date=end_date, fields=fields)
        if df is None:
            df = pd.DataFrame()
        if path.exists():
            old = pd.read_csv(path, dtype={"ts_code": str, "ann_date": str, "end_date": str})
            df = pd.concat([old, df], ignore_index=True)
            if not df.empty:
                keys = [c for c in ["ts_code", "ann_date", "end_date"] if c in df.columns]
                df = df.drop_duplicates(keys, keep="last")
        df.to_csv(path, index=False)
        through.write_text(end_date)
        self._statement_cache[cache_key] = df
        return df

    def latest_visible_row(self, endpoint: str, ts_code: str, data_date: pd.Timestamp) -> pd.Series | None:
        end_date = f"{data_date:%Y%m%d}"
        start_date = f"{data_date - pd.DateOffset(years=3):%Y%m%d}"
        fields = {
            "fina_indicator": (
                "ts_code,ann_date,end_date,roe,roa,grossprofit_margin,netprofit_margin,"
                "q_sales_yoy,q_op_qoq,q_roe,q_ocf_to_sales,netprofit_yoy,dt_netprofit_yoy,"
                "debt_to_assets,ocf_to_debt"
            ),
            "income": "ts_code,ann_date,end_date,total_revenue,revenue,n_income_attr_p,rd_exp,total_profit",
            "cashflow": "ts_code,ann_date,end_date,n_cashflow_act,free_cashflow",
            "balancesheet": "ts_code,ann_date,end_date,accounts_receiv,inventories,contract_liab,total_assets,total_liab",
        }[endpoint]
        df = self.statement(endpoint, ts_code, start_date, end_date, fields)
        if df.empty or "ann_date" not in df.columns:
            return None
        df = df[df["ann_date"].astype(str) <= end_date].copy()
        if df.empty:
            return None
        return df.sort_values(["ann_date", "end_date"]).iloc[-1]

    def prefetch(self, ts_codes: list[str], start: str, end: str) -> None:
        start_date = f"{pd.Timestamp(start) - pd.DateOffset(years=3):%Y%m%d}"
        end_date = f"{pd.Timestamp(end):%Y%m%d}"
        endpoints = {
            "fina_indicator": (
                "ts_code,ann_date,end_date,roe,roa,grossprofit_margin,netprofit_margin,"
                "q_sales_yoy,q_op_qoq,q_roe,q_ocf_to_sales,netprofit_yoy,dt_netprofit_yoy,"
                "debt_to_assets,ocf_to_debt"
            ),
            "income": "ts_code,ann_date,end_date,total_revenue,revenue,n_income_attr_p,rd_exp,total_profit",
            "cashflow": "ts_code,ann_date,end_date,n_cashflow_act,free_cashflow",
            "balancesheet": "ts_code,ann_date,end_date,accounts_receiv,inventories,contract_liab,total_assets,total_liab",
        }
        unique_codes = sorted(set(ts_codes))
        for i, ts_code in enumerate(unique_codes, start=1):
            for endpoint, fields in endpoints.items():
                safe = ts_code.replace(".", "_")
                path = self.cache_dir / endpoint / f"{safe}.csv"
                through = self.cache_dir / endpoint / f"{safe}.through"
                if path.exists() and through.exists() and through.read_text().strip() >= end_date:
                    continue
                self.statement(endpoint, ts_code, start_date, end_date, fields)
            if i % 50 == 0:
                print(f"trend-serenity statement cache: {i}/{len(unique_codes)}", flush=True)

    def snapshot(self, qlib_codes: list[str], data_date: pd.Timestamp) -> pd.DataFrame:
        ts_codes = [qlib_to_tushare(code) for code in qlib_codes]
        basic = self.stock_basic()
        daily = self.daily_basic(data_date)
        rows = []
        for code, ts_code in zip(qlib_codes, ts_codes):
            fina = self.latest_visible_row("fina_indicator", ts_code, data_date)
            inc = self.latest_visible_row("income", ts_code, data_date)
            cf = self.latest_visible_row("cashflow", ts_code, data_date)
            bs = self.latest_visible_row("balancesheet", ts_code, data_date)
            if fina is None or inc is None:
                continue
            row = {"code": code.lower(), "ts_code": ts_code}
            for prefix, item in [("fi", fina), ("inc", inc), ("cf", cf), ("bs", bs)]:
                if item is not None:
                    for k, v in item.items():
                        row[f"{prefix}_{k}"] = v
            rows.append(row)
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df = df.merge(daily, on="ts_code", how="left")
        df = df.merge(basic, on="ts_code", how="left")
        df["industry_name"] = df["industry"].fillna("UNKNOWN")
        return df


def pct_rank(s: pd.Series, ascending: bool = True) -> pd.Series:
    return s.rank(ascending=ascending, pct=True).clip(0, 1)


def score_high_is_good(s: pd.Series) -> pd.Series:
    return pct_rank(s.replace([np.inf, -np.inf], np.nan), ascending=True).fillna(0.0)


def score_low_is_good(s: pd.Series) -> pd.Series:
    return (1 - pct_rank(s.replace([np.inf, -np.inf], np.nan), ascending=True)).fillna(0.0)


def price_strength(close: pd.DataFrame, codes: list[str], data_date: pd.Timestamp) -> pd.DataFrame:
    hist = close.loc[:data_date, codes].tail(252)
    if hist.empty:
        return pd.DataFrame()
    latest = hist.iloc[-1]
    high = hist.max()
    ret60 = latest / hist.shift(60).iloc[-1] - 1
    dist = latest / high - 1
    price_score = pd.Series(-1, index=latest.index)
    price_score[dist >= -0.05] = 2
    price_score[(dist >= -0.15) & (dist < -0.05) & (ret60 > 0.10)] = 1
    price_score[(dist >= -0.15) & (price_score < 1)] = 0
    return pd.DataFrame({"latest_close": latest, "dist_to_252d_high": dist, "ret60": ret60, "price_score": price_score})


def build_serenity_pool(
    data: SerenityDataCache,
    close: pd.DataFrame,
    universe: list[str],
    data_date: pd.Timestamp,
    params: SerenityParams,
) -> pd.DataFrame:
    df = data.snapshot(universe, data_date)
    if df.empty:
        return df
    px = price_strength(close, list(df["code"]), data_date)
    df = df.merge(px, left_on="code", right_index=True, how="left")

    df["list_days"] = (data_date - pd.to_datetime(df["list_date"].astype(str), errors="coerce")).dt.days
    df["n_income_attr_p"] = pd.to_numeric(df.get("inc_n_income_attr_p"), errors="coerce")
    df["revenue"] = pd.to_numeric(df.get("inc_revenue"), errors="coerce").fillna(pd.to_numeric(df.get("inc_total_revenue"), errors="coerce"))
    df["q_sales_yoy"] = pd.to_numeric(df.get("fi_q_sales_yoy"), errors="coerce")
    df["q_profit_yoy"] = pd.to_numeric(df.get("fi_dt_netprofit_yoy"), errors="coerce").fillna(pd.to_numeric(df.get("fi_netprofit_yoy"), errors="coerce"))
    df["gross_margin"] = pd.to_numeric(df.get("fi_grossprofit_margin"), errors="coerce")
    df["net_margin"] = pd.to_numeric(df.get("fi_netprofit_margin"), errors="coerce")
    df["roe"] = pd.to_numeric(df.get("fi_roe"), errors="coerce")
    df["debt_to_assets"] = pd.to_numeric(df.get("fi_debt_to_assets"), errors="coerce")
    df["ocf"] = pd.to_numeric(df.get("cf_n_cashflow_act"), errors="coerce")
    df["rd_exp"] = pd.to_numeric(df.get("inc_rd_exp"), errors="coerce")
    df["inventories"] = pd.to_numeric(df.get("bs_inventories"), errors="coerce")
    df["accounts_receiv"] = pd.to_numeric(df.get("bs_accounts_receiv"), errors="coerce")
    df["contract_liab"] = pd.to_numeric(df.get("bs_contract_liab"), errors="coerce")
    df["pe_ttm"] = pd.to_numeric(df.get("pe_ttm"), errors="coerce")
    df["pb"] = pd.to_numeric(df.get("pb"), errors="coerce")
    df["turnover_rate"] = pd.to_numeric(df.get("turnover_rate"), errors="coerce")

    raw_code = df["code"].str[2:]
    name = df["name"].fillna("")
    sanity_keep = (
        (df["list_days"] >= params.min_list_days)
        & ~raw_code.str.startswith(("688", "689", "4", "8"))
        & ~name.str.contains("ST|退|\\*", regex=True)
        & (df["n_income_attr_p"] > params.min_profit)
        & (df["pe_ttm"] > 0)
        & (df["pe_ttm"] <= params.max_pe_ttm)
        & (df["pb"] > 0)
        & (df["debt_to_assets"] <= params.max_debt_to_assets)
    )
    df = df[sanity_keep].copy()
    if df.empty:
        return df

    df["ocf_to_profit"] = df["ocf"] / df["n_income_attr_p"].replace(0, np.nan)
    df["rd_to_revenue"] = df["rd_exp"] / df["revenue"].replace(0, np.nan)
    df["inventory_to_revenue"] = df["inventories"] / df["revenue"].replace(0, np.nan)
    df["receivable_to_revenue"] = df["accounts_receiv"] / df["revenue"].replace(0, np.nan)
    df["contract_liab_to_revenue"] = df["contract_liab"] / df["revenue"].replace(0, np.nan)

    # Four Serenity dimensions as quantitative proxies.
    df["bottleneck_authenticity"] = (
        0.35 * score_high_is_good(df["gross_margin"])
        + 0.25 * score_high_is_good(df["rd_to_revenue"])
        + 0.25 * score_high_is_good(df["contract_liab_to_revenue"])
        + 0.15 * score_high_is_good(df["price_score"])
    )
    df["financial_translation"] = (
        0.30 * score_high_is_good(df["q_sales_yoy"])
        + 0.25 * score_high_is_good(df["q_profit_yoy"])
        + 0.20 * score_high_is_good(df["net_margin"])
        + 0.25 * score_high_is_good(df["ocf_to_profit"])
    )
    valuation_rank = 0.5 * score_low_is_good(df["pe_ttm"]) + 0.5 * score_low_is_good(df["pb"])
    not_overheated = score_low_is_good(df["ret60"].clip(lower=-1, upper=2))
    df["expectation_gap"] = 0.60 * valuation_rank + 0.25 * not_overheated + 0.15 * score_high_is_good(df["q_sales_yoy"])
    df["reflexivity_risk_control"] = (
        0.30 * score_low_is_good(df["debt_to_assets"])
        + 0.25 * score_low_is_good(df["inventory_to_revenue"])
        + 0.25 * score_low_is_good(df["receivable_to_revenue"])
        + 0.20 * score_low_is_good(df["turnover_rate"])
    )
    df["serenity_score"] = (
        0.30 * df["bottleneck_authenticity"]
        + 0.30 * df["financial_translation"]
        + 0.20 * df["expectation_gap"]
        + 0.20 * df["reflexivity_risk_control"]
    )
    df["channel_a_super_growth"] = (
        (df["q_sales_yoy"] >= params.min_q_sales_yoy)
        & (df["price_score"] >= params.min_price_score)
        & (df["financial_translation"] >= df["financial_translation"].quantile(0.50))
    )
    df["channel_b_bottleneck_quality"] = (
        (df["q_sales_yoy"] >= params.min_bottleneck_q_sales_yoy)
        & (df["price_score"] >= 0)
        & (df["bottleneck_authenticity"] >= df["bottleneck_authenticity"].quantile(0.70))
        & (df["financial_translation"] >= df["financial_translation"].quantile(0.50))
        & (df["reflexivity_risk_control"] >= df["reflexivity_risk_control"].quantile(0.30))
    )
    df = df[df["channel_a_super_growth"] | df["channel_b_bottleneck_quality"]].copy()
    if df.empty:
        return df
    df["needs_verification"] = ""
    df.loc[df["rd_to_revenue"].isna(), "needs_verification"] += "R&D missing;"
    df.loc[df["contract_liab_to_revenue"].isna(), "needs_verification"] += "contract liabilities missing;"
    return df.sort_values("serenity_score", ascending=False).reset_index(drop=True)


def select_targets(pool: pd.DataFrame, params: SerenityParams) -> list[str]:
    selected, industry_count = [], {}
    for _, row in pool.iterrows():
        industry = row.get("industry_name", "UNKNOWN")
        if industry_count.get(industry, 0) >= params.max_per_industry:
            continue
        selected.append(row["code"])
        industry_count[industry] = industry_count.get(industry, 0) + 1
        if len(selected) >= params.target_num:
            break
    return selected


def run_backtest(start: str, end: str, market: str, params: SerenityParams):
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
    close = reader.close_frame(sorted(set(universe + [BENCHMARK])), start, end)
    stock_close = close[[c for c in universe if c in close.columns]]
    bench_close = close[BENCHMARK]

    data = SerenityDataCache(TOKEN_PATH, CACHE_DIR)
    data.prefetch([qlib_to_tushare(c) for c in universe], start, end)

    cash = params.initial_cash
    shares = pd.Series(0.0, index=stock_close.columns)
    records, target_rows = [], []
    rebalance_dates = set(monthly_rebalance_dates(reader.calendar, start, end))

    for i, date in enumerate(stock_close.index[:-1]):
        next_date = stock_close.index[i + 1]
        prices = stock_close.loc[date]

        if date in rebalance_dates and i > 0:
            data_date = stock_close.index[i - 1]
            active_universe = history_universe.codes_for_date(data_date) if history_universe else universe
            pool = build_serenity_pool(data, stock_close, active_universe, data_date, params)
            targets = select_targets(pool, params) if not pool.empty else []
            target_set = set(targets)

            for code in shares.index:
                if shares[code] > 0 and code not in target_set and pd.notnull(prices.get(code, np.nan)):
                    cash += shares[code] * prices[code] * (1 - params.close_cost)
                    shares[code] = 0

            if targets:
                total_value = cash + float((shares * prices.fillna(0)).sum())
                target_value = total_value / len(targets)
                for code in targets:
                    price = prices.get(code, np.nan)
                    if pd.isnull(price) or price <= 0:
                        continue
                    current_value = shares[code] * price
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

            for rank, code in enumerate(targets, start=1):
                row = pool.loc[pool["code"] == code].iloc[0].to_dict()
                target_rows.append(
                    {
                        "date": date,
                        "data_date": data_date,
                        "rank": rank,
                        "code": code,
                        "name": row.get("name", ""),
                        "industry_name": row.get("industry_name", ""),
                        "serenity_score": row.get("serenity_score", np.nan),
                        "bottleneck_authenticity": row.get("bottleneck_authenticity", np.nan),
                        "financial_translation": row.get("financial_translation", np.nan),
                        "expectation_gap": row.get("expectation_gap", np.nan),
                        "reflexivity_risk_control": row.get("reflexivity_risk_control", np.nan),
                        "needs_verification": row.get("needs_verification", ""),
                    }
                )
            print(f"{date.date()} trend-serenity rebalance: {len(targets)} targets")

        next_prices = stock_close.loc[next_date]
        value = cash + float((shares * next_prices.fillna(prices)).sum())
        records.append({"date": next_date, "portfolio_value": value, "cash": cash, "position_count": int((shares > 0).sum())})

    equity = pd.DataFrame(records).set_index("date")
    bench = bench_close.reindex(equity.index)
    first_valid = bench.first_valid_index()
    if first_valid is None:
        equity["benchmark_value"] = np.nan
        equity["benchmark_return"] = np.nan
    else:
        bench = bench.loc[first_valid:].ffill()
        equity["benchmark_value"] = np.nan
        equity.loc[bench.index, "benchmark_value"] = params.initial_cash * bench / bench.iloc[0]
        equity["benchmark_return"] = equity["benchmark_value"] / equity["benchmark_value"].dropna().iloc[0] - 1
    equity["strategy_return"] = equity["portfolio_value"] / equity["portfolio_value"].iloc[0] - 1
    return equity, pd.DataFrame(target_rows)


def summarize(equity: pd.DataFrame) -> dict[str, float]:
    ret = equity["portfolio_value"].pct_change().dropna()
    total_return = equity["portfolio_value"].iloc[-1] / equity["portfolio_value"].iloc[0] - 1
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    annual_return = (1 + total_return) ** (1 / years) - 1
    annual_vol = ret.std() * np.sqrt(252)
    max_dd = (equity["portfolio_value"] / equity["portfolio_value"].cummax() - 1).min()
    bench = equity["benchmark_value"].dropna()
    if bench.empty:
        benchmark_total_return = np.nan
        benchmark_annual_return = np.nan
        benchmark_max_dd = np.nan
    else:
        benchmark_total_return = bench.iloc[-1] / bench.iloc[0] - 1
        bench_years = max((bench.index[-1] - bench.index[0]).days / 365.25, 1e-9)
        benchmark_annual_return = (1 + benchmark_total_return) ** (1 / bench_years) - 1
        benchmark_max_dd = (bench / bench.cummax() - 1).min()
    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "annual_vol": annual_vol,
        "max_drawdown": max_dd,
        "sharpe_like": annual_return / annual_vol if annual_vol > 0 else np.nan,
        "benchmark_total_return": benchmark_total_return,
        "benchmark_annual_return": benchmark_annual_return,
        "benchmark_max_drawdown": benchmark_max_dd,
    }


def plot_returns(equity: pd.DataFrame, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    (equity["strategy_return"] * 100).plot(ax=ax, label="Trend-Serenity Quant", linewidth=2)
    (equity["benchmark_return"] * 100).plot(ax=ax, label="CSI 300 benchmark", linewidth=1.8)
    ax.set_title("Trend-Serenity Quant Strategy vs CSI 300")
    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative return (%)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", default="hs300")
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default=dt.date.today().strftime("%Y-%m-%d"))
    parser.add_argument("--initial-cash", type=float, default=500_000.0)
    parser.add_argument("--target-num", type=int, default=10)
    args = parser.parse_args()

    params = SerenityParams(initial_cash=args.initial_cash, target_num=args.target_num)
    equity, targets = run_backtest(args.start, args.end, args.market, params)
    out_dir = BASE_DIR / "outputs"
    out_dir.mkdir(exist_ok=True)
    suffix = f"{args.market}_{pd.Timestamp(args.start):%Y%m%d}_{pd.Timestamp(args.end):%Y%m%d}"
    equity_path = out_dir / f"trend_serenity_equity_{suffix}.csv"
    targets_path = out_dir / f"trend_serenity_targets_{suffix}.csv"
    plot_path = out_dir / f"trend_serenity_returns_{suffix}.png"
    equity.to_csv(equity_path)
    targets.to_csv(targets_path, index=False)
    plot_returns(equity, plot_path)

    print("\nTrend-Serenity Quant summary")
    for k, v in summarize(equity).items():
        print(f"{k}: {v:.4f}")
    print(f"equity: {equity_path}")
    print(f"targets: {targets_path}")
    print(f"return_plot: {plot_path}")
    print("\nThis is not financial advice. Verify latest filings, price, market cap, float, ownership, and short interest independently.")


if __name__ == "__main__":
    main()
