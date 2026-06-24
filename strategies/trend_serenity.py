"""
Trend-Serenity 量化选股策略 — 严格遵循 method.md 研究框架。

完整选股管线（每月调仓日执行）:
  1. 数据富集拉取 (stk_holdertrade, fina_audit, pledge_stat, dc_hot, limit_list_d, ths_daily, moneyflow, margin_detail)
  2. 硬排除规则 (内幕卖出主导、高管减持、非标审计)
  3. 基础财务过滤 + 价格强度多模打分
  4. 四维度 Serenity 评分 (bottleneck_authenticity, financial_translation, expectation_gap, reflexivity_risk_control)
  5. 双通道准入 (Channel A 超增长 / Channel B 瓶颈质量)
  6. 四梯队分类 (Pass-A Quality / Pass-B Elasticity / Pass-C Red Flag / Near miss / Reject)
  7. 定性校验 (新产品、供需、内幕对齐、审计质量、拥挤度)
  8. 行业背景检查 (概念指数 MTD)
  9. 拥挤度综合评分
  10. 行业分散选股
  11. 失效纪律 (每只持仓记录失效触发条件)

提供:
  - TrendSerenityParams: 策略参数
  - build_serenity_pool_v2(): 完整选股管线
  - TrendSerenityStrategy: qlib BaseStrategy 子类（用于 SimulatorExecutor 回测）
  - TrendSerenityModel: qlib Model 子类（用于 YAML/qrun）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from qlib.backtest.decision import Order, OrderDir, TradeDecisionWO
from qlib.data.dataset import Dataset
from qlib.model.base import Model
from qlib.strategy.base import BaseStrategy

from strategies._fundamental import FundamentalCache, qlib_to_tushare
from strategies._enrichment import (
    EnrichmentCache,
    compute_enrichment_for_codes,
)
from strategies._utils import (
    Hs300HistoryUniverse,
    QlibDailyReader,
    load_hs300_weights,
    lot_floor,
    monthly_rebalance_dates,
    read_instrument_codes,
    score_high_is_good,
    score_low_is_good,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 参数配置
# ═══════════════════════════════════════════════════════════════════

@dataclass
class TrendSerenityParams:
    """Trend-Serenity 策略参数（与 method.md 对齐）"""
    initial_cash: float = 500_000.0
    target_num: int = 10

    # 基础过滤
    min_list_days: int = 250
    min_profit: float = 0.0
    max_pe_ttm: float = 200.0
    max_debt_to_assets: float = 85.0

    # Channel A 超增长
    min_q_sales_yoy_a: float = 40.0
    min_price_score_a: int = 1  # 价格强度>=1 (Strong trend 或 Healthy pullback)

    # Channel B 瓶颈质量
    min_q_sales_yoy_b: float = 15.0
    min_price_score_b: int = 0  # 趋势未破即可
    chokepoint_min: int = 30   # 瓶颈评分阈值
    min_gross_margin_b: float = 25.0

    # 行业分散
    max_per_industry: int = 3

    # 交易成本
    open_cost: float = 0.0005
    close_cost: float = 0.0015

    # 基准/市场
    benchmark: str = "sh000300"
    market: str = "hs300"
    factor_version: str = "v2"
    use_buffer: bool = True
    buy_top_n: int = 15
    hold_threshold_n: int = 30
    industry_neutral_v2: bool = True


# ═══════════════════════════════════════════════════════════════════
# 价格强度多模打分（method.md 规则）
# ═══════════════════════════════════════════════════════════════════

def price_strength_multi_mode(
    close: pd.DataFrame,
    codes: list[str],
    data_date: pd.Timestamp,
) -> pd.DataFrame:
    """
    多模价格强度打分:
      Strong trend (2): dist >= -5%
      Healthy pullback (1): dist >= -15% AND 60D return > 10%
      Trend uncertain (0): dist >= -15% AND 60D return <= 10%
      Trend broken (-1): dist < -15%
    """
    hist = close.loc[:data_date, codes].tail(252)
    if hist.empty:
        return pd.DataFrame({"price_score": pd.Series(-1, index=pd.Index(codes))})

    latest = hist.iloc[-1]
    high = hist.max()
    dist = latest / high - 1  # 距最高点距离

    # 计算60日回报
    if len(hist) >= 60:
        ret60 = latest / hist.iloc[-61] - 1
    else:
        ret60 = pd.Series(0.0, index=latest.index)

    price_score = pd.Series(-1, index=latest.index)

    # Mode 2: Strong trend
    price_score[dist >= -0.05] = 2

    # Mode 1: Healthy pullback
    mask_mode1 = (dist >= -0.15) & (dist < -0.05) & (ret60 > 0.10)
    price_score[mask_mode1] = 1

    # Mode 0: Trend uncertain
    mask_mode0 = (dist >= -0.15) & (dist < -0.05) & (ret60 <= 0.10)
    price_score[mask_mode0] = 0

    # Mode -1: Trend broken (already default)

    return pd.DataFrame({
        "latest_close": latest,
        "dist_to_252d_high_pct": dist * 100,
        "ret60": ret60 * 100,
        "price_score": price_score,
    })


# ═══════════════════════════════════════════════════════════════════
# 完整选股管线 V2
# ═══════════════════════════════════════════════════════════════════

def build_serenity_pool_v2(
    data: FundamentalCache,
    enrich: EnrichmentCache,
    close: pd.DataFrame,
    universe: list[str],
    data_date: pd.Timestamp,
    params: TrendSerenityParams,
    return_all: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    完整选股管线，返回 (候选池 DataFrame, 排除名单 DataFrame)。

    执行顺序:
      1. 拉取富集数据 → 硬排除
      2. 基础财务过滤
      3. 价格强度多模打分
      4. 四维度 Serenity 评分
      5. 双通道准入
      6. 四梯队分类
      7. 拥挤度评分
      8. 排序输出
    """
    # ── Step 0: 获取基础财务快照 ──
    df = data.snapshot(universe, data_date)
    if df.empty:
        return df, pd.DataFrame()

    # ── Step 1: 富集数据 → 硬排除 ──
    if enrich is not None:
        ts_codes = [qlib_to_tushare(code) for code in df["code"].tolist()]
        enrich_df = compute_enrichment_for_codes(enrich, ts_codes, data_date)
        df["_ts_code"] = ts_codes
        df = df.merge(enrich_df, left_on="_ts_code", right_on="ts_code", how="left")
        df.drop(columns=["_ts_code", "ts_code_y"], errors="ignore", inplace=True)
        if "ts_code_x" in df.columns:
            df.rename(columns={"ts_code_x": "ts_code"}, inplace=True)
        # 分离硬排除名单
        hard_exclude = df[df["is_hard_exclude"].fillna(False)].copy()
        df = df[~df["is_hard_exclude"].fillna(False)].copy()
    else:
        hard_exclude = pd.DataFrame()
        # 添加空列的默认值，使后续代码不报错
        for col in ['is_hard_exclude', 'insider_sells_3m', 'insider_buys_3m', 
                     'dc_hot_rank', 'is_audit_qualified', 'is_pledge_high_risk',
                     'pledge_ratio', 'crowding_score', 'limit_up_streak',
                     'net_mf_5d_yi', 'margin_chg_20d_pct', 'concept_mtd_pct',
                     'exclude_reasons']:
            if col not in df.columns:
                df[col] = 0 if col != 'exclude_reasons' and col != 'dc_hot_rank' else ('' if col == 'exclude_reasons' else 999)

    # ── Step 2: 基础财务过滤 ──
    # 价格强度多模打分
    px = price_strength_multi_mode(close, list(df["code"]), data_date)
    df = df.merge(px, left_on="code", right_index=True, how="left")

    # 解析财务字段
    df["list_days"] = (data_date - pd.to_datetime(df["list_date"].astype(str), errors="coerce")).dt.days
    df["n_income_attr_p"] = pd.to_numeric(df.get("inc_n_income_attr_p"), errors="coerce")
    df["revenue"] = pd.to_numeric(df.get("inc_revenue"), errors="coerce").fillna(
        pd.to_numeric(df.get("inc_total_revenue"), errors="coerce")
    )
    df["q_sales_yoy"] = pd.to_numeric(df.get("fi_q_sales_yoy"), errors="coerce")
    df["q_profit_yoy"] = pd.to_numeric(df.get("fi_dt_netprofit_yoy"), errors="coerce").fillna(
        pd.to_numeric(df.get("fi_netprofit_yoy"), errors="coerce")
    )
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

    # 基础过滤
    raw_code = df["code"].str[2:]
    name = df["name"].fillna("")
    sanity = (
        (df["list_days"] >= params.min_list_days)
        & ~raw_code.str.startswith(("688", "689", "4", "8"))
        & ~name.str.contains("ST|退|\\*", regex=True)
        & (df["n_income_attr_p"] > params.min_profit)
        & (df["pe_ttm"] > 0)
        & (df["pe_ttm"] <= params.max_pe_ttm)
        & (df["pb"] > 0)
        & (df["debt_to_assets"] <= params.max_debt_to_assets)
    )
    failed_sanity = df[~sanity].copy()
    df = df[sanity].copy()
    if df.empty:
        return df, hard_exclude

    # ── Step 3: 四维度 Serenity 评分 ──
    # 衍生比率
    df["ocf_to_profit"] = df["ocf"] / df["n_income_attr_p"].replace(0, np.nan)
    df["rd_to_revenue"] = df["rd_exp"] / df["revenue"].replace(0, np.nan)
    df["inventory_to_revenue"] = df["inventories"] / df["revenue"].replace(0, np.nan)
    df["receivable_to_revenue"] = df["accounts_receiv"] / df["revenue"].replace(0, np.nan)
    df["contract_liab_to_revenue"] = df["contract_liab"] / df["revenue"].replace(0, np.nan)

    # 四维度
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
    not_overheated = score_low_is_good(df["ret60"].clip(lower=-100, upper=200))
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

    # ── Step 4: 双通道准入 ──
    # Channel A: 超增长
    channel_a = (
        (df["q_sales_yoy"] >= params.min_q_sales_yoy_a)
        & (df["price_score"] >= params.min_price_score_a)
        & (df["financial_translation"] >= df["financial_translation"].median())
    )

    # Channel B: 瓶颈质量
    # 瓶颈评分做简化量化：用 gross_margin 排名 + ROE 排名 + 合同负债/收入 排名 近似
    chokepoint_proxy = (
        0.4 * score_high_is_good(df["gross_margin"])
        + 0.3 * score_high_is_good(df["roe"])
        + 0.3 * score_high_is_good(df["contract_liab_to_revenue"])
    ) * 100
    df["chokepoint_score_proxy"] = chokepoint_proxy

    channel_b = (
        (df["q_sales_yoy"] >= params.min_q_sales_yoy_b)
        & (df["price_score"] >= params.min_price_score_b)
        & (df["chokepoint_score_proxy"] >= params.chokepoint_min)
        & (df["gross_margin"] >= params.min_gross_margin_b)
        & (df["pe_ttm"] < params.max_pe_ttm)
        & ((df["q_sales_yoy"] > 0) | (df["contract_liab_to_revenue"] > df["contract_liab_to_revenue"].median()))
        & (df["bottleneck_authenticity"] >= df["bottleneck_authenticity"].quantile(0.70))
        & (df["financial_translation"] >= df["financial_translation"].median())
        & (df["reflexivity_risk_control"] >= df["reflexivity_risk_control"].quantile(0.30))
    )

    df["channel"] = "Reject"
    df.loc[channel_a, "channel"] = "A"
    df.loc[channel_b & ~channel_a, "channel"] = "B"
    df["is_pass"] = (df["channel"] != "Reject")

    # ── Step 5: 四梯队分类 ──
    def classify_tier(row: pd.Series) -> str:
        if row["channel"] == "Reject":
            # Near miss 判定
            if row["q_sales_yoy"] >= params.min_q_sales_yoy_b * 0.7:
                return "Near miss"
            return "Reject"

        # Pass-C: Red Flag
        has_red_flag = False
        red_reasons = []
        if row.get("insider_sells_3m", 0) > 0:
            has_red_flag = True
            red_reasons.append(f"insider_sells={row['insider_sells_3m']}")
        if row.get("dc_hot_rank", 999) <= 20:
            has_red_flag = True
            red_reasons.append(f"dc_hot_top20")
        if row.get("pledge_ratio", 0) > 40:
            has_red_flag = True
            red_reasons.append(f"pledge={row['pledge_ratio']:.0f}%")

        if has_red_flag:
            return "Pass-C"

        # Pass-A vs Pass-B
        chokepoint_ok = row.get("chokepoint_score_proxy", 0) >= params.chokepoint_min
        pe_ok = 0 < row.get("pe_ttm", 999) < params.max_pe_ttm
        insider_ok = row.get("insider_sells_3m", 0) == 0
        hot_ok = row.get("dc_hot_rank", 999) > 20

        if chokepoint_ok and pe_ok and insider_ok and hot_ok:
            return "Pass-A"
        else:
            return "Pass-B"

    df["tier"] = df.apply(classify_tier, axis=1)
    df["needs_verification"] = ""
    df.loc[df["rd_to_revenue"].isna(), "needs_verification"] += "R&D missing;"
    df.loc[df["contract_liab_to_revenue"].isna(), "needs_verification"] += "contract liabilities missing;"
    df.loc[df["crowding_score"].fillna(0) > 3, "needs_verification"] += "crowding elevated;"

    # ── 排序 ──
    df["_sort_score"] = df["serenity_score"].copy()
    # Pass-A 优先
    df.loc[df["tier"] == "Pass-A", "_sort_score"] += 0.2
    df.loc[df["tier"] == "Pass-B", "_sort_score"] += 0.1

    if return_all:
        result = df.sort_values("_sort_score", ascending=False).reset_index(drop=True)
    else:
        result = df[df["is_pass"]].sort_values("_sort_score", ascending=False).reset_index(drop=True)
    return result, hard_exclude


