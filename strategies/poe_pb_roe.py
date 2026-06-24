"""
POE PB+ROE monthly strategy — qlib-integrated.

Market-state-aware fundamental strategy:
  - STRONG: top-10 balanced PB+ROE, max 1 strong-cycle
  - WEAK + HIGH_DRAWDOWN: top-25 soft-value, rank-spread reorder
  - WEAK + MID_DRAWDOWN: top-25 balanced, rank-spread reorder
  - WEAK normal / NEUTRAL: top-10/12 balanced

Provides:
  - POEPBRoeParams: strategy parameters
  - build_base_dataframe(), pick_targets(): pure scoring/selection functions
  - POEPBRoeStrategy: qlib BaseStrategy subclass for SimulatorExecutor
  - POEPBRoeModel: qlib Model subclass for YAML/qrun + TopkDropoutStrategy
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from qlib.backtest.decision import Order, OrderDir, TradeDecisionWO
from qlib.data.dataset import Dataset
from qlib.model.base import Model
from qlib.strategy.base import BaseStrategy

from strategies._fundamental import FundamentalCache, qlib_to_tushare
from strategies._enrichment import EnrichmentCache, compute_enrichment_for_codes
from strategies._utils import (
    Hs300HistoryUniverse,
    QlibDailyReader,
    load_hs300_weights,
    market_state,
    monthly_rebalance_dates,
    read_instrument_codes,
)

logger = logging.getLogger(__name__)


@dataclass
class POEPBRoeParams:
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
    benchmark: str = "sh000300"
    market: str = "hs300"


# ═══════════════════════════════════════════════════════════════════
# Industry classification helpers
# ═══════════════════════════════════════════════════════════════════

def _contains_any(text, words):
    return any(w in str(text) for w in words)


def _is_strong_cycle(industry_name):
    return _contains_any(industry_name, ["煤炭", "采掘", "有色金属", "钢铁", "基础化工", "化工", "石油石化", "交通运输"])


def _is_real_estate(industry_name):
    return _contains_any(industry_name, ["房地产"])


def _is_finance(industry_name):
    return _contains_any(industry_name, ["银行", "非银金融", "证券", "保险", "多元金融"])


# ═══════════════════════════════════════════════════════════════════
# PB/ROE bucket classification
# ═══════════════════════════════════════════════════════════════════

def _classify_pb_bucket(p):
    if pd.isnull(p):
        return "PB_Q4_NOT_LOW"
    if p <= 0.1:
        return "PB_Q1_EXTREME_LOW"
    if p <= 0.3:
        return "PB_Q2_CORE_LOW"
    if p <= 0.5:
        return "PB_Q3_ACCEPT_LOW"
    return "PB_Q4_NOT_LOW"


def _classify_roe_bucket(p):
    if pd.isnull(p):
        return "ROE_Q4_WEAK"
    if p <= 0.1:
        return "ROE_Q1_EXTREME_HIGH"
    if p <= 0.3:
        return "ROE_Q2_CORE_HIGH"
    if p <= 0.5:
        return "ROE_Q3_ACCEPT"
    return "ROE_Q4_WEAK"


def _add_rank_bucket_score_fields(df: pd.DataFrame, params: POEPBRoeParams) -> pd.DataFrame:
    df = df.copy()
    df["market_pb_rank_pct"] = df["pb_ratio"].rank(ascending=True, pct=True)
    df["industry_pb_rank_pct"] = df.groupby("industry_name")["pb_ratio"].rank(ascending=True, pct=True)
    df["roe_rank_pct"] = df["roe"].rank(ascending=False, pct=True)
    df["roa_rank_pct"] = df["roa"].rank(ascending=False, pct=True)
    df["score_b_ind_pb_roe"] = (
        0.25 * df["market_pb_rank_pct"]
        + 0.25 * df["industry_pb_rank_pct"]
        + 0.5 * df["roe_rank_pct"]
    )
    df["pb_bucket"] = df["market_pb_rank_pct"].apply(_classify_pb_bucket)
    df["roe_bucket"] = df["roe_rank_pct"].apply(_classify_roe_bucket)
    df["pb_roe_cell"] = df["pb_bucket"] + "__" + df["roe_bucket"]
    df["is_static_core_cell"] = (
        (df["market_pb_rank_pct"] > params.core_pb_low)
        & (df["market_pb_rank_pct"] <= params.core_pb_high)
        & (df["roe_rank_pct"] > params.core_roe_low)
        & (df["roe_rank_pct"] <= params.core_roe_high)
    )
    df["score_regime_neutral_balanced"] = df["score_b_ind_pb_roe"]
    df["score_regime_weak_value_soft"] = (
        0.3 * df["market_pb_rank_pct"]
        + 0.3 * df["industry_pb_rank_pct"]
        + 0.4 * df["roe_rank_pct"]
    )
    return df


def _sort_pool(pool: pd.DataFrame, score_col: str) -> pd.DataFrame:
    pool = pool.copy()
    if score_col not in pool.columns:
        pool[score_col] = 0.5
    pool = pool.sort_values(
        [score_col, "industry_pb_rank_pct", "market_pb_rank_pct", "roe_rank_pct"],
        ascending=[True, True, True, True],
    ).reset_index(drop=True)
    pool["candidate_rank"] = pool.index + 1
    return pool


def _reorder_pool_rank_spread(pool: pd.DataFrame, band_count: int) -> pd.DataFrame:
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


def _select_targets(
    pool: pd.DataFrame,
    top_n: int,
    params: POEPBRoeParams,
    strong_cycle_max: Optional[int],
    max_per_industry: Optional[int],
) -> list[str]:
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


# ═══════════════════════════════════════════════════════════════════
# Pure scoring / selection functions
# ═══════════════════════════════════════════════════════════════════

def build_base_dataframe(
    data: FundamentalCache,
    codes: list[str],
    data_date: pd.Timestamp,
    params: POEPBRoeParams,
) -> pd.DataFrame:
    """Build a PB+ROE candidate pool DataFrame with sanity filters."""
    df = data.fundamentals(codes, data_date)
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
        & (df.get("pe_ratio", df.get("pe_ttm", pd.Series(np.nan))) > params.pe_min)
        & (df.get("pe_ratio", df.get("pe_ttm", pd.Series(np.nan))) < params.pe_max)
    )
    df = df[keep].dropna(subset=["code", "pb_ratio", "roe", "market_cap"]).copy()
    if df.empty:
        return df

    # ── 富集数据硬排除 ──
    try:
        import tushare as _ts
        _token_path = pathlib.Path(_ts.__file__).parent.parent.parent / "config" / "tushare_token.txt"
    except Exception:
        _token_path = pathlib.Path("config/tushare_token.txt")
    _ec = EnrichmentCache(_token_path, pathlib.Path("data/tushare_cache"))
    _ts_codes = [qlib_to_tushare(c) for c in df["code"].tolist()]
    _enrich_df = compute_enrichment_for_codes(_ec, _ts_codes, data_date)
    df["_ts_code"] = _ts_codes
    df = df.merge(_enrich_df, left_on="_ts_code", right_on="ts_code", how="left")
    df.drop(columns=["_ts_code", "ts_code_y"], errors="ignore", inplace=True)
    if "ts_code_x" in df.columns:
        df.rename(columns={"ts_code_x": "ts_code"}, inplace=True)
    # 硬排除
    df["is_hard_exclude"] = df["is_hard_exclude"].fillna(False)
    df = df[~df["is_hard_exclude"]].copy()
    if df.empty:
        return df
    df["roa"] = df["roa"].fillna(0)
    df["industry_name"] = df["industry_name"].fillna("UNKNOWN")
    df["is_real_estate"] = df["industry_name"].apply(_is_real_estate)
    df["is_finance"] = df["industry_name"].apply(_is_finance)
    df["is_strong_cycle_fixed"] = df["industry_name"].apply(_is_strong_cycle)
    df = df[~df["is_real_estate"]].copy()
    # ── 审计/质押降级标记 ──
    df["is_audit_qualified_flag"] = df["is_audit_qualified"].fillna(False)
    df["is_pledge_high_risk_flag"] = df["is_pledge_high_risk"].fillna(False)
    df["has_insider_sells_flag"] = (df["insider_sells_3m"].fillna(0) > 0)
    return _add_rank_bucket_score_fields(df, params)


def pick_targets(
    base_df: pd.DataFrame,
    m_state: str,
    risk_state: str,
    params: POEPBRoeParams,
) -> tuple[list[str], pd.DataFrame, str]:
    """Select targets based on market state and risk state."""
    core = base_df[base_df["is_static_core_cell"]].copy()
    if core.empty:
        core = base_df.copy()

    # 对已有 Red Flag 的股票在选股时降权
    core["_red_flag_penalty"] = 0.0
    core.loc[core["is_audit_qualified_flag"], "_red_flag_penalty"] += 0.3
    core.loc[core["is_pledge_high_risk_flag"], "_red_flag_penalty"] += 0.2
    core.loc[core["has_insider_sells_flag"], "_red_flag_penalty"] += 0.2

    if m_state == "MARKET_STRONG":
        score_col, top_n, branch = "score_regime_neutral_balanced", 10, "STRONG_BALANCED_TOP10"
        pool = _sort_pool(core, score_col)
        targets = _select_targets(pool, top_n, params, params.strong_cycle_max_1, params.max_per_industry)
    elif m_state == "MARKET_WEAK" and risk_state == "HIGH_DRAWDOWN":
        score_col, top_n, branch = "score_regime_weak_value_soft", params.weak_top_n_25, "WEAK_HIGH_SOFT25"
        pool = _reorder_pool_rank_spread(_sort_pool(core, score_col), params.weak_rank_spread_band_count)
        targets = _select_targets(pool, top_n, params, params.weak_broad_strong_cycle_max_25, params.weak_broad_industry_max)
    elif m_state == "MARKET_WEAK" and risk_state == "MID_DRAWDOWN":
        score_col, top_n, branch = "score_regime_neutral_balanced", params.weak_top_n_25, "WEAK_MID_BALANCED25"
        pool = _reorder_pool_rank_spread(_sort_pool(core, score_col), params.weak_rank_spread_band_count)
        targets = _select_targets(pool, top_n, params, params.weak_broad_strong_cycle_max_25, params.weak_broad_industry_max)
    elif m_state == "MARKET_WEAK":
        score_col, top_n, branch = "score_regime_neutral_balanced", 10, "WEAK_NORMAL_BALANCED_TOP10"
        pool = _sort_pool(core, score_col)
        targets = _select_targets(pool, top_n, params, params.strong_cycle_max_1, params.max_per_industry)
    else:
        score_col, top_n, branch = "score_regime_neutral_balanced", 12, "NEUTRAL_BALANCED_TOP12"
        pool = _sort_pool(core, score_col)
        targets = _select_targets(pool, top_n, params, params.strong_cycle_max_1, params.max_per_industry)

    return targets, pool, branch


# ═══════════════════════════════════════════════════════════════════
# Qlib BaseStrategy — works with SimulatorExecutor
# ═══════════════════════════════════════════════════════════════════

class POEPBRoeStrategy(BaseStrategy):
    """
    POE PB+ROE monthly-rebalance strategy for qlib SimulatorExecutor.

    Config (YAML example):
      strategy:
        class: POEPBRoeStrategy
        module_path: strategies.poe_pb_roe
        kwargs:
          provider_uri: /path/to/data/my_qlib
          token_path: /path/to/config/tushare_token.txt
          cache_dir: /path/to/data/tushare_cache/poe_pb_roe
          initial_cash: 500000
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
        min_list_days: int = 250,
        pb_min: float = 0.1,
        pb_max: float = 20.0,
        roe_min: float = 0.0,
        market_cap_min: float = 20.0,
        pe_min: float = 0.1,
        pe_max: float = 200.0,
        max_per_industry: int = 2,
        strong_cycle_max_1: int = 1,
        weak_top_n_25: int = 25,
        weak_broad_industry_max: int = 3,
        weak_broad_strong_cycle_max_25: int = 5,
        weak_rank_spread_band_count: int = 4,
        open_cost: float = 0.0005,
        close_cost: float = 0.0015,
        outer_trade_decision=None,
        level_infra=None,
        common_infra=None,
        trade_exchange=None,
        **kwargs,
    ):
        super().__init__(
            outer_trade_decision=outer_trade_decision,
            level_infra=level_infra,
            common_infra=common_infra,
            trade_exchange=trade_exchange,
        )
        self._provider_uri = Path(provider_uri)
        self._token_path = Path(token_path)
        self._cache_dir = Path(cache_dir)
        self.params = POEPBRoeParams(
            initial_cash=initial_cash,
            min_list_days=min_list_days,
            pb_min=pb_min, pb_max=pb_max,
            roe_min=roe_min, market_cap_min=market_cap_min,
            pe_min=pe_min, pe_max=pe_max,
            max_per_industry=max_per_industry,
            strong_cycle_max_1=strong_cycle_max_1,
            weak_top_n_25=weak_top_n_25,
            weak_broad_industry_max=weak_broad_industry_max,
            weak_broad_strong_cycle_max_25=weak_broad_strong_cycle_max_25,
            weak_rank_spread_band_count=weak_rank_spread_band_count,
            open_cost=open_cost, close_cost=close_cost,
            benchmark=benchmark, market=market,
        )
        self._reader: QlibDailyReader | None = None
        self._data: FundamentalCache | None = None
        self._close: pd.DataFrame | None = None
        self._bench_close: pd.Series | None = None
        self._universe: list[str] = []
        self._rebalance_dates: set[pd.Timestamp] = set()
        self._targets: list[str] = []
        self._initialized: bool = False
        self._history_universe = None

    def _ensure_init(self):
        if self._initialized:
            return
        self._reader = QlibDailyReader(self._provider_uri)
        self._data = FundamentalCache(self._token_path, self._cache_dir / "poe_pb_roe")

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

        ts_codes = [qlib_to_tushare(c) for c in self._universe]
        self._data.prefetch(ts_codes, str(start.date()), str(end.date()))

        cal = self._reader.calendar
        self._rebalance_dates = set(monthly_rebalance_dates(cal, str(start.date()), str(end.date())))
        self._initialized = True
        logger.info("POEPBRoeStrategy initialized: %d universe", len(self._universe))

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

        if self._history_universe is not None:
            active_universe = self._history_universe.codes_for_date(data_date)
        else:
            active_universe = self._universe

        base_df = build_base_dataframe(self._data, active_universe, data_date, self.params)
        if base_df.empty:
            return TradeDecisionWO([], self)

        m_state, risk_state = market_state(self._bench_close, data_date)
        self._targets, pool, branch = pick_targets(base_df, m_state, risk_state, self.params)
        target_set = set(self._targets)

        current = self.trade_position
        sell_orders, buy_orders = [], []
        cash = current.get_cash()

        # Sell
        for code in current.get_stock_list():
            if code not in target_set:
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
                    trade_val, trade_cost, _ = self.trade_exchange.deal_order(order, position=current)
                    cash += trade_val - trade_cost

        # Buy (equal weight)
        if self._targets:
            per_value = cash * 0.95 / max(len(self._targets), 1)
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
                buy_amount = per_value / price
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
                    trade_val, trade_cost, _ = self.trade_exchange.deal_order(order, position=current)
                    cash += trade_val - trade_cost

        logger.info(
            "%s POEPBRoe rebalance [%s]: %d targets, %d sells, %d buys",
            trade_date.date(), branch, len(self._targets), len(sell_orders), len(buy_orders),
        )
        return TradeDecisionWO(sell_orders + buy_orders, self)


