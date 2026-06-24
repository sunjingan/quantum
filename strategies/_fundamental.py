"""
Tushare fundamental data cache for qlib-integrated fundamental strategies.

Provides lazy, disk-cached access to Tushare fundamentals (stock_basic,
daily_basic, fina_indicator, income, cashflow, balancesheet).

Used by both Trend-Serenity and POE PB+ROE strategies.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd
import tushare as ts


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


class FundamentalCache:
    """Lazy, disk-cached Tushare fundamental data loader."""

    ENDPOINTS = {
        "fina_indicator": (
            "ts_code,ann_date,end_date,roe,roa,grossprofit_margin,netprofit_margin,"
            "q_sales_yoy,q_op_qoq,q_roe,q_ocf_to_sales,netprofit_yoy,dt_netprofit_yoy,"
            "debt_to_assets,ocf_to_debt"
        ),
        "income": "ts_code,ann_date,end_date,total_revenue,revenue,n_income_attr_p,rd_exp,total_profit",
        "cashflow": "ts_code,ann_date,end_date,n_cashflow_act,free_cashflow",
        "balancesheet": "ts_code,ann_date,end_date,accounts_receiv,inventories,contract_liab,total_assets,total_liab",
    }

    def __init__(self, token_path: Path, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.pro = ts.pro_api(token=token_path.read_text().strip())
        self._statement_cache: dict[tuple, pd.DataFrame] = {}
        self._bulk_statement_cache: dict[str, pd.DataFrame] = {}

    # ── stock_basic ──────────────────────────────────────────────

    def stock_basic(self) -> pd.DataFrame:
        path = self.cache_dir / "stock_basic_all.csv"
        if path.exists():
            return pd.read_csv(path, dtype={"ts_code": str, "list_date": str, "delist_date": str})
        rows = []
        for status in ["L", "D"]:
            df = self.pro.stock_basic(
                exchange="",
                list_status=status,
                fields="ts_code,symbol,name,area,industry,list_date,delist_date",
            )
            if df is not None and not df.empty:
                df["list_status"] = status
                rows.append(df)
        result = pd.concat(rows, ignore_index=True)
        result.to_csv(path, index=False)
        return result

    # ── daily_basic ──────────────────────────────────────────────

    def daily_basic(self, trade_date: pd.Timestamp) -> pd.DataFrame:
        ymd = trade_date.strftime("%Y%m%d")
        path = self.cache_dir / "daily_basic" / f"{ymd}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return pd.read_csv(path, dtype={"ts_code": str})
        df = self.pro.daily_basic(
            trade_date=ymd,
            fields="ts_code,trade_date,close,turnover_rate,volume_ratio,pe_ttm,pb,ps_ttm,total_mv,circ_mv",
        )
        if df is None:
            df = pd.DataFrame()
        df.to_csv(path, index=False)
        return df

    # ── statement endpoints ──────────────────────────────────────

    def statement(self, endpoint: str, ts_code: str, start_date: str, end_date: str, fields: str) -> pd.DataFrame:
        safe = ts_code.replace(".", "_")
        path = self.cache_dir / endpoint / f"{safe}.csv"
        through = self.cache_dir / endpoint / f"{safe}.through"
        path.parent.mkdir(parents=True, exist_ok=True)
        cache_key = (endpoint, ts_code)
        if path.exists() and through.exists() and through.read_text().strip() >= end_date:
            if cache_key not in self._statement_cache:
                self._statement_cache[cache_key] = pd.read_csv(
                    path, dtype={"ts_code": str, "ann_date": str, "end_date": str}
                )
            return self._statement_cache[cache_key]
        func = getattr(self.pro, endpoint)
        df = func(ts_code=ts_code, start_date=start_date, end_date=end_date, fields=fields)
        if df is None:
            df = pd.DataFrame()
        if path.exists():
            old = pd.read_csv(path, dtype={"ts_code": str, "ann_date": str, "end_date": str})
            df = pd.concat([old, df], ignore_index=True)
            if not df.empty:
                keys = [c for c in ["ts_code", "ann_date", "end_date"] if c in df.columns]
                df = df.drop_duplicates(keys, keep="last")
        df.to_csv(path, index=False)
        through.write_text(end_date)
        self._statement_cache[cache_key] = df
        return df

    def latest_visible_row(self, endpoint: str, ts_code: str, data_date: pd.Timestamp) -> pd.Series | None:
        end_date = f"{data_date:%Y%m%d}"
        start_date = f"{data_date - pd.DateOffset(years=3):%Y%m%d}"
        fields = self.ENDPOINTS[endpoint]
        df = self.statement(endpoint, ts_code, start_date, end_date, fields)
        if df.empty or "ann_date" not in df.columns:
            return None
        df = df[df["ann_date"].astype(str) <= end_date].copy()
        if df.empty:
            return None
        return df.sort_values(["ann_date", "end_date"]).iloc[-1]

    # ── prefetch ─────────────────────────────────────────────────

    def prefetch(self, ts_codes: list[str], start: str, end: str) -> None:
        start_date = f"{pd.Timestamp(start) - pd.DateOffset(years=3):%Y%m%d}"
        end_date = f"{pd.Timestamp(end):%Y%m%d}"
        unique = sorted(set(ts_codes))
        for i, ts_code in enumerate(unique, start=1):
            for endpoint, fields in self.ENDPOINTS.items():
                safe = ts_code.replace(".", "_")
                path = self.cache_dir / endpoint / f"{safe}.csv"
                through = self.cache_dir / endpoint / f"{safe}.through"
                if path.exists() and through.exists() and through.read_text().strip() >= end_date:
                    continue
                self.statement(endpoint, ts_code, start_date, end_date, fields)
            if i % 50 == 0:
                print(f"  fundamental cache: {i}/{len(unique)}", flush=True)

    # ── snapshot (for Trend-Serenity) ────────────────────────────

    def snapshot(self, qlib_codes: list[str], data_date: pd.Timestamp) -> pd.DataFrame:
        """Build a wide merged DataFrame with all fundamental fields for scoring."""
        if len(qlib_codes) >= 1000:
            return self.snapshot_bulk(qlib_codes, data_date)
        ts_codes = [qlib_to_tushare(code) for code in qlib_codes]
        basic = self.stock_basic()
        daily = self.daily_basic(data_date)
        rows = []
        for code, ts_code in zip(qlib_codes, ts_codes):
            fina = self.latest_visible_row("fina_indicator", ts_code, data_date)
            inc = self.latest_visible_row("income", ts_code, data_date)
            cf = self.latest_visible_row("cashflow", ts_code, data_date)
            bs = self.latest_visible_row("balancesheet", ts_code, data_date)
            if fina is None or inc is None:
                continue
            row = {"code": code.lower(), "ts_code": ts_code}
            for prefix, item in [("fi", fina), ("inc", inc), ("cf", cf), ("bs", bs)]:
                if item is not None:
                    for k, v in item.items():
                        row[f"{prefix}_{k}"] = v
            rows.append(row)
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df = df.merge(daily, on="ts_code", how="left")
        df = df.merge(basic, on="ts_code", how="left")
        df["industry_name"] = df["industry"].fillna("UNKNOWN")
        return df

    def bulk_statement(self, endpoint: str) -> pd.DataFrame:
        """Load all cached statement files for an endpoint once for large universes."""
        if endpoint in self._bulk_statement_cache:
            return self._bulk_statement_cache[endpoint]

        directory = self.cache_dir / endpoint
        parts = []
        if directory.exists():
            for path in sorted(directory.glob("*.csv")):
                try:
                    df = pd.read_csv(path, dtype={"ts_code": str, "ann_date": str, "end_date": str})
                except pd.errors.EmptyDataError:
                    continue
                if not df.empty:
                    parts.append(df)
        result = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        if not result.empty:
            result["ann_date"] = result["ann_date"].astype(str)
            result["end_date"] = result["end_date"].astype(str)
            keys = [c for c in ["ts_code", "ann_date", "end_date"] if c in result.columns]
            result = result.drop_duplicates(keys, keep="last")
        self._bulk_statement_cache[endpoint] = result
        return result

    def latest_visible_bulk(self, endpoint: str, ts_codes: list[str], data_date: pd.Timestamp) -> pd.DataFrame:
        df = self.bulk_statement(endpoint)
        if df.empty or "ann_date" not in df.columns:
            return pd.DataFrame()
        end_date = f"{data_date:%Y%m%d}"
        visible = df[(df["ts_code"].isin(ts_codes)) & (df["ann_date"].astype(str) <= end_date)].copy()
        if visible.empty:
            return pd.DataFrame()
        return visible.sort_values(["ts_code", "ann_date", "end_date"]).groupby("ts_code", as_index=False).tail(1)

    def snapshot_bulk(self, qlib_codes: list[str], data_date: pd.Timestamp) -> pd.DataFrame:
        """Vectorized snapshot for all-A backtests; preserves ann_date point-in-time."""
        ts_codes = [qlib_to_tushare(code) for code in qlib_codes]
        code_map = dict(zip(ts_codes, [code.lower() for code in qlib_codes]))
        frames = []
        for prefix, endpoint in [
            ("fi", "fina_indicator"),
            ("inc", "income"),
            ("cf", "cashflow"),
            ("bs", "balancesheet"),
        ]:
            part = self.latest_visible_bulk(endpoint, ts_codes, data_date)
            if part.empty:
                continue
            rename = {c: f"{prefix}_{c}" for c in part.columns if c != "ts_code"}
            frames.append(part.rename(columns=rename))
        if len(frames) < 2:
            return pd.DataFrame()

        df = frames[0]
        for part in frames[1:]:
            df = df.merge(part, on="ts_code", how="left")
        df = df[df["inc_n_income_attr_p"].notna()].copy()
        if df.empty:
            return df
        df["code"] = df["ts_code"].map(code_map)

        daily = self.daily_basic(data_date)
        basic = self.stock_basic()
        df = df.merge(daily, on="ts_code", how="left")
        df = df.merge(basic, on="ts_code", how="left")
        df["industry_name"] = df["industry"].fillna("UNKNOWN")
        return df

    # ── fundamentals (for POE PB+ROE) ────────────────────────────

    def latest_fina_rows(self, ts_codes: list[str], data_date: pd.Timestamp) -> pd.DataFrame:
        """Get latest fina_indicator rows for the POE PB+ROE pipeline."""
        end_date = data_date.strftime("%Y%m%d")
        start_date = (data_date - pd.DateOffset(years=3)).strftime("%Y%m%d")
        rows = []
        for ts_code in ts_codes:
            df = self.statement("fina_indicator", ts_code, start_date, end_date, self.ENDPOINTS["fina_indicator"])
            if df.empty or "ann_date" not in df:
                continue
            visible = df[df["ann_date"].astype(str) <= end_date].copy()
            visible = visible.dropna(subset=["roe"])
            if visible.empty:
                continue
            rows.append(visible.sort_values(["ann_date", "end_date"]).iloc[-1])
        return pd.DataFrame(rows)

    def fundamentals(self, qlib_codes: list[str], data_date: pd.Timestamp) -> pd.DataFrame:
        """Build a POE PB+ROE-ready merged DataFrame."""
        ts_codes = [qlib_to_tushare(code) for code in qlib_codes]
        basic = self.stock_basic()
        daily = self.daily_basic(data_date)
        fina = self.latest_fina_rows(ts_codes, data_date)
        if daily.empty or fina.empty:
            return pd.DataFrame()
        df = daily[daily["ts_code"].isin(ts_codes)].merge(fina, on="ts_code", how="inner")
        df = df.merge(basic, on="ts_code", how="left")
        if df.empty:
            return df
        df["code"] = df["ts_code"].map(lambda x: x.split(".")[1].lower() + x.split(".")[0])
        df = df.rename(
            columns={
                "pb": "pb_ratio",
                "pe_ttm": "pe_ratio",
                "total_mv": "market_cap",
                "industry": "industry_name",
                "netprofit_yoy": "inc_net_profit_year_on_year",
                "or_yoy": "inc_revenue_year_on_year",
            }
        )
        df["market_cap"] = df["market_cap"] / 10000.0
        return df
