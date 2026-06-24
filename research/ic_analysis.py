"""
因子有效性分析 — IC / RankIC / 分组收益 / 单因子分层 / 维度消融。

回答: 这个因子有没有经济含义？

输出:
  1. 因子 IC 表: 每个调仓日 × 每个因子 × 多个时间窗口的 IC/RankIC
  2. IC 汇总表: 均值、ICIR、正比例、t统计量
  3. 分组收益表: Q1-Q5 分层 + Top-Bottom spread
  4. 消融实验表: 四个维度分别/组合的回测指标
"""
from __future__ import annotations

import os, sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from strategies._fundamental import FundamentalCache, qlib_to_tushare
from strategies._enrichment import EnrichmentCache
from strategies._utils import QlibDailyReader, monthly_rebalance_dates
from strategies.trend_serenity import (
    TrendSerenityParams,
    build_serenity_pool_v2,
)
from strategies.trend_serenity_v2 import compute_serenity_v2


def compute_factor_scores(
    data: FundamentalCache,
    enrich: EnrichmentCache | None,
    close: pd.DataFrame,
    universe: list[str],
    data_date: pd.Timestamp,
    params: TrendSerenityParams,
    factor_version: str = "v2",
) -> pd.DataFrame | None:
    """
    对给定日期计算所有因子分数，返回每只股票一行。

    返回字段:
      code, serenity_score, bottleneck_authenticity, financial_translation,
      expectation_gap, reflexivity_risk_control,
      q_sales_yoy, gross_margin, pe_ttm, price_score, 以及各子变量分数
    """
    factor_version = factor_version.lower()
    if factor_version == "v2":
        pool = compute_serenity_v2(
            data,
            enrich,
            close,
            universe,
            data_date,
            industry_neutral=params.industry_neutral_v2,
        )
    else:
        pool, _ = build_serenity_pool_v2(data, enrich, close, universe, data_date, params, return_all=True)
    if pool is None or pool.empty:
        return None

    if factor_version == "v2":
        cols = [
            "code",
            "serenity_score_v2",
            "bottleneck_ind",
            "financial_ind",
            "reflexivity_ind",
            "trend_confirm",
            "valuation_penalty",
            "bottleneck_pure",
        ]
    else:
        cols = [
            "code",
            "serenity_score",
            "bottleneck_authenticity",
            "financial_translation",
            "expectation_gap",
            "reflexivity_risk_control",
        ]
    df = pool[[c for c in cols if c in pool.columns]].copy()

    # 也拉入原始数据中的额外因子以备后续分析
    for col in ["q_sales_yoy", "gross_margin", "pe_ttm", "price_score",
                "roe", "debt_to_assets", "turnover_rate", "pb"]:
        if col in pool.columns:
            df[col] = pool[col]

    df["date"] = data_date
    return df


def compute_forward_returns(
    close: pd.DataFrame,
    codes: list[str],
    data_date: pd.Timestamp,
    horizons: list[int] = [20, 60, 120],
) -> pd.DataFrame:
    """
    计算未来 N 个交易日的收益。

    返回 DataFrame, 列: code, fwd_ret_20d, fwd_ret_60d, fwd_ret_120d
    """
    results = []
    for code in codes:
        if code not in close.columns:
            continue
        ts = close[code].loc[data_date:]
        row = {"code": code}
        for h in horizons:
            if len(ts) > h:
                ret = ts.iloc[h] / ts.iloc[0] - 1
            else:
                ret = np.nan
            row[f"fwd_ret_{h}d"] = ret
        results.append(row)
    return pd.DataFrame(results)


