#!/usr/bin/env python3
"""Minute-level execution overlay for existing ETF Loop daily signals.

The daily ETF Loop engine remains the source of truth for signals and target
weights.  This runner only re-simulates how those targets could be executed
with local 1-minute ETF data.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from run_detailed_trade_log import build_params  # noqa: E402
from strategies.etf_loop_engine import run_and_save  # noqa: E402
from strategies.etf_loop_strategy import ETFDailyStore, SectorProsperityCache  # noqa: E402
from strategies.etf_loop_strategy import _lot_floor  # noqa: E402


LOCAL_DATA = PROJECT_ROOT / "data" / "local_etf_data"
SIGNAL_OUT = PROJECT_ROOT / "outputs" / "etf_loop" / "minute_execution_signals"
OUT = PROJECT_ROOT / "outputs" / "etf_loop" / "minute_execution_backtest"


EXECUTION_MODES: dict[str, dict[str, Any]] = {
    "open_0935": {"delay": "1", "kind": "point", "start": "09:35", "end": "09:35", "field": "open"},
    "vwap_0935_1030": {"delay": "1", "kind": "vwap", "start": "09:35", "end": "10:30"},
    "twap_0935_1030": {"delay": "1", "kind": "twap", "start": "09:35", "end": "10:30"},
    "twap_1000_1430": {"delay": "1", "kind": "twap", "start": "10:00", "end": "14:30"},
    "tail_vwap_1430_1455": {"delay": "1", "kind": "vwap", "start": "14:30", "end": "14:55"},
    "split_0935_1455": {
        "delay": "1",
        "kind": "split_twap",
        "start": "09:35",
        "end": "14:55",
        "windows": [("09:35", "10:30"), ("14:30", "14:55")],
    },
    "t2_open_0935": {"delay": "2", "kind": "point", "start": "09:35", "end": "09:35", "field": "open"},
}


QDII_CODES = {
    "501018",  # 南方原油
    "160216",
    "160416",
    "160717",
    "161126",
    "164824",
}

COMMODITY_CODES = {
    "159980",  # 有色
    "159981",
    "159985",
    "159934",
    "159937",
    "501018",  # 原油
    "518880",  # 黄金
}


@dataclass
class FillContext:
    price: float
    raw_price: float
    date: pd.Timestamp
    start_time: str
    end_time: str
    window_turnover: float
    daily_turnover: float
    window_volume: float
    limit_up: float
    limit_down: float
    is_limit_up: bool
    is_limit_down: bool
    is_suspended: bool
    spread_proxy_bp: float
    window_range_bp: float
    source: str


@dataclass(frozen=True)
class SlippageConfig:
    model: str
    sqrt_k: float
    commission_bp: float
    base_slippage_bp: float
    cross_border_penalty_bp: float
    commodity_penalty_bp: float
    open_penalty_bp: float
    spread_penalty_mult: float
    spread_penalty_cap_bp: float
    max_slippage_bp: float
    near_limit_threshold_bp: float
    near_limit_capacity_mult: float


def pct(x: float) -> str:
    return "" if pd.isna(x) else f"{x * 100:.2f}%"


def local_code(ts_code: str) -> str:
    return ts_code.split(".")[0]


def is_cross_border_etf(ts_code: str) -> bool:
    code = local_code(ts_code)
    return code.startswith("513") or code in QDII_CODES


def is_commodity_etf(ts_code: str) -> bool:
    code = local_code(ts_code)
    return code.startswith("518") or code in COMMODITY_CODES


def lot_floor_shares(value: float, price: float) -> int:
    if price <= 0 or value <= 0:
        return 0
    return _lot_floor(value / price)


def summarize(equity: pd.DataFrame) -> dict[str, float]:
    nav = equity["portfolio_value"].dropna()
    daily = nav.pct_change().dropna()
    if len(daily) < 2:
        return {
            "annual_return": np.nan,
            "cagr": np.nan,
            "sharpe": np.nan,
            "max_drawdown": np.nan,
            "total_return": np.nan,
            "final_value": float(nav.iloc[-1]) if len(nav) else np.nan,
        }
    ann = float(daily.mean() * 252.0)
    vol = float(daily.std() * np.sqrt(252.0))
    return {
        "annual_return": ann,
        "cagr": float((nav.iloc[-1] / nav.iloc[0]) ** (252.0 / len(daily)) - 1.0),
        "sharpe": ann / vol if vol > 0 else np.nan,
        "max_drawdown": float((nav / nav.cummax() - 1.0).min()),
        "total_return": float(nav.iloc[-1] / nav.iloc[0] - 1.0),
        "final_value": float(nav.iloc[-1]),
    }


class LocalMinuteStore:
    def __init__(
        self,
        codes: list[str],
        start: str,
        end: str,
        frequency: str = "1min",
        price_adjustment: str = "none",
    ) -> None:
        self.start = pd.Timestamp(start)
        self.end = pd.Timestamp(end)
        self.frequency = frequency
        self.price_adjustment = price_adjustment
        self.frames: dict[str, pd.DataFrame] = {}
        self._day_cache: dict[tuple[str, pd.Timestamp], pd.DataFrame] = {}
        self._adjustment_cache: dict[tuple[str, pd.Timestamp], float] = {}
        self.daily_store = self._build_daily_store(codes) if price_adjustment == "engine" else None
        for code in sorted(set(codes)):
            df = self._load_code(code)
            if not df.empty:
                self.frames[code] = df
        self.calendar = self._build_calendar()

    def _build_daily_store(self, codes: list[str]) -> ETFDailyStore | None:
        cache = SectorProsperityCache(PROJECT_ROOT / "config" / "tushare_token.txt", PROJECT_ROOT / "data" / "tushare_cache")
        store = ETFDailyStore(cache, sorted(set(codes)), str(self.start), str(self.end))
        return store if store.ts_codes else None

    def _engine_price_scale(self, code: str, date: pd.Timestamp) -> float:
        if self.daily_store is None:
            return 1.0
        key = (code, pd.Timestamp(date))
        if key in self._adjustment_cache:
            return self._adjustment_cache[key]
        scale = 1.0
        ds = self.daily_store
        date = pd.Timestamp(date)
        try:
            if (
                code in ds.open.columns
                and code in ds.signal_open.columns
                and date in ds.open.index
                and date in ds.signal_open.index
            ):
                raw = float(ds.open.at[date, code])
                adj = float(ds.signal_open.at[date, code])
                if pd.notna(raw) and raw > 0 and pd.notna(adj) and adj > 0:
                    scale = adj / raw
            if scale == 1.0 and code in ds.raw_close.columns and code in ds.signal_close.columns:
                raw = float(ds.raw_close.at[date, code]) if date in ds.raw_close.index else np.nan
                adj = float(ds.signal_close.at[date, code]) if date in ds.signal_close.index else np.nan
                if pd.notna(raw) and raw > 0 and pd.notna(adj) and adj > 0:
                    scale = adj / raw
        except Exception:
            scale = 1.0
        self._adjustment_cache[key] = scale
        return scale

    def _apply_engine_adjustment(self, code: str, df: pd.DataFrame) -> pd.DataFrame:
        if self.price_adjustment != "engine" or self.daily_store is None or df.empty:
            return df
        out = df.copy()
        scales = out["date"].map(lambda d: self._engine_price_scale(code, pd.Timestamp(d))).astype(float)
        for col in ["open", "high", "low", "close", "prev_close", "limit_up", "limit_down"]:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce") * scales.to_numpy()
        if "amount" in out.columns:
            out["amount"] = pd.to_numeric(out["amount"], errors="coerce") * scales.to_numpy()
        return out

    def _load_code(self, ts_code: str) -> pd.DataFrame:
        local = ts_code.split(".")[0]
        parts = []
        paths = [
            LOCAL_DATA / "2000-2025" / self.frequency / f"{local}.csv",
            LOCAL_DATA / "2026" / ("2026_1分钟" if self.frequency == "1min" else "2026_5分钟") / f"{local}.csv",
        ]
        for path in paths:
            if not path.exists():
                continue
            df = pd.read_csv(path)
            if df.empty:
                continue
            amount_col = "amount" if "amount" in df.columns else "money" if "money" in df.columns else None
            cols = [
                "date",
                "time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "prev_close",
                "limit_up",
                "limit_down",
            ]
            if amount_col:
                cols.append(amount_col)
            cols = [c for c in cols if c in df.columns]
            df = df[cols].copy()
            if amount_col and amount_col != "amount":
                df["amount"] = df[amount_col]
            elif "amount" not in df.columns:
                df["amount"] = np.nan
            for col in ["open", "high", "low", "close", "volume", "amount", "prev_close", "limit_up", "limit_down"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            df["date"] = pd.to_datetime(df["date"])
            df["time"] = df["time"].astype(str).str.slice(0, 5)
            parts.append(df)
        if not parts:
            return pd.DataFrame()
        out = pd.concat(parts, ignore_index=True)
        out = out[(out["date"] >= self.start - pd.DateOffset(days=5)) & (out["date"] <= self.end + pd.DateOffset(days=5))]
        out = out.drop_duplicates(["date", "time"], keep="last").sort_values(["date", "time"])
        out = self._apply_engine_adjustment(ts_code, out)
        return out

    def _build_calendar(self) -> pd.DatetimeIndex:
        dates: set[pd.Timestamp] = set()
        for df in self.frames.values():
            dates.update(pd.Timestamp(x) for x in df["date"].dropna().unique())
        return pd.DatetimeIndex(sorted(dates))

    def nth_trading_day_after(self, date: pd.Timestamp, delay: int) -> pd.Timestamp | None:
        future = self.calendar[self.calendar > pd.Timestamp(date)]
        if len(future) < delay:
            return None
        return pd.Timestamp(future[delay - 1])

    def day_rows(self, code: str, date: pd.Timestamp) -> pd.DataFrame:
        key = (code, pd.Timestamp(date))
        if key in self._day_cache:
            return self._day_cache[key]
        df = self.frames.get(code)
        if df is None or df.empty:
            return pd.DataFrame()
        rows = df[df["date"].eq(pd.Timestamp(date))]
        self._day_cache[key] = rows
        return rows

    def close_price(self, code: str, date: pd.Timestamp) -> float:
        rows = self.day_rows(code, date)
        if rows.empty:
            return np.nan
        px = rows["close"].dropna()
        return float(px.iloc[-1]) if len(px) else np.nan

    def valuation_close_price(self, code: str, date: pd.Timestamp) -> float:
        if self.price_adjustment == "engine" and self.daily_store is not None:
            px = self.daily_store.latest_price(code, pd.Timestamp(date))
            if pd.notna(px) and px > 0:
                return float(px)
        return self.close_price(code, date)

    def fill_context(self, code: str, date: pd.Timestamp, mode: str) -> FillContext | None:
        spec = EXECUTION_MODES[mode]
        day = self.day_rows(code, date)
        if day.empty:
            return None
        if spec["kind"] == "split_twap":
            window_parts = [
                day[(day["time"] >= start) & (day["time"] <= end)].copy()
                for start, end in spec["windows"]
            ]
            non_empty_parts = [w for w in window_parts if not w.empty]
            if not non_empty_parts:
                return None
            window = pd.concat(non_empty_parts, ignore_index=True)
        else:
            window = day[(day["time"] >= spec["start"]) & (day["time"] <= spec["end"])].copy()
        if window.empty:
            return None
        day_turnover = float(day["amount"].fillna(0).sum())
        window_turnover = float(window["amount"].fillna(0).sum())
        window_volume = float(window["volume"].fillna(0).sum())
        if spec["kind"] == "point":
            row = window.head(1).iloc[0]
            raw_price = float(row.get(spec.get("field", "open"), np.nan))
        elif spec["kind"] == "vwap":
            if window_turnover > 0 and window_volume > 0:
                if self.price_adjustment == "engine":
                    valid = window[["close", "volume"]].dropna()
                    valid = valid[valid["volume"] > 0]
                    if not valid.empty:
                        raw_price = float((valid["close"].astype(float) * valid["volume"].astype(float)).sum() / valid["volume"].astype(float).sum())
                    else:
                        raw_price = np.nan
                else:
                    raw_price = window_turnover / window_volume
            else:
                raw_price = float(window["close"].dropna().mean())
        elif spec["kind"] == "twap":
            raw_price = float(window["close"].dropna().mean())
        elif spec["kind"] == "split_twap":
            leg_prices = []
            for leg in window_parts:
                if not leg.empty and leg["close"].notna().any():
                    leg_prices.append(float(leg["close"].dropna().mean()))
            raw_price = float(np.mean(leg_prices)) if leg_prices else np.nan
        else:
            raise ValueError(f"Unsupported execution kind: {spec['kind']}")
        if pd.isna(raw_price) or raw_price <= 0:
            return None
        limit_up = float(window["limit_up"].dropna().iloc[0]) if "limit_up" in window.columns and window["limit_up"].notna().any() else np.nan
        limit_down = float(window["limit_down"].dropna().iloc[0]) if "limit_down" in window.columns and window["limit_down"].notna().any() else np.nan
        is_limit_up = bool(pd.notna(limit_up) and raw_price >= limit_up * 0.999)
        is_limit_down = bool(pd.notna(limit_down) and raw_price <= limit_down * 1.001)
        is_suspended = bool(day_turnover <= 0 or window_turnover <= 0)
        spread_parts = window[["high", "low", "close"]].dropna()
        spread_parts = spread_parts[spread_parts["close"] > 0]
        if spread_parts.empty:
            spread_proxy_bp = np.nan
        else:
            spread_proxy_bp = float(((spread_parts["high"] - spread_parts["low"]) / spread_parts["close"]).clip(lower=0).median() * 10000.0)
        high = window["high"].dropna().max()
        low = window["low"].dropna().min()
        window_range_bp = float((high / low - 1.0) * 10000.0) if pd.notna(high) and pd.notna(low) and low > 0 else np.nan
        return FillContext(
            price=raw_price,
            raw_price=raw_price,
            date=pd.Timestamp(date),
            start_time=spec["start"],
            end_time=spec["end"],
            window_turnover=window_turnover,
            daily_turnover=day_turnover,
            window_volume=window_volume,
            limit_up=limit_up,
            limit_down=limit_down,
            is_limit_up=is_limit_up,
            is_limit_down=is_limit_down,
            is_suspended=is_suspended,
            spread_proxy_bp=spread_proxy_bp,
            window_range_bp=window_range_bp,
            source=mode,
        )


def generate_daily_signal_logs(setting: str, start: str, trading_start: str, end: str, force: bool = False) -> tuple[Path, Path, Path]:
    SIGNAL_OUT.mkdir(parents=True, exist_ok=True)
    params = build_params(setting, start, end, trading_start, signal_top_n=80)
    params.exp_tag = f"MINEXEC_SIGNAL_{setting}_{start.replace('-', '')}_{end.replace('-', '')}"
    params.write_detailed_logs = True
    suffix = f"{params.exp_tag}_h{params.holdings_num}_{params.start.replace('-', '')}_{params.end.replace('-', '')}"
    paths = (
        SIGNAL_OUT / f"etf_loop_account_{suffix}.csv",
        SIGNAL_OUT / f"etf_loop_signals_{suffix}.csv",
        SIGNAL_OUT / f"etf_loop_equity_{suffix}.csv",
    )
    if force or not all(p.exists() for p in paths):
        run_and_save(params, SIGNAL_OUT)
    else:
        print(f"Reusing signal logs: {params.exp_tag}")
    return paths


def load_target_schedule(account_path: Path, signals_path: Path) -> tuple[pd.DataFrame, dict[pd.Timestamp, dict[str, float]], dict[pd.Timestamp, float]]:
    account = pd.read_csv(account_path)
    signals = pd.read_csv(signals_path)
    account["signal_date"] = pd.to_datetime(account["signal_date"])
    account["trade_date"] = pd.to_datetime(account["trade_date"])
    signals["signal_date"] = pd.to_datetime(signals["signal_date"])
    signals["trade_date"] = pd.to_datetime(signals["trade_date"])
    targets: dict[pd.Timestamp, dict[str, float]] = {}
    exposures: dict[pd.Timestamp, float] = {}
    for signal_date, grp in signals[signals["in_target"].fillna(False)].groupby("signal_date"):
        w = grp.dropna(subset=["target_weight"]).drop_duplicates("ts_code", keep="first")
        targets[pd.Timestamp(signal_date)] = {str(r.ts_code): float(r.target_weight) for r in w.itertuples()}
        if "target_exposure" in grp.columns and grp["target_exposure"].notna().any():
            exposures[pd.Timestamp(signal_date)] = float(grp["target_exposure"].dropna().iloc[0])
    for row in account.itertuples():
        sd = pd.Timestamp(row.signal_date)
        if sd not in targets:
            targets[sd] = {}
        exposures[sd] = float(getattr(row, "target_exposure", 1.0))
    return account.sort_values("signal_date"), targets, exposures


def extra_penalty_bp(code: str, ctx: FillContext, cfg: SlippageConfig) -> dict[str, float]:
    cross_border = cfg.cross_border_penalty_bp if is_cross_border_etf(code) else 0.0
    commodity = cfg.commodity_penalty_bp if is_commodity_etf(code) else 0.0
    open_penalty = cfg.open_penalty_bp if ctx.start_time <= "09:35" else 0.0
    spread_proxy = ctx.spread_proxy_bp if pd.notna(ctx.spread_proxy_bp) else 0.0
    spread_penalty = min(cfg.spread_penalty_cap_bp, spread_proxy * cfg.spread_penalty_mult)
    return {
        "cross_border_penalty_bp": cross_border,
        "commodity_penalty_bp": commodity,
        "open_penalty_bp": open_penalty,
        "spread_penalty_bp": spread_penalty,
        "extra_penalty_bp": cross_border + commodity + open_penalty + spread_penalty,
    }


def impact_slippage_bp(code: str, order_value: float, ctx: FillContext, cfg: SlippageConfig) -> tuple[float, bool, dict[str, float]]:
    window_turnover = ctx.window_turnover
    if window_turnover <= 0:
        return cfg.base_slippage_bp, True, {
            "participation_rate_requested": np.nan,
            "impact_component_bp": 0.0,
            "extra_penalty_bp": 0.0,
        }
    pr = order_value / window_turnover
    too_large = pr > 0.03
    if cfg.model == "tiered":
        if pr <= 0.005:
            impact = cfg.base_slippage_bp
        elif pr <= 0.01:
            impact = max(cfg.base_slippage_bp, 5.0)
        elif pr <= 0.03:
            impact = max(cfg.base_slippage_bp, 10.0)
        else:
            impact = max(cfg.base_slippage_bp, 20.0)
    elif cfg.model == "sqrt":
        impact = cfg.base_slippage_bp + cfg.sqrt_k * np.sqrt(max(pr, 0.0))
    else:
        raise ValueError(f"Unsupported slippage model: {cfg.model}")
    details = {
        "participation_rate_requested": pr,
        "impact_component_bp": float(max(0.0, impact - cfg.base_slippage_bp)),
    }
    penalty = extra_penalty_bp(code, ctx, cfg)
    details.update(penalty)
    slip = min(cfg.max_slippage_bp, max(0.0, impact + penalty["extra_penalty_bp"]))
    return float(slip), too_large, details


def execute_order(
    *,
    cash: float,
    shares: dict[str, int],
    code: str,
    side: str,
    desired_value: float,
    ctx: FillContext | None,
    slippage_config: SlippageConfig,
    max_participation: float,
) -> tuple[float, dict[str, int], dict[str, Any]]:
    record: dict[str, Any] = {
        "ts_code": code,
        "side": side,
        "order_value": desired_value,
        "filled_value": 0.0,
        "unfilled_value": desired_value,
        "fill_ratio": 0.0,
        "shares": 0,
        "raw_price": np.nan,
        "actual_fill_price": np.nan,
        "commission": 0.0,
        "slippage_bp": np.nan,
        "slippage_model": slippage_config.model,
        "base_slippage_bp": slippage_config.base_slippage_bp,
        "commission_bp": slippage_config.commission_bp,
        "impact_component_bp": np.nan,
        "extra_penalty_bp": np.nan,
        "cross_border_penalty_bp": 0.0,
        "commodity_penalty_bp": 0.0,
        "open_penalty_bp": 0.0,
        "spread_penalty_bp": 0.0,
        "spread_proxy_bp": np.nan,
        "window_range_bp": np.nan,
        "is_cross_border": is_cross_border_etf(code),
        "is_commodity": is_commodity_etf(code),
        "near_limit": False,
        "near_limit_distance_bp": np.nan,
        "capacity_multiplier": 1.0,
        "participation_rate_requested": np.nan,
        "participation_rate": np.nan,
        "daily_turnover": np.nan,
        "execution_window_turnover": np.nan,
        "is_limit_up": False,
        "is_limit_down": False,
        "is_suspended": False,
        "reject_reason": "",
    }
    if desired_value <= 0:
        record["reject_reason"] = "NO_ORDER"
        return cash, shares, record
    if ctx is None:
        record["reject_reason"] = "NO_MINUTE_DATA"
        return cash, shares, record
    record.update({
        "raw_price": ctx.raw_price,
        "daily_turnover": ctx.daily_turnover,
        "execution_window_turnover": ctx.window_turnover,
        "spread_proxy_bp": ctx.spread_proxy_bp,
        "window_range_bp": ctx.window_range_bp,
        "is_limit_up": ctx.is_limit_up,
        "is_limit_down": ctx.is_limit_down,
        "is_suspended": ctx.is_suspended,
    })
    if ctx.is_suspended:
        record["reject_reason"] = "SUSPENDED_OR_NO_TURNOVER"
        return cash, shares, record
    if side == "BUY" and ctx.is_limit_up:
        record["reject_reason"] = "LIMIT_UP_BUY_BLOCKED"
        return cash, shares, record
    if side == "SELL" and ctx.is_limit_down:
        record["reject_reason"] = "LIMIT_DOWN_SELL_BLOCKED"
        return cash, shares, record

    capacity_multiplier = 1.0
    near_limit_distance_bp = np.nan
    if slippage_config.near_limit_threshold_bp > 0:
        if side == "BUY" and pd.notna(ctx.limit_up) and ctx.limit_up > 0:
            near_limit_distance_bp = float((ctx.limit_up / ctx.raw_price - 1.0) * 10000.0)
            if 0 <= near_limit_distance_bp <= slippage_config.near_limit_threshold_bp:
                capacity_multiplier = slippage_config.near_limit_capacity_mult
        elif side == "SELL" and pd.notna(ctx.limit_down) and ctx.limit_down > 0:
            near_limit_distance_bp = float((ctx.raw_price / ctx.limit_down - 1.0) * 10000.0)
            if 0 <= near_limit_distance_bp <= slippage_config.near_limit_threshold_bp:
                capacity_multiplier = slippage_config.near_limit_capacity_mult
    record.update({
        "near_limit": capacity_multiplier < 1.0,
        "near_limit_distance_bp": near_limit_distance_bp,
        "capacity_multiplier": capacity_multiplier,
    })
    cap_value = ctx.window_turnover * max_participation * capacity_multiplier
    fill_budget = min(desired_value, cap_value)
    if side == "BUY":
        fill_budget = min(fill_budget, cash)
    else:
        fill_budget = min(fill_budget, shares.get(code, 0) * ctx.raw_price)
    slip_bp, too_large, slip_details = impact_slippage_bp(code, desired_value, ctx, slippage_config)
    record.update(slip_details)
    if too_large and desired_value > cap_value:
        record["reject_reason"] = "PARTIAL_CAPACITY"
    trade_price = ctx.raw_price * (1.0 + slip_bp / 10000.0) if side == "BUY" else ctx.raw_price * (1.0 - slip_bp / 10000.0)
    qty = lot_floor_shares(fill_budget, trade_price)
    if side == "SELL":
        qty = min(qty, shares.get(code, 0))
    if qty <= 0:
        record["reject_reason"] = record["reject_reason"] or "LOT_TOO_SMALL"
        return cash, shares, record
    gross = qty * trade_price
    commission = gross * slippage_config.commission_bp / 10000.0
    if side == "BUY":
        if gross + commission > cash:
            qty = lot_floor_shares(cash / (1.0 + slippage_config.commission_bp / 10000.0), trade_price)
            gross = qty * trade_price
            commission = gross * slippage_config.commission_bp / 10000.0
        if qty <= 0:
            record["reject_reason"] = record["reject_reason"] or "INSUFFICIENT_CASH"
            return cash, shares, record
        cash -= gross + commission
        shares[code] = shares.get(code, 0) + qty
    else:
        cash += gross - commission
        shares[code] = shares.get(code, 0) - qty
        if shares[code] <= 0:
            shares.pop(code, None)
    participation = gross / ctx.window_turnover if ctx.window_turnover > 0 else np.nan
    record.update({
        "filled_value": gross,
        "unfilled_value": max(0.0, desired_value - gross),
        "fill_ratio": gross / desired_value if desired_value > 0 else 0.0,
        "shares": qty,
        "actual_fill_price": trade_price,
        "commission": commission,
        "slippage_bp": slip_bp,
        "participation_rate": participation,
    })
    if gross < desired_value * 0.999 and not record["reject_reason"]:
        record["reject_reason"] = "PARTIAL_LOT_OR_CASH"
    return cash, shares, record


def run_overlay(
    *,
    setting: str,
    trading_start: str,
    initial_cash: float,
    execution_mode: str,
    roundtrip_cost_bp: float,
    max_participation: float,
    slippage_model: str,
    sqrt_k: float,
    cross_border_penalty_bp: float,
    commodity_penalty_bp: float,
    open_penalty_bp: float,
    spread_penalty_mult: float,
    spread_penalty_cap_bp: float,
        max_slippage_bp: float,
        near_limit_threshold_bp: float,
        near_limit_capacity_mult: float,
    account: pd.DataFrame,
    targets_by_signal: dict[pd.Timestamp, dict[str, float]],
    exposure_by_signal: dict[pd.Timestamp, float],
    store: LocalMinuteStore,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    commission_bp = 1.5
    base_slippage_bp = max(0.0, roundtrip_cost_bp / 2.0 - commission_bp)
    slippage_config = SlippageConfig(
        model=slippage_model,
        sqrt_k=sqrt_k,
        commission_bp=commission_bp,
        base_slippage_bp=base_slippage_bp,
        cross_border_penalty_bp=cross_border_penalty_bp,
        commodity_penalty_bp=commodity_penalty_bp,
        open_penalty_bp=open_penalty_bp,
        spread_penalty_mult=spread_penalty_mult,
        spread_penalty_cap_bp=spread_penalty_cap_bp,
        max_slippage_bp=max_slippage_bp,
        near_limit_threshold_bp=near_limit_threshold_bp,
        near_limit_capacity_mult=near_limit_capacity_mult,
    )

    cash = initial_cash
    shares: dict[str, int] = {}
    equity_rows: list[dict[str, Any]] = []
    order_rows: list[dict[str, Any]] = []

    for row in account.itertuples():
        signal_date = pd.Timestamp(row.signal_date)
        if signal_date < pd.Timestamp(trading_start):
            continue
        target = targets_by_signal.get(signal_date, {})
        target_exposure = exposure_by_signal.get(signal_date, 1.0)
        delay = int(EXECUTION_MODES[execution_mode]["delay"])
        exec_date = store.nth_trading_day_after(signal_date, delay)
        if exec_date is None:
            continue

        all_codes = sorted(set(shares) | set(target))
        contexts = {c: store.fill_context(c, exec_date, execution_mode) for c in all_codes}
        price_for_value = {
            c: (contexts[c].raw_price if contexts[c] is not None else store.close_price(c, exec_date))
            for c in all_codes
        }
        portfolio_before = cash + sum(shares.get(c, 0) * price_for_value.get(c, np.nan) for c in shares if pd.notna(price_for_value.get(c, np.nan)))
        investable = portfolio_before * target_exposure
        desired_value = {c: investable * target.get(c, 0.0) for c in all_codes}
        current_value = {c: shares.get(c, 0) * price_for_value.get(c, 0.0) for c in all_codes}

        for code in all_codes:
            diff = current_value.get(code, 0.0) - desired_value.get(code, 0.0)
            if diff <= max(100.0, portfolio_before * 0.0005):
                continue
            cash, shares, rec = execute_order(
                cash=cash,
                shares=shares,
                code=code,
                side="SELL",
                desired_value=diff,
                ctx=contexts.get(code),
                slippage_config=slippage_config,
                max_participation=max_participation,
            )
            rec.update({
                "signal_date": signal_date,
                "trade_date": exec_date,
                "execution_mode": execution_mode,
                "roundtrip_cost_bp": roundtrip_cost_bp,
                "sqrt_k": sqrt_k,
                "max_slippage_bp": max_slippage_bp,
                "target_weight": target.get(code, 0.0),
                "target_exposure": target_exposure,
                "portfolio_before": portfolio_before,
                "execution_start_time": EXECUTION_MODES[execution_mode]["start"],
                "execution_end_time": EXECUTION_MODES[execution_mode]["end"],
            })
            order_rows.append(rec)

        all_codes = sorted(set(shares) | set(target))
        contexts.update({c: store.fill_context(c, exec_date, execution_mode) for c in all_codes if c not in contexts})
        price_for_value = {
            c: (contexts[c].raw_price if contexts.get(c) is not None else store.close_price(c, exec_date))
            for c in all_codes
        }
        portfolio_mid = cash + sum(shares.get(c, 0) * price_for_value.get(c, np.nan) for c in shares if pd.notna(price_for_value.get(c, np.nan)))
        investable = portfolio_mid * target_exposure
        desired_value = {c: investable * target.get(c, 0.0) for c in all_codes}
        current_value = {c: shares.get(c, 0) * price_for_value.get(c, 0.0) for c in all_codes}

        for code in sorted(target):
            diff = desired_value.get(code, 0.0) - current_value.get(code, 0.0)
            if diff <= max(100.0, portfolio_mid * 0.0005):
                continue
            cash, shares, rec = execute_order(
                cash=cash,
                shares=shares,
                code=code,
                side="BUY",
                desired_value=diff,
                ctx=contexts.get(code),
                slippage_config=slippage_config,
                max_participation=max_participation,
            )
            rec.update({
                "signal_date": signal_date,
                "trade_date": exec_date,
                "execution_mode": execution_mode,
                "roundtrip_cost_bp": roundtrip_cost_bp,
                "sqrt_k": sqrt_k,
                "max_slippage_bp": max_slippage_bp,
                "target_weight": target.get(code, 0.0),
                "target_exposure": target_exposure,
                "portfolio_before": portfolio_mid,
                "execution_start_time": EXECUTION_MODES[execution_mode]["start"],
                "execution_end_time": EXECUTION_MODES[execution_mode]["end"],
            })
            order_rows.append(rec)

        market_value = 0.0
        for code, qty in list(shares.items()):
            px = store.close_price(code, exec_date)
            if pd.isna(px) or px <= 0:
                ctx = contexts.get(code)
                px = ctx.raw_price if ctx is not None else np.nan
            if pd.notna(px) and px > 0:
                market_value += qty * px
        portfolio_value = cash + market_value
        actual_exposure = market_value / portfolio_value if portfolio_value > 0 else np.nan
        equity_rows.append({
            "date": exec_date,
            "signal_date": signal_date,
            "portfolio_value": portfolio_value,
            "cash": cash,
            "market_value": market_value,
            "target_exposure": target_exposure,
            "actual_exposure": actual_exposure,
            "exposure_gap": actual_exposure - target_exposure if pd.notna(actual_exposure) else np.nan,
            "position_count": sum(1 for v in shares.values() if v > 0),
            "target_count": len(target),
            "execution_mode": execution_mode,
            "roundtrip_cost_bp": roundtrip_cost_bp,
            "slippage_model": slippage_model,
            "sqrt_k": sqrt_k,
            "cross_border_penalty_bp": cross_border_penalty_bp,
            "commodity_penalty_bp": commodity_penalty_bp,
            "open_penalty_bp": open_penalty_bp,
            "spread_penalty_mult": spread_penalty_mult,
            "initial_cash": initial_cash,
        })

    equity = pd.DataFrame(equity_rows).drop_duplicates("date", keep="last").sort_values("date")
    orders = pd.DataFrame(order_rows)
    stats = summarize(equity)
    if not orders.empty:
        reasons = orders["reject_reason"].fillna("")
        stats.update({
            "orders": float(len(orders)),
            "partial_or_failed_rate": float((orders["fill_ratio"].fillna(0) < 0.999).mean()),
            "failed_rate": float((orders["filled_value"].fillna(0) <= 0).mean()),
            "capacity_limited_rate": float(reasons.eq("PARTIAL_CAPACITY").mean()),
            "lot_residual_rate": float(reasons.eq("PARTIAL_LOT_OR_CASH").mean()),
            "no_minute_data_rate": float(reasons.eq("NO_MINUTE_DATA").mean()),
            "no_turnover_rate": float(reasons.eq("SUSPENDED_OR_NO_TURNOVER").mean()),
            "limit_block_rate": float(reasons.isin(["LIMIT_UP_BUY_BLOCKED", "LIMIT_DOWN_SELL_BLOCKED"]).mean()),
            "avg_slippage_bp": float(orders["slippage_bp"].dropna().mean()) if orders["slippage_bp"].notna().any() else np.nan,
            "avg_impact_component_bp": float(orders["impact_component_bp"].dropna().mean()) if orders["impact_component_bp"].notna().any() else np.nan,
            "avg_extra_penalty_bp": float(orders["extra_penalty_bp"].dropna().mean()) if orders["extra_penalty_bp"].notna().any() else np.nan,
            "avg_spread_proxy_bp": float(orders["spread_proxy_bp"].dropna().mean()) if orders["spread_proxy_bp"].notna().any() else np.nan,
            "near_limit_rate": float(orders["near_limit"].fillna(False).mean()) if "near_limit" in orders else np.nan,
            "avg_participation": float(orders["participation_rate"].dropna().mean()) if orders["participation_rate"].notna().any() else np.nan,
            "avg_abs_exposure_gap": float(equity["exposure_gap"].abs().dropna().mean()) if "exposure_gap" in equity else np.nan,
        })
    else:
        stats.update({
            "orders": 0.0,
            "partial_or_failed_rate": np.nan,
            "failed_rate": np.nan,
            "capacity_limited_rate": np.nan,
            "lot_residual_rate": np.nan,
            "no_minute_data_rate": np.nan,
            "no_turnover_rate": np.nan,
            "limit_block_rate": np.nan,
            "avg_slippage_bp": np.nan,
            "avg_impact_component_bp": np.nan,
            "avg_extra_penalty_bp": np.nan,
            "avg_spread_proxy_bp": np.nan,
            "near_limit_rate": np.nan,
            "avg_participation": np.nan,
            "avg_abs_exposure_gap": np.nan,
        })
    return equity, orders, stats


def write_report(summary: pd.DataFrame, out_dir: Path, setting: str, start: str, trading_start: str, end: str, suffix: str = "") -> Path:
    suffix_part = f"_{suffix}" if suffix else ""
    path = out_dir / f"minute_execution_report_{setting}{suffix_part}_{start.replace('-', '')}_{end.replace('-', '')}.md"
    lines = [
        "# Minute Execution Backtest",
        "",
        f"- setting: `{setting}`",
        f"- signal window: `{start}` to `{end}`",
        f"- trading_start: `{trading_start}`",
        "- signal source: existing daily ETF Loop engine with detailed logs enabled",
        "- minute overlay: independent target-portfolio execution simulator; it does not change ETF scores or candidate strategy logic",
        "- constraints: minute turnover, max participation, limit-up buy block, limit-down sell block, no-minute-data rejection",
        f"- slippage model: `{summary['slippage_model'].iloc[0] if 'slippage_model' in summary.columns and len(summary) else 'tiered'}`",
        "",
        "## Reproduce",
        "",
        "```bash",
        (
            f"source activate.sh && python runs/etf_loop/run_minute_execution_backtest.py "
            f"--setting {setting} --start {start} --trading-start {trading_start} --end {end}"
        ),
        "```",
        "",
        "## Summary",
        "",
        "| setting | capital | model | mode | roundtrip bp | ann | CAGR | Sharpe | DD | final | failed | capacity-limited | avg slip bp | impact bp | extra bp | avg participation | avg abs exposure gap |",
        "|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in summary.itertuples():
        lines.append(
            f"| {r.setting} | {r.initial_cash:.0f} | {getattr(r, 'slippage_model', 'tiered')} | {r.execution_mode} | {r.roundtrip_cost_bp:.0f} | "
            f"{pct(r.annual_return)} | {pct(r.cagr)} | {r.sharpe:.2f} | {pct(r.max_drawdown)} | {r.final_value:.0f} | "
            f"{pct(r.failed_rate)} | {pct(r.capacity_limited_rate)} | {r.avg_slippage_bp:.2f} | "
            f"{getattr(r, 'avg_impact_component_bp', np.nan):.2f} | {getattr(r, 'avg_extra_penalty_bp', np.nan):.2f} | "
            f"{pct(r.avg_participation)} | {pct(r.avg_abs_exposure_gap)} |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "- `partial/failed` includes capacity-limited partial fills, lot-size residuals, missing minute data, limit blocks, and insufficient cash.",
        "- `actual_exposure` is computed from minute-executed holdings at execution-date close; compare it with daily signal `target_exposure`.",
        "- This is an execution-layer stress test.  It is not a replacement for the daily research backtest and should not be used to retune ETF scores directly.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "minute_execution_report_latest.md").write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Minute execution overlay for ETF Loop candidates")
    parser.add_argument("--setting", choices=["F2_CAP_MA60", "WideA", "Current", "Exph_v3_exp_looser"], default="WideA")
    parser.add_argument("--start", default="2025-10-01")
    parser.add_argument("--trading-start", default="2026-01-02")
    parser.add_argument("--end", default="2026-06-25")
    parser.add_argument("--execution-modes", default="open_0935,vwap_0935_1030,twap_0935_1030,tail_vwap_1430_1455,t2_open_0935")
    parser.add_argument("--roundtrip-cost-bps", default="5,7,10,15,20")
    parser.add_argument("--capitals", default="1000000,3000000,5000000,10000000,30000000")
    parser.add_argument("--max-participation", type=float, default=0.10)
    parser.add_argument("--slippage-model", choices=["tiered", "sqrt"], default="tiered")
    parser.add_argument("--sqrt-k", type=float, default=40.0, help="Continuous impact coefficient: slip = base + k * sqrt(order/window_turnover)")
    parser.add_argument("--cross-border-penalty-bp", type=float, default=0.0)
    parser.add_argument("--commodity-penalty-bp", type=float, default=0.0)
    parser.add_argument("--open-penalty-bp", type=float, default=0.0, help="Extra one-way bp when the execution window starts at or before 09:35")
    parser.add_argument("--spread-penalty-mult", type=float, default=0.0, help="Penalty multiplier on median minute (high-low)/close proxy, in bp")
    parser.add_argument("--spread-penalty-cap-bp", type=float, default=10.0)
    parser.add_argument("--max-slippage-bp", type=float, default=50.0)
    parser.add_argument("--near-limit-threshold-bp", type=float, default=0.0, help="If >0, reduce fill capacity when buy/sell price is this close to limit-up/down")
    parser.add_argument("--near-limit-capacity-mult", type=float, default=1.0)
    parser.add_argument("--tag-suffix", default="")
    parser.add_argument("--force-signals", action="store_true", help="Regenerate daily signal logs even if cached files exist")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict[str, Any]] = []
    modes = [x.strip() for x in args.execution_modes.split(",") if x.strip()]
    costs = [float(x) for x in args.roundtrip_cost_bps.split(",") if x.strip()]
    capitals = [float(x) for x in args.capitals.split(",") if x.strip()]
    report_suffix_bits = [args.slippage_model]
    if args.slippage_model == "sqrt":
        report_suffix_bits.append(f"k{args.sqrt_k:g}")
    if args.tag_suffix:
        report_suffix_bits.append(args.tag_suffix)
    report_suffix = "_".join(report_suffix_bits).replace(".", "p")

    account_path, signals_path, _ = generate_daily_signal_logs(args.setting, args.start, args.trading_start, args.end, args.force_signals)
    account, targets_by_signal, exposure_by_signal = load_target_schedule(account_path, signals_path)
    codes = sorted({c for d in targets_by_signal.values() for c in d})
    store = LocalMinuteStore(codes, args.start, args.end, "1min")

    for capital in capitals:
        for mode in modes:
            for cost in costs:
                equity, orders, stats = run_overlay(
                    setting=args.setting,
                    trading_start=args.trading_start,
                    initial_cash=capital,
                    execution_mode=mode,
                    roundtrip_cost_bp=cost,
                    max_participation=args.max_participation,
                    slippage_model=args.slippage_model,
                    sqrt_k=args.sqrt_k,
                    cross_border_penalty_bp=args.cross_border_penalty_bp,
                    commodity_penalty_bp=args.commodity_penalty_bp,
                    open_penalty_bp=args.open_penalty_bp,
                    spread_penalty_mult=args.spread_penalty_mult,
                    spread_penalty_cap_bp=args.spread_penalty_cap_bp,
                    max_slippage_bp=args.max_slippage_bp,
                    near_limit_threshold_bp=args.near_limit_threshold_bp,
                    near_limit_capacity_mult=args.near_limit_capacity_mult,
                    account=account,
                    targets_by_signal=targets_by_signal,
                    exposure_by_signal=exposure_by_signal,
                    store=store,
                )
                model_bits = [args.slippage_model.upper()]
                if args.slippage_model == "sqrt":
                    model_bits.append(f"K{args.sqrt_k:g}")
                if any([
                    args.cross_border_penalty_bp,
                    args.commodity_penalty_bp,
                    args.open_penalty_bp,
                    args.spread_penalty_mult,
                    args.near_limit_threshold_bp,
                    args.tag_suffix,
                ]):
                    model_bits.append(f"X{args.cross_border_penalty_bp:g}")
                    model_bits.append(f"CM{args.commodity_penalty_bp:g}")
                    model_bits.append(f"OP{args.open_penalty_bp:g}")
                    model_bits.append(f"SP{args.spread_penalty_mult:g}")
                    model_bits.append(f"NL{args.near_limit_threshold_bp:g}")
                if args.tag_suffix:
                    model_bits.append(args.tag_suffix)
                model_tag = "_".join(model_bits).replace(".", "p")
                tag = f"{args.setting}_{mode}_COST{int(cost)}BP_CAP{int(capital)}_{model_tag}_{args.start.replace('-', '')}_{args.end.replace('-', '')}"
                equity.to_csv(OUT / f"minute_equity_{tag}.csv", index=False)
                orders.to_csv(OUT / f"minute_orders_{tag}.csv", index=False)
                row = {
                    "setting": args.setting,
                    "start": args.start,
                    "trading_start": args.trading_start,
                    "end": args.end,
                    "initial_cash": capital,
                    "execution_mode": mode,
                    "roundtrip_cost_bp": cost,
                    "max_participation": args.max_participation,
                    "slippage_model": args.slippage_model,
                    "sqrt_k": args.sqrt_k,
                    "cross_border_penalty_bp": args.cross_border_penalty_bp,
                    "commodity_penalty_bp": args.commodity_penalty_bp,
                    "open_penalty_bp": args.open_penalty_bp,
                    "spread_penalty_mult": args.spread_penalty_mult,
                    "spread_penalty_cap_bp": args.spread_penalty_cap_bp,
                    "max_slippage_bp": args.max_slippage_bp,
                    "near_limit_threshold_bp": args.near_limit_threshold_bp,
                    "near_limit_capacity_mult": args.near_limit_capacity_mult,
                    "tag_suffix": args.tag_suffix,
                    **stats,
                }
                summary_rows.append(row)
                print(
                    f"{args.setting:<12s} cap={capital:>10.0f} mode={mode:<20s} cost={cost:>4.0f}bp "
                    f"ann={pct(row['annual_return'])} sharpe={row['sharpe']:.2f} dd={pct(row['max_drawdown'])} "
                    f"partial_failed={pct(row['partial_or_failed_rate'])}"
                )
    summary = pd.DataFrame(summary_rows)
    summary_path = OUT / f"minute_execution_summary_{args.setting}_{report_suffix}_{args.start.replace('-', '')}_{args.end.replace('-', '')}.csv"
    summary.to_csv(summary_path, index=False)
    report = write_report(summary, OUT, args.setting, args.start, args.trading_start, args.end, report_suffix)
    print("Saved:", summary_path)
    print("Saved:", report)


if __name__ == "__main__":
    main()
