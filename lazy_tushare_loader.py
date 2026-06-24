"""
Lazy Tushare -> Qlib cache loader.

It checks whether the requested instruments/date range already exists in the
local Qlib binary cache. Missing data is downloaded from Tushare, saved as raw
CSV, and rebuilt into Qlib's .bin feature format.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np
import pandas as pd
import tushare as ts


FIELDS = ["open", "high", "low", "close", "volume", "amount", "pre_close", "vwap"]
BIN_FIELDS = set(FIELDS)


def qlib_to_tushare(code: str) -> str:
    code = code.lower()
    if code.startswith("sh"):
        return f"{code[2:]}.SH"
    if code.startswith("sz"):
        return f"{code[2:]}.SZ"
    if code.startswith("bj"):
        return f"{code[2:]}.BJ"
    raise ValueError(f"Unsupported qlib code: {code}")


def tushare_to_qlib(ts_code: str) -> str:
    symbol, exchange = ts_code.split(".")
    return f"{exchange.lower()}{symbol}".lower()


def to_yyyymmdd(date: str | pd.Timestamp) -> str:
    return pd.Timestamp(date).strftime("%Y%m%d")


def normalize_raw_daily(df: pd.DataFrame) -> pd.DataFrame:
    rename = {"trade_date": "date", "vol": "volume"}
    df = df.rename(columns=rename)
    df["date"] = pd.to_datetime(df["date"].astype(str))
    df = df.sort_values("date").drop_duplicates("date", keep="last")
    df["vwap"] = np.where(df["volume"] > 0, df["amount"] * 10 / df["volume"], np.nan)
    return df[["date", *FIELDS]]


@dataclass
class LazyTushareLoader:
    provider_uri: Path
    token_path: Path
    raw_stock_dir: Path
    raw_index_dir: Path

    @classmethod
    def for_project(cls, base_dir: Path, provider_uri: Path) -> "LazyTushareLoader":
        return cls(
            provider_uri=provider_uri,
            token_path=base_dir / "config" / "tushare_token.txt",
            raw_stock_dir=base_dir / "data" / "tushare_raw" / "per_stock",
            raw_index_dir=base_dir / "data" / "tushare_raw" / "index",
        )

    @property
    def pro(self):
        if not hasattr(self, "_pro"):
            token = self.token_path.read_text().strip()
            self._pro = ts.pro_api(token=token)
        return self._pro

    @property
    def calendar_path(self) -> Path:
        return self.provider_uri / "calendars" / "day.txt"

    def ensure(
        self,
        instruments: str | Iterable[str] | Mapping[str, str | pd.Timestamp],
        start_time: str,
        end_time: str,
        benchmark: str | None = None,
    ):
        self.ensure_calendar(start_time, end_time)
        calendar = self.read_calendar()
        codes_with_start = self.resolve_instruments(instruments)

        if benchmark:
            bench_code = benchmark.lower()
            codes_with_start.setdefault(bench_code, pd.Timestamp(start_time))

        touched = []
        for code, listed_start in sorted(codes_with_start.items()):
            code = code.lower()
            effective_start = max(pd.Timestamp(start_time), listed_start)
            if self.feature_cache_covers(code, effective_start, pd.Timestamp(end_time), calendar):
                continue
            if self.is_index_code(code):
                raw = self.download_index_daily(code, effective_start, end_time)
                raw_path = self.merge_raw(raw, self.raw_index_dir / f"{code.upper()}.csv")
            else:
                raw = self.download_stock_daily(code, effective_start, end_time)
                raw_path = self.merge_raw(raw, self.raw_stock_dir / f"{code.upper()}.csv")
            merged = pd.read_csv(raw_path)
            merged = normalize_raw_daily(merged)
            self.write_qlib_bins(code, merged, calendar)
            touched.append(code)

        if touched:
            print(f"Lazy Tushare: updated {len(touched)} instruments: {', '.join(touched[:8])}")
            if len(touched) > 8:
                print(f"Lazy Tushare: ... and {len(touched) - 8} more")
        else:
            print("Lazy Tushare: local cache covers requested data")

    def ensure_calendar(self, start_time: str, end_time: str) -> None:
        self.calendar_path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.read_calendar() if self.calendar_path.exists() else []
        if existing and pd.Timestamp(start_time) >= existing[0] and pd.Timestamp(end_time) <= existing[-1]:
            return

        fetch_start = min(pd.Timestamp(start_time), existing[0] if existing else pd.Timestamp(start_time))
        fetch_end = max(pd.Timestamp(end_time), existing[-1] if existing else pd.Timestamp(end_time))
        cal = self.pro.trade_cal(
            exchange="SSE",
            start_date=to_yyyymmdd(fetch_start),
            end_date=to_yyyymmdd(fetch_end),
            is_open="1",
            fields="cal_date",
        )
        values = sorted(pd.to_datetime(cal["cal_date"].astype(str)).dt.strftime("%Y-%m-%d").tolist())
        np.savetxt(self.calendar_path, values, fmt="%s", encoding="utf-8")

    def read_calendar(self) -> list[pd.Timestamp]:
        values = pd.read_csv(self.calendar_path, header=None)[0]
        return pd.to_datetime(values).tolist()

    def resolve_instruments(self, instruments: str | Iterable[str] | Mapping[str, str | pd.Timestamp]) -> dict[str, pd.Timestamp]:
        if isinstance(instruments, str):
            path = self.provider_uri / "instruments" / f"{instruments}.txt"
            df = pd.read_csv(path, sep="\t", header=None, names=["code", "start", "end"])
            return {row.code.lower(): pd.Timestamp(row.start) for row in df.itertuples(index=False)}
        if isinstance(instruments, Mapping):
            return {code.lower(): pd.Timestamp(start) for code, start in instruments.items()}
        return {code.lower(): pd.Timestamp.min for code in instruments}

    def feature_cache_covers(
        self,
        code: str,
        start_time: pd.Timestamp,
        end_time: pd.Timestamp,
        calendar: list[pd.Timestamp],
    ) -> bool:
        feature_dir = self.provider_uri / "features" / code.lower()
        if not feature_dir.exists():
            return False
        if any(not (feature_dir / f"{field}.day.bin").exists() for field in BIN_FIELDS):
            return False

        start_idx = self.calendar_index(calendar, start_time)
        end_idx = self.calendar_index(calendar, end_time)
        close = np.fromfile(feature_dir / "close.day.bin", dtype="<f")
        if len(close) <= 1:
            return False
        cache_start_idx = int(close[0])
        cache_end_idx = cache_start_idx + len(close) - 2
        return cache_start_idx <= start_idx and cache_end_idx >= end_idx

    @staticmethod
    def calendar_index(calendar: list[pd.Timestamp], date: pd.Timestamp) -> int:
        calendar_series = pd.Series(calendar)
        pos = calendar_series.searchsorted(date, side="left")
        if pos >= len(calendar):
            raise ValueError(f"Date {date.date()} is beyond local/trade calendar")
        return int(pos)

    @staticmethod
    def is_index_code(code: str) -> bool:
        return code.lower() in {"sh000300", "sh000905", "sh000852", "sh000001", "sz399001", "sz399006"}

    def download_stock_daily(self, code: str, start_time: pd.Timestamp, end_time: str) -> pd.DataFrame:
        df = self.pro.daily(
            ts_code=qlib_to_tushare(code),
            start_date=to_yyyymmdd(start_time),
            end_date=to_yyyymmdd(end_time),
            fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount",
        )
        if df is None or df.empty:
            raise RuntimeError(f"Tushare returned no stock daily data: {code}")
        return normalize_raw_daily(df)

    def download_index_daily(self, code: str, start_time: pd.Timestamp, end_time: str) -> pd.DataFrame:
        df = self.pro.index_daily(
            ts_code=qlib_to_tushare(code),
            start_date=to_yyyymmdd(start_time),
            end_date=to_yyyymmdd(end_time),
            fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount",
        )
        if df is None or df.empty:
            raise RuntimeError(f"Tushare returned no index daily data: {code}")
        return normalize_raw_daily(df)

    @staticmethod
    def merge_raw(df: pd.DataFrame, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            old = normalize_raw_daily(pd.read_csv(path))
            df = pd.concat([old, df], ignore_index=True)
            df = df.sort_values("date").drop_duplicates("date", keep="last")
        df.to_csv(path, index=False)
        return path

    def write_qlib_bins(self, code: str, df: pd.DataFrame, calendar: list[pd.Timestamp]) -> None:
        feature_dir = self.provider_uri / "features" / code.lower()
        feature_dir.mkdir(parents=True, exist_ok=True)

        df = df.set_index("date").sort_index()
        aligned_calendar = [d for d in calendar if df.index.min() <= d <= df.index.max()]
        aligned = df.reindex(aligned_calendar)
        date_index = calendar.index(aligned.index.min())

        for field in FIELDS:
            values = aligned[field].to_numpy(dtype=np.float32)
            np.hstack([date_index, values]).astype("<f").tofile(feature_dir / f"{field}.day.bin")
