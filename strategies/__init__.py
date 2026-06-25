"""
Quantitative investment strategies — qlib-integrated.

Strategies:
  - TrendSerenityStrategy / TrendSerenityModel: four-dimension Serenity scoring
  - POEPBRoeStrategy / POEPBRoeModel: PB+ROE market-state-aware selection
  - Theme ETF Momentum: weekly strong-theme selection + constituent relative strength

Usage:
  # Direct Python
  python -m strategies.run trend_serenity --market hs300 --start 2018-01-02

  # Via qrun YAML
  qrun config/trend_serenity_qlib.yaml
"""
from strategies._enrichment import EnrichmentCache, compute_enrichment_for_codes
from strategies._fundamental import FundamentalCache, qlib_to_tushare, tushare_to_qlib
from strategies._utils import (
    lot_floor,
    Hs300HistoryUniverse,
    QlibDailyReader,
    load_hs300_weights,
    market_state,
    monthly_rebalance_dates,
    pct_rank,
    score_high_is_good,
    score_low_is_good,
    summarize,
)
try:
    from strategies.trend_serenity import (
        TrendSerenityParams,
        TrendSerenityModel,
        TrendSerenityStrategy,
        build_serenity_pool_v2,
        select_targets_v2,
        price_strength_multi_mode,
        check_invalidation,
    )
except ImportError:
    pass
try:
    from strategies.trend_serenity_v2 import compute_serenity_v2, select_serenity_v2_targets
except ImportError:
    pass
from strategies.sector_prosperity import (
    SectorProsperityCache,
    SectorProsperityParams,
    attach_sector_scores,
    compute_sector_scores,
    compute_stock_topic_scores,
)
try:
    from strategies.poe_pb_roe import (
        POEPBRoeParams,
        POEPBRoeModel,
        POEPBRoeStrategy,
        build_base_dataframe,
        pick_targets,
    )
except ImportError:
    pass
from strategies.theme_etf_momentum import (
    ThemeETFParams,
    compute_theme_scores,
    run_theme_etf_backtest,
    select_targets as select_theme_etf_targets,
    select_themes,
)

__all__ = [
    "FundamentalCache",
    "qlib_to_tushare",
    "tushare_to_qlib",
    "QlibDailyReader",
    "load_hs300_weights",
    "Hs300HistoryUniverse",
    "market_state",
    "monthly_rebalance_dates",
    "pct_rank",
    "score_high_is_good",
    "score_low_is_good",
    "lot_floor",
    "summarize",
    "TrendSerenityParams",
    "TrendSerenityStrategy",
    "TrendSerenityModel",
    "EnrichmentCache",
    "compute_enrichment_for_codes",
    "build_serenity_pool_v2",
    "select_targets_v2",
    "price_strength_multi_mode",
    "check_invalidation",
    "compute_serenity_v2",
    "select_serenity_v2_targets",
    "SectorProsperityCache",
    "SectorProsperityParams",
    "compute_sector_scores",
    "compute_stock_topic_scores",
    "attach_sector_scores",
    "POEPBRoeParams",
    "POEPBRoeStrategy",
    "POEPBRoeModel",
    "build_base_dataframe",
    "pick_targets",
    "ThemeETFParams",
    "compute_theme_scores",
    "select_themes",
    "select_theme_etf_targets",
    "run_theme_etf_backtest",
]
