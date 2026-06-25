"""
ETF Pool Classification — systematic, point-in-time, no look-ahead.

Classifies ETFs into 6 buckets:
  defensive (债券/货币), commodity (黄金/白银/原油/期货/有色),
  overseas (纳指/标普/道琼斯/日经/恒生/中概/港股/QDII),
  broad_a (pure A-share broad indices),
  style (红利/价值/低波/银行/现金流/质量),
  theme (everything else — 半导体/芯片/通信/机器人/卫星/etc.)
"""

import pandas as pd
import numpy as np
from pathlib import Path

# ── Pure broad index benchmarks ──
PURE_BROAD_BENCHMARKS = [
    "沪深300", "中证500", "中证1000", "中证2000",
    "中证A500", "中证A100", "中证A50",
    "上证50", "上证180", "上证380", "上海证券交易所50成份",
    "深证100", "深证300", "深证50",
    "创业板指", "创业板50", "创业板综",
    "科创50", "科创100", "科创综指", "科创板50",
    "北证50",
    "中证小盘500",
]

# ── Explicit code-level overrides for Tushare naming quirks ──
BROAD_OVERRIDES = {
    "510050.SH",   # 上证50 — benchmark uses "上海证券交易所50成份指数"
    "510500.SH",   # 中证500 — benchmark uses "中证小盘500指数"
}

# ── Keyword lists for classification ──
OVERSEAS_KW = [
    "纳斯达克", "标普", "道琼斯", "日经", "恒生",
    "中概", "港股", "QDII", "东南亚", "中韩", "香港",
]

STYLE_KW = [
    "红利", "价值", "低波", "银行", "高股息", "现金流", "质量",
]

COMMODITY_KW = [
    "黄金", "白银", "原油", "期货", "有色", "豆粕", "能源化工",
]

# ── Theme keywords that should NEVER be classified as broad_a ──
THEME_EXCLUDE_KW = [
    "半导体", "芯片", "通信设备", "通信", "5G", "人工智能", "AI", "机器人",
    "电网", "电力", "卫星", "军工", "新能源", "光伏", "电池",
    "汽车", "医药", "医疗", "创新药", "消费", "食品", "饮料",
    "酒", "煤炭", "钢铁", "有色", "化工", "农业", "证券", "券商",
    "保险", "地产", "房地产", "基建", "传媒", "游戏", "软件",
    "科技", "工业", "制造",
]

# ── Bucket quotas ──
BUCKET_QUOTAS = {
    "defensive": 4,
    "commodity": 6,
    "overseas": 8,
    "broad_a": 8,
    "style": 7,
    "theme": 6,
}


def _is_pure_broad(benchmark: str, name: str) -> bool:
    """Check if benchmark is a pure broad index (not a themed variant)."""
    for kw in THEME_EXCLUDE_KW:
        if kw in benchmark:
            return False
    for kw in THEME_EXCLUDE_KW:
        if kw in name:
            return False
    for kw in PURE_BROAD_BENCHMARKS:
        if kw in benchmark:
            return True
    return False


def classify_etf(ts_code: str, name: str, fund_type: str, benchmark: str) -> str:
    """Classify one ETF into a bucket."""
    # 0. Explicit code overrides
    if ts_code in BROAD_OVERRIDES:
        return "broad_a"

    ft = str(fund_type)

    # 1. fund_type first
    if ft in ("债券型", "货币型"):
        return "defensive"

    # 2. "其他" — commodity check
    if ft == "其他":
        combined = benchmark + name
        for kw in COMMODITY_KW:
            if kw in combined:
                return "commodity"
        return "theme"

    # 3. "股票型" — layered keyword classification
    combined = benchmark + name

    # 3a. Commodity keywords override
    for kw in COMMODITY_KW:
        if kw in combined:
            return "commodity"

    # 3b. Overseas keywords
    for kw in OVERSEAS_KW:
        if kw in combined:
            return "overseas"

    # 3c. Style keywords (before broad_a to catch 红利/低波 variants)
    for kw in STYLE_KW:
        if kw in combined:
            return "style"

    # 3d. Pure broad
    if _is_pure_broad(benchmark, name):
        return "broad_a"

    # 3e. Everything else → theme
    return "theme"


