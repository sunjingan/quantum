# ETF Loop Adjusted Core Setting Comparison

- window: `2013-07-01` to `2026-06-25`
- execution: signal day close, next trading day adjusted open
- prices: continuous adjusted OHLC/VWAP for signal, execution, and valuation

| config | ann | sharpe | dd | alpha | trades | dynamic_buys | final |
|---|---:|---:|---:|---:|---:|---:|---:|
| F2O_SM025 | 36.57% | 1.50 | -23.10% | 32.38% | 6502 | 341 | 33297782 |
| F2O_SM025_SW05 | 36.07% | 1.48 | -23.60% | 31.88% | 6305 | 331 | 31343368 |
| F2_CAP_MA60_SW05 | 31.68% | 1.59 | -18.76% | 27.49% | 6617 | 487 | 20510717 |
| F2_CAP_MA60 | 31.53% | 1.59 | -18.34% | 27.35% | 6744 | 515 | 20143336 |
| F2_CAP_BASE | 30.62% | 1.52 | -18.23% | 26.43% | 6631 | 520 | 17822215 |
| F2_STATIC_MA60 | 30.52% | 1.58 | -18.35% | 26.33% | 6047 | 0 | 17992737 |
| F2_STATIC_BASE | 29.99% | 1.54 | -18.36% | 25.80% | 5944 | 0 | 16748780 |
| F2O_CAP_BASE | 27.55% | 1.35 | -20.90% | 23.37% | 7190 | 370 | 12096359 |
| G2_PIT_PURE | 13.00% | 0.80 | -20.15% | 8.81% | 4139 | 0 | 2155981 |