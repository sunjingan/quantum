# Adaptive Sequence V3

- benchmark: `sh000300`
- cost: 1.5bp commission + 2bp slippage per side
- order: window scan -> baseline threshold controls -> wide A/B -> V3 exp/hold split
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
| LONG_2013_2026 | WideA | 35.64% | 1.50 | -22.45% | 30,331,912 | 5870 |
| LONG_2013_2026 | WideB | 31.67% | 1.46 | -24.22% | 19,506,345 | 6617 |

## v3_exp_hold

| period | variant | annual | sharpe | dd | final | trades |
|---|---|---:|---:|---:|---:|---:|
| 2026_NOWARMUP | Exph_v3 | 107.17% | 3.54 | -15.86% | 989,720 | 568 |
| 2026_NOWARMUP | Exph_v5_div_lowbear | 105.38% | 3.30 | -16.51% | 974,751 | 539 |
| 2026_NOWARMUP | Exph_v6_very_high_div | 104.98% | 3.61 | -15.31% | 977,748 | 599 |
| 2026_NOWARMUP | Exph_v2_lower_bear | 101.62% | 3.16 | -16.78% | 950,372 | 533 |
| 2026_NOWARMUP | Exph_base | 100.95% | 3.10 | -16.73% | 945,185 | 501 |
| 2026_NOWARMUP | Exph_v4_smoother | 100.09% | 3.04 | -16.91% | 939,111 | 453 |
| LONG_2013_2026 | Exph_v3 | 32.60% | 1.59 | -20.11% | 22,676,268 | 11005 |
| LONG_2013_2026 | Exph_v4_smoother | 32.36% | 1.53 | -20.77% | 21,647,653 | 9685 |
| LONG_2013_2026 | Exph_v5_div_lowbear | 32.30% | 1.55 | -21.20% | 21,609,336 | 10703 |
| LONG_2013_2026 | Exph_base | 32.17% | 1.53 | -20.88% | 21,155,499 | 10070 |
| LONG_2013_2026 | Exph_v2_lower_bear | 31.56% | 1.50 | -21.24% | 19,612,310 | 10641 |
| LONG_2013_2026 | Exph_v6_very_high_div | 31.40% | 1.56 | -21.49% | 19,678,791 | 11512 |

## Key Takeaways

- `20dRet` window scan: 15d is the best long-period window among the tested set, while 5d/10d are more aggressive and 60d is too slow.
- Baseline threshold controls: fixed thresholds are no-ops on fixed-5; rolling P60 is the only method that materially changes behavior, but it lowers Sharpe and increases drawdown on both periods.
- WideA/WideB: both reduce drawdown versus Current, but also lower annual return; WideA is the better of the two on both periods.
- V3 exp/hold split: `Exph_v3` is the best of the tested split variants on both periods. It improves DD versus Current-style N-only control while keeping long-period Sharpe the best in this block.
