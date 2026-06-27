# Adaptive Holdings FIX2

- pool: `F2_CAP_MA60`
- benchmark: `sh000300`
- adaptive window: `20` trading days
- costs: commission 1.5bp + slippage 2bp per side
- adaptive tiers: 5/4/3/2/1/0 by benchmark 20d return

| label | annual | sharpe | dd | total | final | trades | active annual | active dd |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| LONG_2013_2026_20dRet_ScoreW | 36.81% | 1.40 | -23.99% | 6385.77% | 32,428,860 | 4886 | 0.00% | 0.00% |
| LONG_2013_2026_20dRet_ScoreW_Thresh01 | 36.09% | 1.37 | -23.35% | 5818.49% | 29,592,461 | 4628 | 0.00% | 0.00% |
| LONG_2013_2026_20dRet | 35.83% | 1.45 | -23.58% | 5915.42% | 30,077,119 | 5074 | 0.00% | 0.00% |
| LONG_2013_2026_Baseline_Fixed5 | 29.01% | 1.47 | -18.98% | 2846.38% | 14,731,909 | 7562 | 0.00% | 0.00% |
| 2026_NOWARMUP_20dRet | 116.98% | 3.04 | -19.72% | 107.42% | 1,037,095 | 244 | 180.29% | -19.72% |
| 2026_NOWARMUP_20dRet_ScoreW | 102.95% | 2.67 | -20.51% | 88.91% | 944,532 | 244 | 158.67% | -20.51% |
| 2026_NOWARMUP_20dRet_ScoreW_Thresh01 | 99.94% | 2.58 | -21.76% | 85.10% | 925,500 | 219 | 154.04% | -21.76% |
| 2026_NOWARMUP_Baseline_Fixed5 | 91.86% | 3.30 | -15.76% | 79.63% | 898,160 | 347 | 141.58% | -15.76% |