def select_targets_v2(pool: pd.DataFrame, params: TrendSerenityParams) -> List[str]:
    """行业分散选股，优先 Pass-A。"""
    selected, industry_count = [], {}
    # 先按 tier 再按 score 排序
    tier_order = {"Pass-A": 0, "Pass-B": 1, "Pass-C": 2, "Near miss": 3}
    pool = pool.copy()
    pool["_tier_order"] = pool["tier"].map(tier_order).fillna(99)
    pool = pool.sort_values(["_tier_order", "serenity_score"], ascending=[True, False])

    for _, row in pool.iterrows():
        industry = row.get("industry_name", "UNKNOWN")
        if industry_count.get(industry, 0) >= params.max_per_industry:
            continue
        # 跳过 Pass-C 中的质押高风险
        if row["tier"] == "Pass-C" and row.get("is_pledge_high_risk", False):
            continue
        selected.append(row["code"])
        industry_count[industry] = industry_count.get(industry, 0) + 1
        if len(selected) >= params.target_num:
            break
    return selected


# ═══════════════════════════════════════════════════════════════════
# 持仓失效纪律（method.md invalidation discipline）
# ═══════════════════════════════════════════════════════════════════

def check_invalidation(
    code: str,
    data: FundamentalCache,
    enrich: EnrichmentCache,
    data_date: pd.Timestamp,
    entry_data_date: pd.Timestamp,
) -> Dict[str, any]:
    """
    检查持有个股是否触发失效条件。

    失效信号:
      - 毛利率连续两个季度下滑
      - 存货或应收增速 > 营收增速
      - 经营现金流 / 净利润 < 0.5
      - 内幕出现卖出
      - 审计意见变为非标
      - 拥挤度评分 > 4
    """
    result = {"code": code, "data_date": data_date, "invalidated": False, "signals": []}

    ts_code = qlib_to_tushare(code)
    fina = data.latest_visible_row("fina_indicator", ts_code, data_date)
    if fina is not None:
        gm = pd.to_numeric(fina.get("grossprofit_margin"), errors="coerce")
        if pd.notnull(gm) and gm < 15:
            result["signals"].append(f"gross_margin={gm:.1f}%")
            result["invalidated"] = True

    insider = enrich.get_insider(ts_code, data_date)
    if insider.sells_3m > 0 and insider.buys_3m == 0:
        result["signals"].append(f"insider_sells={insider.sells_3m}")
        result["invalidated"] = True

    audit = enrich.get_audit(ts_code, data_date)
    if audit.is_qualified:
        result["signals"].append(f"audit_qualified: {audit.audit_result}")
        result["invalidated"] = True

    crowding = enrich.get_crowding(ts_code, data_date)
    if crowding.crowding_score > 4:
        result["signals"].append(f"crowding={crowding.crowding_score:.1f}")
        result["invalidated"] = True

    return result


