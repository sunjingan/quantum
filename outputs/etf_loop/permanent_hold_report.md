# ETF Loop Permanent Hold Experiments

- window: `2013-07-01` to `2026-06-25`
- base pool: `F2_v3 + ORIG38 + tested long assets`
- dynamic overlay: capped G2 PIT, max 1 dynamic slot, max 20% weight, 10% score margin, 20d overheat penalty
- permanent rule: after the strategy first buys a listed permanent asset, rank-out and stops are ignored
- dip-add rule: add only when drawdown from holding high exceeds threshold; no next-open fallback is allowed

## Results

| tag | group | asset | ann | sharpe | dd | alpha | first buy | buys | sells | dip adds | final |
|---|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|
| `PERMHOLD_NIKKEI225_HOLDONLY` | NIKKEI225 | 华夏野村日经225ETF(QDII) | 26.11% | 1.38 | -22.32% | 21.92% | 2019-09-25 | 13 | 0 | 0 | 10447525 |
| `PERMHOLD_GOLD_HOLDONLY` | GOLD | 华安易富黄金ETF | 20.92% | 1.37 | -16.03% | 16.74% | 2014-01-20 | 5 | 0 | 0 | 5915981 |
| `PERMHOLD_GOLD_DIP15_ADD5_MAX40` | GOLD | 华安易富黄金ETF | 20.92% | 1.37 | -16.03% | 16.74% | 2014-01-20 | 5 | 0 | 0 | 5915981 |
| `PERMHOLD_GOLD_DIP20_ADD10_MAX50` | GOLD | 华安易富黄金ETF | 20.92% | 1.37 | -16.03% | 16.73% | 2014-01-20 | 6 | 0 | 1 | 5912844 |
| `PERMHOLD_GOLD_DIP10_ADD5_MAX35` | GOLD | 华安易富黄金ETF | 20.75% | 1.36 | -15.99% | 16.56% | 2014-01-20 | 7 | 0 | 3 | 5790026 |
| `PERMHOLD_NIKKEI225_DIP10_ADD5_MAX35` | NIKKEI225 | 华夏野村日经225ETF(QDII) | 25.07% | 1.36 | -22.32% | 20.88% | 2019-09-25 | 13 | 0 | 9 | 9275320 |
| `PERMHOLD_NIKKEI225_DIP20_ADD10_MAX50` | NIKKEI225 | 华夏野村日经225ETF(QDII) | 24.87% | 1.34 | -22.32% | 20.68% | 2019-09-25 | 8 | 0 | 5 | 9037915 |
| `PERMHOLD_NIKKEI225_DIP15_ADD5_MAX40` | NIKKEI225 | 华夏野村日经225ETF(QDII) | 24.78% | 1.34 | -22.32% | 20.59% | 2019-09-25 | 13 | 0 | 8 | 8943423 |
| `PERMHOLD_BASE_EXPANDED` | BASE | 国泰纳斯达克100ETF(QDII), 华夏恒生科技ETF(QDII), 博时标普500ETF(QDII), 华夏野村日经225ETF(QDII), 华安易富黄金ETF | 26.58% | 1.29 | -22.32% | 22.39% | 2013-09-26 | 580 | 425 | 0 | 10651376 |
| `PERMHOLD_HSTECH_HOLDONLY` | HSTECH | 华夏恒生科技ETF(QDII) | 25.39% | 1.25 | -22.32% | 21.20% | 2022-06-17 | 5 | 0 | 0 | 9242042 |
| `PERMHOLD_HSTECH_DIP20_ADD10_MAX50` | HSTECH | 华夏恒生科技ETF(QDII) | 23.96% | 1.20 | -22.32% | 19.77% | 2022-06-17 | 10 | 0 | 6 | 7777174 |
| `PERMHOLD_HSTECH_DIP10_ADD5_MAX35` | HSTECH | 华夏恒生科技ETF(QDII) | 24.08% | 1.19 | -22.32% | 19.90% | 2022-06-17 | 9 | 0 | 8 | 7860709 |
| `PERMHOLD_SP500_HOLDONLY` | SP500 | 博时标普500ETF(QDII) | 21.58% | 1.17 | -31.63% | 17.39% | 2014-03-27 | 9 | 0 | 0 | 5981171 |
| `PERMHOLD_SP500_DIP10_ADD5_MAX35` | SP500 | 博时标普500ETF(QDII) | 20.75% | 1.15 | -31.63% | 16.56% | 2014-03-27 | 13 | 0 | 5 | 5432527 |
| `PERMHOLD_HSTECH_DIP15_ADD5_MAX40` | HSTECH | 华夏恒生科技ETF(QDII) | 23.11% | 1.15 | -22.32% | 18.93% | 2022-06-17 | 13 | 0 | 10 | 6979142 |
| `PERMHOLD_SP500_DIP15_ADD5_MAX40` | SP500 | 博时标普500ETF(QDII) | 20.51% | 1.15 | -31.63% | 16.32% | 2014-03-27 | 13 | 0 | 5 | 5286944 |
| `PERMHOLD_SP500_DIP20_ADD10_MAX50` | SP500 | 博时标普500ETF(QDII) | 20.12% | 1.14 | -31.63% | 15.93% | 2014-03-27 | 13 | 0 | 5 | 5060437 |
| `PERMHOLD_NASDAQ100_HOLDONLY` | NASDAQ100 | 国泰纳斯达克100ETF(QDII) | 22.01% | 0.94 | -54.16% | 17.82% | 2013-09-26 | 7 | 0 | 0 | 5161196 |
| `PERMHOLD_NASDAQ100_DIP15_ADD5_MAX40` | NASDAQ100 | 国泰纳斯达克100ETF(QDII) | 20.47% | 0.89 | -54.32% | 16.29% | 2013-09-26 | 10 | 0 | 6 | 4321645 |
| `PERMHOLD_NASDAQ100_DIP20_ADD10_MAX50` | NASDAQ100 | 国泰纳斯达克100ETF(QDII) | 20.37% | 0.89 | -53.76% | 16.18% | 2013-09-26 | 11 | 0 | 7 | 4277127 |
| `PERMHOLD_NASDAQ100_DIP10_ADD5_MAX35` | NASDAQ100 | 国泰纳斯达克100ETF(QDII) | 20.29% | 0.89 | -54.25% | 16.11% | 2013-09-26 | 10 | 0 | 6 | 4224543 |
| `PERMHOLD_US_GOLD_HOLDONLY` | US_GOLD | 国泰纳斯达克100ETF(QDII), 博时标普500ETF(QDII), 华安易富黄金ETF | 13.36% | 0.60 | -66.96% | 9.17% | 2013-09-26 | 27 | 0 | 0 | 1774160 |
| `PERMHOLD_US_GOLD_DIP20_ADD10_MAX50` | US_GOLD | 国泰纳斯达克100ETF(QDII), 博时标普500ETF(QDII), 华安易富黄金ETF | 12.66% | 0.56 | -66.84% | 8.48% | 2013-09-26 | 27 | 0 | 1 | 1622804 |
| `PERMHOLD_US_GOLD_DIP10_ADD5_MAX35` | US_GOLD | 国泰纳斯达克100ETF(QDII), 博时标普500ETF(QDII), 华安易富黄金ETF | 12.44% | 0.56 | -66.20% | 8.25% | 2013-09-26 | 32 | 0 | 5 | 1587990 |
| `PERMHOLD_US_GOLD_DIP15_ADD5_MAX40` | US_GOLD | 国泰纳斯达克100ETF(QDII), 博时标普500ETF(QDII), 华安易富黄金ETF | 12.45% | 0.56 | -67.00% | 8.27% | 2013-09-26 | 30 | 0 | 4 | 1581665 |