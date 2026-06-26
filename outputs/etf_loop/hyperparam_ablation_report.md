# ETF Loop Hyperparameter Ablation

- window: `2013-07-01` to `2026-06-25`
- execution: signal close -> next trading day open; missing next open is skipped
- benchmark: HS300 (`sh000300`)
- profiles: `F2_STATIC`, `F2_CAP`, `F2O_CAP` where selected

## Best By Sharpe

| rank | tag | profile | family | ann | sharpe | dd | win | alpha | trades |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|
| 1 | `ABL_F2_CAP_MA_OVERHEAT_MR60_T114_P50` | F2_CAP | MA_OVERHEAT | 31.14% | 1.49 | -22.44% | 46.16% | 26.95% | 6709 |
| 2 | `ABL_F2O_CAP_SHORT_MOM_SM0p25` | F2O_CAP | SHORT_MOM | 36.25% | 1.49 | -22.66% | 47.40% | 32.06% | 6476 |
| 3 | `ABL_F2_CAP_MA_OVERHEAT_MR40_T114_P50` | F2_CAP | MA_OVERHEAT | 30.51% | 1.47 | -22.45% | 46.31% | 26.33% | 6706 |
| 4 | `ABL_F2_CAP_MA_OVERHEAT_MR20_T110_P50` | F2_CAP | MA_OVERHEAT | 30.55% | 1.46 | -22.37% | 46.28% | 26.36% | 6706 |
| 5 | `ABL_F2_STATIC_MA_OVERHEAT_MR40_T114_P50` | F2_STATIC | MA_OVERHEAT | 29.20% | 1.44 | -25.12% | 46.33% | 25.01% | 5944 |
| 6 | `ABL_F2_STATIC_MA_OVERHEAT_MR60_T114_P50` | F2_STATIC | MA_OVERHEAT | 29.18% | 1.44 | -25.12% | 46.10% | 24.99% | 5973 |
| 7 | `ABL_F2_STATIC_MA_OVERHEAT_MR20_T110_P50` | F2_STATIC | MA_OVERHEAT | 29.24% | 1.44 | -25.11% | 46.34% | 25.06% | 5978 |
| 8 | `ABL_F2_CAP_MA_OVERHEAT_MR20_T114_P50` | F2_CAP | MA_OVERHEAT | 30.31% | 1.44 | -22.43% | 45.96% | 26.12% | 6643 |
| 9 | `ABL_F2_STATIC_MA_OVERHEAT_MR20_T114_P50` | F2_STATIC | MA_OVERHEAT | 29.24% | 1.43 | -25.12% | 46.25% | 25.05% | 5905 |
| 10 | `ABL_F2_CAP_MA_OVERHEAT_MR20_T114_P70` | F2_CAP | MA_OVERHEAT | 30.22% | 1.43 | -22.43% | 45.87% | 26.03% | 6614 |
| 11 | `ABL_F2_CAP_ATR_ATR3p0` | F2_CAP | ATR | 30.07% | 1.43 | -22.41% | 45.98% | 25.88% | 6535 |
| 12 | `ABL_F2_CAP_ATR_ATR_OFF` | F2_CAP | ATR | 30.07% | 1.43 | -22.41% | 45.98% | 25.88% | 6535 |
| 13 | `ABL_F2_CAP_ATR_ATR2p5` | F2_CAP | ATR | 30.06% | 1.43 | -22.42% | 45.94% | 25.88% | 6541 |
| 14 | `ABL_F2_STATIC_ATR_ATR3p0` | F2_STATIC | ATR | 29.09% | 1.42 | -25.11% | 46.32% | 24.90% | 5820 |
| 15 | `ABL_F2_STATIC_ATR_ATR2p5` | F2_STATIC | ATR | 29.09% | 1.42 | -25.11% | 46.31% | 24.90% | 5826 |
| 16 | `ABL_F2_STATIC_MA_OVERHEAT_MR20_T114_P70` | F2_STATIC | MA_OVERHEAT | 29.17% | 1.42 | -25.11% | 46.28% | 24.98% | 5888 |
| 17 | `ABL_F2_CAP_MA_OVERHEAT_MR20_T114_P30` | F2_CAP | MA_OVERHEAT | 29.79% | 1.42 | -22.32% | 46.03% | 25.60% | 6693 |
| 18 | `ABL_F2_STATIC_ATR_ATR_OFF` | F2_STATIC | ATR | 29.01% | 1.42 | -25.09% | 46.19% | 24.82% | 5819 |
| 19 | `ABL_F2_CAP_STOP_SL_OFF` | F2_CAP | STOP | 29.84% | 1.42 | -22.42% | 45.86% | 25.66% | 6581 |
| 20 | `ABL_F2_STATIC_MA_OVERHEAT_MR20_T114_P30` | F2_STATIC | MA_OVERHEAT | 28.80% | 1.41 | -25.12% | 46.23% | 24.61% | 5966 |

## Family Winners