# ═══════════════════════════════════════════════════════════════════
# Qlib Model — for YAML/qrun + TopkDropoutStrategy
# ═══════════════════════════════════════════════════════════════════

class POEPBRoeModel(Model):
    """
    Qlib Model that computes POE PB+ROE scores for each (datetime, instrument).

    Use with TopkDropoutStrategy for simple top-k usage (bypasses market-state selection).
    """

    def __init__(
        self,
        provider_uri: str,
        token_path: str,
        cache_dir: str,
        market: str = "hs300",
        benchmark: str = "sh000300",
        pb_min: float = 0.1,
        pb_max: float = 20.0,
        roe_min: float = 0.0,
        market_cap_min: float = 20.0,
        pe_min: float = 0.1,
        pe_max: float = 200.0,
        **kwargs,
    ):
        super().__init__()
        self._provider_uri = Path(provider_uri)
        self._token_path = Path(token_path)
        self._cache_dir = Path(cache_dir)
        self.params = POEPBRoeParams(
            pb_min=pb_min, pb_max=pb_max, roe_min=roe_min,
            market_cap_min=market_cap_min, pe_min=pe_min, pe_max=pe_max,
            benchmark=benchmark, market=market,
        )
        self._reader: QlibDailyReader | None = None
        self._data: FundamentalCache | None = None
        self._universe: list[str] = []
        self._bench_close: pd.Series | None = None
        self._fitted: bool = False

    def fit(self, dataset: Dataset, reweighter=None):
        del reweighter
        self._reader = QlibDailyReader(self._provider_uri)
        self._data = FundamentalCache(self._token_path, self._cache_dir / "poe_pb_roe")

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
        close = self._reader.close_frame(all_codes, str(start.date()), str(end.date()))
        self._bench_close = close[self.params.benchmark]

        ts_codes = [qlib_to_tushare(c) for c in self._universe]
        self._data.prefetch(ts_codes, str(start.date()), str(end.date()))
        self._fitted = True
        logger.info("POEPBRoeModel fitted: %d instruments", len(self._universe))

    def predict(self, dataset: Dataset, segment: str = "test") -> pd.Series:
        if not self._fitted:
            raise RuntimeError("POEPBRoeModel must be fit() before predict()")

        segments = getattr(dataset, "segments", {})
        seg = segments.get(segment, segment)
        if isinstance(seg, (tuple, list)) and len(seg) == 2:
            start_dt, end_dt = pd.Timestamp(seg[0]), pd.Timestamp(seg[1])
        else:
            start_dt, end_dt = pd.Timestamp("2019-01-02"), pd.Timestamp("2026-06-22")

        cal = self._reader.calendar
        rebal_dates = monthly_rebalance_dates(cal, str(start_dt.date()), str(end_dt.date()))
        scores = []
        for rebal_date in rebal_dates:
            cal_ts = pd.Series(cal)
            pos = cal_ts.searchsorted(rebal_date, side="left")
            data_date = cal[max(0, pos - 1)]

            base_df = build_base_dataframe(self._data, self._universe, data_date, self.params)
            if base_df.empty:
                continue
            m_state, risk_state = market_state(self._bench_close, data_date)
            targets, pool, branch = pick_targets(base_df, m_state, risk_state, self.params)

            # Assign scores: selected targets get highest scores
            base_score = 0.5
            for _, row in pool.iterrows():
                s = 1.0 if row["code"] in set(targets) else base_score - row.get("candidate_rank", 999) * 0.001
                scores.append({"datetime": rebal_date, "instrument": row["code"], "score": max(s, 0.01)})

        if not scores:
            return pd.Series(dtype=float, name="score")

        result = pd.DataFrame(scores)
        result["datetime"] = pd.to_datetime(result["datetime"])
        result = result.set_index(["datetime", "instrument"]).sort_index()
        return result["score"]
