# ETF Loop Non-Friend FIX1 Rerun - 2026-06-27

本轮只重跑非 `friend_mode` 实验。`friend_mode` 已在日线回测引擎中禁用，因为它需要 9:50 盘中信号和盘中成交数据，当前日线 OHLCV 无法安全复现，继续跑会把不可交易执行假设混入结论。

## 修复后重跑范围

- 成本压力、2026 nowarmup 核心结果：上一轮已用 `COSTTIER_FIX1` / 修复后代码重跑，见 `docs/etf_loop_fix_audit_20260627.md`。
- 仓位和权重实验：本轮重跑，标签前缀 `POSMGT_FIX1`。
- 长周期优化对比：本轮重跑，标签前缀 `LONGPERIOD_FIX1`。
- Wyckoff prefilter：本轮重跑，标签前缀 `WYCKPREFILTER_FIX1`。
- Wyckoff v2：本轮重跑，标签前缀 `WYCKV2_FIX1`。

未重跑：`friend_mode` 相关复现实验。旧 `friend_mode` 结果不应继续作为策略可交易证据。

## 执行命令

```bash
source activate.sh && python archive/etf_loop/run_position_mgmt_experiments.py
source activate.sh && python archive/etf_loop/run_long_period_optimization_compare.py
source activate.sh && python archive/etf_loop/run_wyckoff_prefilter_tests.py
source activate.sh && python archive/etf_loop/run_wyckoff_v2_tests.py
python -m py_compile archive/etf_loop/run_position_mgmt_experiments.py archive/etf_loop/run_long_period_optimization_compare.py archive/etf_loop/run_wyckoff_prefilter_tests.py archive/etf_loop/run_wyckoff_v2_tests.py
```

## 输出文件

- `outputs/etf_loop/F2_CAP_MA60_deep_dive/position_management_fix1.md`
- `outputs/etf_loop/F2_CAP_MA60_deep_dive/position_management_fix1.csv`
- `outputs/etf_loop/F2_CAP_MA60_deep_dive/long_period_optimization_fix1.md`
- `outputs/etf_loop/F2_CAP_MA60_deep_dive/long_period_optimization_fix1.csv`
- `outputs/etf_loop/F2_CAP_MA60_deep_dive/wyckoff_prefilter_fix1.md`
- `outputs/etf_loop/F2_CAP_MA60_deep_dive/wyckoff_prefilter_fix1.csv`
- `outputs/etf_loop/F2_CAP_MA60_deep_dive/wyckoff_v2_fix1.md`
- `outputs/etf_loop/F2_CAP_MA60_deep_dive/wyckoff_v2_fix1.csv`

## 核心结果

### 仓位和权重

| 周期 | 变体 | 年化 | Sharpe | DD | 终值 |
|---|---|---:|---:|---:|---:|
| 长周期 | Baseline 等权 5 | 30.54% | 1.54 | -18.45% | 17,827,823 |
| 长周期 | Score-weighted | 36.39% | 1.56 | -19.26% | 33,654,866 |
| 长周期 | Score+Vol | 34.48% | 1.61 | -18.91% | 27,955,361 |
| 长周期 | Dynamic holdings 3-8 | 35.11% | 1.50 | -26.99% | 28,601,698 |
| 长周期 | DynHold + ScoreW | 35.86% | 1.39 | -31.03% | 29,222,876 |
| 2026 nowarmup | Baseline 等权 5 | 93.34% | 3.35 | -15.61% | 907,070 |
| 2026 nowarmup | Dynamic holdings 3-8 | 114.62% | 3.34 | -16.86% | 1,031,060 |
| 2026 nowarmup | DynHold + ScoreW | 111.77% | 2.99 | -17.93% | 1,004,763 |

结论：Score-weighted 长周期仍有收益增益，但回撤略放大；Dynamic holdings 在 2026 表现最好，但长周期最大回撤扩大到 -26.99%，加 ScoreW 后回撤扩大到 -31.03%，不适合作为无约束默认配置。

### 长周期优化

| 池 | 变体 | 年化 | Sharpe | DD | 终值 |
|---|---|---:|---:|---:|---:|
| F2_CAP_MA60 | Baseline | 30.54% | 1.54 | -18.45% | 17,827,823 |
| F2_CAP_MA60 | Premium soft | 30.78% | 1.56 | -18.47% | 18,413,435 |
| F2_CAP_MA60 | Premium soft + VolW | 25.14% | 1.44 | -18.26% | 9,587,143 |
| F2_STATIC | Baseline | 28.59% | 1.48 | -17.39% | 14,116,550 |
| F2_STATIC | Premium soft | 28.36% | 1.47 | -17.38% | 13,738,963 |
| ORIG38_STATIC | Baseline | 22.34% | 1.46 | -16.43% | 7,060,913 |

结论：动态 cap 在 score/vol weighting 后重新生效后，`Premium soft + VolW` 长周期明显变差。Premium soft 对 F2_CAP_MA60 只有很小正贡献，对静态池没有稳定收益。

### Wyckoff

| 实验 | 池 | 周期 | Baseline 年化 | 实验年化 | 结论 |
|---|---|---|---:|---:|---|
| Prefilter | F2_CAP_MA60 | 2026 nowarmup | 93.34% | 98.81% | 短期改善 |
| Prefilter | F2_CAP_MA60 | 长周期 | 30.54% | 28.93% | 长周期拖累 |
| Prefilter | F2_STATIC | 长周期 | 28.59% | 9.91% | 过滤过激 |
| Prefilter | ORIG38_STATIC | 长周期 | 22.34% | 10.16% | 过滤过激 |
| V2 only | F2_CAP_MA60 | 长周期 | 30.54% | 30.54% | 基本无触发 |
| V2 + Premium | F2_CAP_MA60 | 长周期 | 30.54% | 30.78% | 只有微弱改善 |
| V2 + Premium | F2_CAP_MA60 | 2026 nowarmup | 93.34% | 97.52% | 短期改善 |

结论：Wyckoff prefilter 不能作为默认长期过滤器，只能作为 F2_CAP_MA60 在高波动短窗口中的候选开关。Wyckoff V2 单独基本无效，V2 + Premium 的提升主要来自 Premium。

## 对旧结论的影响

- 旧 `friend_mode` 相关结论失效，不应继续引用。
- 旧 `VolW` / `Score+Vol` / 动态权重融合结论需要以本轮 FIX1 为准，因为此前 dynamic pool cap 可能被后续权重覆盖。
- 旧 Wyckoff 结论需要以本轮 FIX1 为准，因为此前 Wyckoff 打分顺序存在问题。
- 基线 F2_CAP_MA60 非 friend 日线执行仍是当前最稳的研究基准；默认候选仍应优先使用非 `friend_mode`、次日执行、无信号日价格 fallback 的版本。
