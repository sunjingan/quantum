"""
Shared utilities for fundamental quant strategies.

Pure functions: scoring, ranking, selection, market state, Qlib data reading,
HS300 universe helpers.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import tushare as ts


# ═══════════════════════════════════════════════════════════════════
# Qlib daily data reader
# ═══════════════════════════════════════════════════════════════════

class QlibDailyReader:
    """Read daily OHLCV from Qlib .bin feature files."""

    def __init__(self, provider_uri: Path):
        self.provider_uri = provider_uri
        self.calendar = pd.to_datetime(
            pd.read_csv(provider_uri / "calendars" / "day.txt", header=None)[0]
        )

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


# ═══════════════════════════════════════════════════════════════════
# HS300 historical universe
# ═══════════════════════════════════════════════════════════════════

def _ts_to_qlib(ts_code: str) -> str:
    symbol, exchange = ts_code.split(".")
    return f"{exchange.lower()}{symbol}".lower()


def load_hs300_weights(cache_dir: Path, token_path: Path, start: str, end: str) -> pd.DataFrame:
    """Load HS300 constituent weights from Tushare (disk-cached)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"index_weight_000300_{pd.Timestamp(start):%Y%m%d}_{pd.Timestamp(end):%Y%m%d}.csv"
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    if path.exists():
        df = pd.read_csv(path, dtype={"con_code": str, "trade_date": str})
        if not df.empty and pd.Timestamp(str(df["trade_date"].min())) <= start_ts:
            df["date"] = pd.to_datetime(df["trade_date"].astype(str))
            df["code"] = df["con_code"].map(_ts_to_qlib)
            return df.sort_values(["date", "code"])
    pro = ts.pro_api(token=token_path.read_text().strip())
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
    df["code"] = df["con_code"].map(_ts_to_qlib)
    return df.sort_values(["date", "code"])


class Hs300HistoryUniverse:
    """Historical HS300 universe: tracks constituent changes over time."""
    def __init__(self, weights: pd.DataFrame):
        self.weights = weights.sort_values("date")

    def codes_for_date(self, data_date: pd.Timestamp) -> list[str]:
        dates = self.weights.loc[self.weights["date"] <= data_date, "date"]
        if dates.empty:
            return []
        latest = dates.max()
        return sorted(
            self.weights.loc[self.weights["date"] == latest, "code"].str.lower().unique().tolist()
        )

    def first_needed_dates(self, global_start: str) -> dict[str, pd.Timestamp]:
        start = pd.Timestamp(global_start)
        first = self.weights.groupby("code")["date"].min()
        return {code.lower(): max(start, pd.Timestamp(date)) for code, date in first.items()}


# ═══════════════════════════════════════════════════════════════════
# Ranking / scoring helpers
# ═══════════════════════════════════════════════════════════════════

def pct_rank(s: pd.Series, ascending: bool = True) -> pd.Series:
    return s.rank(ascending=ascending, pct=True).clip(0, 1)


def score_high_is_good(s: pd.Series) -> pd.Series:
    return pct_rank(s.replace([np.inf, -np.inf], np.nan), ascending=True).fillna(0.0)


def score_low_is_good(s: pd.Series) -> pd.Series:
    return (1 - pct_rank(s.replace([np.inf, -np.inf], np.nan), ascending=True)).fillna(0.0)


def price_strength(close: pd.DataFrame, codes: list[str], data_date: pd.Timestamp) -> pd.DataFrame:
    """Compute price strength metrics: dist to 252d high, 60d return, price_score."""
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
    return pd.DataFrame({
        "latest_close": latest,
        "dist_to_252d_high": dist,
        "ret60": ret60,
        "price_score": price_score,
    })


# ═══════════════════════════════════════════════════════════════════
# Market state detection (shared across strategies)
# ═══════════════════════════════════════════════════════════════════

def market_state(
    benchmark_close: pd.Series, data_date: pd.Timestamp
) -> tuple[str, str]:
    """Return (market_state, risk_state) from benchmark price action."""
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


# ═══════════════════════════════════════════════════════════════════
# Instrument / universe helpers
# ═══════════════════════════════════════════════════════════════════

def read_instrument_codes(provider_uri: Path, market: str) -> list[str]:
    path = provider_uri / "instruments" / f"{market}.txt"
    df = pd.read_csv(path, sep="	", header=None, names=["code", "start", "end"])
    return df["code"].str.lower().tolist()


def monthly_rebalance_dates(
    calendar: pd.Series, start: str, end: str
) -> list[pd.Timestamp]:
    cal = calendar[(calendar >= pd.Timestamp(start)) & (calendar <= pd.Timestamp(end))]
    return cal.groupby(cal.dt.to_period("M")).first().tolist()


def rebalance_dates(
    calendar: pd.Series,
    start: str,
    end: str,
    frequency: str = "monthly",
) -> list[pd.Timestamp]:
    """Return first trading day per requested rebalance period."""
    cal = calendar[(calendar >= pd.Timestamp(start)) & (calendar <= pd.Timestamp(end))]
    if frequency == "monthly":
        return cal.groupby(cal.dt.to_period("M")).first().tolist()
    if frequency == "weekly":
        return cal.groupby(cal.dt.to_period("W-FRI")).first().tolist()
    raise ValueError(f"Unsupported rebalance frequency: {frequency}")


def lot_floor(amount: float, lot_size: int = 100) -> int:
    if pd.isnull(amount) or amount < lot_size:
        return 0
    return int(amount // lot_size) * lot_size


# ═══════════════════════════════════════════════════════════════════
# Backtest summary statistics
# ═══════════════════════════════════════════════════════════════════

def summarize(equity: pd.DataFrame) -> dict[str, float]:
    ret = equity["portfolio_value"].pct_change().dropna()
    total_return = (
        equity["portfolio_value"].iloc[-1] / equity["portfolio_value"].iloc[0] - 1
    )
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
        "sharpe": sharpe,
    }