def run_ic_analysis(
    provider_uri: Path,
    token_path: Path,
    cache_dir: Path,
    start: str,
    end: str,
    market: str = "hs300",
    skip_enrich: bool = True,
    factor_version: str = "v2",
) -> Dict[str, pd.DataFrame]:
    """
    跑完整的 IC 分析。

    返回 dict:
      - "ic_table": 每个调仓日 × 每个因子 × 每个时间窗口的 IC
      - "ic_summary": IC 汇总统计
      - "grouped_returns": 分组收益
      - "factor_scores": 所有因子分数原始数据
    """
    params = TrendSerenityParams(factor_version=factor_version)
    factor_version = factor_version.lower()

    # ── 数据加载 ──
    from strategies._utils import load_hs300_weights, Hs300HistoryUniverse, read_instrument_codes
    if market.lower() in {"hs300", "csi300_history", "000300"}:
        weights = load_hs300_weights(cache_dir, token_path, start, end)
        hist_uni = Hs300HistoryUniverse(weights)
        universe = sorted(weights["code"].str.lower().unique().tolist())
    else:
        universe = read_instrument_codes(provider_uri, market)
        hist_uni = None

    reader = QlibDailyReader(provider_uri)
    all_codes = sorted(set(universe + ["sh000300"]))
    close = reader.close_frame(all_codes, start, end)
    stock_close = close[[c for c in universe if c in close.columns]]

    data = FundamentalCache(token_path, cache_dir / "trend_serenity")
    ts_uni = [qlib_to_tushare(c) for c in universe]
    data.prefetch(ts_uni, start, end)

    enrich = None
    if not skip_enrich:
        enrich = EnrichmentCache(token_path, cache_dir)
        try:
            enrich.prefetch(ts_uni, start, end)
        except Exception:
            pass

    cal = pd.Series(reader.calendar)
    rebal_dates = monthly_rebalance_dates(cal, start, end)

    # ── 收集因子分数 + 未来收益 ──
    factor_rows = []
    ic_rows = []
    grouped_rows = []

    if factor_version == "v2":
        score_col = "serenity_score_v2"
        factor_names = [
            "serenity_score_v2",
            "bottleneck_ind",
            "financial_ind",
            "reflexivity_ind",
            "trend_confirm",
            "valuation_penalty",
            "bottleneck_pure",
        ]
    else:
        score_col = "serenity_score"
        factor_names = [
            "serenity_score",
            "bottleneck_authenticity",
            "financial_translation",
            "expectation_gap",
            "reflexivity_risk_control",
        ]

    for i, date in enumerate(rebal_dates):
        cal_ts = pd.Series(cal)
        pos = cal_ts.searchsorted(date, side="left")
        data_date = cal[max(0, pos - 1)]

        if hist_uni is not None:
            au = hist_uni.codes_for_date(data_date)
        else:
            au = [c for c in universe if c in stock_close.columns]

        scores = compute_factor_scores(data, enrich, stock_close, au, data_date, params, factor_version=factor_version)
        if scores is None or scores.empty:
            continue

        # 计算未来收益
        fwd = compute_forward_returns(stock_close, list(scores["code"]), date, horizons=[20, 60, 120])
        merged = scores.merge(fwd, on="code", how="inner")
        if merged.empty:
            continue

        # 收集因子分数
        factor_rows.append(merged)

        # 计算 IC / RankIC
        for fn in factor_names:
            for h in [20, 60, 120]:
                fwd_col = f"fwd_ret_{h}d"
                valid = merged[[fn, fwd_col]].dropna()
                if len(valid) < 20:
                    continue

                # Pearson IC
                ic = valid[fn].corr(valid[fwd_col])
                # Rank IC (Spearman)
                rank_ic = valid[fn].rank().corr(valid[fwd_col].rank())

                ic_rows.append({
                    "date": data_date,
                    "factor": fn,
                    "horizon": h,
                    "IC": ic,
                    "RankIC": rank_ic,
                    "n_stocks": len(valid),
                })

        # 分组收益
        for h in [20, 60, 120]:
            fwd_col = f"fwd_ret_{h}d"
            valid = merged[[score_col, fwd_col]].dropna()
            if len(valid) < 20:
                continue
            valid["group"] = pd.qcut(
                valid[score_col].rank(method="first"),
                5,
                labels=["Q1", "Q2", "Q3", "Q4", "Q5"],
            )
            gb = valid.groupby("group", observed=True)[fwd_col].mean()
            for g, v in gb.items():
                grouped_rows.append({
                    "date": data_date,
                    "horizon": h,
                    "group": g,
                    "mean_return": v,
                    "n_stocks": len(valid[valid["group"] == g]),
                })

    # ── 汇总 ──
    ic_df = pd.DataFrame(ic_rows)

    # IC 汇总表
    ic_summary_rows = []
    for fn in factor_names:
        for h in [20, 60, 120]:
            sub = ic_df[(ic_df["factor"] == fn) & (ic_df["horizon"] == h)]
            if sub.empty:
                continue
            mean_ic = sub["IC"].mean()
            mean_ric = sub["RankIC"].mean()
            ic_std = sub["IC"].std()
            icir = mean_ic / ic_std if ic_std > 0 else 0
            pos_ratio = (sub["IC"] > 0).mean()
            t_stat = mean_ic / (ic_std / np.sqrt(len(sub))) if ic_std > 0 else 0
            ic_summary_rows.append({
                "factor": fn,
                "horizon": h,
                "mean_IC": mean_ic,
                "mean_RankIC": mean_ric,
                "ICIR": icir,
                "positive_ratio": pos_ratio,
                "t_stat": t_stat,
                "n_periods": len(sub),
            })

    ic_summary = pd.DataFrame(ic_summary_rows)
    grouped_df = pd.DataFrame(grouped_rows)

    # 分组汇总
    grouped_summary_rows = []
    for h in [20, 60, 120]:
        for g in ["Q1", "Q2", "Q3", "Q4", "Q5"]:
            sub = grouped_df[(grouped_df["horizon"] == h) & (grouped_df["group"] == g)]
            if sub.empty:
                continue
            mean_ret = sub["mean_return"].mean()
            grouped_summary_rows.append({"horizon": h, "group": g, "mean_fwd_return": mean_ret})

    grouped_summary = pd.DataFrame(grouped_summary_rows)

    factor_frames = [frame.dropna(axis=1, how="all") for frame in factor_rows if not frame.empty]

    return {
        "ic_table": ic_df,
        "ic_summary": ic_summary,
        "grouped_returns": grouped_df,
        "grouped_summary": grouped_summary,
        "factor_scores": pd.concat(factor_frames, ignore_index=True) if factor_frames else pd.DataFrame(),
    }


def run_ablation_study(ic_results: dict) -> pd.DataFrame:
    """
    消融实验: 四个维度分别 vs 总分。

    从回测角度: 对每个因子做分组收益的 Top-Bottom spread.
    """
    grouped = ic_results["grouped_returns"]
    if grouped.empty:
        return pd.DataFrame()

    # 另外在 ic_summary 里已有各因子的 IC
    ic_sum = ic_results["ic_summary"]
    if ic_sum.empty:
        return pd.DataFrame()

    # 返回 IC 汇总用于消融分析
    return ic_sum


if __name__ == "__main__":
    print("IC Analysis — 因子有效性检验")
    print("用法: 通过 run_ic_analysis() 调用")
