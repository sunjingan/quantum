"""
Trend-Serenity 因子 V2 — 按用户反馈修正。

关键改动 (P1-P5):
  P1: expectation_gap 改为极端估值惩罚（不作为正向Alpha）
  P2: 所有财务指标改为行业内分位数
  P3: bottleneck_authenticity 拆分为 4 个子因子分别测
  P4: 加入景气加速指标（增速二阶导、毛利率变化、现金流改善）
  P5: 组合 buffer 机制（买入Top15，持有Top30，跌出才卖）

V2 因子公式:
  serenity_score_v2 =
    0.40 × bottleneck_authenticity_ind
    + 0.30 × financial_translation_ind
    + 0.15 × reflexivity_risk_control_ind
    + 0.15 × trend_confirm
    - valuation_penalty

其中 _ind 下标表示行业内分位数版本。
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from strategies._fundamental import FundamentalCache, qlib_to_tushare
from strategies._enrichment import EnrichmentCache, compute_enrichment_for_codes


THEME_INDUSTRY_KEYWORDS = {
    "nonferrous_resources": ["有色", "铜", "铝", "铅锌", "小金属", "黄金", "稀缺资源", "矿物制品"],
    "semiconductor_cpo": ["半导体", "元器件", "通信设备", "IT设备"],
    "aerospace_defense": ["航天", "航空", "船舶", "军工"],
}


def _theme_bucket(industry: object) -> str:
    text = "" if pd.isna(industry) else str(industry)
    for bucket, keywords in THEME_INDUSTRY_KEYWORDS.items():
        if any(k in text for k in keywords):
            return bucket
    return ""


# ═══════════════════════════════════════════════════════════════
# 行业内分位数 (P2)
# ═══════════════════════════════════════════════════════════════

def industry_rank(df: pd.DataFrame, col: str, industry_col: str = "industry_name",
                  ascending: bool = True, pct: bool = True) -> pd.Series:
    """计算行业内分位数排名。"""
    result = df.groupby(industry_col)[col].rank(ascending=ascending, pct=pct).clip(0, 1)
    return result.fillna(0.5)


def safe_industry_rank(df, col, industry_col="industry_name", ascending=True):
    """容错版：如果行业列缺失，退化为全市场排名。"""
    if industry_col not in df.columns or df[industry_col].nunique() < 3:
        return df[col].rank(ascending=ascending, pct=True).clip(0, 1).fillna(0.5)
    return industry_rank(df, col, industry_col, ascending)


# ═══════════════════════════════════════════════════════════════
# 景气加速指标 (P4)
# ═══════════════════════════════════════════════════════════════

def compute_acceleration_metrics(
    data: FundamentalCache,
    qlib_codes: list[str],
    data_date: pd.Timestamp,
) -> pd.DataFrame:
    """
    计算景气加速指标（二阶变化量）。

    返回 DataFrame (code, sales_accel, profit_accel, margin_change_yoy,
                         ocf_improvement, inventory_change)
    """
    if len(qlib_codes) >= 1000 and hasattr(data, "latest_visible_bulk"):
        ts_codes = [qlib_to_tushare(code) for code in qlib_codes]
        code_map = dict(zip(ts_codes, [code.lower() for code in qlib_codes]))
        prev_date = data_date - pd.DateOffset(years=1)

        curr = data.latest_visible_bulk("fina_indicator", ts_codes, data_date)
        prev = data.latest_visible_bulk("fina_indicator", ts_codes, prev_date)
        if curr.empty or prev.empty:
            return pd.DataFrame({
                "code": [code.lower() for code in qlib_codes],
                "sales_accel": np.nan,
                "profit_accel": np.nan,
                "margin_change_yoy": np.nan,
                "ocf_change_yoy": np.nan,
                "debt_change_yoy": np.nan,
            })

        curr = curr.copy()
        prev = prev.copy()
        curr["code"] = curr["ts_code"].map(code_map)
        prev["code"] = prev["ts_code"].map(code_map)
        merged = curr.merge(prev, on="code", how="left", suffixes=("_curr", "_prev"))

        def num(col: str) -> pd.Series:
            value = merged.get(col)
            if value is None:
                return pd.Series(0.0, index=merged.index)
            return pd.to_numeric(value, errors="coerce").fillna(0.0)

        curr_profit_source = merged.get("dt_netprofit_yoy_curr")
        prev_profit_source = merged.get("dt_netprofit_yoy_prev")
        curr_profit = num("dt_netprofit_yoy_curr").where(
            curr_profit_source.notna() if curr_profit_source is not None else pd.Series(False, index=merged.index),
            num("netprofit_yoy_curr"),
        )
        prev_profit = num("dt_netprofit_yoy_prev").where(
            prev_profit_source.notna() if prev_profit_source is not None else pd.Series(False, index=merged.index),
            num("netprofit_yoy_prev"),
        )

        result = pd.DataFrame({
            "code": merged["code"],
            "sales_accel": num("q_sales_yoy_curr") - num("q_sales_yoy_prev"),
            "profit_accel": curr_profit - prev_profit,
            "margin_change_yoy": num("grossprofit_margin_curr") - num("grossprofit_margin_prev"),
            "ocf_change_yoy": num("q_ocf_to_sales_curr") - num("q_ocf_to_sales_prev"),
            "debt_change_yoy": num("debt_to_assets_prev") - num("debt_to_assets_curr"),
        })
        return result

    rows = []
    for code in qlib_codes:
        ts_code = qlib_to_tushare(code)
        curr = data.latest_visible_row("fina_indicator", ts_code, data_date)
        prev_date = data_date - pd.DateOffset(years=1)
        prev = data.latest_visible_row("fina_indicator", ts_code, prev_date)

        row = {"code": code.lower()}
        if curr is not None and prev is not None:
            row["sales_accel"] = (pd.to_numeric(curr.get("q_sales_yoy"), errors="coerce") or 0) - \
                                 (pd.to_numeric(prev.get("q_sales_yoy"), errors="coerce") or 0)
            row["profit_accel"] = (pd.to_numeric(curr.get("dt_netprofit_yoy"), errors="coerce") or
                                    pd.to_numeric(curr.get("netprofit_yoy"), errors="coerce") or 0) - \
                                  (pd.to_numeric(prev.get("dt_netprofit_yoy"), errors="coerce") or
                                    pd.to_numeric(prev.get("netprofit_yoy"), errors="coerce") or 0)
            row["margin_change_yoy"] = (pd.to_numeric(curr.get("grossprofit_margin"), errors="coerce") or 0) - \
                                       (pd.to_numeric(prev.get("grossprofit_margin"), errors="coerce") or 0)
            row["ocf_change_yoy"] = (pd.to_numeric(curr.get("q_ocf_to_sales"), errors="coerce") or 0) - \
                                    (pd.to_numeric(prev.get("q_ocf_to_sales"), errors="coerce") or 0)
            row["debt_change_yoy"] = (pd.to_numeric(prev.get("debt_to_assets"), errors="coerce") or 0) - \
                                     (pd.to_numeric(curr.get("debt_to_assets"), errors="coerce") or 0)
        else:
            for k in ["sales_accel", "profit_accel", "margin_change_yoy", "ocf_change_yoy", "debt_change_yoy"]:
                row[k] = np.nan
        rows.append(row)
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════
# 估值惩罚 (P1) — 代替 expectation_gap
# ═══════════════════════════════════════════════════════════════

def compute_valuation_penalty(df: pd.DataFrame, industry_col: str = "industry_name") -> pd.Series:
    """
    极端估值惩罚: PE 或 PB 在行业内 top 10% → 扣分。

    不在行业内最低 10% 加分（避免低估值陷阱）。
    返回惩罚值 [0, 0.15]，0 = 无惩罚。
    """
    penalty = pd.Series(0.0, index=df.index)

    # PE 极端高 → 扣分
    if "pe_ttm" in df.columns:
        pe_rank = safe_industry_rank(df, "pe_ttm", industry_col, ascending=True)
        penalty += (pe_rank > 0.90).astype(float) * 0.08
        penalty += (pe_rank > 0.95).astype(float) * 0.04

    # PB 极端高 → 扣分
    if "pb" in df.columns:
        pb_rank = safe_industry_rank(df, "pb", industry_col, ascending=True)
        penalty += (pb_rank > 0.90).astype(float) * 0.05

    # PE/PB 极端低 → 轻微扣分（可能是价值陷阱）
    if "pe_ttm" in df.columns:
        pe_rank = safe_industry_rank(df, "pe_ttm", industry_col, ascending=True)
        penalty += (pe_rank < 0.05).astype(float) * 0.02

    return penalty.clip(0, 0.15)


# ═══════════════════════════════════════════════════════════════
# 趋势确认 — 从 bottleneck 中拆出 (P3)
# ═══════════════════════════════════════════════════════════════

def compute_trend_confirm(close: pd.DataFrame, codes: list[str], data_date: pd.Timestamp) -> pd.Series:
    """趋势确认：多模价格强度打分（独立因子，不混入瓶颈维度）。"""
    from strategies.trend_serenity import price_strength_multi_mode
    px = price_strength_multi_mode(close, codes, data_date)
    if "price_score" not in px.columns:
        return pd.Series(0.5, index=pd.Index(codes))
    score = px["price_score"].copy()
    # 映射到 [0, 1]
    score_mapped = score.clip(-1, 2) / 3 + 0.33
    return score_mapped.fillna(0.5)


def compute_theme_enhancement(
    pool: pd.DataFrame,
    close: pd.DataFrame,
    data_date: pd.Timestamp,
    theme_weight: float = 0.18,
) -> pd.DataFrame:
    """
    Point-in-time 景气主题增强。

    只使用 data_date 及之前的价格数据，静态行业关键词只限定可增强主题范围；
    真正加分来自当期行业热度、个股动量和财务景气。
    """
    if pool is None or pool.empty:
        return pool

    df = pool.copy()
    codes = [c for c in df["code"].astype(str).str.lower().tolist() if c in close.columns]
    if not codes:
        df["serenity_score_v2_base"] = df["serenity_score_v2"]
        df["theme_bucket"] = ""
        df["theme_exposure"] = 0.0
        df["theme_score"] = 0.0
        df["theme_boost"] = 0.0
        return df

    hist = close.loc[:data_date, codes].tail(121)
    latest = hist.iloc[-1] if not hist.empty else pd.Series(dtype=float)

    def period_ret(days: int) -> pd.Series:
        if len(hist) <= days:
            return pd.Series(np.nan, index=codes)
        return latest / hist.iloc[-days - 1] - 1

    ret20 = period_ret(20)
    ret60 = period_ret(60)
    ret120 = period_ret(120)
    ma60 = hist.tail(60).mean() if len(hist) >= 20 else latest
    above_ma60 = (latest > ma60).astype(float).reindex(codes)

    mom = (
        0.25 * ret20.rank(pct=True).fillna(0.5)
        + 0.45 * ret60.rank(pct=True).fillna(0.5)
        + 0.30 * ret120.rank(pct=True).fillna(0.5)
    )
    mom.name = "stock_theme_momentum"

    market = pd.DataFrame({
        "code": codes,
        "ret60": ret60.reindex(codes).values,
        "ret120": ret120.reindex(codes).values,
        "above_ma60": above_ma60.reindex(codes).values,
    })
    industry_map = df.set_index("code")["industry_name"]
    market["industry_name"] = market["code"].map(industry_map)
    ind = market.groupby("industry_name").agg(
        industry_ret60=("ret60", "mean"),
        industry_ret120=("ret120", "mean"),
        industry_breadth=("above_ma60", "mean"),
        industry_size=("code", "count"),
    )
    ind["industry_heat"] = (
        0.45 * ind["industry_ret60"].rank(pct=True).fillna(0.5)
        + 0.25 * ind["industry_ret120"].rank(pct=True).fillna(0.5)
        + 0.30 * ind["industry_breadth"].rank(pct=True).fillna(0.5)
    )
    ind.loc[ind["industry_size"] < 3, "industry_heat"] = 0.5

    df["serenity_score_v2_base"] = df["serenity_score_v2"]
    df["theme_bucket"] = df["industry_name"].apply(_theme_bucket)
    df["theme_exposure"] = (df["theme_bucket"] != "").astype(float)
    df["industry_heat"] = df["industry_name"].map(ind["industry_heat"]).fillna(0.5)
    df["stock_theme_momentum"] = df["code"].map(mom).fillna(0.5)

    financial_heat = (
        0.60 * pd.to_numeric(df.get("q_sales_yoy"), errors="coerce").rank(pct=True).fillna(0.5)
        + 0.40 * pd.to_numeric(df.get("sales_accel"), errors="coerce").rank(pct=True).fillna(0.5)
    )
    df["theme_score"] = (
        0.40 * df["industry_heat"]
        + 0.35 * df["stock_theme_momentum"]
        + 0.25 * financial_heat
    ).clip(0, 1)
    df["theme_boost"] = theme_weight * df["theme_exposure"] * df["theme_score"]
    df["serenity_score_v2"] = df["serenity_score_v2"] + df["theme_boost"]
    return df


# ═══════════════════════════════════════════════════════════════
# V2 因子构建
# ═══════════════════════════════════════════════════════════════

def compute_serenity_v2(
    data: FundamentalCache,
    enrich: EnrichmentCache | None,
    close: pd.DataFrame,
    universe: list[str],
    data_date: pd.Timestamp,
    industry_neutral: bool = False,
) -> pd.DataFrame | None:
    """
    计算 Serenity V2 因子分数。

    参数:
      industry_neutral: True = 行业内分位数, False = 全市场分位数

    返回 DataFrame: code, serenity_score_v2, bottleneck_ind, financial_ind,
                     reflexivity_ind, trend_confirm, valuation_penalty,
                     及各子因子分解
    """
    # 获取基础财务快照
    df = data.snapshot(universe, data_date)
    if df.empty:
        return None

    # 价格强度
    px = compute_trend_confirm(close, list(df["code"]), data_date)
    df = df.merge(pd.DataFrame({"trend_confirm": px}, index=pd.Index(list(df["code"]))
                               if isinstance(px, pd.Series) else px.index),
                   left_on="code", right_index=True, how="left")
    df["trend_confirm"] = df["trend_confirm"].fillna(0.5)

    # 财务字段标准化
    df["n_income_attr_p"] = pd.to_numeric(df.get("inc_n_income_attr_p"), errors="coerce")
    df["revenue"] = pd.to_numeric(df.get("inc_revenue"), errors="coerce").fillna(
        pd.to_numeric(df.get("inc_total_revenue"), errors="coerce"))
    df["q_sales_yoy"] = pd.to_numeric(df.get("fi_q_sales_yoy"), errors="coerce")
    df["q_profit_yoy"] = pd.to_numeric(df.get("fi_dt_netprofit_yoy"), errors="coerce").fillna(
        pd.to_numeric(df.get("fi_netprofit_yoy"), errors="coerce"))
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

    # 加速指标
    acc = compute_acceleration_metrics(data, list(df["code"]), data_date)
    if not acc.empty:
        df = df.merge(acc, on="code", how="left")

    # 衍生比率
    df["ocf_to_profit"] = df["ocf"] / df["n_income_attr_p"].replace(0, np.nan)
    df["rd_to_revenue"] = df["rd_exp"] / df["revenue"].replace(0, np.nan)
    df["inventory_to_revenue"] = df["inventories"] / df["revenue"].replace(0, np.nan)
    df["receivable_to_revenue"] = df["accounts_receiv"] / df["revenue"].replace(0, np.nan)
    df["contract_liab_to_revenue"] = df["contract_liab"] / df["revenue"].replace(0, np.nan)

    # 选择排名函数
    def rk(col, asc=True):
        if industry_neutral:
            return safe_industry_rank(df, col, ascending=asc)
        else:
            return df[col].rank(ascending=asc, pct=True).clip(0, 1).fillna(0.5)

    # ══ 瓶颈真实性（行业内分位） ══
    df["bottleneck_ind"] = (
        0.30 * rk("gross_margin", True)
        + 0.20 * rk("rd_to_revenue", True)
        + 0.20 * rk("contract_liab_to_revenue", True)
        + 0.15 * rk("roe", True)
        + 0.15 * rk("sales_accel", True)
    )

    # ══ 财务兑现（行业内分位 + 加速） ══
    df["financial_ind"] = (
        0.25 * rk("q_sales_yoy", True)
        + 0.20 * rk("q_profit_yoy", True)
        + 0.15 * rk("net_margin", True)
        + 0.15 * rk("ocf_to_profit", True)
        + 0.15 * rk("sales_accel", True)
        + 0.10 * rk("margin_change_yoy", True)
    )

    # ══ 反身性风险控制（行业内分位） ══
    df["reflexivity_ind"] = (
        0.25 * rk("debt_to_assets", False)
        + 0.25 * rk("inventory_to_revenue", False)
        + 0.20 * rk("receivable_to_revenue", False)
        + 0.15 * rk("turnover_rate", False)
        + 0.15 * rk("debt_change_yoy", True)
    )

    # ══ 估值惩罚 ══
    df["valuation_penalty"] = compute_valuation_penalty(df)

    # ══ V2 总分 ══
    df["serenity_score_v2"] = (
        0.40 * df["bottleneck_ind"]
        + 0.30 * df["financial_ind"]
        + 0.15 * df["reflexivity_ind"]
        + 0.15 * df["trend_confirm"]
        - df["valuation_penalty"]
    )

    # ══ 瓶颈分解 (P3) ══
    df["bottleneck_sub_gm"] = rk("gross_margin", True)
    df["bottleneck_sub_rd"] = rk("rd_to_revenue", True)
    df["bottleneck_sub_cl"] = rk("contract_liab_to_revenue", True)
    df["bottleneck_sub_roe"] = rk("roe", True)
    df["bottleneck_sub_accel"] = rk("sales_accel", True)
    # 与 V1 对比：不含价格强度的纯基本面瓶颈
    df["bottleneck_pure"] = (
        0.35 * df["bottleneck_sub_gm"]
        + 0.25 * df["bottleneck_sub_rd"]
        + 0.25 * df["bottleneck_sub_cl"]
        + 0.15 * df["bottleneck_sub_roe"]
    )

    # 过滤无效数据
    raw_code = df["code"].str[2:]
    name = df["name"].fillna("")
    df["list_days"] = (data_date - pd.to_datetime(df["list_date"].astype(str), errors="coerce")).dt.days
    sanity = (
        (df["list_days"] >= 250)
        & ~raw_code.str.startswith(("688", "689", "4", "8"))
        & ~name.str.contains("ST|退|\\*", regex=True)
        & (df["n_income_attr_p"] > 0)
        & (df["pe_ttm"].fillna(100) > 0)
        & (df["pb"].fillna(1) > 0)
    )
    df = df[sanity].copy()

    return df[["code", "serenity_score_v2", "bottleneck_ind", "financial_ind",
               "reflexivity_ind", "trend_confirm", "valuation_penalty",
               "bottleneck_sub_gm", "bottleneck_sub_rd", "bottleneck_sub_cl",
               "bottleneck_sub_roe", "bottleneck_sub_accel", "bottleneck_pure",
               "industry_name", "name"] + [c for c in df.columns if c in [
               "q_sales_yoy", "gross_margin", "pe_ttm", "pb", "roe",
               "sales_accel", "profit_accel", "margin_change_yoy"]]]


# ═══════════════════════════════════════════════════════════════
# 组合 Buffer 机制 (P5)
# ═══════════════════════════════════════════════════════════════

def apply_portfolio_buffer(
    current_holdings: set[str],
    new_candidates: pd.DataFrame,
    buy_top_n: int = 15,
    hold_threshold_n: int = 30,
) -> List[str]:
    """
    Buffer 组合管理:
      - 买入: 从候选池选 Top buy_top_n
      - 持有: 当前持仓只要排名在 hold_threshold_n 以内就保留
      - 卖出: 排名跌出 hold_threshold_n → 清仓

    返回: 调整后的目标持仓列表
    """
    if new_candidates.empty:
        return list(current_holdings)

    ranked = new_candidates.sort_values("serenity_score_v2", ascending=False)
    ranked["_rank"] = range(1, len(ranked) + 1)

    # 新买入池
    buy_pool = ranked.head(buy_top_n)
    buy_codes = set(buy_pool["code"])

    # 保留池：当前持仓中仍在 Top hold_threshold_n 的
    keep_pool = ranked.head(hold_threshold_n)
    keep_codes = set(keep_pool["code"])

    # 最终持仓：买入池 ∪ (当前持仓 ∩ 保留池)
    final = buy_codes | (current_holdings & keep_codes)

    return list(final)


def select_serenity_v2_targets(
    pool: pd.DataFrame,
    current_holdings: set[str] | None = None,
    target_num: int = 10,
    buy_top_n: int = 15,
    hold_threshold_n: int = 30,
    max_per_industry: int = 3,
) -> List[str]:
    """Select V2 targets with industry caps and optional holding buffer."""
    if pool is None or pool.empty:
        return []

    ranked = pool.sort_values("serenity_score_v2", ascending=False).copy()
    current_holdings = current_holdings or set()

    def industry_capped(candidates: pd.DataFrame, limit: int | None = None) -> list[str]:
        selected: list[str] = []
        industry_count: dict[str, int] = {}
        for _, row in candidates.iterrows():
            industry = row.get("industry_name", "UNKNOWN")
            if industry_count.get(industry, 0) >= max_per_industry:
                continue
            selected.append(row["code"])
            industry_count[industry] = industry_count.get(industry, 0) + 1
            if limit is not None and len(selected) >= limit:
                break
        return selected

    buy_codes = set(industry_capped(ranked, buy_top_n))
    keep_codes = set(ranked.head(hold_threshold_n)["code"]) if hold_threshold_n > 0 else set()
    buffered = buy_codes | (current_holdings & keep_codes)

    final_ranked = ranked[ranked["code"].isin(buffered)]
    return industry_capped(final_ranked, max(target_num, len(current_holdings & keep_codes)))