def build_classified_pool(
    token_path,
    cache_dir,
    pool_tag: str = "F2_v3",
    force_rebuild: bool = False,
    return_df: bool = False,
):
    """Build a classified ETF pool with bucket quotas.

    Key differences from _build_all_etf_pool():
      - Dedup keeps OLDEST per benchmark (not highest volume)
      - Classifies by fund_type + keyword matching
      - Applies bucket quotas for structured pool
      - Covers ALL fund types (not just 股票型)

    Returns list of ts_codes, or DataFrame if return_df=True.
    """
    import tushare as ts

    cache_file = Path(cache_dir) / "sector_prosperity" / f"etf_pool_{pool_tag}.csv"
    if not force_rebuild and cache_file.exists():
        df = pd.read_csv(cache_file, dtype={"ts_code": str})
        if return_df:
            return df
        return sorted(df["ts_code"].astype(str).tolist())

    token = Path(token_path).read_text().strip()
    pro = ts.pro_api(token)

    # 1. Get all ETF basic info
    fb = pro.fund_basic(market="E")
    if fb is None or fb.empty:
        print("  WARNING: fund_basic returned empty")
        return [] if not return_df else pd.DataFrame()

    fb = fb.copy()
    fb = fb[fb["list_date"].notna()].copy()
    fb = fb[fb["status"].isin(["L", "D"])].copy()
    fb["list_date_dt"] = pd.to_datetime(
        fb["list_date"].astype(str).str.replace(r"\.0$", "", regex=True),
        format="%Y%m%d", errors="coerce",
    )

    # 2. Liquidity from cache
    from strategies.sector_prosperity import SectorProsperityCache
    sp_cache = SectorProsperityCache(token_path, Path(cache_dir))
    daily = sp_cache.etf_daily()
    daily["td"] = pd.to_datetime(
        daily["trade_date"].astype(str).str.replace(r"\.0$", "", regex=True),
        format="%Y%m%d", errors="coerce",
    )
    recent = daily[daily["td"] >= pd.Timestamp.today() - pd.DateOffset(years=1)]
    avg_amount = recent.groupby("ts_code")["amount"].mean()
    fb["avg_amount"] = fb["ts_code"].map(avg_amount).fillna(0)

    # 3. Benchmark dedup: keep OLDEST per benchmark
    fb_sorted = fb.sort_values("list_date_dt", ascending=True)
    fb_dedup = fb_sorted.drop_duplicates("benchmark", keep="first").copy()
    fb_dedup = fb_dedup[fb_dedup["avg_amount"] >= 50000].copy()
    print(f"  After dedup (oldest per benchmark, amount>=50k): {len(fb_dedup)} ETFs")

    # 4. Classify
    fb_dedup["bucket"] = fb_dedup.apply(
        lambda r: classify_etf(
            r["ts_code"], str(r.get("name", "")),
            str(r.get("fund_type", "股票型")),
            str(r.get("benchmark", "")),
        ), axis=1,
    )
    for b in ["defensive", "commodity", "overseas", "broad_a", "style", "theme"]:
        n = len(fb_dedup[fb_dedup["bucket"] == b])
        print(f"    {b}: {n} candidates (after dedup)")

    # 5. Per-bucket selection (top N by liquidity + maturity score)
    pool_rows = []
    for bucket, quota in BUCKET_QUOTAS.items():
        etfs = fb_dedup[fb_dedup["bucket"] == bucket].copy()
        if etfs.empty:
            print(f"    WARNING: {bucket} bucket has NO ETFs!")
            continue
        # Score: mostly liquidity, some bonus for older ETFs
        etfs["liquidity_rank"] = etfs["avg_amount"].rank(pct=True)
        etfs["pool_score"] = 0.7 * etfs["liquidity_rank"].fillna(0.5) + 0.3
        etfs = etfs.sort_values("pool_score", ascending=False)
        selected = etfs.head(quota)
        pool_rows.append(selected)

    if not pool_rows:
        print("  ERROR: No ETFs in any bucket!")
        return [] if not return_df else pd.DataFrame()

    pool_df = pd.concat(pool_rows, ignore_index=True)
    save_cols = ["ts_code", "name", "benchmark", "fund_type", "bucket",
                 "list_date_dt", "avg_amount"]
    pool_df[save_cols].to_csv(cache_file, index=False)

    print(f"  {pool_tag} final pool: {len(pool_df)} ETFs")
    for b in ["defensive", "commodity", "overseas", "broad_a", "style", "theme"]:
        subset = pool_df[pool_df["bucket"] == b]
        codes = subset["ts_code"].tolist()
        print(f"    {b} ({len(subset)}): {', '.join(codes)}")

    if return_df:
        return pool_df
    return sorted(pool_df["ts_code"].astype(str).tolist())


def print_pool_summary(pool_df: pd.DataFrame):
    """Print a human-readable summary of the pool."""
    for b in ["defensive", "commodity", "overseas", "broad_a", "style", "theme"]:
        subset = pool_df[pool_df["bucket"] == b]
        print(f"\n  [{b}] ({len(subset)} ETFs):")
        for _, r in subset.iterrows():
            print(f"    {r['ts_code']}  {r['name']}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    TOKEN = Path(__file__).resolve().parent.parent / "config" / "tushare_token.txt"
    CACHE = Path(__file__).resolve().parent.parent / "data" / "tushare_cache"
    df = build_classified_pool(str(TOKEN), str(CACHE), pool_tag="F2_v3", force_rebuild=True, return_df=True)
    print("\n" + "=" * 70)
    print("FULL POOL SUMMARY")
    print("=" * 70)
    print_pool_summary(df)
