"""Theme ETF momentum + constituent relative-strength strategy.

This module implements a daily/weekly trend strategy:

1. weekly select strong ETF-like themes by liquidity, trend, and flow scores;
2. build a constituent pool from the selected themes;
3. rank constituents by relative strength against their theme;
4. buy only on pullback-stabilization or range-breakout signals;
5. sell on trend break, relative-strength failure, theme failure, stop loss,
   trailing stop, or stale holding.

The local project currently has reliable stock OHLCV, stock_basic,
daily_basic, moneyflow and topic caches.  Full historical ETF holdings are not
guaranteed, so the default layer uses industry/topic baskets as point-in-time
ETF proxies.  If ETF daily/share/holding caches are added later, the scoring
interface can be extended without changing the backtest loop.
"""
from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_right
from pathlib import Path

import numpy as np
import pandas as pd

from strategies._fundamental import FundamentalCache, qlib_to_tushare, tushare_to_qlib
from strategies._utils import QlibDailyReader, lot_floor, summarize
from strategies.sector_prosperity import SectorProsperityCache


def _rank01(s: pd.Series, ascending: bool = True, neutral: float = 0.5) -> pd.Series:
    clean = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan)
    return clean.rank(ascending=ascending, pct=True).clip(0, 1).fillna(neutral)


def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    return a / b.replace(0, np.nan)


def _period_ret(hist: pd.DataFrame, days: int) -> pd.Series:
    if len(hist) <= days:
        return pd.Series(np.nan, index=hist.columns)
    return hist.iloc[-1] / hist.iloc[-days - 1] - 1.0


