#!/usr/bin/env python3
"""Minute-level replication of the friend's ETF rotation strategy.

This is intentionally separate from the daily ETF Loop engine.  The old
`friend_mode` tried to approximate an intraday 09:50 signal with daily bars;
this runner uses local minute ETF files and keeps the assumptions explicit.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from strategies.etf_loop_engine import EngineParams  # noqa: E402
from strategies.etf_loop_strategy import _lot_floor, calculate_atr, get_ranked_etfs  # noqa: E402


LOCAL_DATA = PROJECT_ROOT / "data" / "local_etf_data"
OUT = PROJECT_ROOT / "outputs" / "etf_loop" / "friend_intraday_replication"

FRIEND_POOL_9 = [
    "513100.SH",  # 纳指ETF
    "513520.SH",  # 日经ETF
    "513030.SH",  # 德国ETF
    "518880.SH",  # 黄金ETF
    "159980.SZ",  # 有色ETF
    "501018.SH",  # 南方原油
    "511090.SH",  # 30年国债ETF
    "512890.SH",  # 红利低波
    "159915.SZ",  # 创业板ETF
]

FRIEND_CLAIM = {"annual_return": 0.6604, "max_drawdown": -0.1653}


def ts_to_local(code: str) -> str:
    return code.split(".")[0]


def pct(x: float) -> str:
    return "" if pd.isna(x) else f"{x * 100:.2f}%"


def summarize(equity: pd.DataFrame) -> dict[str, float]:
    nav = equity["portfolio_value"].dropna()
    daily = nav.pct_change().dropna()
    if len(daily) < 2:
        return {
            "annual_return": np.nan,
            "cagr": np.nan,
            "sharpe_ratio": np.nan,
            "max_drawdown": np.nan,
            "total_return": np.nan,
            "final_value": float(nav.iloc[-1]) if len(nav) else np.nan,
        }
    ann = float(daily.mean() * 252.0)
    vol = float(daily.std() * np.sqrt(252.0))
    return {
        "annual_return": ann,
        "cagr": float((nav.iloc[-1] / nav.iloc[0]) ** (252.0 / len(daily)) - 1.0),
        "sharpe_ratio": ann / vol if vol > 0 else np.nan,
        "max_drawdown": float((nav / nav.cummax() - 1.0).min()),
        "total_return": float(nav.iloc[-1] / nav.iloc[0] - 1.0),
        "final_value": float(nav.iloc[-1]),
    }


@dataclass
class IntradayPricePoint:
    date: pd.Timestamp
    price: float
    source: str


class LocalETFIntradayStore:
    """Local 5-minute ETF store with the method surface used by score_etf."""

    def __init__(
        self,
        root: Path,
        ts_codes: list[str],
        start: str,
        end: str,
        signal_time: str = "09:50",
        signal_field: str = "close",
        adjust: str = "none",
        frequency: str = "1min",
    ) -> None:
        self.root = root
        self.ts_codes = ts_codes
        self.start = pd.Timestamp(start)
        self.end = pd.Timestamp(end)
        self.signal_time = signal_time
        self.signal_field = signal_field
        self.adjust = adjust
        self.frequency = frequency
        self.factor_cache: dict[str, pd.Series] = {}
        self.nav_cache: dict[str, pd.Series] = {}
        self.current_signal_date: pd.Timestamp | None = None
        frames: dict[str, pd.DataFrame] = {}
        for code in ts_codes:
            df = self._load_code(code)
            if not df.empty:
                frames[code] = df
        self.frames = frames
        self.ts_codes = [c for c in ts_codes if c in frames]
        self._build_daily_wide()

    def _load_code(self, ts_code: str) -> pd.DataFrame:
        local = ts_to_local(ts_code)
        parts = []
        for path in [
            self.root / "2000-2025" / self.frequency / f"{local}.csv",
            self.root / "2026" / ("2026_1分钟" if self.frequency == "1min" else "2026_5分钟") / f"{local}.csv",
        ]:
            if not path.exists():
                continue
            df = pd.read_csv(path)
            if df.empty:
                continue
            amount_col = "amount" if "amount" in df.columns else "money" if "money" in df.columns else None
            keep = ["date", "time", "open", "high", "low", "close", "volume", "iopv"]
            if amount_col:
                keep.append(amount_col)
            keep = [c for c in keep if c in df.columns]
            df = df[keep].copy()
            df["date"] = pd.to_datetime(df["date"])
            df["time"] = df["time"].astype(str).str.slice(0, 5)
            if amount_col and amount_col != "amount":
                df["amount"] = df[amount_col]
            elif "amount" not in df.columns:
                df["amount"] = np.nan
            df["ts_code"] = ts_code
            parts.append(df)
        if not parts:
            return pd.DataFrame()
        out = pd.concat(parts, ignore_index=True)
        warmup_start = self.start - pd.DateOffset(days=260)
        out = out[(out["date"] >= warmup_start) & (out["date"] <= self.end)].copy()
        out = out.drop_duplicates(["date", "time"], keep="last").sort_values(["date", "time"])
        if self.adjust == "pre":
            out = self._apply_pre_adjustment(ts_code, out)
        return out

    def _factor_file_key(self, ts_code: str) -> str:
        local = ts_to_local(ts_code)
        prefix = "sh" if ts_code.endswith(".SH") else "sz"
        return f"{prefix}{local}.csv"

    def _load_factor(self, ts_code: str) -> pd.Series:
        if ts_code in self.factor_cache:
            return self.factor_cache[ts_code]
        factor_zip = self.root / "全部复权因子" / "涨跌幅" / "全部复权因子.zip"
        key = self._factor_file_key(ts_code)
        if not factor_zip.exists():
            self.factor_cache[ts_code] = pd.Series(dtype=float)
            return self.factor_cache[ts_code]
        with zipfile.ZipFile(factor_zip) as zf:
            names = [n for n in zf.namelist() if n.endswith("/" + key) or n.endswith(key)]
            if not names:
                self.factor_cache[ts_code] = pd.Series(dtype=float)
                return self.factor_cache[ts_code]
            with zf.open(names[0]) as fh:
                df = pd.read_csv(fh)
        if df.empty or "交易日期" not in df.columns or "复权因子" not in df.columns:
            self.factor_cache[ts_code] = pd.Series(dtype=float)
            return self.factor_cache[ts_code]
        df = df.copy()
        df["date"] = pd.to_datetime(df["交易日期"])
        s = df.dropna(subset=["date"]).set_index("date")["复权因子"].astype(float).sort_index()
        self.factor_cache[ts_code] = s
        return s

    def _apply_pre_adjustment(self, ts_code: str, df: pd.DataFrame) -> pd.DataFrame:
        factor = self._load_factor(ts_code)
        if factor.empty:
            return df
        f = factor.reindex(pd.DatetimeIndex(df["date"])).ffill().bfill().to_numpy()
        end_factor_series = factor.loc[:self.end]
        if end_factor_series.empty:
            end_factor = float(factor.iloc[-1])
        else:
            end_factor = float(end_factor_series.iloc[-1])
        if end_factor <= 0:
            return df
        scale = f / end_factor
        out = df.copy()
        for col in ["open", "high", "low", "close", "iopv"]:
            if col in out.columns:
                out[col] = out[col].astype(float) * scale
        return out

    def _load_unit_nav(self, ts_code: str) -> pd.Series:
        if ts_code in self.nav_cache:
            return self.nav_cache[ts_code]
        local = ts_to_local(ts_code)
        prefix = "sh" if ts_code.endswith(".SH") else "sz"
        parts = []
        path = self.root / "全部份额" / "全部份额" / f"{prefix}{local}.csv"
        if path.exists():
            df = pd.read_csv(path)
            if not df.empty and "交易日期" in df.columns and "单位净值" in df.columns:
                parts.append(df[["交易日期", "单位净值"]])
        y2026 = self.root / "全部份额" / "2026"
        if y2026.exists():
            for csv_path in sorted(y2026.glob("*.csv")):
                df = pd.read_csv(csv_path)
                if df.empty or "代码" not in df.columns or "交易日期" not in df.columns or "单位净值" not in df.columns:
                    continue
                sub = df[df["代码"].astype(str).str.zfill(6).eq(local)][["交易日期", "单位净值"]]
                if not sub.empty:
                    parts.append(sub)
        if not parts:
            self.nav_cache[ts_code] = pd.Series(dtype=float)
            return self.nav_cache[ts_code]
        out = pd.concat(parts, ignore_index=True)
        out["date"] = pd.to_datetime(out["交易日期"])
        s = out.dropna(subset=["date"]).drop_duplicates("date", keep="last").set_index("date")["单位净值"].astype(float).sort_index()
        self.nav_cache[ts_code] = s
        return s

    def unit_nav(self, code: str, date: pd.Timestamp) -> float:
        s = self._load_unit_nav(code)
        if s.empty:
            return np.nan
        col = s.loc[:pd.Timestamp(date)].dropna()
        return float(col.iloc[-1]) if not col.empty else np.nan

    def _build_daily_wide(self) -> None:
        daily_parts = []
        for code, df in self.frames.items():
            g = df.groupby("date", sort=True)
            d = pd.DataFrame({
                "open": g["open"].first(),
                "high": g["high"].max(),
                "low": g["low"].min(),
                "close": g["close"].last(),
                "volume": g["volume"].sum(),
                "amount": g["amount"].sum(),
            })
            d["ts_code"] = code
            daily_parts.append(d.reset_index())
        if not daily_parts:
            idx = pd.DatetimeIndex([])
            self.open = self.high = self.low = self.close = self.volume = self.amount = pd.DataFrame(index=idx)
            self.calendar = idx
            return
        daily = pd.concat(daily_parts, ignore_index=True)
        self.open = daily.pivot(index="date", columns="ts_code", values="open").sort_index()
        self.high = daily.pivot(index="date", columns="ts_code", values="high").sort_index()
        self.low = daily.pivot(index="date", columns="ts_code", values="low").sort_index()
        self.close = daily.pivot(index="date", columns="ts_code", values="close").sort_index()
        self.volume = daily.pivot(index="date", columns="ts_code", values="volume").sort_index()
        self.amount = daily.pivot(index="date", columns="ts_code", values="amount").sort_index()
        self.calendar = self.close.index[(self.close.index >= self.start) & (self.close.index <= self.end)]

    def set_signal_date(self, date: pd.Timestamp) -> None:
        self.current_signal_date = pd.Timestamp(date)

    def _minute_row_at_or_after(self, code: str, date: pd.Timestamp, time_str: str) -> pd.Series | None:
        df = self.frames.get(code)
        if df is None or df.empty:
            return None
        day = df[df["date"].eq(pd.Timestamp(date))]
        if day.empty:
            return None
        row = day[day["time"].ge(time_str)].head(1)
        if row.empty:
            return None
        return row.iloc[0]

    def _minute_row_at_or_before(self, code: str, date: pd.Timestamp, time_str: str) -> pd.Series | None:
        df = self.frames.get(code)
        if df is None or df.empty:
            return None
        day = df[df["date"].eq(pd.Timestamp(date))]
        if day.empty:
            return None
        row = day[day["time"].le(time_str)].tail(1)
        if row.empty:
            return None
        return row.iloc[0]

    def signal_price(self, code: str, date: pd.Timestamp) -> float:
        row = self._minute_row_at_or_before(code, date, self.signal_time)
        if row is None:
            return np.nan
        px = row.get(self.signal_field, np.nan)
        return float(px) if pd.notna(px) and px > 0 else np.nan

    def fill_price(self, code: str, signal_date: pd.Timestamp, mode: str) -> IntradayPricePoint | None:
        if mode == "same_0950_close":
            row = self._minute_row_at_or_before(code, signal_date, "09:50")
            field = "close"
            date = signal_date
        elif mode == "same_0951_open":
            row = self._minute_row_at_or_after(code, signal_date, "09:51")
            field = "open"
            date = signal_date
        elif mode == "same_0955_open":
            row = self._minute_row_at_or_after(code, signal_date, "09:55")
            field = "open"
            date = signal_date
        elif mode == "next_day_open":
            future_dates = self.calendar[self.calendar > pd.Timestamp(signal_date)]
            if len(future_dates) == 0:
                return None
            date = future_dates[0]
            row = self._minute_row_at_or_after(code, date, "09:35")
            field = "open"
        else:
            raise ValueError(f"Unsupported fill mode: {mode}")
        if row is None:
            return None
        px = row.get(field, np.nan)
        if pd.isna(px) or px <= 0:
            return None
        return IntradayPricePoint(pd.Timestamp(date), float(px), f"{mode}:{field}")

    # score_etf(friend_mode=True) calls this to append today's intraday price.
    def open_price(self, code: str, date: pd.Timestamp) -> float:
        return self.signal_price(code, date)

    def latest_price(self, code: str, date: pd.Timestamp) -> float:
        if code not in self.close.columns:
            return np.nan
        col = self.close[code].loc[:pd.Timestamp(date)].dropna()
        return float(col.iloc[-1]) if not col.empty else np.nan

    def price_series(self, ts_code: str, date: pd.Timestamp, lookback: int) -> np.ndarray:
        if ts_code not in self.close.columns:
            return np.array([])
        col = self.close[ts_code].loc[:pd.Timestamp(date)].dropna()
        if len(col) < lookback + 1:
            return np.array([])
        return col.iloc[-(lookback + 1):].values

    def ohlc_series(self, ts_code: str, date: pd.Timestamp, lookback: int) -> dict[str, np.ndarray] | None:
        result = {}
        for name, df in [("close", self.close), ("high", self.high), ("low", self.low)]:
            if ts_code not in df.columns:
                return None
            col = df[ts_code].loc[:pd.Timestamp(date)].dropna()
            if len(col) < lookback:
                return None
            result[name] = col.iloc[-lookback:].values
        return result

    def volume_ratio(self, ts_code: str, date: pd.Timestamp, lookback: int) -> float | None:
        if ts_code not in self.volume.columns:
            return None
        hist = self.volume[ts_code].loc[:pd.Timestamp(date)].dropna().tail(lookback)
        if len(hist) < lookback or hist.mean() <= 0:
            return None
        signal_date = self.current_signal_date
        if signal_date is None:
            return None
        df = self.frames.get(ts_code)
        if df is None or df.empty:
            return None
        day = df[(df["date"].eq(signal_date)) & (df["time"].le(self.signal_time))]
        if day.empty:
            return None
        current_volume = float(day["volume"].sum())
        return current_volume / float(hist.mean())


def build_friend_params(start: str, end: str, tag: str, full_logic: bool) -> EngineParams:
    common: dict[str, Any] = {
        "start": start,
        "end": end,
        "exp_tag": tag,
        "etf_pool_ts": FRIEND_POOL_9,
        "holdings_num": 1,
        "lookback_days": 25,
        "friend_mode": True,
        "use_dynamic_pool": False,
        "stop_loss": 0.0,
        "mr_ma_period": 0,
        "mr_penalty": 0,
        "use_atr_stop_loss": False,
        "open_cost": 0.0002,
        "close_cost": 0.0002,
        "slippage": 0.001,
        "min_score_threshold": 0.0,
        "max_score_threshold": 500.0,
    }
    if full_logic:
        common.update({
            "use_dynamic_lookback": True,
            "dyn_lookback_min": 20,
            "dyn_lookback_max": 60,
            "dyn_lookback_vol_ratio_cap": 0.9,
            "dyn_lookback_use_atr": True,
            "use_drawdown_filter": True,
            "dd_use_enhanced": True,
            "min_score_threshold": 0.001,
            "max_score_threshold": 6.0,
            "use_premium_penalty": True,
            "premium_penalty": 1.0,
            "premium_threshold": 0.05,
        })
    return EngineParams(**common)


def _weighted_regression_score(prices: np.ndarray) -> dict[str, float] | None:
    if len(prices) < 4 or np.any(pd.isna(prices)) or np.any(prices <= 0):
        return None
    y = np.log(prices)
    x = np.arange(len(y))
    weights = np.linspace(1, 2, len(y))
    slope, intercept = np.polyfit(x, y, 1, w=weights)
    annualized_returns = float(np.exp(slope * 250) - 1.0)
    ss_res = float(np.sum(weights * (y - (slope * x + intercept)) ** 2))
    ss_tot = float(np.sum(weights * (y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 0.0
    return {
        "annualized_returns": annualized_returns,
        "r_squared": r2,
        "score": annualized_returns * r2,
        "slope": float(slope),
    }


def _jq_rank_simple(store: LocalETFIntradayStore, current_date: pd.Timestamp, prev_date: pd.Timestamp) -> list[dict]:
    rows = []
    for code in store.ts_codes:
        hist = store.close[code].loc[:prev_date].tail(25) if code in store.close.columns else pd.Series(dtype=float)
        if hist.isna().any():
            hist = hist.dropna()
        current_px = store.signal_price(code, current_date)
        if len(hist) < 25 or np.isnan(current_px) or current_px <= 0:
            continue
        prices = np.append(hist.values, current_px)
        metrics = _weighted_regression_score(prices)
        if metrics is None:
            continue
        if min(prices[-1] / prices[-2], prices[-2] / prices[-3], prices[-3] / prices[-4]) < 0.95:
            metrics["score"] = 0.0
        if 0 < metrics["score"] < 6:
            rows.append({"ts_code": code, "current_price": current_px, "lookback": 25, **metrics})
    rows.sort(key=lambda x: x["score"], reverse=True)
    return rows


def _jq_rank_auto(store: LocalETFIntradayStore, current_date: pd.Timestamp, prev_date: pd.Timestamp) -> list[dict]:
    rows = []
    min_days = 20
    max_days = 60
    for code in store.ts_codes:
        if code not in store.close.columns or code not in store.high.columns or code not in store.low.columns:
            continue
        # Keep close/high/low date-aligned, matching JoinQuant attribute_history rows.
        hist = pd.concat(
            {
                "close": store.close[code],
                "high": store.high[code],
                "low": store.low[code],
            },
            axis=1,
        ).loc[:prev_date].tail(max_days + 10)
        if (
            len(hist) < (max_days + 10)
            or hist["low"].isna().sum() > max_days
            or hist["close"].isna().sum() > max_days
            or hist["high"].isna().sum() > max_days
        ):
            continue
        hist = hist.dropna(subset=["close", "high", "low"])
        if len(hist) < max_days + 10:
            continue
        close = hist["close"]
        high = hist["high"]
        low = hist["low"]
        long_atr = calculate_atr(high.values, low.values, close.values, max_days)
        short_atr = calculate_atr(high.values, low.values, close.values, min_days)
        if long_atr <= 0 or np.isnan(long_atr) or np.isnan(short_atr):
            continue
        lookback = int(min_days + (max_days - min_days) * (1.0 - min(0.9, short_atr / long_atr)))
        current_px = store.signal_price(code, current_date)
        if np.isnan(current_px) or current_px <= 0:
            continue
        prices = np.append(close.values, current_px)
        prices = prices[-lookback:]
        metrics = _weighted_regression_score(prices)
        if metrics is None:
            continue

        con1 = min(prices[-1] / prices[-2], prices[-2] / prices[-3], prices[-3] / prices[-4]) < 0.95
        con2 = (
            (prices[-1] < prices[-2])
            & (prices[-2] < prices[-3])
            & (prices[-3] < prices[-4])
            & (prices[-1] / prices[-4] < 0.95)
        )
        con3 = (
            (prices[-2] < prices[-3])
            & (prices[-3] < prices[-4])
            & (prices[-4] < prices[-5])
            & (prices[-2] / prices[-5] < 0.95)
        )
        if con1 or con2 or con3:
            metrics["score"] = 0.0

        prev_close = float(close.iloc[-1])
        unit_nav = store.unit_nav(code, prev_date)
        premium_rate = (prev_close - unit_nav) / unit_nav * 100.0 if unit_nav and unit_nav > 0 and not np.isnan(unit_nav) else 0.0
        if premium_rate >= 5:
            metrics["score"] = metrics["score"] - 1.0

        if 0 < metrics["score"] < 6:
            rows.append({
                "ts_code": code,
                "current_price": current_px,
                "lookback": lookback,
                "long_atr": long_atr,
                "short_atr": short_atr,
                "premium_rate": premium_rate,
                "unit_nav": unit_nav,
                **metrics,
            })
    rows.sort(key=lambda x: x["score"], reverse=True)
    return rows


def _apply_jq_slippage(price: float, action: str, fixed_slippage: float) -> float:
    if action == "BUY":
        return price + fixed_slippage
    if action == "SELL":
        return max(0.0, price - fixed_slippage)
    return price


def _jq_commission(gross: float) -> float:
    return max(1.0, gross * 0.0002)


def run_intraday_backtest(
    store: LocalETFIntradayStore,
    params: EngineParams,
    fill_mode: str,
    ranking_mode: str,
    exact_jq_cost: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    cash = params.initial_cash
    shares: dict[str, int] = {}
    entry_price: dict[str, float] = {}
    equity_rows: list[dict] = []
    trade_rows: list[dict] = []
    signal_rows: list[dict] = []

    cal = list(store.calendar)
    for idx, current_date in enumerate(cal):
        prev_dates = store.close.index[store.close.index < current_date]
        if len(prev_dates) == 0:
            continue
        prev_date = prev_dates[-1]
        if len(store.close.loc[:prev_date]) < params.lookback_days + 30:
            continue

        store.set_signal_date(current_date)
        if ranking_mode == "jq_simple":
            ranked = _jq_rank_simple(store, current_date, prev_date)
        elif ranking_mode == "jq_auto":
            ranked = _jq_rank_auto(store, current_date, prev_date)
        else:
            ranked = get_ranked_etfs(store, prev_date, params, current_date)
        for rank, row in enumerate(ranked[:9], start=1):
            signal_rows.append({
                "signal_date": current_date,
                "prev_date": prev_date,
                "rank": rank,
                "ts_code": row["ts_code"],
                "score": row.get("score", np.nan),
                "current_price": row.get("current_price", np.nan),
                "annualized_returns": row.get("annualized_returns", np.nan),
                "r_squared": row.get("r_squared", np.nan),
                "short_annualized": row.get("short_annualized", np.nan),
                "lookback": row.get("lookback", np.nan),
                "premium_rate": row.get("premium_rate", np.nan),
                "unit_nav": row.get("unit_nav", np.nan),
            })

        target = ranked[0]["ts_code"] if ranked and float(ranked[0].get("score", 0.0)) > 0 else None
        held = next((c for c, s in shares.items() if s > 0), None)

        stop_triggered = False
        atr_triggered = False
        if held:
            sig_px = store.signal_price(held, current_date)
            if not np.isnan(sig_px) and held in entry_price:
                stop_triggered = sig_px <= entry_price[held] * params.stop_loss
            if params.use_atr_stop_loss:
                ohlc = store.ohlc_series(held, prev_date, params.atr_period + 20)
                if ohlc is not None:
                    atr = calculate_atr(ohlc["high"], ohlc["low"], ohlc["close"], params.atr_period)
                    if atr > 0 and held in entry_price and not np.isnan(sig_px):
                        atr_triggered = sig_px <= entry_price[held] - params.atr_multiplier * atr

        should_sell = held is not None and (held != target or stop_triggered or atr_triggered)
        if should_sell and held:
            fill = store.fill_price(held, current_date, fill_mode)
            if fill is not None:
                qty = shares[held]
                trade_px = _apply_jq_slippage(fill.price, "SELL", 0.001) if exact_jq_cost else fill.price
                gross = qty * trade_px
                cost = _jq_commission(gross) if exact_jq_cost else gross * (params.close_cost + params.slippage)
                cash += gross - cost
                reason = []
                if held != target:
                    reason.append("RANK_OUT")
                if stop_triggered:
                    reason.append("STOP_LOSS")
                if atr_triggered:
                    reason.append("ATR_STOP")
                trade_rows.append({
                    "signal_date": current_date,
                    "trade_date": fill.date,
                    "ts_code": held,
                    "action": "SELL",
                    "reason": "|".join(reason) if reason else "SELL",
                    "shares": qty,
                    "price": trade_px,
                    "raw_price": fill.price,
                    "gross": gross,
                    "cost": cost,
                    "cash_after": cash,
                    "fill_source": fill.source,
                })
                shares[held] = 0
                entry_price.pop(held, None)
                held = None

        if target and shares.get(target, 0) <= 0:
            fill = store.fill_price(target, current_date, fill_mode)
            if fill is not None:
                px = fill.price
                trade_px = _apply_jq_slippage(px, "BUY", 0.001) if exact_jq_cost else px
                qty = _lot_floor(cash / (trade_px * (1.0 + params.open_cost + (0.0 if exact_jq_cost else params.slippage))))
                if qty > 0:
                    gross = qty * trade_px
                    cost = _jq_commission(gross) if exact_jq_cost else gross * (params.open_cost + params.slippage)
                    if gross + cost <= cash:
                        cash -= gross + cost
                        shares[target] = shares.get(target, 0) + qty
                        entry_price[target] = px
                        trade_rows.append({
                            "signal_date": current_date,
                            "trade_date": fill.date,
                            "ts_code": target,
                            "action": "BUY",
                            "reason": "RANK_IN",
                            "shares": qty,
                            "price": trade_px,
                            "raw_price": px,
                            "gross": gross,
                            "cost": cost,
                            "cash_after": cash,
                            "fill_source": fill.source,
                            "score": ranked[0].get("score", np.nan) if ranked else np.nan,
                        })

        value_date = current_date
        if fill_mode == "next_day_open" and idx + 1 < len(cal):
            value_date = cal[idx + 1]
        market_value = 0.0
        held_codes = []
        for code, qty in shares.items():
            if qty <= 0:
                continue
            px = store.latest_price(code, value_date)
            if np.isnan(px):
                px = entry_price.get(code, np.nan)
            if not np.isnan(px):
                market_value += qty * px
                held_codes.append(code)
        portfolio_value = cash + market_value
        equity_rows.append({
            "date": value_date,
            "signal_date": current_date,
            "portfolio_value": portfolio_value,
            "cash": cash,
            "market_value": market_value,
            "cash_ratio": cash / portfolio_value if portfolio_value > 0 else np.nan,
            "position_count": len(held_codes),
            "holding": "|".join(held_codes),
            "top_signal": target or "CASH",
            "top_score": ranked[0].get("score", np.nan) if ranked else np.nan,
        })

    equity = pd.DataFrame(equity_rows).drop_duplicates("date", keep="last").set_index("date").sort_index()
    trades = pd.DataFrame(trade_rows)
    signals = pd.DataFrame(signal_rows)
    stats = summarize(equity)
    return equity, trades, signals, stats


def write_report(rows: list[dict], out_dir: Path, start: str, end: str) -> Path:
    df = pd.DataFrame(rows)
    date_suffix = f"{start.replace('-', '')}_{end.replace('-', '')}"
    path = out_dir / f"friend_intraday_replication_report_{date_suffix}.md"
    freq_values = ",".join(sorted(df["frequency"].astype(str).unique())) if not df.empty else "1min"
    adjust_values = ",".join(sorted(df["adjust"].astype(str).unique())) if not df.empty else "none"
    rank_values = ",".join(sorted(df["ranking_mode"].astype(str).unique())) if not df.empty else "jq_simple,jq_auto"
    fill_values = ",".join(df["fill_mode"].astype(str).drop_duplicates().tolist()) if not df.empty else ""
    lines = [
        "# Friend Intraday Replication",
        "",
        f"- window: `{start}` to `{end}`",
        "- pool: 9 ETFs from the friend baseline",
        "- signal: previous daily close history + current-day intraday last price at configured signal time",
        "- exact JQ cost mode: fixed price slippage 0.001 yuan/share plus 2bp fund commission with 1 yuan minimum",
        "- no independent stop loss: original JoinQuant code only sells when the current holding is not the top-ranked ETF",
        "- data: `data/local_etf_data/2000-2025/{1min,5min}` and `data/local_etf_data/2026/2026_{1分钟,5分钟}`",
        "- note: this is independent from the daily ETF Loop engine; old daily `friend_mode` remains disabled.",
        "",
        "## Reproduce",
        "",
        "```bash",
        (
            "source activate.sh && python runs/etf_loop/run_friend_intraday_replication.py "
            f"--start {start} --end {end} --frequency {freq_values} --adjust {adjust_values} "
            f"--ranking-modes {rank_values} --fill-modes {fill_values}"
        ),
        "```",
        "",
        "## Results",
        "",
        "| variant | rank | freq | fill mode | adjust | exact cost | ann | CAGR | sharpe | dd | total | final | trades | buys | sells |",
        "|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['variant']} | {r['ranking_mode']} | {r['frequency']} | {r['fill_mode']} | {r['adjust']} | "
            f"{r['exact_jq_cost']} | {pct(r['annual_return'])} | "
            f"{pct(r['cagr'])} | {r['sharpe_ratio']:.2f} | {pct(r['max_drawdown'])} | {pct(r['total_return'])} | "
            f"{r['final_value']:.0f} | {int(r['trade_count'])} | {int(r['buy_count'])} | {int(r['sell_count'])} |"
        )
    lines += [
        "",
        "## Friend Claim",
        "",
        f"- claimed annual return: `{pct(FRIEND_CLAIM['annual_return'])}`",
        f"- claimed max drawdown: `{pct(FRIEND_CLAIM['max_drawdown'])}`",
        "",
        "## Interpretation",
        "",
        "- `same_0950_close` is optimistic and may contain same-minute bar lookahead if the local minute timestamp represents the completed 09:50 bar.",
        "- `same_0951_open` is the first more tradeable T+0 assumption available from 1-minute bars.",
        "- `same_0955_open` is a conservative T+0 assumption available from 5-minute bars.",
        "- `next_day_open` is included only as a latency comparison; it is not the friend's intended execution model.",
        "- The original code's intraday/T+0 execution assumption is material: switching to next-day open cuts performance sharply in the simple 25d variant and changes drawdown behavior.",
        "- Remaining gaps can still come from JoinQuant fill simulation, exact current_data timing, unit_net_value source, and any unpublished code differences.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    latest_report = out_dir / "friend_intraday_replication_report.md"
    latest_report.write_text("\n".join(lines), encoding="utf-8")
    df.to_csv(out_dir / f"friend_intraday_replication_summary_{date_suffix}.csv", index=False)
    df.to_csv(out_dir / "friend_intraday_replication_summary.csv", index=False)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Replicate friend ETF strategy with local intraday data")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--signal-time", default="09:50")
    parser.add_argument("--signal-field", choices=["open", "close"], default="close")
    parser.add_argument("--frequency", choices=["1min", "5min"], default="1min")
    parser.add_argument("--fill-modes", default="same_0950_close,same_0951_open,same_0955_open,next_day_open")
    parser.add_argument("--adjust", choices=["none", "pre"], default="none")
    parser.add_argument("--ranking-modes", default="jq_simple,jq_auto")
    parser.add_argument("--legacy-score", action="store_true", help="Also run the old approximation based on this project's score_etf")
    parser.add_argument("--rate-slippage", action="store_true", help="Use old percentage slippage instead of JoinQuant FixedSlippage emulation")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    store = LocalETFIntradayStore(
        LOCAL_DATA,
        FRIEND_POOL_9,
        args.start,
        args.end,
        args.signal_time,
        args.signal_field,
        adjust=args.adjust,
        frequency=args.frequency,
    )
    if len(store.ts_codes) != len(FRIEND_POOL_9):
        missing = sorted(set(FRIEND_POOL_9) - set(store.ts_codes))
        raise RuntimeError(f"Missing intraday ETF files: {missing}")

    rows: list[dict] = []
    ranking_modes = [x.strip() for x in args.ranking_modes.split(",") if x.strip()]
    if args.legacy_score:
        ranking_modes.append("legacy_score")
    for ranking_mode in ranking_modes:
        if ranking_mode == "jq_simple":
            variant = "simple25d"
            full_logic = False
        elif ranking_mode == "jq_auto":
            variant = "full_friend_logic"
            full_logic = True
        elif ranking_mode == "legacy_score":
            variant = "legacy_score"
            full_logic = True
        else:
            raise ValueError(f"Unsupported ranking mode: {ranking_mode}")
        for fill_mode in [x.strip() for x in args.fill_modes.split(",") if x.strip()]:
            tag = f"FRMIN_{variant}_{ranking_mode}_{args.frequency}_{fill_mode}"
            if args.adjust != "none":
                tag = f"{tag}_{args.adjust}"
            params = build_friend_params(args.start, args.end, tag, full_logic)
            equity, trades, signals, stats = run_intraday_backtest(
                store,
                params,
                fill_mode,
                ranking_mode,
                exact_jq_cost=not args.rate_slippage,
            )
            suffix = f"{tag}_{args.start.replace('-', '')}_{args.end.replace('-', '')}"
            equity.to_csv(OUT / f"equity_{suffix}.csv")
            trades.to_csv(OUT / f"trades_{suffix}.csv", index=False)
            signals.to_csv(OUT / f"signals_{suffix}.csv", index=False)
            row = {
                "variant": variant,
                "ranking_mode": ranking_mode,
                "frequency": args.frequency,
                "signal_time": args.signal_time,
                "signal_field": args.signal_field,
                "fill_mode": fill_mode,
                "adjust": args.adjust,
                "exact_jq_cost": not args.rate_slippage,
                **stats,
                "trade_count": int(len(trades)),
                "buy_count": int((trades.get("action", pd.Series(dtype=str)) == "BUY").sum()) if not trades.empty else 0,
                "sell_count": int((trades.get("action", pd.Series(dtype=str)) == "SELL").sum()) if not trades.empty else 0,
            }
            rows.append(row)
            print(
                f"{variant:<18s} {ranking_mode:<10s} {args.frequency:<5s} {fill_mode:<16s} "
                f"adjust={args.adjust:<4s} exact_cost={not args.rate_slippage} ann={pct(row['annual_return'])} "
                f"sharpe={row['sharpe_ratio']:.2f} dd={pct(row['max_drawdown'])} trades={row['trade_count']}"
            )

    report = write_report(rows, OUT, args.start, args.end)
    print("Saved:", OUT / "friend_intraday_replication_summary.csv")
    print("Saved:", report)


if __name__ == "__main__":
    main()