| profile | family | tag | ann | sharpe | dd | alpha | notes |
|---|---|---|---:|---:|---:|---:|---|
| F2O_CAP | ATR | `ABL_F2O_CAP_ATR_ATR3p0` | 26.82% | 1.31 | -22.40% | 22.63% | ATR multiplier=3.0 |
| F2O_CAP | BASE | `ABL_F2O_CAP_BASE_BASE` | 26.58% | 1.29 | -22.32% | 22.39% | baseline |
| F2O_CAP | HOLD | `ABL_F2O_CAP_HOLD_H6` | 26.62% | 1.38 | -21.02% | 22.43% | holdings_num=6 |
| F2O_CAP | LOOKBACK | `ABL_F2O_CAP_LOOKBACK_LB25` | 26.58% | 1.29 | -22.32% | 22.39% | regression lookback=25 trading days |
| F2O_CAP | MA_OVERHEAT | `ABL_F2O_CAP_MA_OVERHEAT_MR60_T114_P50` | 28.05% | 1.38 | -22.48% | 23.87% | penalize price/MA60>=1.15 by x0.50 |
| F2O_CAP | REBAL | `ABL_F2O_CAP_REBAL_RB1` | 26.58% | 1.29 | -22.32% | 22.39% | rebalance every 1 trading day(s) |
| F2O_CAP | SHORT_MOM | `ABL_F2O_CAP_SHORT_MOM_SM0p25` | 36.25% | 1.49 | -22.66% | 32.06% | short annualized momentum threshold=0.25 |
| F2O_CAP | STOP | `ABL_F2O_CAP_STOP_SL90` | 26.58% | 1.29 | -22.32% | 22.39% | fixed stop loss=0.90 |
| F2_CAP | ATR | `ABL_F2_CAP_ATR_ATR3p0` | 30.07% | 1.43 | -22.41% | 25.88% | ATR multiplier=3.0 |
| F2_CAP | BASE | `ABL_F2_CAP_BASE_BASE` | 29.70% | 1.41 | -22.43% | 25.51% | baseline |
| F2_CAP | HOLD | `ABL_F2_CAP_HOLD_H5` | 29.70% | 1.41 | -22.43% | 25.51% | holdings_num=5 |
| F2_CAP | LOOKBACK | `ABL_F2_CAP_LOOKBACK_LB25` | 29.70% | 1.41 | -22.43% | 25.51% | regression lookback=25 trading days |
| F2_CAP | MA_OVERHEAT | `ABL_F2_CAP_MA_OVERHEAT_MR60_T114_P50` | 31.14% | 1.49 | -22.44% | 26.95% | penalize price/MA60>=1.15 by x0.50 |
| F2_CAP | REBAL | `ABL_F2_CAP_REBAL_RB1` | 29.70% | 1.41 | -22.43% | 25.51% | rebalance every 1 trading day(s) |
| F2_CAP | SHORT_MOM | `ABL_F2_CAP_SHORT_MOM_SM0p0` | 29.70% | 1.41 | -22.43% | 25.51% | short annualized momentum threshold=0.00 |
| F2_CAP | STOP | `ABL_F2_CAP_STOP_SL_OFF` | 29.84% | 1.42 | -22.42% | 25.66% | disable fixed stop loss |
| F2_STATIC | ATR | `ABL_F2_STATIC_ATR_ATR3p0` | 29.09% | 1.42 | -25.11% | 24.90% | ATR multiplier=3.0 |
| F2_STATIC | BASE | `ABL_F2_STATIC_BASE_BASE` | 28.72% | 1.41 | -25.10% | 24.53% | baseline |
| F2_STATIC | HOLD | `ABL_F2_STATIC_HOLD_H5` | 28.72% | 1.41 | -25.10% | 24.53% | holdings_num=5 |
| F2_STATIC | LOOKBACK | `ABL_F2_STATIC_LOOKBACK_LB25` | 28.72% | 1.41 | -25.10% | 24.53% | regression lookback=25 trading days |
| F2_STATIC | MA_OVERHEAT | `ABL_F2_STATIC_MA_OVERHEAT_MR40_T114_P50` | 29.20% | 1.44 | -25.12% | 25.01% | penalize price/MA40>=1.15 by x0.50 |
| F2_STATIC | REBAL | `ABL_F2_STATIC_REBAL_RB1` | 28.72% | 1.41 | -25.10% | 24.53% | rebalance every 1 trading day(s) |
| F2_STATIC | SHORT_MOM | `ABL_F2_STATIC_SHORT_MOM_SM0p0` | 28.72% | 1.41 | -25.10% | 24.53% | short annualized momentum threshold=0.00 |
| F2_STATIC | STOP | `ABL_F2_STATIC_STOP_SL_OFF` | 28.86% | 1.41 | -25.10% | 24.68% | disable fixed stop loss |

## Baselines

| profile | tag | ann | sharpe | dd | final | hs300 ann | alpha |
|---|---|---:|---:|---:|---:|---:|---:|
| F2O_CAP | `ABL_F2O_CAP_BASE_BASE` | 26.58% | 1.29 | -22.32% | 10651376 | 4.19% | 22.39% |
| F2_CAP | `ABL_F2_CAP_BASE_BASE` | 29.70% | 1.41 | -22.43% | 15516027 | 4.19% | 25.51% |
| F2_STATIC | `ABL_F2_STATIC_BASE_BASE` | 28.72% | 1.41 | -25.10% | 13959908 | 4.19% | 24.53% |