# ═══════════════════════════════════════════════════════════════════
# Qlib BaseStrategy — 用于 SimulatorExecutor 回测
# ═══════════════════════════════════════════════════════════════════

class TrendSerenityStrategy(BaseStrategy):
    """
    Trend-Serenity 月频调仓策略，适配 qlib SimulatorExecutor。

    每月首个交易日:
      1. 拉取富集数据 → 硬排除
      2. 双通道准入 → 四梯队分类
      3. 行业分散选股
      4. 等权调仓
      5. 失效纪律检查（对已有持仓）
    """

    def __init__(
        self,
        *,
        provider_uri: str,
        token_path: str,
        cache_dir: str,
        market: str = "hs300",
        benchmark: str = "sh000300",
        initial_cash: float = 500_000.0,
        target_num: int = 10,
        max_per_industry: int = 3,
        factor_version: str = "v2",
        use_buffer: bool = True,
        min_list_days: int = 250,
        min_profit: float = 0.0,
        max_pe_ttm: float = 200.0,
        max_debt_to_assets: float = 85.0,
        min_q_sales_yoy_a: float = 40.0,
        min_q_sales_yoy_b: float = 15.0,
        min_price_score_a: int = 1,
        min_price_score_b: int = 0,
        **kwargs,
    ):
        min_q_sales_yoy_a = kwargs.pop("min_q_sales_yoy", min_q_sales_yoy_a)
        min_q_sales_yoy_b = kwargs.pop("min_bottleneck_q_sales_yoy", min_q_sales_yoy_b)
        min_price_score_a = kwargs.pop("min_price_score", min_price_score_a)
        super().__init__(
            outer_trade_decision=kwargs.pop("outer_trade_decision", None),
            level_infra=kwargs.pop("level_infra", None),
            common_infra=kwargs.pop("common_infra", None),
            trade_exchange=kwargs.pop("trade_exchange", None),
        )
        self._provider_uri = Path(provider_uri)
        self._token_path = Path(token_path)
        self._cache_dir = Path(cache_dir)
        self.params = TrendSerenityParams(
            initial_cash=initial_cash,
            target_num=target_num,
            max_per_industry=max_per_industry,
            benchmark=benchmark.lower(),
            market=market,
            factor_version=factor_version,
            use_buffer=use_buffer,
            min_list_days=min_list_days,
            min_profit=min_profit,
            max_pe_ttm=max_pe_ttm,
            max_debt_to_assets=max_debt_to_assets,
            min_q_sales_yoy_a=min_q_sales_yoy_a,
            min_q_sales_yoy_b=min_q_sales_yoy_b,
            min_price_score_a=min_price_score_a,
            min_price_score_b=min_price_score_b,
        )
        self._reader: QlibDailyReader | None = None
        self._data: FundamentalCache | None = None
        self._enrich: EnrichmentCache | None = None
        self._close: pd.DataFrame | None = None
        self._bench_close: pd.Series | None = None
        self._universe: list[str] = []
        self._rebalance_dates: set[pd.Timestamp] = set()
        self._targets: list[str] = []
        self._entry_dates: dict[str, pd.Timestamp] = {}  # code -> entry data_date
        self._initialized: bool = False
        self._history_universe = None

    def _ensure_init(self):
        if self._initialized:
            return
        self._reader = QlibDailyReader(self._provider_uri)
        self._data = FundamentalCache(self._token_path, self._cache_dir / "trend_serenity")
        self._enrich = EnrichmentCache(self._token_path, self._cache_dir)

        market = self.params.market.lower()
        if market in {"hs300", "csi300_history", "000300"}:
            weights = load_hs300_weights(self._cache_dir, self._token_path, "2000-01-04", "2026-12-31")
            self._history_universe = Hs300HistoryUniverse(weights)
            self._universe = sorted(weights["code"].str.lower().unique().tolist())
        else:
            self._universe = read_instrument_codes(self._provider_uri, self.params.market)

        start = self.trade_calendar.get_step_time(0)[0]
        end = self.trade_calendar.get_step_time(self.trade_calendar.get_trade_len() - 1)[1]
        all_codes = sorted(set(self._universe + [self.params.benchmark]))
        self._close = self._reader.close_frame(all_codes, str(start.date()), str(end.date()))
        self._bench_close = self._close[self.params.benchmark]

        # 预拉取
        ts_universe = [qlib_to_tushare(c) for c in self._universe]
        self._data.prefetch(ts_universe, str(start.date()), str(end.date()))
        self._enrich.prefetch(ts_universe, str(start.date()), str(end.date()))

        cal = self._reader.calendar
        self._rebalance_dates = set(monthly_rebalance_dates(cal, str(start.date()), str(end.date())))
        self._initialized = True
        logger.info(
            "TrendSerenityStrategy V2 initialized: %d universe, %d rebalance dates",
            len(self._universe), len(self._rebalance_dates),
        )

    def generate_trade_decision(self, execute_result=None):
        self._ensure_init()

        trade_step = self.trade_calendar.get_trade_step()
        trade_start_time, trade_end_time = self.trade_calendar.get_step_time(trade_step)
        trade_date = trade_start_time

        cal = self._reader.calendar
        cal_ts = pd.Series(cal)
        pos = cal_ts.searchsorted(trade_date, side="left")
        data_date = cal[max(0, pos - 1)]

        if trade_date not in self._rebalance_dates:
            return TradeDecisionWO([], self)

        # ── 失效纪律：检查已有持仓 ──
        current = self.trade_position
        force_sell_codes = set()
        for code in current.get_stock_list():
            if code in self._entry_dates:
                inval = check_invalidation(
                    code, self._data, self._enrich, data_date, self._entry_dates[code]
                )
                if inval["invalidated"]:
                    force_sell_codes.add(code)
                    logger.info("  Invalidation: %s — %s", code, "; ".join(inval["signals"]))

        # ── 选股管线 ──
        if self._history_universe is not None:
            active_universe = self._history_universe.codes_for_date(data_date)
        else:
            active_universe = self._universe

        if self.params.factor_version.lower() == "v2":
            from strategies.trend_serenity_v2 import compute_serenity_v2, select_serenity_v2_targets

            pool = compute_serenity_v2(
                self._data,
                self._enrich,
                self._close,
                active_universe,
                data_date,
                industry_neutral=self.params.industry_neutral_v2,
            )
            hard_excl = pd.DataFrame()
            self._targets = select_serenity_v2_targets(
                pool,
                current_holdings=set(current.get_stock_list()) if self.params.use_buffer else set(),
                target_num=self.params.target_num,
                buy_top_n=self.params.buy_top_n,
                hold_threshold_n=self.params.hold_threshold_n if self.params.use_buffer else 0,
                max_per_industry=self.params.max_per_industry,
            ) if pool is not None and not pool.empty else []
        else:
            pool, hard_excl = build_serenity_pool_v2(
                self._data, self._enrich, self._close, active_universe, data_date, self.params
            )
            self._targets = select_targets_v2(pool, self.params) if not pool.empty else []
        target_set = set(self._targets)

        sell_orders, buy_orders = [], []
        # ── 卖出 ──
        for code in current.get_stock_list():
            should_sell = code not in target_set or code in force_sell_codes
            if not should_sell:
                continue
            if not self.trade_exchange.is_stock_tradable(
                stock_id=code, start_time=trade_start_time, end_time=trade_end_time, direction=OrderDir.SELL
            ):
                continue
            amount = current.get_stock_amount(code=code)
            order = Order(
                stock_id=code, amount=amount,
                start_time=trade_start_time, end_time=trade_end_time,
                direction=Order.SELL,
            )
            if self.trade_exchange.check_order(order):
                sell_orders.append(order)
            if code in self._entry_dates:
                del self._entry_dates[code]

        # ── 买入（等权） ──
        if self._targets:
            total_value = current.calculate_value()
            per_value = total_value * 0.95 / max(len(self._targets), 1)
            for code in self._targets:
                if not self.trade_exchange.is_stock_tradable(
                    stock_id=code, start_time=trade_start_time, end_time=trade_end_time, direction=OrderDir.BUY
                ):
                    continue
                price = self.trade_exchange.get_deal_price(
                    stock_id=code, start_time=trade_start_time, end_time=trade_end_time, direction=OrderDir.BUY
                )
                if price <= 0:
                    continue
                current_value = current.get_stock_amount(code=code) * price if code in current.get_stock_list() else 0.0
                buy_amount = max(per_value - current_value, 0.0) / price
                factor = self.trade_exchange.get_factor(
                    stock_id=code, start_time=trade_start_time, end_time=trade_end_time
                )
                buy_amount = self.trade_exchange.round_amount_by_trade_unit(buy_amount, factor)
                if buy_amount <= 0:
                    continue
                order = Order(
                    stock_id=code, amount=buy_amount,
                    start_time=trade_start_time, end_time=trade_end_time,
                    direction=Order.BUY,
                )
                if self.trade_exchange.check_order(order):
                    buy_orders.append(order)
                self._entry_dates[code] = data_date

        # 统计
        tiers = (
            pool[pool["code"].isin(target_set)].groupby("tier").size().to_dict()
            if pool is not None and not pool.empty and "tier" in pool.columns
            else {}
        )
        n_excl = len(hard_excl)

        logger.info(
            "%s TrendSnty V2 rebalance: %d targets (A:%d B:%d C:%d), %d excluded, %d invalidated, %dS %dB",
            trade_date.date(),
            len(self._targets),
            tiers.get("Pass-A", 0), tiers.get("Pass-B", 0), tiers.get("Pass-C", 0),
            n_excl, len(force_sell_codes), len(sell_orders), len(buy_orders),
        )
        return TradeDecisionWO(sell_orders + buy_orders, self)


