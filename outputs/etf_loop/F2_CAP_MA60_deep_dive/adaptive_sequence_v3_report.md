# Adaptive Sequence V3

- benchmark: `sh000300`
- cost: 1.5bp commission + 2bp slippage per side
- order: window scan -> baseline threshold controls -> wide A/B -> V3 exp/hold split
- data source: current code + current engine, rerun in this pass
- control rule: each block changes one axis only

## window_scan

| period | variant | annual | sharpe | dd | final | trades |
|---|---|---:|---:|---:|---:|---:|
| 2026_NOWARMUP | 5d | 152.63% | 3.84 | -20.96% | 1,310,153 | 214 |
| 2026_NOWARMUP | 10d | 145.92% | 3.79 | -20.32% | 1,256,764 | 233 |
| 2026_NOWARMUP | 15d | 144.20% | 3.60 | -19.00% | 1,238,045 | 245 |
| 2026_NOWARMUP | 20d | 116.98% | 3.04 | -19.72% | 1,037,095 | 244 |
| 2026_NOWARMUP | 30d | 109.99% | 3.05 | -16.00% | 996,130 | 266 |
| 2026_NOWARMUP | 60d | 99.13% | 2.92 | -17.31% | 931,114 | 275 |
| LONG_2013_2026 | 15d | 39.81% | 1.57 | -25.44% | 48,555,145 | 5041 |
| LONG_2013_2026 | 20d | 35.83% | 1.45 | -23.58% | 30,077,119 | 5074 |
| LONG_2013_2026 | 10d | 34.80% | 1.38 | -36.41% | 26,106,971 | 4875 |
| LONG_2013_2026 | 5d | 34.74% | 1.34 | -25.26% | 25,340,172 | 4849 |
| LONG_2013_2026 | 30d | 32.04% | 1.35 | -21.27% | 19,303,242 | 4940 |
| LONG_2013_2026 | 60d | 25.77% | 1.11 | -32.90% | 8,976,198 | 4846 |

## threshold_baseline

| period | variant | annual | sharpe | dd | final | trades |
|---|---|---:|---:|---:|---:|---:|
| 2026_NOWARMUP | Dynamic ratio 0.5 | 91.86% | 3.30 | -15.76% | 898,160 | 347 |
| 2026_NOWARMUP | Fixed threshold 0.1 | 91.86% | 3.30 | -15.76% | 898,160 | 347 |
| 2026_NOWARMUP | Rolling P60 | 52.02% | 1.65 | -18.96% | 684,321 | 177 |
| LONG_2013_2026 | Rolling P60 | 32.46% | 1.32 | -25.29% | 19,847,304 | 4292 |
| LONG_2013_2026 | Dynamic ratio 0.5 | 29.01% | 1.47 | -18.98% | 14,731,909 | 7562 |
| LONG_2013_2026 | Fixed threshold 0.1 | 29.01% | 1.47 | -18.98% | 14,731,909 | 7562 |

## wide_ab

| period | variant | annual | sharpe | dd | final | trades |
|---|---|---:|---:|---:|---:|---:|
| 2026_NOWARMUP | Current | 144.20% | 3.60 | -19.00% | 1,238,045 | 245 |
| 2026_NOWARMUP | WideA | 115.15% | 3.39 | -16.33% | 1,035,666 | 288 |
| 2026_NOWARMUP | WideB | 101.17% | 3.26 | -17.15% | 949,553 | 321 |
| LONG_2013_2026 | Current | 39.81% | 1.57 | -25.44% | 48,555,145 | 5041 |
| LONG_2013_2026 | WideA | 37.12% | 1.62 | -19.66% | 37,363,494 | 5877 |
| LONG_2013_2026 | WideB | 32.81% | 1.52 | -21.80% | 22,590,142 | 6601 |

## v3_exp_hold

| period | variant | annual | sharpe | dd | final | trades |
|---|---|---:|---:|---:|---:|---:|
| 2026_NOWARMUP | Exph_v3 | 87.66% | 3.67 | -11.84% | 879,433 | 358 |
| 2026_NOWARMUP | Exph_v4_smoother | 83.62% | 3.20 | -13.65% | 853,005 | 326 |
| 2026_NOWARMUP | Exph_v6_very_high_div | 82.38% | 3.64 | -11.88% | 850,713 | 369 |
| 2026_NOWARMUP | Exph_base | 79.96% | 3.20 | -13.07% | 834,129 | 322 |
| 2026_NOWARMUP | Exph_v5_div_lowbear | 75.75% | 3.37 | -11.56% | 814,229 | 337 |
| 2026_NOWARMUP | Exph_v2_lower_bear | 72.14% | 3.16 | -11.86% | 794,574 | 331 |
| LONG_2013_2026 | Exph_v4_smoother | 26.94% | 1.45 | -17.65% | 11,687,466 | 7706 |
| LONG_2013_2026 | Exph_v3 | 26.14% | 1.47 | -17.53% | 10,789,967 | 8332 |
| LONG_2013_2026 | Exph_base | 26.07% | 1.43 | -18.29% | 10,573,093 | 7683 |
| LONG_2013_2026 | Exph_v6_very_high_div | 24.96% | 1.42 | -18.26% | 9,342,331 | 8692 |
| LONG_2013_2026 | Exph_v5_div_lowbear | 23.46% | 1.37 | -17.29% | 7,811,795 | 7931 |
| LONG_2013_2026 | Exph_v2_lower_bear | 23.37% | 1.33 | -19.29% | 7,668,726 | 7809 |
