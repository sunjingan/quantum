"""Point-in-time sector prosperity scoring for Trend-Serenity.

The module builds a sector layer before stock selection.  It uses only data
available on or before ``data_date``:

- all-universe price momentum and breadth by sector
- cached limit-up / limit-down activity when available
- cached DC hot ranking when available
- optional financial acceleration already computed in the stock pool

The sector score can be used as a boost, a hard gate, or a hybrid gate that
keeps a small reserve of globally strong stocks outside hot sectors.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import tushare as ts

from strategies._fundamental import qlib_to_tushare, tushare_to_qlib


EXCLUDED_TOPIC_KEYWORDS = [
    "样本股", "成份股", "成分股", "沪深300", "中证", "上证", "深证", "创业板指",
    "融资融券", "转融券", "深股通", "沪股通", "陆股通", "MSCI", "富时", "标普",
    "破净股", "低价股", "高价股", "证金", "社保", "QFII", "基金重仓", "预盈预增",
]


def _is_excluded_topic_name(name: object) -> bool:
    text = "" if pd.isna(name) else str(name)
    return any(k in text for k in EXCLUDED_TOPIC_KEYWORDS)


def _parse_ymd(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype(str).str.replace(r"\.0$", "", regex=True), format="%Y%m%d", errors="coerce")


def _date_col(df: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in df.columns:
            return _parse_ymd(df[name])
    return pd.Series(pd.NaT, index=df.index)


def _rank01(s: pd.Series, ascending: bool = True) -> pd.Series:
    return s.rank(ascending=ascending, pct=True).clip(0, 1).fillna(0.5)


@dataclass
class SectorProsperityParams:
    model: str = "none"  # none | boost | gate | hybrid
    top_k: int = 12
    min_score: float = 0.58
    weight: float = 0.25
    reserve_quantile: float = 0.30
    lookback_days: int = 120
    event_lookback_days: int = 20
    use_topic_graph: bool = True
    topic_top_k: int = 30
    topic_min_score: float = 0.60


class SectorProsperityCache:
    """Cached sector event loader.

    The current implementation is intentionally cache-first.  It consumes the
    enrichment files already produced by the project and leaves optional fetch
    methods as a narrow extension point for additional licensed endpoints.
    """

    def __init__(self, token_path: Path, cache_dir: Path):
        self.cache_dir = cache_dir
        self.sector_dir = cache_dir / "sector_prosperity"
        self.enrichment_dir = cache_dir / "enrichment"
        self.sector_dir.mkdir(parents=True, exist_ok=True)
        self.pro = ts.pro_api(token=token_path.read_text().strip()) if token_path.exists() else None
        self._limit_df: pd.DataFrame | None = None
        self._hot_df: pd.DataFrame | None = None
        self._topic_catalog: pd.DataFrame | None = None
        self._topic_members: pd.DataFrame | None = None
        self._topic_daily: pd.DataFrame | None = None
        self._lhb_df: pd.DataFrame | None = None
        self._limit_topic_df: pd.DataFrame | None = None
        self._etf_basic_df: pd.DataFrame | None = None
        self._etf_daily_df: pd.DataFrame | None = None
        self._etf_share_df: pd.DataFrame | None = None
        self._fund_basic_etf_df: pd.DataFrame | None = None
        self._index_weight_cache: dict[str, pd.DataFrame] = {}

    def _load_glob(self, directory: Path, pattern: str, dtype: dict[str, str] | None = None) -> pd.DataFrame:
        parts = []
        if directory.exists():
            for path in sorted(directory.glob(pattern)):
                try:
                    df = pd.read_csv(path, dtype=dtype)
                except (pd.errors.EmptyDataError, UnicodeDecodeError):
                    continue
                if not df.empty:
                    df["_source_file"] = path.name
                    parts.append(df)
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    def limit_events(self) -> pd.DataFrame:
        if self._limit_df is not None:
            return self._limit_df
        df = pd.concat(
            [
                self._load_glob(self.enrichment_dir, "limit_list*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "limit_list*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "ths_limit*.csv", {"ts_code": str}),
            ],
            ignore_index=True,
        )
        if not df.empty:
            keys = [c for c in ["trade_date", "fetch_date", "ts_code", "limit"] if c in df.columns]
            if keys:
                df = df.drop_duplicates(keys, keep="last")
        self._limit_df = df
        return df

    def hot_rankings(self) -> pd.DataFrame:
        if self._hot_df is not None:
            return self._hot_df
        df = pd.concat(
            [
                self._load_glob(self.enrichment_dir, "dc_hot*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "dc_hot*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "ths_hot*.csv", {"ts_code": str}),
            ],
            ignore_index=True,
        )
        if not df.empty:
            keys = [c for c in ["trade_date", "fetch_date", "ts_code", "rank", "rank_time"] if c in df.columns]
            if keys:
                df = df.drop_duplicates(keys, keep="last")
        self._hot_df = df
        return df

    def _safe_fetch(self, method: str, **kwargs) -> pd.DataFrame:
        if self.pro is None or not hasattr(self.pro, method):
            return pd.DataFrame()
        try:
            df = getattr(self.pro, method)(**kwargs)
        except Exception:
            return pd.DataFrame()
        return df if df is not None else pd.DataFrame()

    def _cached_fetch(self, name: str, fetch_fn) -> pd.DataFrame:
        path = self.sector_dir / f"{name}.csv"
        if path.exists():
            try:
                return pd.read_csv(path, dtype={"ts_code": str, "con_code": str, "code": str})
            except pd.errors.EmptyDataError:
                return pd.DataFrame()
        df = fetch_fn()
        if df is None:
            df = pd.DataFrame()
        df.to_csv(path, index=False)
        return df

    def prefetch_topic_graph(
        self,
        start: str,
        end: str,
        max_topics: int = 500,
        fetch_topic_daily: bool = False,
        fetch_events: bool = False,
        fetch_etf: bool = False,
    ) -> None:
        """Optionally fetch and cache concept graph/event data.

        This method is deliberately opt-in because full concept/event history can
        consume quota.  Backtests use whatever is already cached.
        """
        start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)

        ths_idx = self._cached_fetch(
            "ths_index_all",
            lambda: self._safe_fetch("ths_index", exchange="A", type="N"),
        )
        dc_idx = self._cached_fetch("dc_index_all", lambda: self._safe_fetch("dc_index"))

        catalog = self._normalize_topic_catalog(pd.concat([ths_idx, dc_idx], ignore_index=True))
        if not catalog.empty:
            catalog = catalog[~catalog["topic_name"].apply(_is_excluded_topic_name)].copy()
        topic_codes = catalog["topic_code"].dropna().astype(str).drop_duplicates().head(max_topics).tolist()
        for topic_code in topic_codes:
            safe = topic_code.replace(".", "_").replace("/", "_")
            if topic_code.endswith(".TI"):
                self._cached_fetch(f"ths_member_{safe}", lambda tc=topic_code: self._safe_fetch("ths_member", ts_code=tc))
                if fetch_topic_daily:
                    self._cached_fetch(
                        f"ths_daily_{safe}_{start_ts:%Y%m%d}_{end_ts:%Y%m%d}",
                        lambda tc=topic_code: self._safe_fetch("ths_daily", ts_code=tc, start_date=f"{start_ts:%Y%m%d}", end_date=f"{end_ts:%Y%m%d}"),
                    )
            else:
                self._cached_fetch(f"dc_member_{safe}", lambda tc=topic_code: self._safe_fetch("dc_member", ts_code=tc))
                if fetch_topic_daily:
                    self._cached_fetch(
                        f"dc_daily_{safe}_{start_ts:%Y%m%d}_{end_ts:%Y%m%d}",
                        lambda tc=topic_code: self._safe_fetch("dc_daily", ts_code=tc, start_date=f"{start_ts:%Y%m%d}", end_date=f"{end_ts:%Y%m%d}"),
                    )

        if fetch_events:
            cursor = start_ts
            while cursor <= end_ts:
                ymd = f"{cursor:%Y%m%d}"
                self._cached_fetch(f"limit_step_{ymd}", lambda d=ymd: self._safe_fetch("limit_step", trade_date=d))
                self._cached_fetch(f"limit_cpt_list_{ymd}", lambda d=ymd: self._safe_fetch("limit_cpt_list", trade_date=d))
                self._cached_fetch(f"top_list_{ymd}", lambda d=ymd: self._safe_fetch("top_list", trade_date=d))
                self._cached_fetch(f"top_inst_{ymd}", lambda d=ymd: self._safe_fetch("top_inst", trade_date=d))
                self._cached_fetch(f"hm_detail_{ymd}", lambda d=ymd: self._safe_fetch("hm_detail", trade_date=d))
                cursor += pd.DateOffset(days=1)

        if fetch_etf:
            self._cached_fetch("fund_basic_etf", lambda: self._safe_fetch("fund_basic", market="E"))
            self._cached_fetch("etf_basic_all", lambda: self._safe_fetch("etf_basic"))
            cursor = start_ts
            while cursor <= end_ts:
                ymd = f"{cursor:%Y%m%d}"
                self._cached_fetch(f"fund_daily_{ymd}", lambda d=ymd: self._safe_fetch("fund_daily", trade_date=d))
                self._cached_fetch(f"fund_share_{ymd}", lambda d=ymd: self._safe_fetch("fund_share", trade_date=d))
                cursor += pd.DateOffset(days=1)

    def prefetch_etf_data(self, start: str, end: str) -> None:
        """Prefetch real ETF data needed by the theme momentum strategy."""
        start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
        self._cached_fetch("fund_basic_etf", lambda: self._safe_fetch("fund_basic", market="E"))
        self._cached_fetch("etf_basic_all", lambda: self._safe_fetch("etf_basic"))
        cursor = start_ts
        while cursor <= end_ts:
            ymd = f"{cursor:%Y%m%d}"
            self._cached_fetch(f"fund_daily_{ymd}", lambda d=ymd: self._safe_fetch("fund_daily", trade_date=d))
            self._cached_fetch(f"fund_share_{ymd}", lambda d=ymd: self._safe_fetch("fund_share", trade_date=d))
            cursor += pd.DateOffset(days=1)

    def _normalize_topic_catalog(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=["topic_code", "topic_name", "provider"])
        result = df.copy()
        code_col = next((c for c in ["ts_code", "index_code", "topic_code", "code"] if c in result.columns), None)
        name_col = next((c for c in ["name", "index_name", "topic_name", "concept_name", "cpt"] if c in result.columns), None)
        if code_col is None:
            return pd.DataFrame(columns=["topic_code", "topic_name", "provider"])
        result["topic_code"] = result[code_col].astype(str)
        result["topic_name"] = result[name_col].astype(str) if name_col else result["topic_code"]
        if "provider" not in result.columns:
            result["provider"] = np.where(result["topic_code"].str.endswith(".TI"), "ths", "dc")
        return result[["topic_code", "topic_name", "provider"]].drop_duplicates()

    def topic_catalog(self) -> pd.DataFrame:
        if self._topic_catalog is not None:
            return self._topic_catalog
        raw = pd.concat(
            [
                self._load_glob(self.sector_dir, "ths_index*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "dc_index*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "*concept*class*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "*topic*class*.csv", {"ts_code": str}),
            ],
            ignore_index=True,
        )
        self._topic_catalog = self._normalize_topic_catalog(raw)
        return self._topic_catalog

    def topic_members(self) -> pd.DataFrame:
        if self._topic_members is not None:
            return self._topic_members
        raw = pd.concat(
            [
                self._load_glob(self.sector_dir, "ths_member*.csv", {"ts_code": str, "con_code": str}),
                self._load_glob(self.sector_dir, "dc_member*.csv", {"ts_code": str, "con_code": str}),
                self._load_glob(self.sector_dir, "*concept*member*.csv", {"ts_code": str, "con_code": str}),
                self._load_glob(self.sector_dir, "*topic*member*.csv", {"ts_code": str, "con_code": str}),
            ],
            ignore_index=True,
        )
        if raw.empty:
            self._topic_members = pd.DataFrame(columns=["topic_code", "topic_name", "code", "ts_code", "in_date", "out_date", "provider"])
            return self._topic_members

        topic_col = next((c for c in ["topic_code", "index_code", "concept_code", "cpt_code", "ts_code"] if c in raw.columns), None)
        stock_col = next((c for c in ["con_code", "stock_code", "stock_ts_code", "symbol"] if c in raw.columns), None)
        if topic_col is None or stock_col is None:
            self._topic_members = pd.DataFrame(columns=["topic_code", "topic_name", "code", "ts_code", "in_date", "out_date", "provider"])
            return self._topic_members

        df = raw.copy()
        df["topic_code"] = df[topic_col].astype(str)
        df["ts_code"] = df[stock_col].astype(str)
        df = df[df["ts_code"].str.contains(r"\.(?:SH|SZ|BJ)$", regex=True, na=False)].copy()
        if df.empty:
            self._topic_members = pd.DataFrame(columns=["topic_code", "topic_name", "code", "ts_code", "in_date", "out_date", "provider"])
            return self._topic_members
        df["code"] = df["ts_code"].apply(tushare_to_qlib)
        catalog = self.topic_catalog()
        if not catalog.empty:
            df = df.merge(catalog, on="topic_code", how="left")
        else:
            df["topic_name"] = df["topic_code"]
            df["provider"] = ""
        df = df[~df["topic_name"].apply(_is_excluded_topic_name)].copy()
        for col in ["in_date", "out_date"]:
            if col not in df.columns:
                df[col] = ""
        self._topic_members = df[["topic_code", "topic_name", "code", "ts_code", "in_date", "out_date", "provider"]].drop_duplicates()
        return self._topic_members

    def topic_daily(self) -> pd.DataFrame:
        if self._topic_daily is not None:
            return self._topic_daily
        df = pd.concat(
            [
                self._load_glob(self.enrichment_dir, "ths_daily*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "ths_daily*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "dc_daily*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "*concept*daily*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "*topic*daily*.csv", {"ts_code": str}),
            ],
            ignore_index=True,
        )
        if df.empty:
            self._topic_daily = pd.DataFrame()
            return df
        code_col = next((c for c in ["topic_code", "index_code", "ts_code"] if c in df.columns), None)
        if code_col and code_col != "topic_code":
            df["topic_code"] = df[code_col].astype(str)
        self._topic_daily = df
        return df

    def lhb_events(self) -> pd.DataFrame:
        if self._lhb_df is not None:
            return self._lhb_df
        self._lhb_df = pd.concat(
            [
                self._load_glob(self.sector_dir, "top_list*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "top_inst*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "hm_detail*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "*lhb*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "*youzi*.csv", {"ts_code": str}),
            ],
            ignore_index=True,
        )
        return self._lhb_df

    def limit_topics(self) -> pd.DataFrame:
        if self._limit_topic_df is not None:
            return self._limit_topic_df
        self._limit_topic_df = pd.concat(
            [
                self._load_glob(self.sector_dir, "limit_cpt_list*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "limit_step*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "*strong*sector*.csv", {"ts_code": str}),
            ],
            ignore_index=True,
        )
        return self._limit_topic_df

    def etf_basic(self) -> pd.DataFrame:
        if self._etf_basic_df is not None:
            return self._etf_basic_df
        self._etf_basic_df = pd.concat(
            [
                self._load_glob(self.sector_dir, "fund_basic*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "etf_basic*.csv", {"ts_code": str}),
            ],
            ignore_index=True,
        )
        return self._etf_basic_df

    def fund_basic_etf(self) -> pd.DataFrame:
        if self._fund_basic_etf_df is not None:
            return self._fund_basic_etf_df
        self._fund_basic_etf_df = pd.concat(
            [
                self._load_glob(self.sector_dir, "fund_basic*.csv", {"ts_code": str}),
            ],
            ignore_index=True,
        )
        return self._fund_basic_etf_df

    def etf_daily(self) -> pd.DataFrame:
        if self._etf_daily_df is not None:
            return self._etf_daily_df
        self._etf_daily_df = pd.concat(
            [
                self._load_glob(self.sector_dir, "fund_daily*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "etf_daily*.csv", {"ts_code": str}),
            ],
            ignore_index=True,
        )
        return self._etf_daily_df

    def etf_share(self) -> pd.DataFrame:
        if self._etf_share_df is not None:
            return self._etf_share_df
        self._etf_share_df = pd.concat(
            [
                self._load_glob(self.sector_dir, "fund_share*.csv", {"ts_code": str}),
                self._load_glob(self.sector_dir, "etf_share*.csv", {"ts_code": str}),
            ],
            ignore_index=True,
        )
        return self._etf_share_df

    def index_weight(self, index_code: str, start: str, end: str) -> pd.DataFrame:
        key = f"{index_code}_{pd.Timestamp(start):%Y%m%d}_{pd.Timestamp(end):%Y%m%d}"
        if key in self._index_weight_cache:
            return self._index_weight_cache[key]
        safe = index_code.replace(".", "_")
        path = self.sector_dir / f"index_weight_{safe}_{pd.Timestamp(start):%Y%m%d}_{pd.Timestamp(end):%Y%m%d}.csv"
        if path.exists():
            try:
                df = pd.read_csv(path, dtype={"index_code": str, "con_code": str})
                self._index_weight_cache[key] = df
                return df
            except pd.errors.EmptyDataError:
                pass
        if self.pro is None:
            return pd.DataFrame()
        try:
            df = self.pro.index_weight(
                index_code=index_code,
                start_date=f"{pd.Timestamp(start):%Y%m%d}",
                end_date=f"{pd.Timestamp(end):%Y%m%d}",
            )
        except Exception:
            df = pd.DataFrame()
        if df is None:
            df = pd.DataFrame()
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        self._index_weight_cache[key] = df
        return df


def stock_sector_map(universe: list[str], stock_basic: pd.DataFrame | None, pool: pd.DataFrame | None = None) -> pd.Series:
    """Return qlib-code -> sector name."""
    mapping: dict[str, str] = {}
    if stock_basic is not None and not stock_basic.empty and {"ts_code", "industry"}.issubset(stock_basic.columns):
        basic = stock_basic[["ts_code", "industry"]].dropna(subset=["ts_code"]).copy()
        basic["code"] = basic["ts_code"].astype(str).apply(tushare_to_qlib)
        mapping.update(basic.set_index("code")["industry"].fillna("UNKNOWN").to_dict())
    if pool is not None and not pool.empty and {"code", "industry_name"}.issubset(pool.columns):
        mapping.update(pool.set_index("code")["industry_name"].fillna("UNKNOWN").to_dict())
    return pd.Series({code.lower(): mapping.get(code.lower(), "UNKNOWN") for code in universe})


def _price_sector_frame(
    close: pd.DataFrame,
    universe: list[str],
    sectors: pd.Series,
    data_date: pd.Timestamp,
    lookback_days: int,
) -> pd.DataFrame:
    codes = [c for c in universe if c in close.columns]
    if not codes:
        return pd.DataFrame()
    hist = close.loc[:data_date, codes].tail(lookback_days + 1)
    if hist.empty:
        return pd.DataFrame()
    latest = hist.iloc[-1]

    def period_ret(days: int) -> pd.Series:
        if len(hist) <= days:
            return pd.Series(np.nan, index=codes)
        return latest / hist.iloc[-days - 1] - 1

    ret20 = period_ret(20)
    ret60 = period_ret(60)
    ret120 = period_ret(120)
    ma60 = hist.tail(60).mean() if len(hist) >= 20 else latest
    valid = latest.notna().astype(float)
    stock = pd.DataFrame({
        "code": codes,
        "sector_name": sectors.reindex(codes).fillna("UNKNOWN").values,
        "ret20": ret20.reindex(codes).values,
        "ret60": ret60.reindex(codes).values,
        "ret120": ret120.reindex(codes).values,
        "above_ma60": (latest > ma60).astype(float).reindex(codes).values,
        "valid": valid.reindex(codes).values,
    })
    stock = stock[stock["sector_name"] != "UNKNOWN"].copy()
    if stock.empty:
        return pd.DataFrame()
    return stock.groupby("sector_name", as_index=False).agg(
        sector_size=("code", "count"),
        ret20=("ret20", "mean"),
        ret60=("ret60", "mean"),
        ret120=("ret120", "mean"),
        breadth_ma60=("above_ma60", "mean"),
        valid_count=("valid", "sum"),
    )


def _event_sector_scores(
    cache: SectorProsperityCache | None,
    sectors: pd.Series,
    data_date: pd.Timestamp,
    lookback_days: int,
) -> pd.DataFrame:
    if cache is None:
        return pd.DataFrame(columns=["sector_name", "limit_heat_raw", "hot_heat_raw", "event_risk_raw"])

    ts_to_sector = {qlib_to_tushare(code): sector for code, sector in sectors.items()}
    cutoff = data_date - pd.DateOffset(days=lookback_days)

    rows = []
    limit_df = cache.limit_events()
    if not limit_df.empty:
        dt = _date_col(limit_df, "fetch_date", "trade_date")
        recent = limit_df[(dt >= cutoff) & (dt <= data_date)].copy()
        if not recent.empty:
            recent["sector_name"] = recent.get("ts_code", pd.Series(index=recent.index, dtype=str)).map(ts_to_sector)
            if "industry" in recent.columns:
                recent["sector_name"] = recent["sector_name"].fillna(recent["industry"].astype(str).str.replace("行业", "", regex=False))
            limit_col = recent["limit"] if "limit" in recent.columns else pd.Series("", index=recent.index)
            open_times = recent["open_times"] if "open_times" in recent.columns else pd.Series(0, index=recent.index)
            recent["is_up"] = limit_col.astype(str).eq("U").astype(float)
            recent["is_down"] = limit_col.astype(str).eq("D").astype(float)
            recent["open_times_num"] = pd.to_numeric(open_times, errors="coerce").fillna(0.0)
            lim = recent.dropna(subset=["sector_name"]).groupby("sector_name", as_index=False).agg(
                limit_up_count=("is_up", "sum"),
                limit_down_count=("is_down", "sum"),
                avg_open_times=("open_times_num", "mean"),
            )
            rows.append(lim)

    hot_df = cache.hot_rankings()
    if not hot_df.empty:
        dt = _date_col(hot_df, "fetch_date", "trade_date")
        recent = hot_df[(dt >= cutoff) & (dt <= data_date)].copy()
        if not recent.empty and "rank" in recent.columns:
            recent["sector_name"] = recent.get("ts_code", pd.Series(index=recent.index, dtype=str)).map(ts_to_sector)
            recent["rank_num"] = pd.to_numeric(recent["rank"], errors="coerce")
            recent["hot_score_stock"] = (1.0 - recent["rank_num"].clip(1, 500) / 500.0).clip(0, 1)
            hot = recent.dropna(subset=["sector_name"]).groupby("sector_name", as_index=False).agg(
                hot_heat_raw=("hot_score_stock", "mean"),
                hot_count=("hot_score_stock", "count"),
            )
            rows.append(hot)

    if not rows:
        return pd.DataFrame(columns=["sector_name", "limit_heat_raw", "hot_heat_raw", "event_risk_raw"])

    result = rows[0]
    for part in rows[1:]:
        result = result.merge(part, on="sector_name", how="outer")
    def col(name: str, default: float = 0.0) -> pd.Series:
        if name in result.columns:
            return pd.to_numeric(result[name], errors="coerce").fillna(default)
        return pd.Series(default, index=result.index)

    result["limit_heat_raw"] = col("limit_up_count")
    result["hot_heat_raw"] = col("hot_heat_raw")
    result["event_risk_raw"] = (
        col("limit_down_count")
        + col("avg_open_times")
    )
    return result[["sector_name", "limit_heat_raw", "hot_heat_raw", "event_risk_raw"]]


def _financial_sector_scores(pool: pd.DataFrame | None) -> pd.DataFrame:
    if pool is None or pool.empty or "industry_name" not in pool.columns:
        return pd.DataFrame(columns=["sector_name", "financial_heat_raw"])
    df = pool.copy()
    cols = []
    for col in ["q_sales_yoy", "sales_accel", "margin_change_yoy"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            cols.append(col)
    if not cols:
        return pd.DataFrame(columns=["sector_name", "financial_heat_raw"])
    out = df.groupby("industry_name")[cols].mean()
    raw = pd.Series(0.0, index=out.index)
    for col in cols:
        raw += _rank01(out[col], ascending=True) / len(cols)
    return raw.rename("financial_heat_raw").reset_index().rename(columns={"industry_name": "sector_name"})


def _visible_topic_members(
    cache: SectorProsperityCache | None,
    universe: list[str],
    data_date: pd.Timestamp,
) -> pd.DataFrame:
    if cache is None:
        return pd.DataFrame()
    members = cache.topic_members()
    if members.empty:
        return members
    df = members[members["code"].isin([c.lower() for c in universe])].copy()
    if df.empty:
        return df

    in_dt = _date_col(df, "in_date")
    out_dt = _date_col(df, "out_date")
    visible = (in_dt.isna() | (in_dt <= data_date)) & (out_dt.isna() | (out_dt > data_date))
    return df[visible].copy()


def _member_topic_price_scores(
    close: pd.DataFrame,
    members: pd.DataFrame,
    data_date: pd.Timestamp,
    lookback_days: int,
) -> pd.DataFrame:
    codes = sorted(set(members["code"]) & set(close.columns))
    if not codes:
        return pd.DataFrame()
    hist = close.loc[:data_date, codes].tail(lookback_days + 1)
    if hist.empty:
        return pd.DataFrame()
    latest = hist.iloc[-1]

    def period_ret(days: int) -> pd.Series:
        if len(hist) <= days:
            return pd.Series(np.nan, index=codes)
        return latest / hist.iloc[-days - 1] - 1

    stock = pd.DataFrame({
        "code": codes,
        "ret20": period_ret(20).reindex(codes).values,
        "ret60": period_ret(60).reindex(codes).values,
        "ret120": period_ret(120).reindex(codes).values,
        "above_ma60": (latest > hist.tail(60).mean()).astype(float).reindex(codes).values,
    })
    linked = members[["topic_code", "topic_name", "code"]].merge(stock, on="code", how="inner")
    if linked.empty:
        return pd.DataFrame()
    return linked.groupby(["topic_code", "topic_name"], as_index=False).agg(
        topic_size=("code", "count"),
        member_ret20=("ret20", "mean"),
        member_ret60=("ret60", "mean"),
        member_ret120=("ret120", "mean"),
        topic_breadth=("above_ma60", "mean"),
    )


def _daily_topic_price_scores(
    cache: SectorProsperityCache | None,
    data_date: pd.Timestamp,
    lookback_days: int,
) -> pd.DataFrame:
    if cache is None:
        return pd.DataFrame()
    df = cache.topic_daily()
    if df.empty or "topic_code" not in df.columns:
        return pd.DataFrame()
    dt = _date_col(df, "trade_date", "fetch_date")
    recent = df[(dt <= data_date) & (dt >= data_date - pd.DateOffset(days=lookback_days * 2))].copy()
    if recent.empty:
        return pd.DataFrame()
    recent["_date"] = dt.loc[recent.index]
    close_col = next((c for c in ["close", "index_close", "price"] if c in recent.columns), None)
    pct_col = next((c for c in ["pct_change", "pct_chg", "change_pct"] if c in recent.columns), None)
    amount_col = next((c for c in ["amount", "amt", "turnover"] if c in recent.columns), None)
    if close_col is None and pct_col is None:
        return pd.DataFrame()

    rows = []
    for topic_code, g in recent.sort_values("_date").groupby("topic_code"):
        row = {"topic_code": topic_code}
        if close_col is not None:
            close_s = pd.to_numeric(g[close_col], errors="coerce").dropna()
            for days, col in [(20, "daily_ret20"), (60, "daily_ret60"), (120, "daily_ret120")]:
                row[col] = close_s.iloc[-1] / close_s.iloc[-days - 1] - 1 if len(close_s) > days and close_s.iloc[-days - 1] else np.nan
        else:
            pct = pd.to_numeric(g[pct_col], errors="coerce").fillna(0.0) / 100.0
            for days, col in [(20, "daily_ret20"), (60, "daily_ret60"), (120, "daily_ret120")]:
                row[col] = (1.0 + pct.tail(days)).prod() - 1 if len(pct) >= days else np.nan
        row["topic_amount"] = pd.to_numeric(g[amount_col], errors="coerce").tail(20).mean() if amount_col else np.nan
        rows.append(row)
    daily = pd.DataFrame(rows)
    catalog = cache.topic_catalog()
    if not catalog.empty:
        daily = daily.merge(catalog[["topic_code", "topic_name"]], on="topic_code", how="left")
    daily["topic_name"] = daily["topic_name"].fillna(daily["topic_code"])
    return daily


def _topic_limit_scores(cache: SectorProsperityCache | None, members: pd.DataFrame, data_date: pd.Timestamp, lookback_days: int) -> pd.DataFrame:
    if cache is None or members.empty:
        return pd.DataFrame(columns=["topic_code", "limit_topic_raw", "risk_topic_raw"])
    cutoff = data_date - pd.DateOffset(days=lookback_days)
    rows = []

    limit_df = cache.limit_events()
    if not limit_df.empty:
        dt = _date_col(limit_df, "fetch_date", "trade_date")
        recent = limit_df[(dt >= cutoff) & (dt <= data_date)].copy()
        if not recent.empty and "ts_code" in recent.columns:
            link = members[["topic_code", "topic_name", "ts_code"]].drop_duplicates()
            recent = recent.merge(link, on="ts_code", how="inner")
            limit_col = recent["limit"] if "limit" in recent.columns else pd.Series("", index=recent.index)
            open_times = recent["open_times"] if "open_times" in recent.columns else pd.Series(0, index=recent.index)
            recent["is_up"] = limit_col.astype(str).eq("U").astype(float)
            recent["is_down"] = limit_col.astype(str).eq("D").astype(float)
            recent["open_times_num"] = pd.to_numeric(open_times, errors="coerce").fillna(0.0)
            rows.append(recent.groupby(["topic_code", "topic_name"], as_index=False).agg(
                limit_topic_raw=("is_up", "sum"),
                risk_topic_raw=("is_down", "sum"),
                open_times_raw=("open_times_num", "mean"),
            ))

    limit_topics = cache.limit_topics()
    if not limit_topics.empty:
        dt = _date_col(limit_topics, "trade_date", "fetch_date")
        recent = limit_topics[(dt >= cutoff) & (dt <= data_date)].copy()
        if not recent.empty:
            name_col = next((c for c in ["name", "cpt", "concept", "sector", "industry", "topic_name"] if c in recent.columns), None)
            if name_col:
                recent["topic_name"] = recent[name_col].astype(str).str.replace("行业", "", regex=False)
                recent["limit_topic_raw"] = 1.0
                rows.append(recent.groupby("topic_name", as_index=False).agg(limit_topic_raw=("limit_topic_raw", "sum")))

    if not rows:
        return pd.DataFrame(columns=["topic_code", "topic_name", "limit_topic_raw", "risk_topic_raw"])
    result = rows[0]
    for part in rows[1:]:
        result = result.merge(part, on=[c for c in ["topic_code", "topic_name"] if c in result.columns and c in part.columns], how="outer")
    if "topic_code" not in result.columns:
        result["topic_code"] = result["topic_name"]
    result["risk_topic_raw"] = pd.to_numeric(result.get("risk_topic_raw", pd.Series(0, index=result.index)), errors="coerce").fillna(0.0)
    result["limit_topic_raw"] = pd.to_numeric(result.get("limit_topic_raw", pd.Series(0, index=result.index)), errors="coerce").fillna(0.0)
    result["risk_topic_raw"] += pd.to_numeric(result.get("open_times_raw", pd.Series(0, index=result.index)), errors="coerce").fillna(0.0)
    return result[["topic_code", "topic_name", "limit_topic_raw", "risk_topic_raw"]].drop_duplicates()


def _topic_fund_scores(cache: SectorProsperityCache | None, members: pd.DataFrame, data_date: pd.Timestamp, lookback_days: int) -> pd.DataFrame:
    if cache is None or members.empty:
        return pd.DataFrame(columns=["topic_code", "lhb_topic_raw", "hot_topic_raw"])
    cutoff = data_date - pd.DateOffset(days=lookback_days)
    rows = []

    lhb = cache.lhb_events()
    if not lhb.empty and "ts_code" in lhb.columns:
        dt = _date_col(lhb, "trade_date", "fetch_date", "ann_date")
        recent = lhb[(dt >= cutoff) & (dt <= data_date)].copy()
        if not recent.empty:
            link = members[["topic_code", "topic_name", "ts_code"]].drop_duplicates()
            recent = recent.merge(link, on="ts_code", how="inner")
            net_col = next((c for c in ["net_buy", "net_amount", "net_buy_amount", "net_mf_amount"] if c in recent.columns), None)
            if net_col:
                recent["net_buy_raw"] = pd.to_numeric(recent[net_col], errors="coerce").fillna(0.0)
            else:
                buy_col = next((c for c in ["buy", "buy_amount", "buy_inst", "bamount"] if c in recent.columns), None)
                sell_col = next((c for c in ["sell", "sell_amount", "sell_inst", "samount"] if c in recent.columns), None)
                recent["net_buy_raw"] = (
                    pd.to_numeric(recent[buy_col], errors="coerce").fillna(0.0)
                    - pd.to_numeric(recent[sell_col], errors="coerce").fillna(0.0)
                ) if buy_col and sell_col else 1.0
            rows.append(recent.groupby(["topic_code", "topic_name"], as_index=False).agg(
                lhb_topic_raw=("net_buy_raw", "sum"),
                lhb_count=("net_buy_raw", "count"),
            ))

    hot = cache.hot_rankings()
    if not hot.empty and {"ts_code", "rank"}.issubset(hot.columns):
        dt = _date_col(hot, "trade_date", "fetch_date")
        recent = hot[(dt >= cutoff) & (dt <= data_date)].copy()
        if not recent.empty:
            link = members[["topic_code", "topic_name", "ts_code"]].drop_duplicates()
            recent = recent.merge(link, on="ts_code", how="inner")
            rank = pd.to_numeric(recent["rank"], errors="coerce")
            recent["hot_topic_stock"] = (1.0 - rank.clip(1, 500) / 500.0).clip(0, 1)
            rows.append(recent.groupby(["topic_code", "topic_name"], as_index=False).agg(
                hot_topic_raw=("hot_topic_stock", "mean"),
                hot_count=("hot_topic_stock", "count"),
            ))

    if not rows:
        return pd.DataFrame(columns=["topic_code", "topic_name", "lhb_topic_raw", "hot_topic_raw"])
    result = rows[0]
    for part in rows[1:]:
        result = result.merge(part, on=["topic_code", "topic_name"], how="outer")
    for col in ["lhb_topic_raw", "hot_topic_raw"]:
        result[col] = pd.to_numeric(result.get(col, pd.Series(0, index=result.index)), errors="coerce").fillna(0.0)
    return result[["topic_code", "topic_name", "lhb_topic_raw", "hot_topic_raw"]].drop_duplicates()


def _topic_etf_scores(cache: SectorProsperityCache | None, topic_scores: pd.DataFrame, data_date: pd.Timestamp, lookback_days: int) -> pd.DataFrame:
    if cache is None or topic_scores.empty:
        return pd.DataFrame(columns=["topic_code", "etf_topic_raw"])
    basic = cache.etf_basic()
    daily = cache.etf_daily()
    share = cache.etf_share()
    if basic.empty:
        return pd.DataFrame(columns=["topic_code", "etf_topic_raw"])
    name_col = next((c for c in ["name", "fund_name", "short_name"] if c in basic.columns), None)
    code_col = next((c for c in ["ts_code", "fund_code"] if c in basic.columns), None)
    if name_col is None or code_col is None:
        return pd.DataFrame(columns=["topic_code", "etf_topic_raw"])

    rows = []
    etf = basic[[code_col, name_col]].dropna().copy()
    etf.columns = ["etf_code", "etf_name"]
    for _, topic in topic_scores[["topic_code", "topic_name"]].drop_duplicates().iterrows():
        topic_name = str(topic["topic_name"])
        if len(topic_name) < 2:
            continue
        matched = etf[etf["etf_name"].astype(str).str.contains(topic_name, regex=False, na=False)]
        if matched.empty:
            continue
        raw = 0.0
        if not daily.empty:
            dt = _date_col(daily, "trade_date", "fetch_date")
            recent = daily[(daily[code_col].isin(matched["etf_code"])) & (dt <= data_date) & (dt >= data_date - pd.DateOffset(days=lookback_days * 2))].copy() if code_col in daily.columns else pd.DataFrame()
            if not recent.empty:
                pct_col = next((c for c in ["pct_chg", "pct_change"] if c in recent.columns), None)
                if pct_col:
                    raw += pd.to_numeric(recent[pct_col], errors="coerce").tail(20).mean() / 10.0
        if not share.empty and code_col in share.columns:
            dt = _date_col(share, "trade_date", "fetch_date")
            recent = share[(share[code_col].isin(matched["etf_code"])) & (dt <= data_date) & (dt >= data_date - pd.DateOffset(days=lookback_days * 2))].copy()
            share_col = next((c for c in ["fund_share", "share", "total_share"] if c in recent.columns), None)
            if not recent.empty and share_col:
                s = pd.to_numeric(recent[share_col], errors="coerce").dropna()
                if len(s) > 20 and s.iloc[-21]:
                    raw += s.iloc[-1] / s.iloc[-21] - 1
        rows.append({"topic_code": topic["topic_code"], "etf_topic_raw": raw})
    return pd.DataFrame(rows)


def _topic_financial_scores(pool: pd.DataFrame | None, members: pd.DataFrame) -> pd.DataFrame:
    if pool is None or pool.empty or members.empty or "code" not in pool.columns:
        return pd.DataFrame(columns=["topic_code", "financial_topic_raw"])
    df = members[["topic_code", "topic_name", "code"]].merge(pool, on="code", how="inner")
    cols = [c for c in ["q_sales_yoy", "sales_accel", "margin_change_yoy"] if c in df.columns]
    if not cols:
        return pd.DataFrame(columns=["topic_code", "financial_topic_raw"])
    for col in cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    raw = df.groupby(["topic_code", "topic_name"])[cols].mean()
    score = pd.Series(0.0, index=raw.index)
    for col in cols:
        score += _rank01(raw[col], ascending=True) / len(cols)
    return score.rename("financial_topic_raw").reset_index()


def compute_stock_topic_scores(
    close: pd.DataFrame,
    universe: list[str],
    data_date: pd.Timestamp,
    cache: SectorProsperityCache | None = None,
    pool: pd.DataFrame | None = None,
    params: SectorProsperityParams | None = None,
) -> pd.DataFrame:
    """Compute best point-in-time topic prosperity score for each stock."""
    params = params or SectorProsperityParams()
    if cache is None or not params.use_topic_graph:
        return pd.DataFrame()
    members = _visible_topic_members(cache, universe, data_date)
    if members.empty:
        return pd.DataFrame()

    member_price = _member_topic_price_scores(close, members, data_date, params.lookback_days)
    daily_price = _daily_topic_price_scores(cache, data_date, params.lookback_days)
    if member_price.empty and daily_price.empty:
        return pd.DataFrame()

    topic = member_price if not member_price.empty else daily_price[["topic_code", "topic_name"]].drop_duplicates()
    if not daily_price.empty:
        topic = topic.merge(daily_price, on=["topic_code", "topic_name"], how="outer")
    topic["topic_name"] = topic["topic_name"].fillna(topic["topic_code"])

    def num_col(name: str, default: float = np.nan) -> pd.Series:
        source = topic[name] if name in topic.columns else pd.Series(default, index=topic.index)
        return pd.to_numeric(source, errors="coerce")

    topic["topic_ret20"] = num_col("daily_ret20").fillna(num_col("member_ret20"))
    topic["topic_ret60"] = num_col("daily_ret60").fillna(num_col("member_ret60"))
    topic["topic_ret120"] = num_col("daily_ret120").fillna(num_col("member_ret120"))
    topic["topic_breadth"] = num_col("topic_breadth", 0.5).fillna(0.5)

    for part in [
        _topic_limit_scores(cache, members, data_date, params.event_lookback_days),
        _topic_fund_scores(cache, members, data_date, params.event_lookback_days),
        _topic_financial_scores(pool, members),
    ]:
        if part is not None and not part.empty:
            topic = topic.merge(part, on=["topic_code", "topic_name"], how="left")
    etf = _topic_etf_scores(cache, topic, data_date, params.event_lookback_days)
    if not etf.empty:
        topic = topic.merge(etf, on="topic_code", how="left")

    for col in ["limit_topic_raw", "risk_topic_raw", "lhb_topic_raw", "hot_topic_raw", "financial_topic_raw", "etf_topic_raw"]:
        default = 0.0 if col != "financial_topic_raw" else 0.5
        topic[col] = pd.to_numeric(topic.get(col, pd.Series(default, index=topic.index)), errors="coerce").fillna(default)

    topic["topic_momentum"] = (
        0.25 * _rank01(topic["topic_ret20"], ascending=True)
        + 0.45 * _rank01(topic["topic_ret60"], ascending=True)
        + 0.30 * _rank01(topic["topic_ret120"], ascending=True)
    )
    topic["topic_breadth_score"] = _rank01(topic["topic_breadth"], ascending=True)
    topic["topic_limit_score"] = _rank01(topic["limit_topic_raw"], ascending=True) if topic["limit_topic_raw"].sum() > 0 else 0.5
    topic["topic_lhb_score"] = _rank01(topic["lhb_topic_raw"], ascending=True) if topic["lhb_topic_raw"].abs().sum() > 0 else 0.5
    topic["topic_hot_score"] = _rank01(topic["hot_topic_raw"], ascending=True) if topic["hot_topic_raw"].sum() > 0 else 0.5
    topic["topic_etf_score"] = _rank01(topic["etf_topic_raw"], ascending=True) if topic["etf_topic_raw"].abs().sum() > 0 else 0.5
    topic["topic_financial_score"] = topic["financial_topic_raw"].clip(0, 1)
    topic["topic_risk_penalty"] = _rank01(topic["risk_topic_raw"], ascending=True) if topic["risk_topic_raw"].sum() > 0 else 0.0
    topic["topic_score"] = (
        0.28 * topic["topic_momentum"]
        + 0.18 * topic["topic_breadth_score"]
        + 0.15 * topic["topic_limit_score"]
        + 0.13 * topic["topic_lhb_score"]
        + 0.08 * topic["topic_hot_score"]
        + 0.08 * topic["topic_etf_score"]
        + 0.15 * topic["topic_financial_score"]
        - 0.05 * topic["topic_risk_penalty"]
    ).clip(0, 1)
    topic["topic_rank"] = topic["topic_score"].rank(ascending=False, method="min").astype(int)
    topic["topic_selected"] = (topic["topic_rank"] <= params.topic_top_k) | (topic["topic_score"] >= params.topic_min_score)

    linked = members[["code", "topic_code", "topic_name"]].merge(
        topic[[
            "topic_code", "topic_name", "topic_score", "topic_rank", "topic_selected",
            "topic_momentum", "topic_breadth_score", "topic_limit_score",
            "topic_lhb_score", "topic_hot_score", "topic_etf_score",
            "topic_financial_score", "topic_risk_penalty",
        ]],
        on=["topic_code", "topic_name"],
        how="inner",
    )
    if linked.empty:
        return pd.DataFrame()
    linked = linked.sort_values(["code", "topic_score"], ascending=[True, False])
    return linked.groupby("code", as_index=False).head(1).reset_index(drop=True)


def compute_sector_scores(
    close: pd.DataFrame,
    universe: list[str],
    data_date: pd.Timestamp,
    stock_basic: pd.DataFrame | None = None,
    pool: pd.DataFrame | None = None,
    cache: SectorProsperityCache | None = None,
    params: SectorProsperityParams | None = None,
) -> pd.DataFrame:
    """Compute point-in-time sector scores over the full tradable universe."""
    params = params or SectorProsperityParams()
    sectors = stock_sector_map(universe, stock_basic, pool)
    price = _price_sector_frame(close, universe, sectors, data_date, params.lookback_days)
    if price.empty:
        return pd.DataFrame()

    events = _event_sector_scores(cache, sectors, data_date, params.event_lookback_days)
    financial = _financial_sector_scores(pool)
    df = price.merge(events, on="sector_name", how="left").merge(financial, on="sector_name", how="left")
    for col in ["limit_heat_raw", "hot_heat_raw", "event_risk_raw", "financial_heat_raw"]:
        default = 0.0 if col != "financial_heat_raw" else 0.5
        source = df[col] if col in df.columns else pd.Series(default, index=df.index)
        df[col] = pd.to_numeric(source, errors="coerce").fillna(default)

    df["price_momentum"] = (
        0.25 * _rank01(df["ret20"], ascending=True)
        + 0.45 * _rank01(df["ret60"], ascending=True)
        + 0.30 * _rank01(df["ret120"], ascending=True)
    )
    df["breadth_score"] = _rank01(df["breadth_ma60"], ascending=True)
    df["limit_score"] = _rank01(df["limit_heat_raw"], ascending=True) if df["limit_heat_raw"].sum() > 0 else 0.5
    df["hot_score"] = _rank01(df["hot_heat_raw"], ascending=True) if df["hot_heat_raw"].sum() > 0 else 0.5
    df["financial_score"] = df["financial_heat_raw"].fillna(0.5).clip(0, 1)
    df["risk_penalty"] = (
        _rank01(df["event_risk_raw"], ascending=True) if df["event_risk_raw"].sum() > 0 else 0.0
    )
    df["sector_score"] = (
        0.32 * df["price_momentum"]
        + 0.23 * df["breadth_score"]
        + 0.17 * df["limit_score"]
        + 0.10 * df["hot_score"]
        + 0.18 * df["financial_score"]
        - 0.08 * df["risk_penalty"]
    ).clip(0, 1)
    df["sector_rank"] = df["sector_score"].rank(ascending=False, method="min").astype(int)
    df["sector_percentile"] = df["sector_score"].rank(ascending=True, pct=True).clip(0, 1)
    df["sector_selected"] = (
        (df["sector_rank"] <= params.top_k)
        | (df["sector_score"] >= params.min_score)
    )
    return df.sort_values("sector_score", ascending=False).reset_index(drop=True)


def attach_sector_scores(
    pool: pd.DataFrame,
    sector_scores: pd.DataFrame,
    params: SectorProsperityParams,
    score_col: str | None = None,
    stock_topic_scores: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Attach sector scores and apply boost/gate/hybrid semantics."""
    if pool is None or pool.empty or params.model == "none":
        return pool

    df = pool.copy()
    if "industry_name" not in df.columns:
        return df
    if score_col is None:
        score_col = "serenity_score_v2" if "serenity_score_v2" in df.columns else "serenity_score"
    if score_col not in df.columns:
        return df

    df["serenity_score_before_sector"] = pd.to_numeric(df[score_col], errors="coerce")
    if sector_scores is not None and not sector_scores.empty:
        df = df.merge(
            sector_scores[[
                "sector_name", "sector_score", "sector_rank", "sector_percentile", "sector_selected",
                "price_momentum", "breadth_score", "limit_score", "hot_score", "financial_score", "risk_penalty",
            ]],
            left_on="industry_name",
            right_on="sector_name",
            how="left",
        )
    else:
        df["sector_name"] = df["industry_name"]
        df["sector_score"] = np.nan
        df["sector_rank"] = np.nan
        df["sector_percentile"] = np.nan
        df["sector_selected"] = False
    df["sector_score"] = df["sector_score"].fillna(0.5)
    df["sector_selected"] = df["sector_selected"].fillna(False).astype(bool)

    if stock_topic_scores is not None and not stock_topic_scores.empty:
        df = df.merge(stock_topic_scores, on="code", how="left")
    else:
        df["topic_score"] = np.nan
        df["topic_selected"] = False

    df["topic_score"] = pd.to_numeric(df.get("topic_score"), errors="coerce")
    if "topic_selected" not in df.columns:
        df["topic_selected"] = False
    df["topic_selected"] = np.where(df["topic_selected"].isna(), False, df["topic_selected"]).astype(bool)
    df["prosperity_score"] = df[["sector_score", "topic_score"]].max(axis=1, skipna=True).fillna(0.5)
    df["prosperity_source"] = np.where(
        df["topic_score"].fillna(-1) > df["sector_score"].fillna(-1),
        "topic",
        "industry",
    )
    df["prosperity_selected"] = df["sector_selected"] | df["topic_selected"]

    if params.model == "gate":
        df = df[df["prosperity_selected"]].copy()
    elif params.model == "hybrid":
        reserve_cutoff = df["serenity_score_before_sector"].quantile(1 - params.reserve_quantile)
        df = df[df["prosperity_selected"] | (df["serenity_score_before_sector"] >= reserve_cutoff)].copy()

    if df.empty:
        return df

    boost = params.weight * (df["prosperity_score"] - 0.5)
    if params.model in {"boost", "hybrid"}:
        df[score_col] = (df["serenity_score_before_sector"] + boost).clip(0, 1.2)
    elif params.model == "gate":
        df[score_col] = df["serenity_score_before_sector"]
    df["sector_adjustment"] = df[score_col] - df["serenity_score_before_sector"]
    return df