def _date_col(df: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in df.columns:
            return pd.to_datetime(df[name].astype(str).str.replace(r"\.0$", "", regex=True), format="%Y%m%d", errors="coerce")
    return pd.Series(pd.NaT, index=df.index)


@dataclass
class ThemeETFParams:
    initial_cash: float = 500_000.0
    benchmark: str = "sh000300"
    market: str = "hs300"

    # ETF/theme layer
    etf_count: int = 5
    theme_top_pct: float = 0.10
    min_theme_amount_20d: float = 100_000.0
    min_theme_ret20: float = 0.05
    min_theme_ret60: float = 0.10
    max_theme_dist_ma60: float = 0.25

    # Constituent pool
    constituents_per_theme: int = 30
    min_list_days: int = 120
    min_stock_amount_20d: float = 100_000.0
    min_turnover_20d: float = 1.0
    min_total_mv: float = 1_000_000.0
    allow_min_total_mv: float = 500_000.0

    # Relative strength / structure
    rs_top_pct: float = 0.20
    max_dist_ma20: float = 0.12
    max_dist_ma60: float = 0.35
    pullback_high_min: float = -0.08
    pullback_high_max: float = -0.02
    pullback_ma20_min: float = -0.03
    pullback_ma20_max: float = 0.05

    # Portfolio / execution
    target_num: int = 5
    max_theme_weight: float = 0.40
    open_cost: float = 0.0010
    close_cost: float = 0.0015
    stop_loss: float = -0.08
    trailing_stop: float = -0.10
    stale_hold_days: int = 20

    # Experiments: v0 strong-theme proxy, v1 constituent weight, v2 RS, v3 RS+timing
    experiment: str = "v3"
    theme_source: str = "real_etf"  # real_etf | proxy_industry
    use_moneyflow: bool = True
    market_filter: bool = True
    weak_market_position_scale: float = 0.50


class DailyFrames:
    """OHLCVA matrices read from the local Qlib feature store."""

    def __init__(self, reader: QlibDailyReader, codes: list[str], start: str, end: str):
        self.open = self._frame(reader, codes, "open", start, end)
        self.high = self._frame(reader, codes, "high", start, end)
        self.low = self._frame(reader, codes, "low", start, end)
        self.close = self._frame(reader, codes, "close", start, end)
        self.volume = self._frame(reader, codes, "volume", start, end)
        self.amount = self._frame(reader, codes, "amount", start, end)

    @staticmethod
    def _frame(reader: QlibDailyReader, codes: list[str], field: str, start: str, end: str) -> pd.DataFrame:
        series = [reader.read_field(code, field) for code in codes]
        df = pd.concat(series, axis=1).sort_index() if series else pd.DataFrame()
        return df.loc[pd.Timestamp(start): pd.Timestamp(end)]


class RollingFeatureStore:
    """Precomputed daily rolling features for full-universe backtests."""

    def __init__(self, frames: DailyFrames, codes: list[str]):
        self.codes = [c for c in codes if c in frames.close.columns]
        self.open = frames.open.reindex(columns=self.codes).astype("float32")
        self.high = frames.high.reindex(columns=self.codes).astype("float32")
        self.low = frames.low.reindex(columns=self.codes).astype("float32")
        self.close = frames.close.reindex(columns=self.codes).astype("float32")
        self.volume = frames.volume.reindex(columns=self.codes).astype("float32")
        self.amount = frames.amount.reindex(columns=self.codes).astype("float32")

        self.ma20 = self.close.rolling(20, min_periods=20).mean().astype("float32")
        self.ma60 = self.close.rolling(60, min_periods=60).mean().astype("float32")
        self.ret20 = (self.close / self.close.shift(20) - 1.0).astype("float32")
        self.ret60 = (self.close / self.close.shift(60) - 1.0).astype("float32")
        self.amount20 = self.amount.rolling(20, min_periods=20).mean().astype("float32")
        self.amount60 = self.amount.rolling(60, min_periods=60).mean().astype("float32")
        daily_ret = self.close.pct_change(fill_method=None)
        self.vol20 = daily_ret.rolling(20, min_periods=20).std().astype("float32")
        self.high20 = self.high.rolling(20, min_periods=20).max().astype("float32")
        self.high60 = self.high.rolling(60, min_periods=60).max().astype("float32")
        self.high10_prev = self.high.rolling(10, min_periods=10).max().shift(1).astype("float32")
        self.low10 = self.low.rolling(10, min_periods=10).min().astype("float32")
        self.volume_ma5 = self.volume.rolling(5, min_periods=5).mean().astype("float32")
        self.volume_ma20 = self.volume.rolling(20, min_periods=20).mean().astype("float32")
        self.prev_volume_ma5 = self.volume.shift(1).rolling(5, min_periods=5).mean().astype("float32")
        self.prev_volume_ma20 = self.volume.shift(6).rolling(15, min_periods=15).mean().astype("float32")
        self.pct_chg = (self.close / self.close.shift(1) - 1.0).astype("float32")
        self.amount5 = self.amount.rolling(5, min_periods=5).mean().astype("float32")

    def row(self, name: str, date: pd.Timestamp) -> pd.Series:
        return getattr(self, name).loc[date]


class ThemeUniverse:
    """Point-in-time theme membership built from stock_basic industries."""

    def __init__(self, stock_basic: pd.DataFrame, universe: list[str]):
        basic = stock_basic.copy()
        if "ts_code" not in basic.columns:
            self.industry = pd.Series("UNKNOWN", index=pd.Index(universe))
            self.name = pd.Series("", index=pd.Index(universe))
            self.list_date = pd.Series(pd.NaT, index=pd.Index(universe))
            return
        basic["code"] = basic["ts_code"].astype(str).apply(tushare_to_qlib)
        basic = basic[basic["code"].isin([c.lower() for c in universe])].drop_duplicates("code", keep="last")
        self.industry = basic.set_index("code").get("industry", pd.Series(dtype=object)).fillna("UNKNOWN")
        self.name = basic.set_index("code").get("name", pd.Series(dtype=object)).fillna("")
        self.list_date = pd.to_datetime(basic.set_index("code").get("list_date", pd.Series(dtype=object)).astype(str), errors="coerce")
        self.theme_to_codes = {
            theme: sorted(group.index.tolist())
            for theme, group in self.industry.groupby(self.industry)
            if theme != "UNKNOWN"
        }

    def codes_for_theme(self, theme_name: str) -> list[str]:
        return self.theme_to_codes.get(theme_name, [])


def load_stock_basic_snapshot(data: FundamentalCache, cache_dir: Path) -> pd.DataFrame:
    """Reuse an existing full-market stock_basic cache before fetching a new one."""
    own = data.cache_dir / "stock_basic_all.csv"
    if own.exists():
        return pd.read_csv(own, dtype={"ts_code": str, "list_date": str, "delist_date": str})
    for rel in [
        "trend_serenity/stock_basic_all.csv",
        "poe_pb_roe/stock_basic_all.csv",
        "poe_pb_roe/trend_serenity/stock_basic_all.csv",
    ]:
        path = cache_dir / rel
        if path.exists():
            return pd.read_csv(path, dtype={"ts_code": str, "list_date": str, "delist_date": str})
    return data.stock_basic()


def load_visible_daily_basic(cache_dir: Path, data_date: pd.Timestamp) -> pd.DataFrame:
    """Load the latest cached daily_basic snapshot visible on data_date.

    This strategy is price-led and can run without daily_basic.  We therefore
    avoid fetching one file per trading day during first-pass experiments.
    """
    roots = [
        cache_dir / "theme_etf_momentum" / "daily_basic",
        cache_dir / "trend_serenity" / "daily_basic",
        cache_dir / "poe_pb_roe" / "daily_basic",
    ]
    candidates: list[tuple[pd.Timestamp, Path]] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.glob("*.csv"):
            try:
                dt = pd.Timestamp(path.stem)
            except ValueError:
                continue
            if dt <= data_date:
                candidates.append((dt, path))
    if not candidates:
        return pd.DataFrame()
    _, path = max(candidates, key=lambda item: item[0])
    try:
        return pd.read_csv(path, dtype={"ts_code": str})
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


class DailyBasicStore:
    """Index visible daily_basic cache files once, then read on demand."""

    def __init__(self, cache_dir: Path):
        roots = [
            cache_dir / "theme_etf_momentum" / "daily_basic",
            cache_dir / "trend_serenity" / "daily_basic",
            cache_dir / "poe_pb_roe" / "daily_basic",
        ]
        candidates: list[tuple[pd.Timestamp, Path]] = []
        for root in roots:
            if not root.exists():
                continue
            for path in root.glob("*.csv"):
                try:
                    dt = pd.Timestamp(path.stem)
                except ValueError:
                    continue
                candidates.append((dt, path))
        dedup: dict[pd.Timestamp, Path] = {}
        for dt, path in sorted(candidates):
            dedup[dt] = path
        self.items = sorted(dedup.items())
        self.dates = [item[0] for item in self.items]
        self._last_path: Path | None = None
        self._last_df: pd.DataFrame = pd.DataFrame()

    def get(self, data_date: pd.Timestamp) -> pd.DataFrame:
        pos = bisect_right(self.dates, data_date) - 1
        if pos < 0:
            return pd.DataFrame()
        path = self.items[pos][1]
        if self._last_path == path:
            return self._last_df
        try:
            df = pd.read_csv(path, dtype={"ts_code": str})
        except pd.errors.EmptyDataError:
            df = pd.DataFrame()
        self._last_path = path
        self._last_df = df
        return df


def _pivot_wide(df: pd.DataFrame, date_col: str, code_col: str, value_col: str) -> pd.DataFrame:
    if df is None or df.empty or date_col not in df.columns or code_col not in df.columns or value_col not in df.columns:
        return pd.DataFrame()
    frame = df.copy()
    frame[date_col] = pd.to_datetime(frame[date_col].astype(str), format="%Y%m%d", errors="coerce")
    frame = frame.dropna(subset=[date_col, code_col])
    if frame.empty:
        return pd.DataFrame()
    wide = frame.pivot_table(index=date_col, columns=code_col, values=value_col, aggfunc="last").sort_index()
    wide.columns = wide.columns.astype(str)
    return wide


def _latest_snapshot(df: pd.DataFrame, code_col: str, date_col: str, data_date: pd.Timestamp) -> pd.DataFrame:
    if df is None or df.empty or code_col not in df.columns or date_col not in df.columns:
        return pd.DataFrame()
    frame = df.copy()
    frame[date_col] = pd.to_datetime(frame[date_col].astype(str), format="%Y%m%d", errors="coerce")
    frame = frame[(frame[date_col] <= data_date) & frame[code_col].notna()].copy()
    if frame.empty:
        return pd.DataFrame()
    return frame.sort_values([code_col, date_col]).groupby(code_col, as_index=False).tail(1)


class RealETFUniverse:
    """Real ETF universe built from Tushare ETF metadata."""

    def __init__(self, cache: SectorProsperityCache):
        self.cache = cache
        self.meta = self._build_meta()

    def _build_meta(self) -> pd.DataFrame:
        fund_basic = self.cache.fund_basic_etf()
        etf_basic = self.cache.etf_basic()
        if fund_basic.empty and etf_basic.empty:
            return pd.DataFrame(columns=["ts_code", "etf_name", "theme_name", "index_code", "index_name", "list_date"])

        fb = fund_basic.copy()
        if "name" not in fb.columns and "csname" in fb.columns:
            fb["name"] = fb["csname"]
        fb["fund_name"] = fb.get("name", fb.get("csname", fb["ts_code"])).astype(str)

        eb = etf_basic.copy()
        keep_cols = [c for c in ["ts_code", "index_code", "index_name", "list_status", "etf_type"] if c in eb.columns]
        eb = eb[keep_cols].copy() if keep_cols else pd.DataFrame({"ts_code": fb["ts_code"]})
        meta = fb.merge(eb, on="ts_code", how="left")

        if "index_code" not in meta.columns:
            meta["index_code"] = pd.NA
        if "index_name" not in meta.columns:
            meta["index_name"] = pd.NA
        if "list_status" not in meta.columns:
            meta["list_status"] = pd.NA
        if "etf_type" not in meta.columns:
            meta["etf_type"] = pd.NA

        status_s = meta["status"] if "status" in meta.columns else pd.Series(["L"] * len(meta), index=meta.index)
        list_status_s = meta["list_status"]
        fund_type_s = meta["fund_type"] if "fund_type" in meta.columns else pd.Series([""] * len(meta), index=meta.index)
        type_s = meta["type"] if "type" in meta.columns else pd.Series([""] * len(meta), index=meta.index)
        etf_type_s = meta["etf_type"].fillna("")

        meta["is_stock_like"] = (
            fund_type_s.astype(str).eq("股票型")
            | type_s.astype(str).eq("股票型")
            | etf_type_s.astype(str).str.contains("ETF", na=False)
            | meta["fund_name"].astype(str).str.contains("ETF", na=False)
        )
        meta["is_listed"] = status_s.astype(str).eq("L") | list_status_s.astype(str).eq("L")
        meta["has_index"] = meta["index_code"].notna() & (meta["index_code"].astype(str).str.len() > 0) & (meta["index_code"].astype(str) != "nan")
        meta = meta[meta["is_stock_like"] & meta["is_listed"] & meta["has_index"]].copy()
        meta = meta.drop_duplicates("ts_code", keep="last")
        meta["ts_code"] = meta["ts_code"].astype(str)
        if "list_date" in meta.columns:
            list_date = meta["list_date"]
        elif "setup_date" in meta.columns:
            list_date = meta["setup_date"]
        elif "issue_date" in meta.columns:
            list_date = meta["issue_date"]
        else:
            list_date = pd.Series([pd.NA] * len(meta), index=meta.index)
        meta["list_date"] = pd.to_datetime(list_date.astype(str), errors="coerce")
        meta["theme_name"] = meta["index_name"].fillna(meta["fund_name"]).astype(str)
        meta["code"] = meta["ts_code"].apply(tushare_to_qlib)
        return meta[["ts_code", "code", "fund_name", "theme_name", "index_code", "index_name", "list_date"]].drop_duplicates()

    def codes(self) -> list[str]:
        return sorted(self.meta["code"].str.lower().tolist())

    def codes_for_theme(self, theme_name: str) -> list[str]:
        return sorted(self.meta.loc[self.meta["theme_name"] == theme_name, "code"].str.lower().tolist())

    def row_for_code(self, code: str) -> pd.Series:
        if self.meta.empty:
            return pd.Series(dtype=object)
        rows = self.meta[self.meta["code"].str.lower() == code.lower()]
        return rows.iloc[0] if not rows.empty else pd.Series(dtype=object)


class RealETFStore:
    """Point-in-time ETF market data built from Tushare caches."""

    def __init__(self, cache: SectorProsperityCache, universe: RealETFUniverse, start: str, end: str):
        self.cache = cache
        self.universe = universe
        daily = cache.etf_daily()
        share = cache.etf_share()
        if daily.empty:
            self.open = self.high = self.low = self.close = self.amount = pd.DataFrame()
            self.share = pd.DataFrame()
            self.calendar = pd.DatetimeIndex([])
            self.codes = universe.codes()
            return

        code_col = next((c for c in ["ts_code", "fund_code"] if c in daily.columns), None)
        if code_col is None:
            self.open = self.high = self.low = self.close = self.amount = pd.DataFrame()
            self.share = pd.DataFrame()
            self.calendar = pd.DatetimeIndex([])
            self.codes = universe.codes()
            return

        daily = daily.copy()
        daily["ts_code"] = daily[code_col].astype(str)
        daily["trade_date"] = pd.to_datetime(daily["trade_date"].astype(str), format="%Y%m%d", errors="coerce")
        daily = daily[(daily["trade_date"] >= pd.Timestamp(start)) & (daily["trade_date"] <= pd.Timestamp(end))].copy()
        codes = sorted(set(universe.meta["ts_code"].astype(str).tolist()) & set(daily["ts_code"].astype(str).tolist()))
        self.codes = [tushare_to_qlib(c) for c in codes]
        daily = daily[daily["ts_code"].isin(codes)].copy()

        self.open = _pivot_wide(daily, "trade_date", "ts_code", "open").rename(columns=tushare_to_qlib)
        self.high = _pivot_wide(daily, "trade_date", "ts_code", "high").rename(columns=tushare_to_qlib)
        self.low = _pivot_wide(daily, "trade_date", "ts_code", "low").rename(columns=tushare_to_qlib)
        self.close = _pivot_wide(daily, "trade_date", "ts_code", "close").rename(columns=tushare_to_qlib)
        self.amount = _pivot_wide(daily, "trade_date", "ts_code", "amount").rename(columns=tushare_to_qlib)

        if share is not None and not share.empty and "ts_code" in share.columns and "fd_share" in share.columns:
            share = share.copy()
            share["ts_code"] = share["ts_code"].astype(str)
            share["trade_date"] = pd.to_datetime(share["trade_date"].astype(str), format="%Y%m%d", errors="coerce")
            share = share[(share["trade_date"] >= pd.Timestamp(start)) & (share["trade_date"] <= pd.Timestamp(end))].copy()
            share = share[share["ts_code"].isin(codes)].copy()
            self.share = _pivot_wide(share, "trade_date", "ts_code", "fd_share").rename(columns=tushare_to_qlib)
        else:
            self.share = pd.DataFrame(index=self.close.index, columns=self.close.columns, dtype=float)

        self.calendar = self.close.index.intersection(self.amount.index)
        self.open = self.open.reindex(self.calendar)
        self.high = self.high.reindex(self.calendar)
        self.low = self.low.reindex(self.calendar)
        self.close = self.close.reindex(self.calendar)
        self.amount = self.amount.reindex(self.calendar)
        self.share = self.share.reindex(self.calendar)

        self.ma20 = self.close.rolling(20, min_periods=20).mean()
        self.ma60 = self.close.rolling(60, min_periods=60).mean()
        self.ret20 = self.close / self.close.shift(20) - 1.0
        self.ret60 = self.close / self.close.shift(60) - 1.0
        self.amount20 = self.amount.rolling(20, min_periods=20).mean()
        self.amount60 = self.amount.rolling(60, min_periods=60).mean()
        self.share_chg_5d = self.share / self.share.shift(5) - 1.0
        self.share_chg_20d = self.share / self.share.shift(20) - 1.0
        self.high20 = self.high.rolling(20, min_periods=20).max()
        self.high60 = self.high.rolling(60, min_periods=60).max()
        self.low10 = self.low.rolling(10, min_periods=10).min()
        self.high10_prev = self.high.rolling(10, min_periods=10).max().shift(1)
        self.volume = pd.DataFrame(index=self.amount.index, columns=self.amount.columns, dtype=float)
        self.amount5 = self.amount.rolling(5, min_periods=5).mean()

    def row(self, name: str, date: pd.Timestamp) -> pd.Series:
        return getattr(self, name).loc[date]

class MoneyFlowCache:
    """Optional 5-day moneyflow and top_inst enhancement from existing CSV caches."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.enrichment_dir = cache_dir / "enrichment"
        self.sector_dir = cache_dir / "sector_prosperity"
        self._moneyflow: pd.DataFrame | None = None
        self._top_inst: pd.DataFrame | None = None

    def _load_glob(self, directory: Path, pattern: str) -> pd.DataFrame:
        parts = []
        if directory.exists():
            for path in sorted(directory.glob(pattern)):
                try:
                    part = pd.read_csv(path, dtype={"ts_code": str})
                except (pd.errors.EmptyDataError, UnicodeDecodeError):
                    continue
                if not part.empty:
                    parts.append(part)
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    def moneyflow(self) -> pd.DataFrame:
        if self._moneyflow is None:
            self._moneyflow = pd.concat(
                [
                    self._load_glob(self.enrichment_dir, "moneyflow*.csv"),
                    self._load_glob(self.sector_dir, "moneyflow*.csv"),
                ],
                ignore_index=True,
            )
        return self._moneyflow

    def top_inst(self) -> pd.DataFrame:
        if self._top_inst is None:
            self._top_inst = self._load_glob(self.sector_dir, "top_inst*.csv")
        return self._top_inst

    def score(self, codes: list[str], data_date: pd.Timestamp, amount_5d: pd.Series) -> pd.Series:
        if not codes:
            return pd.Series(dtype=float)
        out = pd.Series(0.5, index=pd.Index(codes))
        ts_codes = [qlib_to_tushare(c) for c in codes]
        ts_to_code = dict(zip(ts_codes, codes))
        cutoff = data_date - pd.DateOffset(days=10)

        mf = self.moneyflow()
        if not mf.empty and "net_mf_amount" in mf.columns:
            dt = _date_col(mf, "trade_date", "fetch_date")
            recent = mf[(mf["ts_code"].isin(ts_codes)) & (dt <= data_date) & (dt >= cutoff)].copy()
            if not recent.empty:
                recent["code"] = recent["ts_code"].map(ts_to_code)
                raw = pd.to_numeric(recent["net_mf_amount"], errors="coerce").groupby(recent["code"]).sum()
                ratio = raw.reindex(codes).fillna(0.0) / amount_5d.reindex(codes).replace(0, np.nan)
                out = 0.75 * _rank01(ratio, ascending=True) + 0.25 * out

        inst = self.top_inst()
        if not inst.empty:
            dt = _date_col(inst, "trade_date", "fetch_date")
            recent = inst[(inst["ts_code"].isin(ts_codes)) & (dt <= data_date) & (dt >= data_date - pd.DateOffset(days=3))].copy()
            if not recent.empty:
                buy_col = next((c for c in ["buy", "buy_amount", "buy_amt"] if c in recent.columns), None)
                sell_col = next((c for c in ["sell", "sell_amount", "sell_amt"] if c in recent.columns), None)
                net_col = next((c for c in ["net_buy", "net_buy_amount", "net_amount"] if c in recent.columns), None)
                if net_col:
                    net = pd.to_numeric(recent[net_col], errors="coerce")
                elif buy_col and sell_col:
                    net = pd.to_numeric(recent[buy_col], errors="coerce") - pd.to_numeric(recent[sell_col], errors="coerce")
                else:
                    net = pd.Series(0.0, index=recent.index)
                recent["code"] = recent["ts_code"].map(ts_to_code)
                inst_score = (net.groupby(recent["code"]).sum().reindex(codes).fillna(0.0) > 0).astype(float)
                out = (out + inst_score) / 2.0
        return out.fillna(0.5)


def compute_theme_scores(
    close: pd.DataFrame,
    amount: pd.DataFrame,
    themes: pd.Series,
    data_date: pd.Timestamp,
    params: ThemeETFParams,
) -> pd.DataFrame:
    codes = [c for c in themes.index if c in close.columns]
    hist = close.loc[:data_date, codes].tail(121)
    amt_hist = amount.loc[:data_date, codes].tail(61)
    if len(hist) < 61 or hist.empty:
        return pd.DataFrame()

    latest = hist.iloc[-1]
    ma20 = hist.tail(20).mean()
    ma60 = hist.tail(60).mean()
    ret20 = _period_ret(hist, 20)
    ret60 = _period_ret(hist, 60)
    amount20 = amt_hist.tail(20).mean()
    amount60 = amt_hist.tail(60).mean()

    stock = pd.DataFrame(
        {
            "code": codes,
            "theme": themes.reindex(codes).fillna("UNKNOWN").values,
            "ret20": ret20.reindex(codes).values,
            "ret60": ret60.reindex(codes).values,
            "close_gt_ma20": (latest > ma20).astype(float).reindex(codes).values,
            "ma20_gt_ma60": (ma20 > ma60).astype(float).reindex(codes).values,
            "dist_ma60": (latest / ma60 - 1.0).reindex(codes).values,
            "amount20": amount20.reindex(codes).values,
            "amount60": amount60.reindex(codes).values,
        }
    )
    stock = stock[stock["theme"] != "UNKNOWN"].dropna(subset=["ret20", "ret60"])
    if stock.empty:
        return pd.DataFrame()

    theme = stock.groupby("theme", as_index=False).agg(
        member_count=("code", "count"),
        ret20=("ret20", "mean"),
        ret60=("ret60", "mean"),
        close_gt_ma20=("close_gt_ma20", "mean"),
        ma20_gt_ma60=("ma20_gt_ma60", "mean"),
        dist_ma60=("dist_ma60", "mean"),
        amount20=("amount20", "sum"),
        amount60=("amount60", "sum"),
    )
    theme["amount_ratio"] = theme["amount20"] / theme["amount60"].replace(0, np.nan)
    theme["liquidity_score"] = _rank01(np.log1p(theme["amount20"]), ascending=True)
    theme["trend_score"] = (
        0.5 * _rank01(theme["ret20"], ascending=True)
        + 0.3 * _rank01(theme["ret60"], ascending=True)
        + 0.2 * _rank01(theme["dist_ma60"], ascending=True)
    )
    theme["flow_score"] = (
        0.5 * _rank01(theme["amount_ratio"], ascending=True)
        + 0.3 * _rank01(theme["close_gt_ma20"], ascending=True)
        + 0.2 * _rank01(theme["ma20_gt_ma60"], ascending=True)
    )
    crowd_penalty = (
        0.4 * _rank01(theme["ret20"], ascending=True)
        + 0.3 * _rank01(theme["dist_ma60"], ascending=True)
        + 0.3 * _rank01(theme["amount_ratio"], ascending=True)
    )
    theme["crowding_penalty"] = np.where(theme["dist_ma60"] > params.max_theme_dist_ma60, 0.20 * crowd_penalty, 0.0)
    theme["etf_score"] = (
        0.35 * theme["liquidity_score"]
        + 0.35 * theme["trend_score"]
        + 0.30 * theme["flow_score"]
        - theme["crowding_penalty"]
    )
    theme["trend_ok"] = (theme["close_gt_ma20"] >= 0.55) & (theme["ma20_gt_ma60"] >= 0.55)
    theme["flow_ok"] = theme["amount_ratio"] > 1.0
    theme["selected_filter"] = (
        (theme["amount20"] > params.min_theme_amount_20d)
        & theme["trend_ok"]
        & (theme["ret20"] > params.min_theme_ret20)
        & (theme["ret60"] > params.min_theme_ret60)
        & theme["flow_ok"]
        & (theme["dist_ma60"] <= params.max_theme_dist_ma60)
    )
    theme = theme.sort_values("etf_score", ascending=False).reset_index(drop=True)
    theme["theme_rank"] = theme.index + 1
    return theme


def select_themes(theme_scores: pd.DataFrame, params: ThemeETFParams) -> pd.DataFrame:
    if theme_scores.empty:
        return theme_scores
    filtered = theme_scores[theme_scores["selected_filter"]].copy()
    if filtered.empty:
        filtered = theme_scores.head(max(params.etf_count, 1)).copy()
    pct_n = max(1, int(np.ceil(len(theme_scores) * params.theme_top_pct)))
    return filtered.head(max(params.etf_count, pct_n)).head(params.etf_count).copy()


def compute_real_etf_scores(
    store: RealETFStore,
    meta: pd.DataFrame,
    data_date: pd.Timestamp,
    params: ThemeETFParams,
) -> pd.DataFrame:
    codes = [c for c in meta["code"].astype(str).str.lower().tolist() if c in store.close.columns]
    if not codes:
        return pd.DataFrame()
    latest = store.row("close", data_date).reindex(codes)
    ma20 = store.row("ma20", data_date).reindex(codes)
    ma60 = store.row("ma60", data_date).reindex(codes)
    ret20 = store.row("ret20", data_date).reindex(codes)
    ret60 = store.row("ret60", data_date).reindex(codes)
    amount20 = store.row("amount20", data_date).reindex(codes)
    amount60 = store.row("amount60", data_date).reindex(codes)
    share_chg_5d = store.row("share_chg_5d", data_date).reindex(codes)
    share_chg_20d = store.row("share_chg_20d", data_date).reindex(codes)

    df = meta.copy()
    df["code"] = df["code"].astype(str).str.lower()
    df = df[df["code"].isin(codes)].copy()
    df["latest_close"] = df["code"].map(latest)
    df["ma20"] = df["code"].map(ma20)
    df["ma60"] = df["code"].map(ma60)
    df["ret20"] = df["code"].map(ret20)
    df["ret60"] = df["code"].map(ret60)
    df["amount20"] = df["code"].map(amount20)
    df["amount60"] = df["code"].map(amount60)
    df["share_chg_5d"] = df["code"].map(share_chg_5d)
    df["share_chg_20d"] = df["code"].map(share_chg_20d)
    df["theme"] = df["code"]
    df["theme_name"] = df["theme_name"].fillna(df["fund_name"])
    df["liquidity_score"] = _rank01(np.log1p(df["amount20"]), ascending=True)
    df["trend_score"] = (
        0.5 * _rank01(df["ret20"], ascending=True)
        + 0.3 * _rank01(df["ret60"], ascending=True)
        + 0.2 * _rank01(df["latest_close"] / df["ma60"] - 1.0, ascending=True)
    )
    df["flow_score"] = (
        0.4 * _rank01(df["share_chg_5d"], ascending=True)
        + 0.4 * _rank01(df["share_chg_20d"], ascending=True)
        + 0.2 * _rank01(df["amount20"] / df["amount60"].replace(0, np.nan), ascending=True)
    )
    crowding = (
        0.4 * _rank01(df["ret20"], ascending=True)
        + 0.3 * _rank01(df["latest_close"] / df["ma60"] - 1.0, ascending=True)
        + 0.3 * _rank01(df["amount20"] / df["amount60"].replace(0, np.nan), ascending=True)
    )
    df["crowding_penalty"] = np.where((df["latest_close"] / df["ma60"] - 1.0) > params.max_theme_dist_ma60, 0.20 * crowding, 0.0)
    df["etf_score"] = 0.35 * df["liquidity_score"] + 0.35 * df["trend_score"] + 0.30 * df["flow_score"] - df["crowding_penalty"]
    df["trend_ok"] = (df["latest_close"] > df["ma20"]) & (df["ma20"] > df["ma60"])
    df["flow_ok"] = (df["share_chg_20d"] > 0) & (df["amount20"] / df["amount60"].replace(0, np.nan) > 1.0)
    df["selected_filter"] = (
        (df["amount20"] > params.min_theme_amount_20d)
        & df["trend_ok"]
        & (df["ret20"] > params.min_theme_ret20)
        & (df["ret60"] > params.min_theme_ret60)
        & df["flow_ok"]
        & ((df["latest_close"] / df["ma60"] - 1.0) <= params.max_theme_dist_ma60)
    )
    df = df.sort_values("etf_score", ascending=False).reset_index(drop=True)
    df["theme_rank"] = df.index + 1
    return df


def build_real_candidate_pool(
    store: RealETFStore,
    real_cache: SectorProsperityCache,
    selected_etfs: pd.DataFrame,
    data_date: pd.Timestamp,
    daily_basic: pd.DataFrame,
    stock_basic: pd.DataFrame,
    start: str,
    end: str,
    params: ThemeETFParams,
) -> pd.DataFrame:
    if selected_etfs.empty:
        return pd.DataFrame()
    rows = []
    selected = selected_etfs.copy()
    selected["code"] = selected["code"].astype(str).str.lower()
    selected_map = selected.set_index("code")
    stock_name_map = {}
    stock_list_date_map = {}
    if stock_basic is not None and not stock_basic.empty and "ts_code" in stock_basic.columns:
        sb = stock_basic.copy()
        sb["code"] = sb["ts_code"].astype(str).apply(tushare_to_qlib)
        stock_name_map = dict(zip(sb["code"].str.lower(), sb.get("name", pd.Series(index=sb.index, dtype=object)).fillna("").tolist()))
        if "list_date" in sb.columns:
            stock_list_date_map = dict(zip(sb["code"].str.lower(), pd.to_datetime(sb["list_date"].astype(str), errors="coerce")))
    for row in selected.itertuples(index=False):
        etf_code = row.code
        theme_name = getattr(row, "theme_name", etf_code)
        index_code = getattr(row, "index_code", np.nan)
        if pd.isna(index_code) or not str(index_code):
            continue
        weights = real_cache.index_weight(str(index_code), start, end)
        if weights.empty or "con_code" not in weights.columns:
            continue
        w = weights.copy()
        if "trade_date" in w.columns:
            w["trade_date"] = pd.to_datetime(w["trade_date"].astype(str), format="%Y%m%d", errors="coerce")
            w = w[w["trade_date"] <= data_date].copy()
            if w.empty:
                continue
            latest_dt = w["trade_date"].max()
            w = w[w["trade_date"] == latest_dt].copy()
        w["code"] = w["con_code"].astype(str).apply(tushare_to_qlib)
        if "weight" not in w.columns:
            w["weight"] = np.nan
        w["theme"] = etf_code
        w["theme_name"] = theme_name
        w["theme_score"] = float(selected_map.loc[etf_code, "etf_score"]) if etf_code in selected_map.index else np.nan
        w["theme_ret20"] = float(selected_map.loc[etf_code, "ret20"]) if etf_code in selected_map.index else np.nan
        w["theme_ret60"] = float(selected_map.loc[etf_code, "ret60"]) if etf_code in selected_map.index else np.nan
        rows.append(w[["code", "theme", "theme_name", "theme_score", "theme_ret20", "theme_ret60", "weight"]])
    if not rows:
        return pd.DataFrame()
    pool = pd.concat(rows, ignore_index=True).dropna(subset=["code"]).copy()
    pool = pool.drop_duplicates(["code", "theme"], keep="first")
    pool["latest_close"] = store.row("close", data_date).reindex(pool["code"].tolist()).values
    pool["ma20"] = store.row("ma20", data_date).reindex(pool["code"].tolist()).values
    pool["ma60"] = store.row("ma60", data_date).reindex(pool["code"].tolist()).values
    pool["ret20"] = store.row("ret20", data_date).reindex(pool["code"].tolist()).values
    pool["ret60"] = store.row("ret60", data_date).reindex(pool["code"].tolist()).values
    pool["amount20"] = store.row("amount20", data_date).reindex(pool["code"].tolist()).values
    if not daily_basic.empty and "ts_code" in daily_basic.columns:
        db = daily_basic.copy()
        db["code"] = db["ts_code"].astype(str).apply(tushare_to_qlib)
        db = db.drop_duplicates("code", keep="last").set_index("code")
        for col in ["turnover_rate", "total_mv", "circ_mv", "pe_ttm", "pb"]:
            pool[col] = db[col].reindex(pool["code"]).values if col in db.columns else np.nan
    pool["name"] = pool["code"].map(stock_name_map).fillna("")
    pool["list_date"] = pool["code"].map(stock_list_date_map)
    pool["list_days"] = (data_date - pd.to_datetime(pool["list_date"], errors="coerce")).dt.days
    raw_code = pool["code"].str[2:]
    keep = (
        (pool["list_days"] >= params.min_list_days)
        & ~raw_code.str.startswith(("4", "8"))
        & ~pool["name"].fillna("").str.contains("ST|退|\\*", regex=True)
        & (pool["amount20"] > params.min_stock_amount_20d)
        & (pool["latest_close"] > pool["ma20"])
        & (pool["ma20"] > pool["ma60"])
    )
    if "turnover_rate" in pool.columns and pool["turnover_rate"].notna().any():
        keep &= pool["turnover_rate"].fillna(0) >= params.min_turnover_20d
    if "total_mv" in pool.columns and pool["total_mv"].notna().any():
        keep &= pool["total_mv"].fillna(0) >= params.allow_min_total_mv
    pool = pool[keep].copy()
    if pool.empty:
        return pool
    sort_col = "total_mv" if "total_mv" in pool.columns and pool["total_mv"].notna().any() else "amount20"
    pool = (
        pool.sort_values(["theme", sort_col], ascending=[True, False])
        .groupby("theme", as_index=False)
        .head(params.constituents_per_theme)
        .reset_index(drop=True)
    )
    return pool


def compute_theme_scores_fast(
    store: RollingFeatureStore,
    themes: pd.Series,
    data_date: pd.Timestamp,
    params: ThemeETFParams,
) -> pd.DataFrame:
    codes = [c for c in themes.index if c in store.codes]
    if not codes:
        return pd.DataFrame()
    latest = store.row("close", data_date).reindex(codes)
    ma20 = store.row("ma20", data_date).reindex(codes)
    ma60 = store.row("ma60", data_date).reindex(codes)
    stock = pd.DataFrame(
        {
            "code": codes,
            "theme": themes.reindex(codes).fillna("UNKNOWN").values,
            "ret20": store.row("ret20", data_date).reindex(codes).values,
            "ret60": store.row("ret60", data_date).reindex(codes).values,
            "close_gt_ma20": (latest > ma20).astype(float).values,
            "ma20_gt_ma60": (ma20 > ma60).astype(float).values,
            "dist_ma60": (latest / ma60 - 1.0).values,
            "amount20": store.row("amount20", data_date).reindex(codes).values,
            "amount60": store.row("amount60", data_date).reindex(codes).values,
        }
    )
    stock = stock[stock["theme"] != "UNKNOWN"].dropna(subset=["ret20", "ret60"])
    if stock.empty:
        return pd.DataFrame()
    theme = stock.groupby("theme", as_index=False).agg(
        member_count=("code", "count"),
        ret20=("ret20", "mean"),
        ret60=("ret60", "mean"),
        close_gt_ma20=("close_gt_ma20", "mean"),
        ma20_gt_ma60=("ma20_gt_ma60", "mean"),
        dist_ma60=("dist_ma60", "mean"),
        amount20=("amount20", "sum"),
        amount60=("amount60", "sum"),
    )
    theme["amount_ratio"] = theme["amount20"] / theme["amount60"].replace(0, np.nan)
    theme["liquidity_score"] = _rank01(np.log1p(theme["amount20"]), ascending=True)
    theme["trend_score"] = (
        0.5 * _rank01(theme["ret20"], ascending=True)
        + 0.3 * _rank01(theme["ret60"], ascending=True)
        + 0.2 * _rank01(theme["dist_ma60"], ascending=True)
    )
    theme["flow_score"] = (
        0.5 * _rank01(theme["amount_ratio"], ascending=True)
        + 0.3 * _rank01(theme["close_gt_ma20"], ascending=True)
        + 0.2 * _rank01(theme["ma20_gt_ma60"], ascending=True)
    )
    crowd_penalty = (
        0.4 * _rank01(theme["ret20"], ascending=True)
        + 0.3 * _rank01(theme["dist_ma60"], ascending=True)
        + 0.3 * _rank01(theme["amount_ratio"], ascending=True)
    )
    theme["crowding_penalty"] = np.where(theme["dist_ma60"] > params.max_theme_dist_ma60, 0.20 * crowd_penalty, 0.0)
    theme["etf_score"] = (
        0.35 * theme["liquidity_score"]
        + 0.35 * theme["trend_score"]
        + 0.30 * theme["flow_score"]
        - theme["crowding_penalty"]
    )
    theme["trend_ok"] = (theme["close_gt_ma20"] >= 0.55) & (theme["ma20_gt_ma60"] >= 0.55)
    theme["flow_ok"] = theme["amount_ratio"] > 1.0
    theme["selected_filter"] = (
        (theme["amount20"] > params.min_theme_amount_20d)
        & theme["trend_ok"]
        & (theme["ret20"] > params.min_theme_ret20)
        & (theme["ret60"] > params.min_theme_ret60)
        & theme["flow_ok"]
        & (theme["dist_ma60"] <= params.max_theme_dist_ma60)
    )
    theme = theme.sort_values("etf_score", ascending=False).reset_index(drop=True)
    theme["theme_rank"] = theme.index + 1
    return theme


def build_candidate_pool_fast(
    store: RollingFeatureStore,
    theme_universe: ThemeUniverse,
    selected_themes: pd.DataFrame,
    data_date: pd.Timestamp,
    daily_basic: pd.DataFrame,
    params: ThemeETFParams,
) -> pd.DataFrame:
    if selected_themes.empty:
        return pd.DataFrame()
    selected_map = selected_themes.set_index("theme")
    selected_codes = sorted(
        {
            code
            for theme_name in selected_map.index
            for code in theme_universe.codes_for_theme(theme_name)
            if code in store.codes
        }
    )
    if not selected_codes:
        return pd.DataFrame()

    theme_by_code = {
        code: theme_name
        for theme_name in selected_map.index
        for code in theme_universe.codes_for_theme(theme_name)
    }
    pool = pd.DataFrame(
        {
            "code": selected_codes,
            "theme": [theme_by_code[c] for c in selected_codes],
            "latest_close": store.row("close", data_date).reindex(selected_codes).values,
            "ma20": store.row("ma20", data_date).reindex(selected_codes).values,
            "ma60": store.row("ma60", data_date).reindex(selected_codes).values,
            "ret20": store.row("ret20", data_date).reindex(selected_codes).values,
            "ret60": store.row("ret60", data_date).reindex(selected_codes).values,
            "amount20": store.row("amount20", data_date).reindex(selected_codes).values,
            "name": theme_universe.name.reindex(selected_codes).fillna("").values,
            "list_date": theme_universe.list_date.reindex(selected_codes).values,
        }
    )
    pool["theme_score"] = pool["theme"].map(selected_map["etf_score"])
    pool["theme_ret20"] = pool["theme"].map(selected_map["ret20"])
    pool["theme_ret60"] = pool["theme"].map(selected_map["ret60"])

    db = daily_basic.copy() if daily_basic is not None and not daily_basic.empty else pd.DataFrame()
    if not db.empty and "ts_code" in db.columns:
        db["code"] = db["ts_code"].astype(str).apply(tushare_to_qlib)
        db = db.drop_duplicates("code", keep="last").set_index("code")
        for col in ["turnover_rate", "total_mv", "circ_mv", "pe_ttm", "pb"]:
            pool[col] = db[col].reindex(selected_codes).values if col in db.columns else np.nan

    pool["list_days"] = (data_date - pd.to_datetime(pool["list_date"], errors="coerce")).dt.days
    raw_code = pool["code"].str[2:]
    keep = (
        (pool["list_days"] >= params.min_list_days)
        & ~raw_code.str.startswith(("4", "8"))
        & ~pool["name"].fillna("").str.contains("ST|退|\\*", regex=True)
        & (pool["amount20"] > params.min_stock_amount_20d)
        & (pool["latest_close"] > pool["ma20"])
        & (pool["ma20"] > pool["ma60"])
    )
    if "turnover_rate" in pool.columns and pool["turnover_rate"].notna().any():
        keep &= pool["turnover_rate"].fillna(0) >= params.min_turnover_20d
    if "total_mv" in pool.columns and pool["total_mv"].notna().any():
        keep &= pool["total_mv"].fillna(0) >= params.allow_min_total_mv
    pool = pool[keep].copy()
    if pool.empty:
        return pool
    sort_col = "total_mv" if "total_mv" in pool.columns and pool["total_mv"].notna().any() else "amount20"
    return (
        pool.sort_values(["theme", sort_col], ascending=[True, False])
        .groupby("theme", as_index=False)
        .head(params.constituents_per_theme)
        .reset_index(drop=True)
    )


def build_candidate_pool(
    frames: DailyFrames,
    theme_universe: ThemeUniverse,
    selected_themes: pd.DataFrame,
    data_date: pd.Timestamp,
    daily_basic: pd.DataFrame,
    params: ThemeETFParams,
) -> pd.DataFrame:
    rows = []
    if selected_themes.empty:
        return pd.DataFrame()
    codes_all = [c for c in theme_universe.industry.index if c in frames.close.columns]
    hist_close = frames.close.loc[:data_date, codes_all].tail(61)
    hist_amount = frames.amount.loc[:data_date, codes_all].tail(20)
    if len(hist_close) < 61:
        return pd.DataFrame()
    latest = hist_close.iloc[-1]
    ma20 = hist_close.tail(20).mean()
    ma60 = hist_close.tail(60).mean()
    amount20 = hist_amount.mean()
    ret20 = _period_ret(hist_close, 20)
    ret60 = _period_ret(hist_close, 60)

    db = daily_basic.copy() if daily_basic is not None and not daily_basic.empty else pd.DataFrame()
    if not db.empty and "ts_code" in db.columns:
        db["code"] = db["ts_code"].astype(str).apply(tushare_to_qlib)
        db = db.drop_duplicates("code", keep="last").set_index("code")
    selected_map = selected_themes.set_index("theme")
    for theme_name, theme_row in selected_map.iterrows():
        codes = [c for c in theme_universe.codes_for_theme(theme_name) if c in latest.index]
        if not codes:
            continue
        part = pd.DataFrame(
            {
                "code": codes,
                "theme": theme_name,
                "theme_score": theme_row["etf_score"],
                "theme_ret20": theme_row["ret20"],
                "theme_ret60": theme_row["ret60"],
                "latest_close": latest.reindex(codes).values,
                "ma20": ma20.reindex(codes).values,
                "ma60": ma60.reindex(codes).values,
                "ret20": ret20.reindex(codes).values,
                "ret60": ret60.reindex(codes).values,
                "amount20": amount20.reindex(codes).values,
                "name": theme_universe.name.reindex(codes).fillna("").values,
                "list_date": theme_universe.list_date.reindex(codes).values,
            }
        )
        if not db.empty:
            for col in ["turnover_rate", "total_mv", "circ_mv", "pe_ttm", "pb"]:
                part[col] = db[col].reindex(codes).values if col in db.columns else np.nan
        rows.append(part)
    if not rows:
        return pd.DataFrame()
    pool = pd.concat(rows, ignore_index=True).drop_duplicates("code", keep="first")
    pool["list_days"] = (data_date - pd.to_datetime(pool["list_date"], errors="coerce")).dt.days
    raw_code = pool["code"].str[2:]
    keep = (
        (pool["list_days"] >= params.min_list_days)
        & ~raw_code.str.startswith(("4", "8"))
        & ~pool["name"].fillna("").str.contains("ST|退|\\*", regex=True)
        & (pool["amount20"] > params.min_stock_amount_20d)
        & (pool["latest_close"] > pool["ma20"])
        & (pool["ma20"] > pool["ma60"])
    )
    if "turnover_rate" in pool.columns and pool["turnover_rate"].notna().any():
        keep &= pool["turnover_rate"].fillna(0) >= params.min_turnover_20d
    if "total_mv" in pool.columns and pool["total_mv"].notna().any():
        keep &= pool["total_mv"].fillna(0) >= params.allow_min_total_mv
    pool = pool[keep].copy()
    if pool.empty:
        return pool
    sort_col = "total_mv" if "total_mv" in pool.columns and pool["total_mv"].notna().any() else "amount20"
    pool = (
        pool.sort_values(["theme", sort_col], ascending=[True, False])
        .groupby("theme", as_index=False)
        .head(params.constituents_per_theme)
        .reset_index(drop=True)
    )
    return pool


def score_stock_pool(
    pool: pd.DataFrame,
    frames: DailyFrames,
    data_date: pd.Timestamp,
    moneyflow: MoneyFlowCache | None,
    params: ThemeETFParams,
) -> pd.DataFrame:
    if pool.empty:
        return pool
    codes = [c for c in pool["code"].tolist() if c in frames.close.columns]
    hist_close = frames.close.loc[:data_date, codes].tail(61)
    hist_high = frames.high.loc[:data_date, codes].tail(21)
    hist_low = frames.low.loc[:data_date, codes].tail(11)
    hist_vol = frames.volume.loc[:data_date, codes].tail(21)
    hist_amt = frames.amount.loc[:data_date, codes].tail(5)
    if len(hist_close) < 61:
        return pd.DataFrame()

    latest = hist_close.iloc[-1]
    ma20 = hist_close.tail(20).mean()
    ma60 = hist_close.tail(60).mean()
    high20 = hist_high.max()
    high10_prev = hist_high.tail(11).iloc[:-1].max()
    low10 = hist_low.min()
    ret = hist_close.pct_change(fill_method=None)
    ret20 = _period_ret(hist_close, 20)
    ret60 = _period_ret(hist_close, 60)
    vol20 = ret.tail(20).std()

    df = pool.set_index("code").reindex(codes).copy()
    df["ret20"] = ret20.reindex(codes)
    df["ret60"] = ret60.reindex(codes)
    df["ma20"] = ma20.reindex(codes)
    df["ma60"] = ma60.reindex(codes)
    df["high20"] = high20.reindex(codes)
    df["high10_prev"] = high10_prev.reindex(codes)
    df["range10"] = (high10_prev / low10.reindex(codes) - 1.0)
    df["rs20"] = df["ret20"] - df["theme_ret20"]
    df["rs60"] = df["ret60"] - df["theme_ret60"]
    df["rsir20"] = df["rs20"] / vol20.reindex(codes).replace(0, np.nan)
    df["dist_ma20"] = latest.reindex(codes) / df["ma20"] - 1.0
    df["dist_ma60"] = latest.reindex(codes) / df["ma60"] - 1.0
    df["dist_high20"] = latest.reindex(codes) / df["high20"] - 1.0
    df["stock_rs_score"] = (
        0.5 * _rank01(df["rs20"], ascending=True)
        + 0.3 * _rank01(df["rs60"], ascending=True)
        + 0.2 * _rank01(df["rsir20"], ascending=True)
    )
    df["trend_score"] = _rank01(df["ret60"], ascending=True)
    df["pullback_score"] = _rank01(-df["dist_ma20"].abs(), ascending=True)
    df["breakout_score"] = _rank01(latest.reindex(codes) / high20.reindex(codes), ascending=True)
    df["structure_score"] = 0.4 * df["trend_score"] + 0.3 * df["pullback_score"] + 0.3 * df["breakout_score"]
    amount_5d = hist_amt.mean()
    df["moneyflow_score"] = moneyflow.score(codes, data_date, amount_5d) if moneyflow else 0.5
    df["final_score"] = (
        0.30 * df["theme_score"]
        + 0.35 * df["stock_rs_score"]
        + 0.20 * df["structure_score"]
        + 0.15 * df["moneyflow_score"]
    )
    df["rs_ok"] = (df["rs20"] > 0) & (df["rs60"] > 0)
    df["trend_ok"] = (latest.reindex(codes) > df["ma20"]) & (df["ma20"] > df["ma60"])
    df["not_overheated"] = (df["dist_ma20"] < params.max_dist_ma20) & (df["dist_ma60"] < params.max_dist_ma60)
    df["pullback_zone"] = (
        (df["dist_high20"] > params.pullback_high_min)
        & (df["dist_high20"] < params.pullback_high_max)
        & (df["dist_ma20"] > params.pullback_ma20_min)
        & (df["dist_ma20"] < params.pullback_ma20_max)
    )
    df = df.reset_index()
    return df


def score_stock_pool_fast(
    pool: pd.DataFrame,
    store: RollingFeatureStore,
    data_date: pd.Timestamp,
    moneyflow: MoneyFlowCache | None,
    params: ThemeETFParams,
) -> pd.DataFrame:
    if pool.empty:
        return pool
    codes = [c for c in pool["code"].tolist() if c in store.codes]
    if not codes:
        return pd.DataFrame()
    latest = store.row("close", data_date).reindex(codes)
    high20 = store.row("high20", data_date).reindex(codes)
    high10_prev = store.row("high10_prev", data_date).reindex(codes)
    low10 = store.row("low10", data_date).reindex(codes)
    vol20 = store.row("vol20", data_date).reindex(codes)

    df = pool.set_index("code").reindex(codes).copy()
    df["ret20"] = store.row("ret20", data_date).reindex(codes)
    df["ret60"] = store.row("ret60", data_date).reindex(codes)
    df["ma20"] = store.row("ma20", data_date).reindex(codes)
    df["ma60"] = store.row("ma60", data_date).reindex(codes)
    df["high20"] = high20
    df["high10_prev"] = high10_prev
    df["range10"] = high10_prev / low10.replace(0, np.nan) - 1.0
    df["rs20"] = df["ret20"] - df["theme_ret20"]
    df["rs60"] = df["ret60"] - df["theme_ret60"]
    df["rsir20"] = df["rs20"] / vol20.replace(0, np.nan)
    df["dist_ma20"] = latest / df["ma20"] - 1.0
    df["dist_ma60"] = latest / df["ma60"] - 1.0
    df["dist_high20"] = latest / high20.replace(0, np.nan) - 1.0
    df["stock_rs_score"] = (
        0.5 * _rank01(df["rs20"], ascending=True)
        + 0.3 * _rank01(df["rs60"], ascending=True)
        + 0.2 * _rank01(df["rsir20"], ascending=True)
    )
    df["trend_score"] = _rank01(df["ret60"], ascending=True)
    df["pullback_score"] = _rank01(-df["dist_ma20"].abs(), ascending=True)
    df["breakout_score"] = _rank01(latest / high20.replace(0, np.nan), ascending=True)
    df["structure_score"] = 0.4 * df["trend_score"] + 0.3 * df["pullback_score"] + 0.3 * df["breakout_score"]
    amount_5d = store.row("amount5", data_date).reindex(codes)
    df["moneyflow_score"] = moneyflow.score(codes, data_date, amount_5d) if moneyflow else 0.5
    df["final_score"] = (
        0.30 * df["theme_score"]
        + 0.35 * df["stock_rs_score"]
        + 0.20 * df["structure_score"]
        + 0.15 * df["moneyflow_score"]
    )
    df["rs_ok"] = (df["rs20"] > 0) & (df["rs60"] > 0)
    df["trend_ok"] = (latest > df["ma20"]) & (df["ma20"] > df["ma60"])
    df["not_overheated"] = (df["dist_ma20"] < params.max_dist_ma20) & (df["dist_ma60"] < params.max_dist_ma60)
    df["pullback_zone"] = (
        (df["dist_high20"] > params.pullback_high_min)
        & (df["dist_high20"] < params.pullback_high_max)
        & (df["dist_ma20"] > params.pullback_ma20_min)
        & (df["dist_ma20"] < params.pullback_ma20_max)
    )
    return df.reset_index()


def add_buy_signals(pool: pd.DataFrame, frames: DailyFrames, data_date: pd.Timestamp) -> pd.DataFrame:
    if pool.empty:
        return pool
    codes = [c for c in pool["code"].tolist() if c in frames.close.columns]
    hist_close = frames.close.loc[:data_date, codes].tail(21)
    hist_open = frames.open.loc[:data_date, codes].tail(2)
    hist_low = frames.low.loc[:data_date, codes].tail(2)
    hist_high = frames.high.loc[:data_date, codes].tail(11)
    hist_volume = frames.volume.loc[:data_date, codes].tail(21)
    if len(hist_close) < 21 or len(hist_open) < 2:
        pool["buy_signal_a"] = False
        pool["buy_signal_b"] = False
        return pool
    close = hist_close.iloc[-1]
    prev_close = hist_close.iloc[-2]
    open_ = hist_open.iloc[-1]
    low = hist_low.iloc[-1]
    volume = hist_volume.iloc[-1]
    volume_ma5 = hist_volume.tail(5).mean()
    volume_ma20 = hist_volume.tail(20).mean()
    prev_volume_ma5 = hist_volume.iloc[-6:-1].mean()
    prev_volume_ma20 = hist_volume.iloc[-21:-6].mean()
    pct_chg = close / prev_close - 1.0
    ma20 = hist_close.tail(20).mean()
    ma60 = frames.close.loc[:data_date, codes].tail(60).mean()
    high10_prev = hist_high.iloc[:-1].max()

    signal_a = (
        (close > ma20)
        & (ma20 > ma60)
        & (low <= ma20 * 1.03)
        & (close > open_)
        & (pct_chg > 0.02)
        & (volume > 1.5 * volume_ma5)
        & (prev_volume_ma5 < prev_volume_ma20)
    )
    signal_b = (
        (close > high10_prev)
        & (volume > 1.5 * volume_ma20)
        & (pct_chg > 0.02)
        & (close > ma20)
        & (ma20 > ma60)
    )
    out = pool.copy()
    out["buy_signal_a"] = out["code"].map(signal_a.fillna(False).to_dict()).fillna(False).astype(bool)
    out["buy_signal_b"] = out["code"].map(signal_b.fillna(False).to_dict()).fillna(False).astype(bool)
    out["buy_signal"] = out["buy_signal_a"] | out["buy_signal_b"]
    return out


def add_buy_signals_fast(pool: pd.DataFrame, store: RollingFeatureStore, data_date: pd.Timestamp) -> pd.DataFrame:
    if pool.empty:
        return pool
    codes = [c for c in pool["code"].tolist() if c in store.codes]
    if not codes:
        out = pool.copy()
        out["buy_signal_a"] = False
        out["buy_signal_b"] = False
        out["buy_signal"] = False
        return out

    close = store.row("close", data_date).reindex(codes)
    prev_close = store.close.shift(1).loc[data_date].reindex(codes)
    open_ = store.row("open", data_date).reindex(codes)
    low = store.row("low", data_date).reindex(codes)
    volume = store.row("volume", data_date).reindex(codes)
    ma20 = store.row("ma20", data_date).reindex(codes)
    ma60 = store.row("ma60", data_date).reindex(codes)
    pct_chg = store.row("pct_chg", data_date).reindex(codes)
    volume_ma5 = store.row("volume_ma5", data_date).reindex(codes)
    volume_ma20 = store.row("volume_ma20", data_date).reindex(codes)
    prev_volume_ma5 = store.row("prev_volume_ma5", data_date).reindex(codes)
    prev_volume_ma20 = store.row("prev_volume_ma20", data_date).reindex(codes)
    high10_prev = store.row("high10_prev", data_date).reindex(codes)

    signal_a = (
        (close > ma20)
        & (ma20 > ma60)
        & (low <= ma20 * 1.03)
        & (close > open_)
        & (pct_chg > 0.02)
        & (volume > 1.5 * volume_ma5)
        & (prev_volume_ma5 < prev_volume_ma20)
    )
    signal_b = (
        (close > high10_prev)
        & (volume > 1.5 * volume_ma20)
        & (pct_chg > 0.02)
        & (close > ma20)
        & (ma20 > ma60)
    )
    out = pool.copy()
    out["buy_signal_a"] = out["code"].map(signal_a.fillna(False).to_dict()).fillna(False).astype(bool)
    out["buy_signal_b"] = out["code"].map(signal_b.fillna(False).to_dict()).fillna(False).astype(bool)
    out["buy_signal"] = out["buy_signal_a"] | out["buy_signal_b"]
    return out


def compute_real_etf_scores(
    store: RealETFStore,
    meta: pd.DataFrame,
    data_date: pd.Timestamp,
    params: ThemeETFParams,
) -> pd.DataFrame:
    codes = [c for c in meta["code"].astype(str).str.lower().tolist() if c in store.close.columns]
    if not codes:
        return pd.DataFrame()
    latest = store.row("close", data_date).reindex(codes)
    ma20 = store.row("ma20", data_date).reindex(codes)
    ma60 = store.row("ma60", data_date).reindex(codes)
    ret20 = store.row("ret20", data_date).reindex(codes)
    ret60 = store.row("ret60", data_date).reindex(codes)
    amount20 = store.row("amount20", data_date).reindex(codes)
    amount60 = store.row("amount60", data_date).reindex(codes)
    share_chg_5d = store.row("share_chg_5d", data_date).reindex(codes)
    share_chg_20d = store.row("share_chg_20d", data_date).reindex(codes)

    df = meta.copy()
    df["code"] = df["code"].astype(str).str.lower()
    df = df[df["code"].isin(codes)].copy()
    df["latest_close"] = df["code"].map(latest)
    df["ma20"] = df["code"].map(ma20)
    df["ma60"] = df["code"].map(ma60)
    df["ret20"] = df["code"].map(ret20)
    df["ret60"] = df["code"].map(ret60)
    df["amount20"] = df["code"].map(amount20)
    df["amount60"] = df["code"].map(amount60)
    df["share_chg_5d"] = df["code"].map(share_chg_5d)
    df["share_chg_20d"] = df["code"].map(share_chg_20d)
    df["theme"] = df["code"]
    df["liquidity_score"] = _rank01(np.log1p(df["amount20"]), ascending=True)
    df["trend_score"] = (
        0.5 * _rank01(df["ret20"], ascending=True)
        + 0.3 * _rank01(df["ret60"], ascending=True)
        + 0.2 * _rank01(df["latest_close"] / df["ma60"] - 1.0, ascending=True)
    )
    df["flow_score"] = (
        0.4 * _rank01(df["share_chg_5d"], ascending=True)
        + 0.4 * _rank01(df["share_chg_20d"], ascending=True)
        + 0.2 * _rank01(df["amount20"] / df["amount60"].replace(0, np.nan), ascending=True)
    )
    crowding = (
        0.4 * _rank01(df["ret20"], ascending=True)
        + 0.3 * _rank01(df["latest_close"] / df["ma60"] - 1.0, ascending=True)
        + 0.3 * _rank01(df["amount20"] / df["amount60"].replace(0, np.nan), ascending=True)
    )
    df["crowding_penalty"] = np.where((df["latest_close"] / df["ma60"] - 1.0) > params.max_theme_dist_ma60, 0.20 * crowding, 0.0)
    df["etf_score"] = 0.35 * df["liquidity_score"] + 0.35 * df["trend_score"] + 0.30 * df["flow_score"] - df["crowding_penalty"]
    df["trend_ok"] = (df["latest_close"] > df["ma20"]) & (df["ma20"] > df["ma60"])
    df["flow_ok"] = (df["share_chg_20d"] > 0) & (df["amount20"] / df["amount60"].replace(0, np.nan) > 1.0)
    df["selected_filter"] = (
        (df["amount20"] > params.min_theme_amount_20d)
        & df["trend_ok"]
        & (df["ret20"] > params.min_theme_ret20)
        & (df["ret60"] > params.min_theme_ret60)
        & df["flow_ok"]
        & ((df["latest_close"] / df["ma60"] - 1.0) <= params.max_theme_dist_ma60)
    )
    df = df.sort_values("etf_score", ascending=False).reset_index(drop=True)
    df["theme_rank"] = df.index + 1
    return df


def build_real_candidate_pool(
    store: RealETFStore,
    real_cache: SectorProsperityCache,
    selected_etfs: pd.DataFrame,
    data_date: pd.Timestamp,
    daily_basic: pd.DataFrame,
    stock_basic: pd.DataFrame,
    start: str,
    end: str,
    params: ThemeETFParams,
) -> pd.DataFrame:
    if selected_etfs.empty:
        return pd.DataFrame()
    rows = []
    selected = selected_etfs.copy()
    selected["code"] = selected["code"].astype(str).str.lower()
    selected_map = selected.set_index("code")
    stock_name_map = {}
    stock_list_date_map = {}
    if stock_basic is not None and not stock_basic.empty and "ts_code" in stock_basic.columns:
        sb = stock_basic.copy()
        sb["code"] = sb["ts_code"].astype(str).apply(tushare_to_qlib)
        stock_name_map = dict(zip(sb["code"].str.lower(), sb.get("name", pd.Series(index=sb.index, dtype=object)).fillna("").tolist()))
        if "list_date" in sb.columns:
            stock_list_date_map = dict(zip(sb["code"].str.lower(), pd.to_datetime(sb["list_date"].astype(str), errors="coerce")))
    for row in selected.itertuples(index=False):
        etf_code = row.code
        theme_name = getattr(row, "theme_name", etf_code)
        index_code = getattr(row, "index_code", np.nan)
        if pd.isna(index_code) or not str(index_code):
            continue
        weights = real_cache.index_weight(str(index_code), start, end)
        if weights.empty or "con_code" not in weights.columns:
            continue
        w = weights.copy()
        if "trade_date" in w.columns:
            w["trade_date"] = pd.to_datetime(w["trade_date"].astype(str), format="%Y%m%d", errors="coerce")
            w = w[w["trade_date"] <= data_date].copy()
            if w.empty:
                continue
            latest_dt = w["trade_date"].max()
            w = w[w["trade_date"] == latest_dt].copy()
        w["code"] = w["con_code"].astype(str).apply(tushare_to_qlib)
        if "weight" not in w.columns:
            w["weight"] = np.nan
        w["theme"] = etf_code
        w["theme_name"] = theme_name
        w["theme_score"] = float(selected_map.loc[etf_code, "etf_score"]) if etf_code in selected_map.index else np.nan
        w["theme_ret20"] = float(selected_map.loc[etf_code, "ret20"]) if etf_code in selected_map.index else np.nan
        w["theme_ret60"] = float(selected_map.loc[etf_code, "ret60"]) if etf_code in selected_map.index else np.nan
        rows.append(w[["code", "theme", "theme_name", "theme_score", "theme_ret20", "theme_ret60", "weight"]])
    if not rows:
        return pd.DataFrame()
    pool = pd.concat(rows, ignore_index=True).dropna(subset=["code"]).copy()
    pool = pool.drop_duplicates(["code", "theme"], keep="first")
    pool["latest_close"] = store.row("close", data_date).reindex(pool["code"].tolist()).values
    pool["ma20"] = store.row("ma20", data_date).reindex(pool["code"].tolist()).values
    pool["ma60"] = store.row("ma60", data_date).reindex(pool["code"].tolist()).values
    pool["ret20"] = store.row("ret20", data_date).reindex(pool["code"].tolist()).values
    pool["ret60"] = store.row("ret60", data_date).reindex(pool["code"].tolist()).values
    pool["amount20"] = store.row("amount20", data_date).reindex(pool["code"].tolist()).values
    pool["name"] = pool["code"].map(stock_name_map).fillna("")
    pool["list_date"] = pool["code"].map(stock_list_date_map)
    if not daily_basic.empty and "ts_code" in daily_basic.columns:
        db = daily_basic.copy()
        db["code"] = db["ts_code"].astype(str).apply(tushare_to_qlib)
        db = db.drop_duplicates("code", keep="last").set_index("code")
        for col in ["turnover_rate", "total_mv", "circ_mv", "pe_ttm", "pb"]:
            pool[col] = db[col].reindex(pool["code"]).values if col in db.columns else np.nan
    pool["list_days"] = (data_date - pd.to_datetime(pool["list_date"], errors="coerce")).dt.days
    raw_code = pool["code"].str[2:]
    keep = (
        (pool["list_days"] >= params.min_list_days)
        & ~raw_code.str.startswith(("4", "8"))
        & ~pool["name"].fillna("").str.contains("ST|退|\\*", regex=True)
        & (pool["amount20"] > params.min_stock_amount_20d)
        & (pool["latest_close"] > pool["ma20"])
        & (pool["ma20"] > pool["ma60"])
    )
    if "turnover_rate" in pool.columns and pool["turnover_rate"].notna().any():
        keep &= pool["turnover_rate"].fillna(0) >= params.min_turnover_20d
    if "total_mv" in pool.columns and pool["total_mv"].notna().any():
        keep &= pool["total_mv"].fillna(0) >= params.allow_min_total_mv
    pool = pool[keep].copy()
    if pool.empty:
        return pool
    sort_col = "total_mv" if "total_mv" in pool.columns and pool["total_mv"].notna().any() else "amount20"
    pool = (
        pool.sort_values(["theme", sort_col], ascending=[True, False])
        .groupby("theme", as_index=False)
        .head(params.constituents_per_theme)
        .reset_index(drop=True)
    )
    return pool


def select_targets(pool: pd.DataFrame, params: ThemeETFParams) -> list[str]:
    if pool.empty:
        return []
    df = pool.copy()
    if params.experiment == "v0":
        df = df.sort_values(["theme_score", "amount20"], ascending=[False, False]).groupby("theme", as_index=False).head(1)
    elif params.experiment == "v1":
        sort_col = "total_mv" if "total_mv" in df.columns and df["total_mv"].notna().any() else "amount20"
        df = df.sort_values(["theme_score", sort_col], ascending=[False, False])
    else:
        df = df[df["rs_ok"] & df["trend_ok"] & df["not_overheated"]].copy()
        if df.empty:
            return []
        rs_cut = df["stock_rs_score"].quantile(1.0 - params.rs_top_pct)
        df = df[df["stock_rs_score"] >= rs_cut].copy()
        if params.experiment == "v3":
            buy_a = df["buy_signal_a"].fillna(False) & df["pullback_zone"].fillna(False)
            buy_b = df["buy_signal_b"].fillna(False)
            df = df[buy_a | buy_b].copy()
        df = df.sort_values("final_score", ascending=False)
    selected: list[str] = []
    theme_counts: dict[str, int] = {}
    max_per_theme = max(1, int(np.floor(params.target_num * params.max_theme_weight)))
    for row in df.itertuples(index=False):
        theme = getattr(row, "theme")
        if theme_counts.get(theme, 0) >= max_per_theme:
            continue
        selected.append(getattr(row, "code"))
        theme_counts[theme] = theme_counts.get(theme, 0) + 1
        if len(selected) >= params.target_num:
            break
    if len(selected) < params.target_num:
        for code in df["code"].tolist():
            if code not in selected:
                selected.append(code)
            if len(selected) >= params.target_num:
                break
    return selected


def weak_market_scale(benchmark_close: pd.Series, data_date: pd.Timestamp, params: ThemeETFParams) -> float:
    if not params.market_filter:
        return 1.0
    hist = benchmark_close.loc[:data_date].dropna().tail(61)
    if len(hist) < 61:
        return 1.0
    ma60 = hist.tail(60).mean()
    ret20 = hist.iloc[-1] / hist.iloc[-21] - 1.0
    if hist.iloc[-1] < ma60 and ret20 < -0.05:
        return params.weak_market_position_scale
    return 1.0


def _is_limit_up_buy_block(prev_close: float, open_price: float) -> bool:
    if pd.isna(prev_close) or pd.isna(open_price) or prev_close <= 0:
        return True
    return open_price / prev_close - 1.0 >= 0.095


def _is_limit_down_sell_block(prev_close: float, open_price: float) -> bool:
    if pd.isna(prev_close) or pd.isna(open_price) or prev_close <= 0:
        return True
    return open_price / prev_close - 1.0 <= -0.095


def sell_reasons(
    code: str,
    theme: str,
    frames: DailyFrames,
    theme_scores: pd.DataFrame,
    stock_scores: pd.DataFrame,
    data_date: pd.Timestamp,
    entry_price: float,
    peak_price: float,
    entry_idx: int,
    current_idx: int,
    params: ThemeETFParams,
) -> list[str]:
    reasons: list[str] = []
    if code not in frames.close.columns:
        return ["NO_PRICE"]
    hist = frames.close.loc[:data_date, [code]].dropna().iloc[:, 0]
    if len(hist) < 60:
        return []
    close = hist.iloc[-1]
    ma20 = hist.tail(20).mean()
    if close < ma20:
        reasons.append("CLOSE_LT_MA20")
    if entry_price > 0 and close / entry_price - 1.0 < params.stop_loss:
        reasons.append("STOP_LOSS")
    if peak_price > 0 and close / peak_price - 1.0 < params.trailing_stop:
        reasons.append("TRAILING_STOP")
    if current_idx - entry_idx > params.stale_hold_days and close < peak_price:
        reasons.append("STALE_NO_NEWHIGH")

    row = stock_scores[stock_scores["code"] == code] if "code" in stock_scores.columns else pd.DataFrame()
    if not row.empty and float(row.iloc[0].get("rs20", 0.0)) < 0:
        reasons.append("RS20_LT_0")
    theme_row = theme_scores[theme_scores["theme"] == theme]
    if not theme_row.empty:
        tr = theme_row.iloc[0]
        if bool((tr["ret20"] < 0) or (not tr["trend_ok"]) or (not tr["flow_ok"])):
            reasons.append("THEME_FAILED")

    volume = frames.volume.loc[:data_date, [code]].dropna().iloc[:, 0]
    if len(volume) >= 20:
        high60 = hist.tail(60).max()
        vol_ma20 = volume.tail(20).mean()
        pct_chg = hist.iloc[-1] / hist.iloc[-2] - 1.0 if len(hist) > 1 else 0.0
        if close / high60 > 0.95 and volume.iloc[-1] > 2.0 * vol_ma20 and abs(pct_chg) < 0.01:
            reasons.append("HIGH_VOLUME_STALL")
    return reasons


def sell_reasons_fast(
    code: str,
    theme: str,
    store: RollingFeatureStore,
    theme_scores: pd.DataFrame,
    stock_scores: pd.DataFrame,
    data_date: pd.Timestamp,
    entry_price: float,
    peak_price: float,
    entry_idx: int,
    current_idx: int,
    params: ThemeETFParams,
) -> list[str]:
    reasons: list[str] = []
    if code not in store.codes:
        return ["NO_PRICE"]
    close = store.row("close", data_date).get(code, np.nan)
    ma20 = store.row("ma20", data_date).get(code, np.nan)
    if pd.isna(close) or pd.isna(ma20):
        return []
    if close < ma20:
        reasons.append("CLOSE_LT_MA20")
    if entry_price > 0 and close / entry_price - 1.0 < params.stop_loss:
        reasons.append("STOP_LOSS")
    if peak_price > 0 and close / peak_price - 1.0 < params.trailing_stop:
        reasons.append("TRAILING_STOP")
    if current_idx - entry_idx > params.stale_hold_days and close < peak_price:
        reasons.append("STALE_NO_NEWHIGH")

    row = stock_scores[stock_scores["code"] == code] if "code" in stock_scores.columns else pd.DataFrame()
    if not row.empty and float(row.iloc[0].get("rs20", 0.0)) < 0:
        reasons.append("RS20_LT_0")
    theme_row = theme_scores[theme_scores["theme"] == theme] if "theme" in theme_scores.columns else pd.DataFrame()
    if not theme_row.empty:
        tr = theme_row.iloc[0]
        if bool((tr["ret20"] < 0) or (not tr["trend_ok"]) or (not tr["flow_ok"])):
            reasons.append("THEME_FAILED")

    high60 = store.row("high60", data_date).get(code, np.nan)
    volume = store.row("volume", data_date).get(code, np.nan)
    vol_ma20 = store.row("volume_ma20", data_date).get(code, np.nan)
    pct_chg = store.row("pct_chg", data_date).get(code, np.nan)
    if pd.notnull(high60) and pd.notnull(volume) and pd.notnull(vol_ma20) and vol_ma20 > 0:
        if close / high60 > 0.95 and volume > 2.0 * vol_ma20 and abs(pct_chg) < 0.01:
            reasons.append("HIGH_VOLUME_STALL")
    return reasons


def run_real_etf_backtest(
    provider_uri: Path,
    token_path: Path,
    cache_dir: Path,
    market: str,
    start: str,
    end: str,
    params: ThemeETFParams,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cache = SectorProsperityCache(token_path, cache_dir)
    cache.prefetch_etf_data(start, end)
    real_universe = RealETFUniverse(cache)
    if real_universe.meta.empty:
        raise RuntimeError("No real ETF universe could be built from Tushare caches")

    data = FundamentalCache(token_path, cache_dir / "theme_etf_momentum")
    if market.lower() in {"hs300", "csi300", "000300"}:
        from strategies._utils import Hs300HistoryUniverse, load_hs300_weights

        weights = load_hs300_weights(cache_dir, token_path, start, end)
        hist_uni = Hs300HistoryUniverse(weights)
        universe = sorted(weights["code"].str.lower().unique().tolist())
    else:
        from strategies._utils import read_instrument_codes

        hist_uni = None
        universe = read_instrument_codes(provider_uri, market)

    reader = QlibDailyReader(provider_uri)
    all_codes = sorted(set(universe + [params.benchmark]))
    frames = DailyFrames(reader, all_codes, start, end)
    stock_codes = [c for c in universe if c in frames.close.columns]
    if not stock_codes:
        raise RuntimeError("No stock OHLCV data available for selected market")
    stock_store = RollingFeatureStore(frames, stock_codes)
    etf_store = RealETFStore(cache, real_universe, start, end)
    benchmark_close = stock_store.close[params.benchmark].dropna() if params.benchmark in stock_store.close.columns else frames.close[params.benchmark].dropna()

    stock_basic = load_stock_basic_snapshot(data, cache_dir)
    daily_basic_store = DailyBasicStore(cache_dir)

    cash = params.initial_cash
    shares = pd.Series(0.0, index=pd.Index(stock_codes))
    entry_price: dict[str, float] = {}
    entry_idx: dict[str, int] = {}
    peak_price: dict[str, float] = {}
    code_theme: dict[str, str] = {}
    records: list[dict] = []
    target_rows: list[dict] = []
    theme_rows: list[dict] = []

    calendar = stock_store.close.index
    week_keys = pd.Series(calendar, index=calendar).dt.to_period("W-MON")
    first_days = set(pd.Series(calendar, index=calendar).groupby(week_keys).first().tolist())

    for i, data_date in enumerate(calendar[:-1]):
        if i < 61:
            continue
        next_date = calendar[i + 1]
        active_universe = hist_uni.codes_for_date(data_date) if hist_uni is not None else stock_codes
        active_universe = [c for c in active_universe if c in stock_codes]

        etf_scores = compute_real_etf_scores(etf_store, real_universe.meta, data_date, params)
        selected_etfs = select_themes(etf_scores, params) if not etf_scores.empty else pd.DataFrame()
        daily_basic = daily_basic_store.get(data_date)

        pool = build_real_candidate_pool(
            stock_store,
            cache,
            selected_etfs,
            data_date,
            daily_basic,
            stock_basic,
            start,
            end,
            params,
        )
        stock_scores = score_stock_pool_fast(pool, stock_store, data_date, None, params) if not pool.empty else pd.DataFrame()
        stock_scores = add_buy_signals_fast(stock_scores, stock_store, data_date) if not stock_scores.empty else stock_scores
        target_codes = select_targets(stock_scores, params) if not stock_scores.empty else []
        target_set = set(target_codes)

        next_open = stock_store.open.loc[next_date]
        signal_close = stock_store.close.loc[data_date]
        next_close = stock_store.close.loc[next_date]

        sold = []
        for code in shares[shares > 0].index.tolist():
            theme = code_theme.get(code, "UNKNOWN")
            reasons = sell_reasons_fast(
                code,
                theme,
                stock_store,
                etf_scores,
                stock_scores,
                data_date,
                entry_price.get(code, np.nan),
                peak_price.get(code, np.nan),
                entry_idx.get(code, i),
                i,
                params,
            )
            if code in target_set and not reasons:
                continue
            px = next_open.get(code, np.nan)
            prev_px = signal_close.get(code, np.nan)
            if _is_limit_down_sell_block(prev_px, px):
                continue
            if pd.notnull(px) and px > 0:
                cash += shares[code] * px * (1 - params.close_cost)
                sold.append((code, ",".join(reasons or ["REBALANCE"])))
                shares[code] = 0.0
                entry_price.pop(code, None)
                entry_idx.pop(code, None)
                peak_price.pop(code, None)
                code_theme.pop(code, None)

        position_scale = weak_market_scale(benchmark_close, data_date, params)
        buy_targets = [c for c in target_codes if c in stock_codes]
        if buy_targets:
            total_value = cash + float((shares * next_open.reindex(stock_codes).fillna(signal_close.reindex(stock_codes))).sum())
            target_value = total_value * position_scale / len(buy_targets)
            for code in buy_targets:
                px = next_open.get(code, np.nan)
                prev_px = signal_close.get(code, np.nan)
                if _is_limit_up_buy_block(prev_px, px) or pd.isna(px) or px <= 0:
                    continue
                current_value = shares.get(code, 0.0) * px
                diff_value = target_value - current_value
                if diff_value <= 0:
                    continue
                buy_cash = min(cash, diff_value)
                buy_shares = lot_floor(buy_cash / (px * (1 + params.open_cost)))
                if buy_shares <= 0:
                    continue
                cash -= buy_shares * px * (1 + params.open_cost)
                shares[code] += buy_shares
                if code not in entry_price:
                    entry_price[code] = px
                    entry_idx[code] = i + 1
                    peak_price[code] = next_close.get(code, px)
                    row = stock_scores[stock_scores["code"] == code]
                    code_theme[code] = row.iloc[0]["theme"] if not row.empty else "UNKNOWN"

        for code in shares[shares > 0].index:
            px_close = next_close.get(code, np.nan)
            if pd.notnull(px_close):
                peak_price[code] = max(peak_price.get(code, px_close), px_close)

        for rank, code in enumerate(target_codes, start=1):
            row = stock_scores[stock_scores["code"] == code]
            base = {"date": data_date, "trade_date": next_date, "rank": rank, "code": code, "experiment": params.experiment}
            if not row.empty:
                payload = row.iloc[0].to_dict()
                for key in [
                    "name", "theme", "theme_name", "theme_score", "theme_ret20", "theme_ret60", "rs20", "rs60",
                    "stock_rs_score", "structure_score", "moneyflow_score", "final_score",
                    "dist_ma20", "dist_high20", "buy_signal_a", "buy_signal_b", "pullback_zone",
                ]:
                    if key in payload:
                        base[key] = payload[key]
            target_rows.append(base)

        if not selected_etfs.empty:
            for row in selected_etfs.itertuples(index=False):
                theme_rows.append(
                    {
                        "date": data_date,
                        "theme": row.code,
                        "theme_name": getattr(row, "theme_name", ""),
                        "theme_rank": row.theme_rank,
                        "etf_score": row.etf_score,
                        "ret20": row.ret20,
                        "ret60": row.ret60,
                        "amount20": row.amount20,
                        "amount_ratio": row.amount20 / row.amount60 if pd.notnull(row.amount60) and row.amount60 else np.nan,
                        "flow_score": row.flow_score,
                        "trend_score": row.trend_score,
                        "liquidity_score": row.liquidity_score,
                    }
                )

        portfolio_value = cash + float((shares * next_close.reindex(stock_codes).fillna(next_open.reindex(stock_codes))).sum())
        records.append(
            {
                "date": next_date,
                "portfolio_value": portfolio_value,
                "cash": cash,
                "position_count": int((shares > 0).sum()),
                "selected_theme_count": int(len(selected_etfs)),
                "target_count": int(len(target_codes)),
                "sold_count": int(len(sold)),
                "position_scale": position_scale,
            }
        )

    equity = pd.DataFrame(records).drop_duplicates("date", keep="last").set_index("date")
    if equity.empty:
        raise RuntimeError("Backtest produced no equity records; check date range and lookback")
    bench = benchmark_close.reindex(equity.index).ffill()
    equity["benchmark_value"] = params.initial_cash * bench / bench.dropna().iloc[0]
    equity["strategy_return"] = equity["portfolio_value"] / equity["portfolio_value"].iloc[0] - 1.0
    equity["benchmark_return"] = equity["benchmark_value"] / equity["benchmark_value"].iloc[0] - 1.0
    return equity, pd.DataFrame(target_rows), pd.DataFrame(theme_rows)


def run_theme_etf_backtest(
    provider_uri: Path,
    token_path: Path,
    cache_dir: Path,
    market: str,
    start: str,
    end: str,
    params: ThemeETFParams,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if params.theme_source == "real_etf":
        return run_real_etf_backtest(provider_uri, token_path, cache_dir, market, start, end, params)

    data = FundamentalCache(token_path, cache_dir / "theme_etf_momentum")
    if market.lower() in {"hs300", "csi300", "000300"}:
        from strategies._utils import Hs300HistoryUniverse, load_hs300_weights

        weights = load_hs300_weights(cache_dir, token_path, start, end)
        hist_uni = Hs300HistoryUniverse(weights)
        universe = sorted(weights["code"].str.lower().unique().tolist())
    else:
        from strategies._utils import read_instrument_codes

        hist_uni = None
        universe = read_instrument_codes(provider_uri, market)

    if pd.Timestamp(end) <= pd.Timestamp.today() and provider_uri.exists():
        try:
            from lazy_tushare_loader import LazyTushareLoader

            base_dir = provider_uri.parent.parent
            if str(Path.cwd()) != str(base_dir):
                base_dir = Path.cwd()
            if __import__("os").environ.get("QLIB_LAZY_TUSHARE", "1") != "0":
                LazyTushareLoader.for_project(base_dir, provider_uri).ensure(
                    instruments=universe,
                    start_time=start,
                    end_time=end,
                    benchmark=params.benchmark.upper(),
                )
        except Exception as exc:
            print(f"Lazy Tushare skipped/failed for theme strategy: {exc}")

    reader = QlibDailyReader(provider_uri)
    all_codes = sorted(set(universe + [params.benchmark]))
    frames = DailyFrames(reader, all_codes, start, end)
    stock_codes = [c for c in universe if c in frames.close.columns]
    if not stock_codes:
        raise RuntimeError("No stock OHLCV data available for selected market")
    benchmark_close = frames.close[params.benchmark].dropna()
    store = RollingFeatureStore(frames, stock_codes)

    stock_basic = load_stock_basic_snapshot(data, cache_dir)
    theme_universe = ThemeUniverse(stock_basic, stock_codes)
    daily_basic_store = DailyBasicStore(cache_dir)
    moneyflow = MoneyFlowCache(cache_dir) if params.use_moneyflow else None

    cash = params.initial_cash
    shares = pd.Series(0.0, index=pd.Index(stock_codes))
    entry_price: dict[str, float] = {}
    entry_idx: dict[str, int] = {}
    peak_price: dict[str, float] = {}
    code_theme: dict[str, str] = {}
    records: list[dict] = []
    target_rows: list[dict] = []
    theme_rows: list[dict] = []
    selected_themes = pd.DataFrame()

    calendar = frames.close.index
    week_keys = pd.Series(calendar, index=calendar).dt.to_period("W-MON")
    first_days = set(pd.Series(calendar, index=calendar).groupby(week_keys).first().tolist())
    static_active_themes = theme_universe.industry.reindex(stock_codes).dropna()

    for i, data_date in enumerate(calendar[:-1]):
        if i < 61:
            continue
        next_date = calendar[i + 1]
        active_universe = hist_uni.codes_for_date(data_date) if market.lower() in {"hs300", "csi300", "000300"} else stock_codes
        active_themes = theme_universe.industry.reindex(active_universe).dropna() if hist_uni is not None else static_active_themes

        if data_date in first_days or selected_themes.empty:
            theme_scores = compute_theme_scores_fast(store, active_themes, data_date, params)
            selected_themes = select_themes(theme_scores, params)
        else:
            theme_scores = compute_theme_scores_fast(store, active_themes, data_date, params)

        daily_basic = daily_basic_store.get(data_date)

        pool = build_candidate_pool_fast(store, theme_universe, selected_themes, data_date, daily_basic, params)
        stock_scores = score_stock_pool_fast(pool, store, data_date, moneyflow, params) if not pool.empty else pd.DataFrame()
        stock_scores = add_buy_signals_fast(stock_scores, store, data_date) if not stock_scores.empty else stock_scores
        target_codes = select_targets(stock_scores, params) if not stock_scores.empty else []
        target_set = set(target_codes)

        next_open = store.open.loc[next_date]
        signal_close = store.close.loc[data_date]
        next_close = store.close.loc[next_date]

        # Sell at t+1 open using t close signal.
        sold = []
        for code in shares[shares > 0].index.tolist():
            theme = code_theme.get(code, theme_universe.industry.get(code, "UNKNOWN"))
            reasons = sell_reasons_fast(
                code,
                theme,
                store,
                theme_scores,
                stock_scores,
                data_date,
                entry_price.get(code, np.nan),
                peak_price.get(code, np.nan),
                entry_idx.get(code, i),
                i,
                params,
            )
            if code in target_set and not reasons:
                continue
            px = next_open.get(code, np.nan)
            prev_px = signal_close.get(code, np.nan)
            if _is_limit_down_sell_block(prev_px, px):
                continue
            if pd.notnull(px) and px > 0:
                cash += shares[code] * px * (1 - params.close_cost)
                sold.append((code, ",".join(reasons or ["REBALANCE"])))
                shares[code] = 0.0
                entry_price.pop(code, None)
                entry_idx.pop(code, None)
                peak_price.pop(code, None)
                code_theme.pop(code, None)

        # Buy/rebalance at t+1 open.
        position_scale = weak_market_scale(benchmark_close, data_date, params)
        buy_targets = [c for c in target_codes if c in stock_codes]
        if buy_targets:
            total_value = cash + float((shares * next_open.reindex(stock_codes).fillna(signal_close.reindex(stock_codes))).sum())
            target_value = total_value * position_scale / len(buy_targets)
            for code in buy_targets:
                px = next_open.get(code, np.nan)
                prev_px = signal_close.get(code, np.nan)
                if _is_limit_up_buy_block(prev_px, px) or pd.isna(px) or px <= 0:
                    continue
                current_value = shares.get(code, 0.0) * px
                diff_value = target_value - current_value
                if diff_value <= 0:
                    continue
                buy_cash = min(cash, diff_value)
                buy_shares = lot_floor(buy_cash / (px * (1 + params.open_cost)))
                if buy_shares <= 0:
                    continue
                cash -= buy_shares * px * (1 + params.open_cost)
                shares[code] += buy_shares
                if code not in entry_price:
                    entry_price[code] = px
                    entry_idx[code] = i + 1
                    peak_price[code] = next_close.get(code, px)
                    row = stock_scores[stock_scores["code"] == code]
                    code_theme[code] = row.iloc[0]["theme"] if not row.empty else theme_universe.industry.get(code, "UNKNOWN")

        for code in shares[shares > 0].index:
            px_close = next_close.get(code, np.nan)
            if pd.notnull(px_close):
                peak_price[code] = max(peak_price.get(code, px_close), px_close)

        for rank, code in enumerate(target_codes, start=1):
            row = stock_scores[stock_scores["code"] == code]
            base = {"date": data_date, "trade_date": next_date, "rank": rank, "code": code, "experiment": params.experiment}
            if not row.empty:
                payload = row.iloc[0].to_dict()
                for key in [
                    "name", "theme", "theme_score", "theme_ret20", "theme_ret60", "rs20", "rs60",
                    "stock_rs_score", "structure_score", "moneyflow_score", "final_score",
                    "dist_ma20", "dist_high20", "buy_signal_a", "buy_signal_b", "pullback_zone",
                ]:
                    if key in payload:
                        base[key] = payload[key]
            target_rows.append(base)

        if not selected_themes.empty:
            for row in selected_themes.itertuples(index=False):
                theme_rows.append(
                    {
                        "date": data_date,
                        "theme": row.theme,
                        "theme_rank": row.theme_rank,
                        "etf_score": row.etf_score,
                        "ret20": row.ret20,
                        "ret60": row.ret60,
                        "amount20": row.amount20,
                        "amount_ratio": row.amount_ratio,
                        "flow_score": row.flow_score,
                        "trend_score": row.trend_score,
                        "liquidity_score": row.liquidity_score,
                    }
                )

        portfolio_value = cash + float((shares * next_close.reindex(stock_codes).fillna(next_open.reindex(stock_codes))).sum())
        records.append(
            {
                "date": next_date,
                "portfolio_value": portfolio_value,
                "cash": cash,
                "position_count": int((shares > 0).sum()),
                "selected_theme_count": int(len(selected_themes)),
                "target_count": int(len(target_codes)),
                "sold_count": int(len(sold)),
                "position_scale": position_scale,
            }
        )

    equity = pd.DataFrame(records).drop_duplicates("date", keep="last").set_index("date")
    if equity.empty:
        raise RuntimeError("Backtest produced no equity records; check date range and lookback")
    bench = benchmark_close.reindex(equity.index).ffill()
    equity["benchmark_value"] = params.initial_cash * bench / bench.dropna().iloc[0]
    equity["strategy_return"] = equity["portfolio_value"] / equity["portfolio_value"].iloc[0] - 1.0
    equity["benchmark_return"] = equity["benchmark_value"] / equity["benchmark_value"].iloc[0] - 1.0
    return equity, pd.DataFrame(target_rows), pd.DataFrame(theme_rows)


def output_paths(out_dir: Path, market: str, start: str, end: str, experiment: str) -> dict[str, Path]:
    exp_dir = out_dir / "theme_etf_momentum" / experiment
    exp_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"{market}_{experiment}_{pd.Timestamp(start):%Y%m%d}_{pd.Timestamp(end):%Y%m%d}"
    return {
        "equity": exp_dir / f"theme_etf_momentum_equity_{suffix}.csv",
        "targets": exp_dir / f"theme_etf_momentum_targets_{suffix}.csv",
        "themes": exp_dir / f"theme_etf_momentum_themes_{suffix}.csv",
        "summary": exp_dir / f"theme_etf_momentum_summary_{suffix}.csv",
        "plot": exp_dir / f"theme_etf_momentum_returns_{suffix}.png",
    }


def summary_frame(equity: pd.DataFrame, params: ThemeETFParams) -> pd.DataFrame:
    stats = summarize(equity)
    stats.update(
        {
            "experiment": params.experiment,
            "target_num": params.target_num,
            "etf_count": params.etf_count,
            "rs_top_pct": params.rs_top_pct,
            "stop_loss": params.stop_loss,
            "trailing_stop": params.trailing_stop,
        }
    )
    return pd.DataFrame([stats])
