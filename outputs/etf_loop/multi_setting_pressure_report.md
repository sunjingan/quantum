# ETF Loop Multi-Setting Pressure Tests

- window: `2018-01-01` to `2026-06-25`
- prices: continuous adjusted OHLC/VWAP for signal, execution, and valuation
- execution: signal on day T close, trade on configured future trading day; no signal-day fallback

## Base Results

| config | ann | sharpe | dd | alpha | trades | dynamic_buys | final |
|---|---:|---:|---:|---:|---:|---:|---:|
| F2O_SM025 | 37.85% | 1.44 | -23.09% | 33.73% | 4722 | 306 | 8210446 |
| F2O_SM025_SW05 | 37.23% | 1.43 | -23.48% | 33.11% | 4584 | 301 | 7817715 |
| F2_CAP_MA60_SW05 | 37.12% | 1.66 | -18.79% | 33.00% | 5112 | 458 | 8349063 |
| F2_CAP_MA60 | 36.66% | 1.64 | -18.40% | 32.54% | 5191 | 476 | 8047163 |
| F2_CAP_BASE | 35.33% | 1.55 | -18.24% | 31.21% | 5097 | 478 | 7163637 |
| F2_STATIC_MA60 | 35.13% | 1.63 | -17.03% | 31.01% | 4492 | 0 | 7205985 |
| F2_STATIC_BASE | 34.32% | 1.57 | -17.00% | 30.20% | 4373 | 0 | 6709729 |
| F2O_CAP_BASE | 32.79% | 1.43 | -20.89% | 28.68% | 5258 | 349 | 5818063 |
| G2_PIT_PURE | 19.97% | 0.99 | -20.16% | 15.85% | 4161 | 0 | 2152789 |

## Stress Delta Vs open_d1

| config | stress | ann | ann_delta | sharpe | dd | trades |
|---|---|---:|---:|---:|---:|---:|
| F2O_CAP_BASE | close_d1 | 32.94% | 0.15% | 1.42 | -23.27% | 5392 |
| F2O_CAP_BASE | open_d1_adverse_20bp | 10.62% | -22.17% | 0.46 | -45.07% | 5001 |
| F2O_CAP_BASE | open_d2 | 33.10% | 0.31% | 1.41 | -26.01% | 5426 |
| F2O_CAP_BASE | vwap_d1 | 33.23% | 0.44% | 1.47 | -22.22% | 5317 |
| F2O_SM025 | close_d1 | 35.68% | -2.17% | 1.35 | -22.85% | 4829 |
| F2O_SM025 | open_d1_adverse_20bp | 15.14% | -22.71% | 0.58 | -53.61% | 4530 |
| F2O_SM025 | open_d2 | 37.17% | -0.68% | 1.38 | -27.90% | 4944 |
| F2O_SM025 | vwap_d1 | 38.55% | 0.70% | 1.50 | -21.56% | 4796 |
| F2O_SM025_SW05 | close_d1 | 34.72% | -2.51% | 1.32 | -23.19% | 4689 |
| F2O_SM025_SW05 | open_d1_adverse_20bp | 15.27% | -21.95% | 0.58 | -51.48% | 4417 |
| F2O_SM025_SW05 | open_d2 | 36.68% | -0.54% | 1.36 | -28.29% | 4779 |
| F2O_SM025_SW05 | vwap_d1 | 37.57% | 0.35% | 1.47 | -21.76% | 4642 |
| F2_CAP_BASE | close_d1 | 32.20% | -3.13% | 1.39 | -22.15% | 5168 |
| F2_CAP_BASE | open_d1_adverse_20bp | 15.28% | -20.04% | 0.67 | -34.15% | 4939 |
| F2_CAP_BASE | open_d2 | 31.91% | -3.42% | 1.36 | -24.60% | 5180 |
| F2_CAP_BASE | vwap_d1 | 33.54% | -1.78% | 1.49 | -21.13% | 5125 |
| F2_CAP_MA60 | close_d1 | 33.64% | -3.02% | 1.47 | -21.32% | 5274 |
| F2_CAP_MA60 | open_d1_adverse_20bp | 16.22% | -20.44% | 0.73 | -32.74% | 5042 |
| F2_CAP_MA60 | open_d2 | 32.52% | -4.14% | 1.40 | -22.88% | 5293 |
| F2_CAP_MA60 | vwap_d1 | 34.60% | -2.06% | 1.56 | -19.77% | 5230 |
| F2_CAP_MA60_SW05 | close_d1 | 34.13% | -2.99% | 1.49 | -21.10% | 5140 |
| F2_CAP_MA60_SW05 | open_d1_adverse_20bp | 17.39% | -19.73% | 0.78 | -28.76% | 4962 |
| F2_CAP_MA60_SW05 | open_d2 | 33.41% | -3.71% | 1.44 | -22.66% | 5170 |
| F2_CAP_MA60_SW05 | vwap_d1 | 34.69% | -2.43% | 1.56 | -19.97% | 5074 |
| F2_STATIC_BASE | close_d1 | 32.33% | -1.99% | 1.45 | -21.09% | 4457 |
| F2_STATIC_BASE | open_d1_adverse_20bp | 15.89% | -18.43% | 0.72 | -35.00% | 4184 |
| F2_STATIC_BASE | open_d2 | 32.91% | -1.40% | 1.46 | -23.08% | 4488 |
| F2_STATIC_BASE | vwap_d1 | 33.09% | -1.23% | 1.53 | -19.09% | 4378 |
| F2_STATIC_MA60 | close_d1 | 32.45% | -2.67% | 1.47 | -21.07% | 4509 |
| F2_STATIC_MA60 | open_d1_adverse_20bp | 16.36% | -18.77% | 0.76 | -33.89% | 4296 |
| F2_STATIC_MA60 | open_d2 | 32.35% | -2.77% | 1.45 | -21.88% | 4547 |
| F2_STATIC_MA60 | vwap_d1 | 33.03% | -2.10% | 1.54 | -19.07% | 4462 |
| G2_PIT_PURE | close_d1 | 18.52% | -1.45% | 0.92 | -22.61% | 4186 |
| G2_PIT_PURE | open_d1_adverse_20bp | 2.40% | -17.57% | 0.12 | -49.83% | 4057 |
| G2_PIT_PURE | open_d2 | 16.26% | -3.71% | 0.80 | -22.03% | 4173 |
| G2_PIT_PURE | vwap_d1 | 18.74% | -1.23% | 0.95 | -21.67% | 4126 |

## Notes

- `F2_STATIC_*`: static F2_v3 pool only.
- `G2_PIT_PURE`: point-in-time monthly dynamic pool only.
- `F2_CAP_*`: F2_v3 core plus capped PIT dynamic supplement.
- `F2O_*`: F2_v3 plus original 38 ETF core, with capped PIT dynamic supplement.
- `SW05`: keep current holding unless replacement score is at least 5% better.