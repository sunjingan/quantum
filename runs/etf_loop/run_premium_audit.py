#!/usr/bin/env python3
"""Premium audit for ETF Loop executed orders.

The audit is intentionally read-only: it does not change strategy signals or
fills.  It joins executed orders with locally cached ETF NAV/share files and
flags trades that would have been exposed to observable premium risk.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

OUT = PROJECT_ROOT / "outputs" / "etf_loop" / "premium_audit"
MINUTE_OUT = PROJECT_ROOT / "outputs" / "etf_loop" / "minute_execution_backtest"
LOCAL_DATA = PROJECT_ROOT / "data" / "local_etf_data"

QDII_CODES = {"501018", "160216", "160416", "160717", "161126", "164824"}
COMMODITY_CODES = {"159980", "159981", "159985", "159934", "159937", "501018", "518880"}


def local_code(ts_code: str) -> str:
    return str(ts_code).split(".")[0].zfill(6)


def exchange_prefix(ts_code: str) -> str:
    ts = str(ts_code)
    if ts.endswith(".SH"):
        return "sh"
    if ts.endswith(".SZ"):
        return "sz"
    code = local_code(ts)
    return "sh" if code.startswith(("5", "6")) else "sz"


def is_cross_border(ts_code: str) -> bool:
    code = local_code(ts_code)
    return code.startswith("513") or code in QDII_CODES


def is_commodity(ts_code: str) -> bool:
    code = local_code(ts_code)
    return code.startswith("518") or code in COMMODITY_CODES


def load_meta() -> pd.DataFrame:
    path = LOCAL_DATA / "etf.csv"
    if not path.exists():
        return pd.DataFrame(columns=["ts_code", "csname", "etf_type"])
    df = pd.read_csv(path)
    keep = [c for c in ["ts_code", "csname", "extname", "etf_type"] if c in df.columns]
    return df[keep].drop_duplicates("ts_code", keep="first")


class PremiumStore:
    def __init__(self) -> None:
        self.cache: dict[str, pd.DataFrame] = {}
        self.daily_2026 = self._load_2026_snapshots()

    def _load_2026_snapshots(self) -> pd.DataFrame:
        parts = []
        for path in sorted((LOCAL_DATA / "全部份额" / "2026").glob("*.csv")):
            try:
                df = pd.read_csv(path)
            except Exception:
                continue
            if df.empty or "代码" not in df.columns:
                continue
            parts.append(df)
        if not parts:
            return pd.DataFrame()
        df = pd.concat(parts, ignore_index=True)
        return self._normalize(df)

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        rename = {
            "代码": "code",
            "交易日期": "date",
            "单位净值": "unit_nav",
            "收盘价": "close",
            "份额(万份)": "shares_10k",
            "基金规模(万元)": "fund_size_10k",
        }
        cols = [c for c in rename if c in df.columns]
        out = df[cols].rename(columns=rename).copy()
        if out.empty:
            return out
        out["code"] = out["code"].astype(str).str.extract(r"(\d+)")[0].str.zfill(6)
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        for col in ["unit_nav", "close", "shares_10k", "fund_size_10k"]:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
        out = out.dropna(subset=["code", "date"]).sort_values(["code", "date"])
        return out

    def _load_code_history(self, ts_code: str) -> pd.DataFrame:
        code = local_code(ts_code)
        if code in self.cache:
            return self.cache[code]
        prefix = exchange_prefix(ts_code)
        path = LOCAL_DATA / "全部份额" / "全部份额" / f"{prefix}{code}.csv"
        parts = []
        if path.exists():
            try:
                parts.append(pd.read_csv(path))
            except Exception:
                pass
        if not self.daily_2026.empty:
            parts.append(self.daily_2026[self.daily_2026["code"].eq(code)].copy())
        if not parts:
            out = pd.DataFrame(columns=["code", "date", "unit_nav", "close", "shares_10k", "fund_size_10k"])
        else:
            normed = [p if "unit_nav" in p.columns else self._normalize(p) for p in parts]
            out = pd.concat(normed, ignore_index=True)
            out = out.drop_duplicates(["code", "date"], keep="last").sort_values("date")
            out = out[(out["unit_nav"].notna()) & (out["close"].notna()) & (out["unit_nav"] > 0)]
            out["price_scale"] = np.where((out["close"] > 10.0) & (out["unit_nav"] < 10.0), 100.0, 1.0)
            out["close_norm"] = out["close"] / out["price_scale"]
            out["premium"] = out["close_norm"] / out["unit_nav"] - 1.0
        self.cache[code] = out
        return out

    def asof(self, ts_code: str, date: pd.Timestamp) -> dict[str, Any]:
        hist = self._load_code_history(ts_code)
        if hist.empty:
            return {"matched": False}
        rows = hist[hist["date"] <= pd.Timestamp(date)]
        if rows.empty:
            return {"matched": False}
        r = rows.iloc[-1]
        return {
            "matched": True,
            "premium_date": r["date"],
            "unit_nav": float(r["unit_nav"]),
            "nav_close": float(r["close"]),
            "nav_close_norm": float(r["close_norm"]) if "close_norm" in r and pd.notna(r["close_norm"]) else np.nan,
            "price_scale": float(r["price_scale"]) if "price_scale" in r and pd.notna(r["price_scale"]) else 1.0,
            "premium": float(r["premium"]),
            "premium_stale_days": int((pd.Timestamp(date) - pd.Timestamp(r["date"])).days),
            "shares_10k": float(r["shares_10k"]) if "shares_10k" in r and pd.notna(r["shares_10k"]) else np.nan,
            "fund_size_10k": float(r["fund_size_10k"]) if "fund_size_10k" in r and pd.notna(r["fund_size_10k"]) else np.nan,
        }


def parse_order_file(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    stem = path.stem
    setting = stem.split("_vwap_")[0].replace("minute_orders_", "")
    if setting.startswith("Exph_v3_exp_looser"):
        setting = "Exph_v3_exp_looser"
    df["setting"] = setting
    df["source_file"] = path.name
    for col in ["signal_date", "trade_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def audit_orders(files: list[Path]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    meta = load_meta()
    store = PremiumStore()
    orders = pd.concat([parse_order_file(p) for p in files], ignore_index=True)
    orders = orders[orders["side"].isin(["BUY", "SELL"])].copy()
    if not meta.empty:
        orders = orders.merge(meta, on="ts_code", how="left")
    rows = []
    for r in orders.itertuples():
        signal = store.asof(r.ts_code, pd.Timestamp(r.signal_date))
        trade = store.asof(r.ts_code, pd.Timestamp(r.trade_date))
        signal_premium = signal.get("premium", np.nan)
        trade_premium = trade.get("premium", np.nan)
        fill_price = float(getattr(r, "actual_fill_price", np.nan)) if pd.notna(getattr(r, "actual_fill_price", np.nan)) else np.nan
        signal_scale = signal.get("price_scale", 1.0)
        fill_price_norm = fill_price / signal_scale if pd.notna(fill_price) and signal_scale else np.nan
        rows.append({
            "setting": r.setting,
            "source_file": r.source_file,
            "ts_code": r.ts_code,
            "side": r.side,
            "signal_date": r.signal_date,
            "trade_date": r.trade_date,
            "order_value": getattr(r, "order_value", np.nan),
            "filled_value": getattr(r, "filled_value", np.nan),
            "fill_ratio": getattr(r, "fill_ratio", np.nan),
            "actual_fill_price": getattr(r, "actual_fill_price", np.nan),
            "raw_price": getattr(r, "raw_price", np.nan),
            "reject_reason": getattr(r, "reject_reason", ""),
            "csname": getattr(r, "csname", ""),
            "etf_type": getattr(r, "etf_type", ""),
            "is_cross_border": is_cross_border(r.ts_code),
            "is_commodity": is_commodity(r.ts_code),
            "premium_matched_signal": signal.get("matched", False),
            "signal_premium_date": signal.get("premium_date", pd.NaT),
            "signal_unit_nav": signal.get("unit_nav", np.nan),
            "signal_nav_close": signal.get("nav_close", np.nan),
            "signal_nav_close_norm": signal.get("nav_close_norm", np.nan),
            "signal_price_scale": signal.get("price_scale", np.nan),
            "signal_premium": signal_premium,
            "signal_premium_stale_days": signal.get("premium_stale_days", np.nan),
            "premium_matched_trade": trade.get("matched", False),
            "trade_premium_date": trade.get("premium_date", pd.NaT),
            "trade_unit_nav": trade.get("unit_nav", np.nan),
            "trade_nav_close": trade.get("nav_close", np.nan),
            "trade_nav_close_norm": trade.get("nav_close_norm", np.nan),
            "trade_price_scale": trade.get("price_scale", np.nan),
            "trade_premium": trade_premium,
            "trade_premium_stale_days": trade.get("premium_stale_days", np.nan),
            "signal_premium_ge_3pct": bool(pd.notna(signal_premium) and signal_premium >= 0.03),
            "signal_premium_ge_5pct": bool(pd.notna(signal_premium) and signal_premium >= 0.05),
            "signal_premium_ge_8pct": bool(pd.notna(signal_premium) and signal_premium >= 0.08),
            "signal_discount_le_minus_3pct": bool(pd.notna(signal_premium) and signal_premium <= -0.03),
            "fill_vs_signal_nav": (
                fill_price_norm / signal["unit_nav"] - 1.0
                if signal.get("matched", False) and pd.notna(fill_price_norm)
                else np.nan
            ),
        })
    audited = pd.DataFrame(rows)
    buys = audited[audited["side"].eq("BUY")].copy()
    summary_rows = []
    for setting, grp in buys.groupby("setting"):
        matched = grp[grp["premium_matched_signal"]]
        risk_scope = matched[matched["is_cross_border"] | matched["is_commodity"] | matched["etf_type"].fillna("").str.contains("跨境|商品|QDII|境外", regex=True)]
        total_filled = grp["filled_value"].fillna(0).sum()
        for label, sub in [("all_buys", matched), ("cross_or_commodity_buys", risk_scope)]:
            filled = sub["filled_value"].fillna(0).sum()
            high3 = sub[sub["signal_premium_ge_3pct"]]
            high5 = sub[sub["signal_premium_ge_5pct"]]
            high8 = sub[sub["signal_premium_ge_8pct"]]
            summary_rows.append({
                "setting": setting,
                "scope": label,
                "buy_orders": int(len(sub)),
                "matched_rate": len(matched) / len(grp) if len(grp) else np.nan,
                "filled_value": filled,
                "filled_value_share_of_all_buys": filled / total_filled if total_filled > 0 else np.nan,
                "avg_signal_premium": sub["signal_premium"].mean(),
                "p95_signal_premium": sub["signal_premium"].quantile(0.95),
                "max_signal_premium": sub["signal_premium"].max(),
                "premium_ge_3pct_orders": int(len(high3)),
                "premium_ge_3pct_filled": high3["filled_value"].fillna(0).sum(),
                "premium_ge_5pct_orders": int(len(high5)),
                "premium_ge_5pct_filled": high5["filled_value"].fillna(0).sum(),
                "premium_ge_8pct_orders": int(len(high8)),
                "premium_ge_8pct_filled": high8["filled_value"].fillna(0).sum(),
                "discount_le_minus_3pct_orders": int(sub["signal_discount_le_minus_3pct"].sum()),
            })
    summary = pd.DataFrame(summary_rows)
    top = buys[buys["premium_matched_signal"]].sort_values("signal_premium", ascending=False).head(80)
    return audited, summary, top


def pct(x: float) -> str:
    return "" if pd.isna(x) else f"{x * 100:.2f}%"


def money(x: float) -> str:
    return "" if pd.isna(x) else f"{x:,.0f}"


def write_report(summary: pd.DataFrame, top: pd.DataFrame, out_path: Path, files: list[Path]) -> None:
    lines = [
        "# ETF Loop 候选策略溢价率逐笔审计",
        "",
        "## 1. 口径",
        "",
        "- 审计对象：分钟执行层已有订单，不改信号、不改成交、不重跑策略。",
        "- 核心无未来函数口径：买入日前一交易信号日 `signal_date` 的 `单位净值` 和 `收盘价`。",
        "- `signal_premium = signal_close / signal_unit_nav - 1`，这是 T 日收盘后已知、T+1 买入前可用的信息。",
        "- `trade_date` 的单位净值只作事后执行偏差参考，不作为交易决策依据。",
        "- 重点关注跨境、商品、QDII 以及 ETF 元数据里标记为跨境/商品的标的。",
        "",
        "## 2. 输入订单文件",
        "",
    ]
    lines += [f"- `{p}`" for p in files]
    lines += [
        "",
        "## 3. 汇总表",
        "",
        "| setting | 范围 | 买入单数 | 匹配率 | 买入成交额 | 占全部买入成交额 | 平均溢价 | P95溢价 | 最大溢价 | >=3%单数 | >=3%成交额 | >=5%单数 | >=5%成交额 | >=8%单数 | <=-3%折价单数 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in summary.itertuples():
        lines.append(
            f"| `{r.setting}` | `{r.scope}` | {r.buy_orders} | {pct(r.matched_rate)} | {money(r.filled_value)} | "
            f"{pct(r.filled_value_share_of_all_buys)} | {pct(r.avg_signal_premium)} | {pct(r.p95_signal_premium)} | "
            f"{pct(r.max_signal_premium)} | {r.premium_ge_3pct_orders} | {money(r.premium_ge_3pct_filled)} | "
            f"{r.premium_ge_5pct_orders} | {money(r.premium_ge_5pct_filled)} | {r.premium_ge_8pct_orders} | "
            f"{r.discount_le_minus_3pct_orders} |"
        )
    lines += [
        "",
        "## 4. 信号日溢价最高的买入记录 Top 30",
        "",
        "| setting | ts_code | 名称 | side | signal_date | trade_date | signal_premium | fill_vs_signal_nav | filled_value | etf_type |",
        "|---|---|---|---|---|---|---:|---:|---:|---|",
    ]
    for r in top.head(30).itertuples():
        lines.append(
            f"| `{r.setting}` | `{r.ts_code}` | {getattr(r, 'csname', '')} | {r.side} | "
            f"{pd.Timestamp(r.signal_date).date()} | {pd.Timestamp(r.trade_date).date()} | "
            f"{pct(r.signal_premium)} | {pct(r.fill_vs_signal_nav)} | {money(r.filled_value)} | {getattr(r, 'etf_type', '')} |"
        )
    lines += [
        "",
        "## 5. 解释",
        "",
        "- 如果 `signal_premium >= 5%` 的买入单较多，说明策略存在可观的溢价追高风险，实盘应设置禁买或降权。",
        "- 对跨境/商品 ETF，短期溢价不一定全是错误，但高溢价意味着交易拥挤和回归风险更高。",
        "- 当前审计只判断“买入前可见溢价是否过高”，不直接评价后续收益贡献。后续可把高溢价交易和逐笔 PnL 连接，判断是否确实伤害收益。",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def default_files(settings: list[str], capital: int) -> list[Path]:
    files = []
    for setting in settings:
        pattern = f"minute_orders_{setting}_vwap_0935_1030_COST7BP_CAP{capital}_20130701_20260625.csv"
        files.extend(MINUTE_OUT.glob(pattern))
    return sorted(files)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit ETF premium exposure on executed orders")
    parser.add_argument("--settings", default="WideA,F2_CAP_MA60,Exph_v3_exp_looser")
    parser.add_argument("--capital", type=int, default=1000000)
    parser.add_argument("--order-files", default="", help="Comma-separated explicit order files. Overrides settings/capital.")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    if args.order_files:
        files = [Path(x.strip()) for x in args.order_files.split(",") if x.strip()]
    else:
        files = default_files([x.strip() for x in args.settings.split(",") if x.strip()], args.capital)
    if not files:
        raise FileNotFoundError("No order files found for premium audit")

    audited, summary, top = audit_orders(files)
    audited_path = OUT / f"candidate_premium_audit_orders_CAP{args.capital}.csv"
    summary_path = OUT / f"candidate_premium_audit_summary_CAP{args.capital}.csv"
    top_path = OUT / f"candidate_premium_audit_top_CAP{args.capital}.csv"
    report_path = OUT / f"candidate_premium_audit_report_CAP{args.capital}.md"
    audited.to_csv(audited_path, index=False)
    summary.to_csv(summary_path, index=False)
    top.to_csv(top_path, index=False)
    write_report(summary, top, report_path, files)
    print("Saved:", audited_path)
    print("Saved:", summary_path)
    print("Saved:", top_path)
    print("Saved:", report_path)


if __name__ == "__main__":
    main()
