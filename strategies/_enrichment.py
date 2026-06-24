"""
Tushare P0/P1 富集数据缓存模块。

在每月调仓前拉取以下 8 个确认可用的 Tushare 接口:
  - stk_holdertrade  (内幕交易，最强置信度信号)
  - fina_audit       (审计意见)
  - pledge_stat      (质押比例)
  - dc_hot           (东财人气榜)
  - limit_list_d     (涨跌停列表)
  - ths_daily        (概念指数趋势)
  - moneyflow        (主力资金流向)
  - margin_detail    (融资融券余额变化)

所有数据做磁盘缓存，按 stock/date 粒度查询。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import tushare as ts

logger = logging.getLogger(__name__)


def _to_ymd(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y%m%d")


def _parse_ymd_series(s: pd.Series) -> pd.Series:
    """Parse Tushare YYYYMMDD fields safely after CSV round-trips."""
    return pd.to_datetime(s.astype(str).str.replace(r"\.0$", "", regex=True), format="%Y%m%d", errors="coerce")


def _date_col(df: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in df.columns:
            return _parse_ymd_series(df[name])
    return pd.Series(pd.NaT, index=df.index)


@dataclass
class InsiderSignal:
    """单只股票的内幕交易信号"""
    ts_code: str
    data_date: pd.Timestamp
    trades_3m: int = 0       # 近3月交易总笔数
    buys_3m: int = 0          # 近3月买入笔数
    sells_3m: int = 0         # 近3月卖出笔数
    exec_sells_3m: int = 0    # 高管本人减持笔数
    latest_buy_date: Optional[str] = None
    latest_sell_date: Optional[str] = None
    # 硬排除标记
    is_excluded_insider: bool = False   # 内幕卖出主导
    is_excluded_exec: bool = False      # 高管减持
    risk_flag: str = ""                 # 风险描述


@dataclass
class AuditSignal:
    """审计意见信号"""
    ts_code: str
    audit_result: str = ""          # 最近一次审计意见
    auditor: str = ""               # 审计机构
    is_qualified: bool = False      # 非标意见
    risk_flag: str = ""


@dataclass
class PledgeSignal:
    """质押风险信号"""
    ts_code: str
    pledge_ratio: float = 0.0       # 质押比例 %
    is_high_risk: bool = False      # >50%
    risk_flag: str = ""


@dataclass
class CrowdingMetrics:
    """拥挤度量化指标"""
    ts_code: str
    data_date: pd.Timestamp
    dc_hot_rank: int = 999          # 东财人气排名 (越小越热)
    dc_hot_on_list: bool = False    # 是否在人气榜上
    limit_up_streak: int = 0        # 涨停连续天数
    limit_down_streak: int = 0      # 跌停连续天数
    net_mf_5d_yi: float = 0.0       # 5日主力净流入(亿元)
    margin_chg_20d_pct: float = 0.0 # 20日融资余额变化(%)
    concept_mtd_pct: float = 0.0    # 所属概念指数MTD涨跌幅(%)
    crowding_score: float = 0.0     # 拥挤度综合评分 0-5


class EnrichmentCache:
    """
    P0/P1 富集数据缓存。

    用法:
        ec = EnrichmentCache(token_path, cache_dir)
        ec.prefetch(ts_codes, start, end)  # 拉取所有富集数据
        insider = ec.get_insider(ts_code, data_date)
        audit = ec.get_audit(ts_code)
        pledge = ec.get_pledge(ts_code)
        crowding = ec.get_crowding(ts_code, data_date)
    """

    def __init__(self, token_path: Path, cache_dir: Path):
        self.cache_dir = cache_dir / "enrichment"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.pro = ts.pro_api(token=token_path.read_text().strip())

        # 内存缓存
        self._insider_cache: dict[str, pd.DataFrame] = {}
        self._audit_cache: dict[str, pd.DataFrame] = {}
        self._pledge_cache: pd.DataFrame | None = None
        self._dc_hot_cache: dict[str, pd.DataFrame] = {}
        self._limit_list_cache: dict[str, pd.DataFrame] = {}
        self._ths_daily_cache: dict[str, pd.DataFrame] = {}
        self._moneyflow_cache: dict[str, pd.DataFrame] = {}
        self._margin_cache: dict[str, pd.DataFrame] = {}

    # ═══════════════════════════════════════════════════════════════
    # 批量预拉取
    # ═══════════════════════════════════════════════════════════════

    def prefetch(self, ts_codes: list[str], start: str, end: str) -> None:
        """拉取所有富集接口数据（盘前批量调用）。"""
        start_dt, end_dt = pd.Timestamp(start), pd.Timestamp(end)
        self._fetch_insider(ts_codes, start_dt, end_dt)
        self._fetch_audit(ts_codes)
        self._fetch_pledge()
        self._fetch_dc_hot(start_dt, end_dt)
        self._fetch_limit_list(start_dt, end_dt)
        self._fetch_moneyflow(ts_codes, start_dt, end_dt)
        self._fetch_margin(ts_codes, start_dt, end_dt)
        self._fetch_ths_concepts(start_dt, end_dt)

    # ═══════════════════════════════════════════════════════════════
    # 内幕交易 (stk_holdertrade)
    # ═══════════════════════════════════════════════════════════════

    def _fetch_insider(self, ts_codes: list[str], start: pd.Timestamp, end: pd.Timestamp) -> None:
        path = self.cache_dir / f"stk_holdertrade_{_to_ymd(start)}_{_to_ymd(end)}.csv"
        if path.exists():
            df = pd.read_csv(path, dtype={"ts_code": str, "in_de": str, "holder_type": str})
            self._insider_cache["_all"] = df
            logger.info("Enrichment: insider data loaded from cache (%d rows)", len(df))
            return

        all_parts = []
        for i, ts_code in enumerate(sorted(set(ts_codes)), start=1):
            try:
                df = self.pro.stk_holdertrade(
                    ts_code=ts_code,
                    start_date=_to_ymd(start),
                    end_date=_to_ymd(end),
                )
                if df is not None and not df.empty:
                    all_parts.append(df)
            except Exception as e:
                logger.debug("stk_holdertrade failed for %s: %s", ts_code, e)
            if i % 100 == 0:
                logger.info("  stk_holdertrade: %d/%d", i, len(ts_codes))

        if all_parts:
            result = pd.concat(all_parts, ignore_index=True)
            result.to_csv(path, index=False)
            self._insider_cache["_all"] = result
            logger.info("Enrichment: insider data fetched (%d rows)", len(result))
        else:
            self._insider_cache["_all"] = pd.DataFrame()

    def get_insider(self, ts_code: str, data_date: pd.Timestamp) -> InsiderSignal:
        """获取单只股票的内幕交易信号。"""
        df = self._insider_cache.get("_all", pd.DataFrame())
        if df.empty:
            return InsiderSignal(ts_code=ts_code, data_date=data_date)

        # 筛选最近3个月
        cutoff = data_date - pd.DateOffset(months=3)
        event_date = _date_col(df, "trade_date", "ann_date")
        mask = (df["ts_code"] == ts_code) & (event_date >= cutoff) & (event_date <= data_date)
        recent = df[mask]
        if recent.empty:
            return InsiderSignal(ts_code=ts_code, data_date=data_date)

        # 统计买卖
        in_field = "in_de"
        if in_field not in recent.columns:
            in_field = next((c for c in recent.columns if "in" in c.lower() and "de" in c.lower()), None)

        if in_field:
            buys = (recent[in_field] == "IN").sum()
            sells = (recent[in_field] == "DE").sum()
        else:
            buys, sells = 0, 0

        # 高管本人减持（holder_type == 'G' 且 in_de == 'DE'）
        holder_field = next((c for c in recent.columns if "holder" in c.lower()), None)
        exec_sells = 0
        if holder_field and in_field:
            exec_sells = ((recent[holder_field] == "G") & (recent[in_field] == "DE")).sum()

        signal = InsiderSignal(
            ts_code=ts_code,
            data_date=data_date,
            trades_3m=len(recent),
            buys_3m=buys,
            sells_3m=sells,
            exec_sells_3m=exec_sells,
        )

        # 硬排除规则
        if signal.sells_3m > 3 and signal.buys_3m == 0:
            signal.is_excluded_insider = True
            signal.risk_flag = f"内幕卖出主导({signal.sells_3m}卖, 0买)"
        if signal.exec_sells_3m > 0:
            signal.is_excluded_exec = True
            signal.risk_flag = f"高管本人减持({signal.exec_sells_3m}笔)"

        return signal

    # ═══════════════════════════════════════════════════════════════
    # 审计意见 (fina_audit)
    # ═══════════════════════════════════════════════════════════════

    def _fetch_audit(self, ts_codes: list[str]) -> None:
        path = self.cache_dir / "fina_audit_all.csv"
        if path.exists():
            df = pd.read_csv(path, dtype={"ts_code": str})
            self._audit_cache["_all"] = df
            logger.info("Enrichment: audit data loaded from cache (%d rows)", len(df))
            return

        all_parts = []
        for i, ts_code in enumerate(sorted(set(ts_codes)), start=1):
            try:
                df = self.pro.fina_audit(ts_code=ts_code)
                if df is not None and not df.empty:
                    all_parts.append(df)
            except Exception as e:
                logger.debug("fina_audit failed for %s: %s", ts_code, e)
            if i % 200 == 0:
                logger.info("  fina_audit: %d/%d", i, len(ts_codes))

        if all_parts:
            result = pd.concat(all_parts, ignore_index=True)
            result.to_csv(path, index=False)
            self._audit_cache["_all"] = result
            logger.info("Enrichment: audit data fetched (%d rows)", len(result))
        else:
            self._audit_cache["_all"] = pd.DataFrame()

    def get_audit(self, ts_code: str, data_date: pd.Timestamp | None = None) -> AuditSignal:
        """获取最近一次审计意见。"""
        df = self._audit_cache.get("_all", pd.DataFrame())
        if df.empty or ts_code not in df["ts_code"].values:
            return AuditSignal(ts_code=ts_code)

        recs = df[df["ts_code"] == ts_code].copy()
        if data_date is not None and "ann_date" in recs.columns:
            recs = recs[_parse_ymd_series(recs["ann_date"]) <= data_date]
            if recs.empty:
                return AuditSignal(ts_code=ts_code)
        aud_field = next((c for c in recs.columns if "audit" in c.lower() and "result" in c.lower()), "audit_result")
        if aud_field not in recs.columns:
            recs = recs.sort_values("ann_date", ascending=False) if "ann_date" in recs.columns else recs
        else:
            recs = recs.sort_values("ann_date", ascending=False) if "ann_date" in recs.columns else recs
        row = recs.iloc[0]

        result = str(row.get(aud_field, ""))
        auditor = str(row.get("audit_agency", ""))

        signal = AuditSignal(ts_code=ts_code, audit_result=result, auditor=auditor)
        standard = "标准无保留意见"
        if result and result != standard:
            signal.is_qualified = True
            signal.risk_flag = f"非标审计意见: {result}"
        return signal

    # ═══════════════════════════════════════════════════════════════
    # 质押比例 (pledge_stat)
    # ═══════════════════════════════════════════════════════════════

    def _fetch_pledge(self) -> None:
        path = self.cache_dir / "pledge_stat.csv"
        if path.exists():
            df = pd.read_csv(path, dtype={"ts_code": str})
            self._pledge_cache = df
            logger.info("Enrichment: pledge data loaded from cache (%d rows)", len(df))
            return

        try:
            df = self.pro.pledge_stat()
            if df is not None and not df.empty:
                df.to_csv(path, index=False)
                self._pledge_cache = df
                logger.info("Enrichment: pledge data fetched (%d rows)", len(df))
        except Exception as e:
            logger.warning("pledge_stat failed: %s", e)
            self._pledge_cache = pd.DataFrame()

    def get_pledge(self, ts_code: str, data_date: pd.Timestamp | None = None) -> PledgeSignal:
        """获取质押比例。"""
        df = self._pledge_cache
        if df is None or df.empty:
            return PledgeSignal(ts_code=ts_code)

        rec = df[df["ts_code"] == ts_code]
        if data_date is not None and "end_date" in rec.columns:
            rec = rec[_parse_ymd_series(rec["end_date"]) <= data_date]
        if rec.empty:
            return PledgeSignal(ts_code=ts_code)
        if "end_date" in rec.columns:
            rec = rec.assign(_end_date=_parse_ymd_series(rec["end_date"])).sort_values("_end_date", ascending=False)

        ratio = float(rec.iloc[0].get("pledge_ratio", 0) or 0)
        signal = PledgeSignal(ts_code=ts_code, pledge_ratio=ratio)
        if ratio > 50.0:
            signal.is_high_risk = True
            signal.risk_flag = f"质押比例 {ratio:.0f}% > 50% (流动性风险)"
        return signal

    # ═══════════════════════════════════════════════════════════════
    # 东财人气榜 (dc_hot)
    # ═══════════════════════════════════════════════════════════════

    def _fetch_dc_hot(self, start: pd.Timestamp, end: pd.Timestamp) -> None:
        # dc_hot 只有近期数据（约最近3个月），对历史日期直接跳过
        effective_start = max(start, end - pd.DateOffset(days=120))
        if effective_start > end:
            self._dc_hot_cache["_all"] = pd.DataFrame()
            return
        path = self.cache_dir / f"dc_hot_{_to_ymd(effective_start)}_{_to_ymd(end)}.csv"
        if path.exists():
            df = pd.read_csv(path, dtype={"ts_code": str})
            self._dc_hot_cache["_all"] = df
            logger.info("Enrichment: dc_hot loaded from cache (%d rows)", len(df))
            return

        all_parts = []
        cursor = effective_start
        consecutive_failures = 0
        while cursor <= end and consecutive_failures < 10:
            try:
                df = self.pro.dc_hot(trade_date=_to_ymd(cursor))
                if df is not None and not df.empty:
                    df["fetch_date"] = _to_ymd(cursor)
                    all_parts.append(df)
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
            except Exception:
                consecutive_failures += 1
            cursor += pd.DateOffset(days=1)

        if all_parts:
            result = pd.concat(all_parts, ignore_index=True)
            result.to_csv(path, index=False)
            self._dc_hot_cache["_all"] = result
            logger.info("Enrichment: dc_hot fetched (%d rows)", len(result))
        else:
            self._dc_hot_cache["_all"] = pd.DataFrame()

    def _fetch_limit_list(self, start: pd.Timestamp, end: pd.Timestamp) -> None:
        effective_start = max(start, end - pd.DateOffset(days=180))
        if effective_start > end:
            self._limit_list_cache["_all"] = pd.DataFrame()
            return
        path = self.cache_dir / f"limit_list_{_to_ymd(effective_start)}_{_to_ymd(end)}.csv"
        if path.exists():
            df = pd.read_csv(path, dtype={"ts_code": str})
            self._limit_list_cache["_all"] = df
            logger.info("Enrichment: limit_list loaded from cache (%d rows)", len(df))
            return

        all_parts = []
        cursor = effective_start
        consecutive_failures = 0
        while cursor <= end and consecutive_failures < 10:
            try:
                df = self.pro.limit_list_d(trade_date=_to_ymd(cursor))
                if df is not None and not df.empty:
                    df["fetch_date"] = _to_ymd(cursor)
                    all_parts.append(df)
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
            except Exception:
                consecutive_failures += 1
            cursor += pd.DateOffset(days=1)

        if all_parts:
            result = pd.concat(all_parts, ignore_index=True)
            result.to_csv(path, index=False)
            self._limit_list_cache["_all"] = result
            logger.info("Enrichment: limit_list fetched (%d rows)", len(result))
        else:
            self._limit_list_cache["_all"] = pd.DataFrame()

    def _fetch_moneyflow(self, ts_codes: list[str], start: pd.Timestamp, end: pd.Timestamp) -> None:
        effective_start = max(start, end - pd.DateOffset(days=365))
        if effective_start > end:
            self._moneyflow_cache["_all"] = pd.DataFrame()
            return
        path = self.cache_dir / f"moneyflow_{_to_ymd(effective_start)}_{_to_ymd(end)}.csv"
        if path.exists():
            df = pd.read_csv(path, dtype={"ts_code": str})
            self._moneyflow_cache["_all"] = df
            logger.info("Enrichment: moneyflow loaded from cache (%d rows)", len(df))
            return

        all_parts = []
        cursor = effective_start
        consecutive_failures = 0
        while cursor <= end and consecutive_failures < 10:
            try:
                df = self.pro.moneyflow(trade_date=_to_ymd(cursor))
                if df is not None and not df.empty:
                    df["fetch_date"] = _to_ymd(cursor)
                    all_parts.append(df)
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
            except Exception:
                consecutive_failures += 1
            cursor += pd.DateOffset(days=1)

        if all_parts:
            result = pd.concat(all_parts, ignore_index=True)
            result.to_csv(path, index=False)
            self._moneyflow_cache["_all"] = result
            logger.info("Enrichment: moneyflow fetched (%d rows)", len(result))
        else:
            self._moneyflow_cache["_all"] = pd.DataFrame()

    def _fetch_margin(self, ts_codes: list[str], start: pd.Timestamp, end: pd.Timestamp) -> None:
        effective_start = max(start, end - pd.DateOffset(days=365))
        if effective_start > end:
            self._margin_cache["_all"] = pd.DataFrame()
            return
        path = self.cache_dir / f"margin_detail_{_to_ymd(effective_start)}_{_to_ymd(end)}.csv"
        if path.exists():
            df = pd.read_csv(path, dtype={"ts_code": str})
            self._margin_cache["_all"] = df
            logger.info("Enrichment: margin_detail loaded from cache (%d rows)", len(df))
            return

        all_parts = []
        cursor = effective_start
        consecutive_failures = 0
        while cursor <= end and consecutive_failures < 10:
            try:
                df = self.pro.margin_detail(trade_date=_to_ymd(cursor))
                if df is not None and not df.empty:
                    df["fetch_date"] = _to_ymd(cursor)
                    all_parts.append(df)
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
            except Exception:
                consecutive_failures += 1
            cursor += pd.DateOffset(days=1)

        if all_parts:
            result = pd.concat(all_parts, ignore_index=True)
            result.to_csv(path, index=False)
            self._margin_cache["_all"] = result
            logger.info("Enrichment: margin fetched (%d rows)", len(result))
        else:
            self._margin_cache["_all"] = pd.DataFrame()

    def _fetch_ths_concepts(self, start: pd.Timestamp, end: pd.Timestamp) -> None:
        """拉取同花顺概念指数日线，用于行业背景检查。"""
        path = self.cache_dir / f"ths_daily_{_to_ymd(start)}_{_to_ymd(end)}.csv"
        if path.exists():
            df = pd.read_csv(path, dtype={"ts_code": str})
            self._ths_daily_cache["_all"] = df
            logger.info("Enrichment: ths_daily loaded from cache (%d rows)", len(df))
            return

        all_parts = []
        # 默认拉取沪深300相关概念指数
        concept_indices = ["885809.TI", "885888.TI", "885911.TI"]  # 芯片、人工智能、新能源
        for idx in concept_indices:
            try:
                df = self.pro.ths_daily(
                    ts_code=idx,
                    start_date=_to_ymd(start),
                    end_date=_to_ymd(end),
                )
                if df is not None and not df.empty:
                    all_parts.append(df)
            except Exception as e:
                logger.debug("ths_daily failed for %s: %s", idx, e)

        if all_parts:
            result = pd.concat(all_parts, ignore_index=True)
            result.to_csv(path, index=False)
            self._ths_daily_cache["_all"] = result
            logger.info("Enrichment: ths_daily fetched (%d rows)", len(result))
        else:
            self._ths_daily_cache["_all"] = pd.DataFrame()

    # ═══════════════════════════════════════════════════════════════
    # 拥挤度综合评分 (crowding score 0-5)
    # ═══════════════════════════════════════════════════════════════

    def get_crowding(self, ts_code: str, data_date: pd.Timestamp) -> CrowdingMetrics:
        """计算单只股票的拥挤度量化指标。"""
        m = CrowdingMetrics(ts_code=ts_code, data_date=data_date)

        # ── dc_hot 人气排名 ──
        dc_df = self._dc_hot_cache.get("_all", pd.DataFrame())
        if not dc_df.empty and ts_code in dc_df["ts_code"].values:
            fetch_date = _date_col(dc_df, "fetch_date", "trade_date")
            latest = dc_df[
                (dc_df["ts_code"] == ts_code)
                & (fetch_date <= data_date)
            ]
            if not latest.empty:
                latest = latest.assign(_fetch_date=fetch_date.loc[latest.index]).sort_values("_fetch_date", ascending=False).iloc[0]
                m.dc_hot_rank = int(latest.get("rank", 999))
                m.dc_hot_on_list = True

        # ── limit_list_d 涨跌停连续 ──
        ll_df = self._limit_list_cache.get("_all", pd.DataFrame())
        if not ll_df.empty and ts_code in ll_df["ts_code"].values:
            cutoff = data_date - pd.DateOffset(days=10)
            fetch_date = _date_col(ll_df, "fetch_date", "trade_date")
            recent = ll_df[
                (ll_df["ts_code"] == ts_code)
                & (fetch_date >= cutoff)
                & (fetch_date <= data_date)
            ]
            if not recent.empty:
                m.limit_up_streak = int((recent["limit"] == "U").sum())
                m.limit_down_streak = int((recent["limit"] == "D").sum())

        # ── moneyflow 5日主力净流入 ──
        mf_df = self._moneyflow_cache.get("_all", pd.DataFrame())
        if not mf_df.empty and ts_code in mf_df["ts_code"].values:
            cutoff = data_date - pd.DateOffset(days=7)
            fetch_date = _date_col(mf_df, "fetch_date", "trade_date")
            recent = mf_df[
                (mf_df["ts_code"] == ts_code)
                & (fetch_date >= cutoff)
                & (fetch_date <= data_date)
            ]
            if not recent.empty and "net_mf_amount" in recent.columns:
                m.net_mf_5d_yi = recent["net_mf_amount"].sum() / 10000.0  # 万元->亿元

        # ── margin 融资余额变化 ──
        mg_df = self._margin_cache.get("_all", pd.DataFrame())
        if not mg_df.empty and ts_code in mg_df["ts_code"].values:
            fetch_date = _date_col(mg_df, "fetch_date", "trade_date")
            recent = mg_df[
                (mg_df["ts_code"] == ts_code)
                & (fetch_date <= data_date)
            ].assign(_fetch_date=fetch_date).sort_values("_fetch_date", ascending=False).head(20)
            if len(recent) >= 2 and "rzye" in recent.columns:
                old = float(recent.iloc[-1].get("rzye", recent.iloc[-1].get("rqye", 0) or 0))
                new = float(recent.iloc[0].get("rzye", recent.iloc[0].get("rqye", 0) or 0))
                if old > 0:
                    m.margin_chg_20d_pct = (new / old - 1) * 100

        # ── 概念指数 MTD ──
        ths_df = self._ths_daily_cache.get("_all", pd.DataFrame())
        if not ths_df.empty:
            # 取第一个概念指数的MTD变化
            month_start = data_date.replace(day=1)
            trade_date = _date_col(ths_df, "trade_date", "fetch_date")
            mtd_data = ths_df[
                (trade_date >= month_start)
                & (trade_date <= data_date)
            ]
            if not mtd_data.empty and "pct_change" in mtd_data.columns:
                m.concept_mtd_pct = mtd_data["pct_change"].sum()

        # ── 拥挤度综合评分 ──
        score_components = {}

        # dc_hot rank -> 0-5 (weight 30%)
        if m.dc_hot_on_list:
            if m.dc_hot_rank <= 5:
                score_components["dc_hot"] = (5, 0.30)
            elif m.dc_hot_rank <= 20:
                score_components["dc_hot"] = (4, 0.30)
            elif m.dc_hot_rank <= 50:
                score_components["dc_hot"] = (3, 0.30)
            elif m.dc_hot_rank <= 100:
                score_components["dc_hot"] = (2, 0.30)
            else:
                score_components["dc_hot"] = (1, 0.30)
        else:
            score_components["dc_hot"] = (0, 0.30)

        # limit_list -> 0-5 (weight 20%)
        if m.limit_up_streak >= 3:
            score_components["limit"] = (5, 0.20)
        elif m.limit_up_streak >= 1:
            score_components["limit"] = (3, 0.20)
        else:
            score_components["limit"] = (0, 0.20)

        # moneyflow extreme -> 0-5 (weight 20%)
        if m.net_mf_5d_yi > 50:
            score_components["moneyflow"] = (5, 0.20)
        elif m.net_mf_5d_yi > 20:
            score_components["moneyflow"] = (3, 0.20)
        elif m.net_mf_5d_yi < -15:
            score_components["moneyflow"] = (5, 0.20)  # 极端流出也是拥挤
        elif m.net_mf_5d_yi < -5:
            score_components["moneyflow"] = (3, 0.20)
        else:
            score_components["moneyflow"] = (1, 0.20)

        # concept momentum -> 0-5 (weight 15%)
        if m.concept_mtd_pct > 20:
            score_components["concept"] = (5, 0.15)
        elif m.concept_mtd_pct > 10:
            score_components["concept"] = (4, 0.15)
        elif m.concept_mtd_pct > 5:
            score_components["concept"] = (2, 0.15)
        else:
            score_components["concept"] = (0, 0.15)

        # margin change -> 0-5 (weight 15%)
        if m.margin_chg_20d_pct > 30:
            score_components["margin"] = (5, 0.15)
        elif m.margin_chg_20d_pct > 15:
            score_components["margin"] = (4, 0.15)
        elif m.margin_chg_20d_pct > 5:
            score_components["margin"] = (2, 0.15)
        else:
            score_components["margin"] = (1, 0.15)

        m.crowding_score = sum(score * weight for score, weight in score_components.values())
        return m

    # ═══════════════════════════════════════════════════════════════
    # 行业背景检查
    # ═══════════════════════════════════════════════════════════════

    def get_sector_context(self, data_date: pd.Timestamp) -> str:
        """
        检查概念指数趋势，返回行业背景:
          Tailwind (顺风) / Neutral (中性) / Headwind (逆风)
        """
        ths_df = self._ths_daily_cache.get("_all", pd.DataFrame())
        if ths_df.empty:
            return "Neutral"

        month_start = data_date.replace(day=1)
        trade_date = _date_col(ths_df, "trade_date", "fetch_date")
        mtd_data = ths_df[
            (trade_date >= month_start)
            & (trade_date <= data_date)
        ]
        if mtd_data.empty or "pct_change" not in mtd_data.columns:
            return "Neutral"

        mtd = mtd_data["pct_change"].sum()
        if mtd > 10:
            return "Tailwind"
        elif mtd < -5:
            return "Headwind"
        else:
            return "Neutral"


# ═══════════════════════════════════════════════════════════════════
# 便捷函数：批量获取所有富集信号
# ═══════════════════════════════════════════════════════════════════

def compute_enrichment_for_codes(
    ec: EnrichmentCache,
    ts_codes: list[str],
    data_date: pd.Timestamp,
) -> pd.DataFrame:
    """
    对一批股票批量计算富集信号，返回 DataFrame，每行一只股票。
    包含：硬排除标记、审计意见、质押风险、拥挤度评分、行业背景。
    """
    rows = []
    for tc in ts_codes:
        insider = ec.get_insider(tc, data_date)
        audit = ec.get_audit(tc, data_date)
        pledge = ec.get_pledge(tc, data_date)
        crowding = ec.get_crowding(tc, data_date)

        # 硬排除判定
        is_hard_exclude = False
        exclude_reasons = []
        if insider.is_excluded_insider:
            is_hard_exclude = True
            exclude_reasons.append(insider.risk_flag)
        if insider.is_excluded_exec:
            is_hard_exclude = True
            exclude_reasons.append(insider.risk_flag)
        if audit.is_qualified:
            is_hard_exclude = True
            exclude_reasons.append(audit.risk_flag)
        if pledge.is_high_risk:
            # 质押高风险不直接硬排除，但会降级
            pass

        rows.append({
            "ts_code": tc,
            "is_hard_exclude": is_hard_exclude,
            "exclude_reasons": "; ".join(exclude_reasons),
            "insider_trades_3m": insider.trades_3m,
            "insider_buys_3m": insider.buys_3m,
            "insider_sells_3m": insider.sells_3m,
            "exec_sells_3m": insider.exec_sells_3m,
            "audit_result": audit.audit_result,
            "is_audit_qualified": audit.is_qualified,
            "pledge_ratio": pledge.pledge_ratio,
            "is_pledge_high_risk": pledge.is_high_risk,
            "dc_hot_rank": crowding.dc_hot_rank,
            "dc_hot_on_list": crowding.dc_hot_on_list,
            "limit_up_streak": crowding.limit_up_streak,
            "limit_down_streak": crowding.limit_down_streak,
            "net_mf_5d_yi": crowding.net_mf_5d_yi,
            "margin_chg_20d_pct": crowding.margin_chg_20d_pct,
            "concept_mtd_pct": crowding.concept_mtd_pct,
            "crowding_score": crowding.crowding_score,
        })

    return pd.DataFrame(rows)