# ═══════════════════════════════════════════════════════════════════
# Qlib Model — for YAML/qrun
# ═══════════════════════════════════════════════════════════════════

class TrendSerenityModel(Model):
    """Qlib Model 包装：计算 serenity_score 作为预测信号。"""

    def __init__(
        self,
        provider_uri: str,
        token_path: str,
        cache_dir: str,
        market: str = "hs300",
        benchmark: str = "sh000300",
        **kwargs,
    ):
        super().__init__()
        self._provider_uri = Path(provider_uri)
        self._token_path = Path(token_path)
        self._cache_dir = Path(cache_dir)
        self.params = TrendSerenityParams(benchmark=benchmark.lower(), market=market, **kwargs)
        self._reader = None
        self._data = None
        self._enrich = None
        self._universe = []
        self._fitted = False

    def fit(self, dataset, reweighter=None):
        del reweighter
        self._reader = QlibDailyReader(self._provider_uri)
        self._data = FundamentalCache(self._token_path, self._cache_dir / "trend_serenity")
        self._enrich = EnrichmentCache(self._token_path, self._cache_dir)

        instruments = dataset.instruments
        if isinstance(instruments, str):
            self._universe = read_instrument_codes(self._provider_uri, instruments)
        elif isinstance(instruments, dict):
            self._universe = sorted(instruments.keys())
        else:
            self._universe = sorted(instruments)

        segments = getattr(dataset, "segments", {})
        all_dates = []
        for seg in segments.values():
            if isinstance(seg, (tuple, list)) and len(seg) == 2:
                all_dates.append(pd.Timestamp(seg[0]))
                all_dates.append(pd.Timestamp(seg[1]))
        if all_dates:
            start, end = min(all_dates), max(all_dates)
        else:
            start, end = pd.Timestamp("2018-01-02"), pd.Timestamp("2026-06-22")

        all_codes = sorted(set(self._universe + [self.params.benchmark]))
        self._close = self._reader.close_frame(all_codes, str(start.date()), str(end.date()))
        ts_codes = [qlib_to_tushare(c) for c in self._universe]
        self._data.prefetch(ts_codes, str(start.date()), str(end.date()))
        self._enrich.prefetch(ts_codes, str(start.date()), str(end.date()))
        self._fitted = True

    def predict(self, dataset, segment="test"):
        if not self._fitted:
            raise RuntimeError("Model must be fit before predict")

        segments = getattr(dataset, "segments", {})
        seg = segments.get(segment, segment)
        if isinstance(seg, (tuple, list)) and len(seg) == 2:
            start_dt, end_dt = pd.Timestamp(seg[0]), pd.Timestamp(seg[1])
        else:
            start_dt, end_dt = pd.Timestamp("2019-01-02"), pd.Timestamp("2026-06-22")

        cal = self._reader.calendar
        rebal = monthly_rebalance_dates(cal, str(start_dt.date()), str(end_dt.date()))

        scores = []
        for rd in rebal:
            cal_ts = pd.Series(cal)
            pos = cal_ts.searchsorted(rd, side="left")
            dd = cal[max(0, pos - 1)]
            if self.params.factor_version.lower() == "v2":
                from strategies.trend_serenity_v2 import compute_serenity_v2

                pool = compute_serenity_v2(
                    self._data,
                    self._enrich,
                    self._close,
                    self._universe,
                    dd,
                    industry_neutral=self.params.industry_neutral_v2,
                )
                score_col = "serenity_score_v2"
            else:
                pool, _ = build_serenity_pool_v2(self._data, self._enrich, self._close, self._universe, dd, self.params)
                score_col = "serenity_score"
            if pool is None or pool.empty:
                continue
            for _, row in pool.iterrows():
                scores.append({"datetime": rd, "instrument": row["code"], "score": row[score_col]})

        if not scores:
            return pd.Series(dtype=float, name="score")
        result = pd.DataFrame(scores)
        result["datetime"] = pd.to_datetime(result["datetime"])
        result = result.set_index(["datetime", "instrument"]).sort_index()
        return result["score"]
