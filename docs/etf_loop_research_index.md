# ETF Loop 实验主线总记录

这份记录只保留已经修复后的关键节点。`outputs/etf_loop/legacy_pre_execution_fix/` 里是旧结果归档，不再作为结论依据。

关键参数释义见 [`docs/etf_loop_setting_glossary.md`](etf_loop_setting_glossary.md)。

## 1. 统一前提

- 数据源：本地缓存 + Tushare 已预取数据。
- 执行规则：`signal_date` 收盘生成信号，`next_date` 精确开盘成交；没有次日开盘价就跳过，不再 fallback 到信号日收盘。
- 成本口径：默认 1.5bp 佣金 + 2bp 滑点，单边 3.5bp，双边 7bp。
- 复现入口：所有命令都在仓库根目录执行，先 `source activate.sh`。

## 2. 主线演化

### 2.1 执行修复与核心复跑

- 报告：[`execution_fix_rerun_report.md`](../outputs/etf_loop/execution_fix_rerun_report.md)
- 复现：

```bash
source activate.sh
python runs/etf_loop/rerun_etf_loop_core.py
python analysis/etf_loop/analyze_dynamic_pool_impact.py
python analysis/etf_loop/analyze_etf_loop_deep_dive.py
```

- 关键修复：
  - 次日开盘价必须是精确 `next_date` 开盘，不允许历史开盘 fallback。
  - 卖出不再使用信号日收盘价成交。
  - 动态池与静态池的覆盖范围、单位、部分成交逻辑统一修正。
- 关键结论：
  - G2 PIT 优于 G1 PIT。
  - 成本越高，收益衰减越快，策略对摩擦很敏感。
  - 纯动态池弱于静态精选池，动态池更适合作为受限补漏。

### 2.2 固定样本外与压力测试

- 报告：[`validation_suite_report.md`](../outputs/etf_loop/validation_suite_report.md)
- 复现：

```bash
source activate.sh
python runs/etf_loop/run_etf_loop_validation_suite.py
```

- 关键设置：
  - 固定样本外：2018-2021 / 2022 / 2023-2026。
  - 年度拆分：2018 到 2026。
  - 成本三档、容量四档。
- 关键结论：
  - `F2_CAP_MA60` 是当前固定样本外里最稳的一档。
  - 2018 仍是明显弱年，2025/2026 是主要收益来源。
  - 成本上升后策略会明显退化，容量到数百万级后部分成交显著增加。

### 2.3 capped 动态池补漏

- 报告：[`dynamic_fusion_capped_report.md`](../outputs/etf_loop/dynamic_fusion_capped_report.md)
- 复现：

```bash
source activate.sh
python runs/etf_loop/run_dynamic_fusion_experiments.py
python analysis/etf_loop/analyze_dynamic_fusion_experiment_results.py
```

- 关键设置：
  - 静态核心池先占满大部分名额。
  - 动态 PIT 独有标的最多补 1 个席位。
  - 动态独有标的总权重受限，且要超过静态候选的分数边际。
  - 买入前 20 日涨幅过高时给动态候选额外过热惩罚。
- 关键结论：
  - 对 `F2_v3`，capped 动态补漏有效，最佳版本优于静态 `F2_v3`。
  - 对 `F2_v3 ∪ ORIG38`，动态补漏略有改善，但仍不如更强的静态 64 池。
  - 动态池应作为“补漏”，不是与静态池平权竞争。

### 2.4 动态持仓模式重审

- 报告：[`adaptive_holdings_reaudit_v1_report.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/adaptive_holdings_reaudit_v1_report.md)
- 复现：

```bash
source activate.sh
python runs/etf_loop/run_adaptive_holdings_reaudit.py
```

- 关键设置：
  - `F2_CAP_MA60`
  - 只比较单一动态持仓轴：`bench_ma60` / `bench_20d_ret` / `bench_vol` / `portfolio_dd`
  - `20dRet` 的 20dRet 行来自重刷后的结果，其余模式按当前引擎重跑
- 关键结论：
  - `20dRet` 仍是最强的动态持仓模式。
  - `MA60` 太慢，`Vol` 太弱，`DD + ScoreW` 在长周期上明显失真。
  - 评分阈值 `0.1` 过低，收益约束作用有限。

### 2.5 V3：把“总仓位”和“持仓数”拆开

- 报告：
  - [`adaptive_sequence_v3_report.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/adaptive_sequence_v3_report.md)
  - [`v3_multi_setting_diagnostics.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/v3_multi_setting_diagnostics.md)
  - [`single_factor_followups_v1_report.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/single_factor_followups_v1_report.md)
  - [`adaptive_15d_v3_tuning_report.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/adaptive_15d_v3_tuning_report.md)
- 复现：

```bash
source activate.sh
python runs/etf_loop/run_adaptive_sequence_v3.py
python runs/etf_loop/run_v3_attribution_tables.py
python runs/etf_loop/run_single_factor_followups_v1.py
python runs/etf_loop/run_15d_behavior_v3_tuning.py
```

- 关键设置：
  - `adaptive_window=15` 是本轮主窗口。
  - `adaptive_tiers_n` 只控制持仓数。
  - `adaptive_tiers_exposure` 只控制总仓位。
  - `use_score_weighting` 和 `switch_score_margin` 作为单因子补充测试。
- 关键结论：
  - `Current` 仍是长周期最强的高收益候选之一。
  - `WideA` 降回撤更明显，属于更保守的版本。
  - `Exph_v3_exp_looser` 代表“降总仓位但不过度压缩持仓数”的思路，风险最温和。
  - 单因素扰动里，`adaptive_window=15` 最像甜点区。
  - `use_score_weighting` 和 `switch_score_margin` 的效果只能在固定池/固定窗口下单独看，不能和池子改动混跑。

## 3. 当前可复现的候选策略

下面只列修复后可复现、且有明确结果支撑的候选，不列旧 bug 结果。

| 候选 | 适用主线 | 长周期年化 | 长周期 Sharpe | 长周期 DD | 2018 / 2022 / 2024 | 2026 nowarmup 年化 | 2026 nowarmup Sharpe | 2026 nowarmup DD | 备注 |
|---|---|---:|---:|---:|---|---:|---:|---:|---|
| `F2_CAP_MA60` | 稳定 baseline | 30.54% | 1.54 | -18.45% | -14.07% / -3.22% / 27.87% | 93.34% | 3.35 | -15.61% | 当前主对照 |
| `Current` | V3 主候选 | 39.81% | 1.57 | -25.44% | 5.26% / 2.81% / 11.32% | 144.20% | 3.60 | -19.00% | 收益最强，但回撤偏大 |
| `WideA` | 保守候选 | 37.12% | 1.62 | -19.66% | -0.62% / 31.21% / 29.58% | 115.15% | 3.39 | -16.33% | 风险更好，2018 受损 |
| `20dRet + ScoreW` | 动态持仓候选 | 36.81% | 1.40 | -23.99% | — | 102.95% | 2.67 | -20.51% | 动态持仓里长周期最强之一 |
| `Exph_v3_exp_looser` | 风险暴露拆分候选 | 27.33% | 1.51 | -17.30% | -9.31% / 14.53% / 31.20% | 81.43% | 3.20 | -18.57% | 更接近“降仓位不压死持仓数” |
| `DYNFUSE_F2v3_CAP1_W10_M05_H10P50` | 动态池补漏候选 | 29.70% | 1.41 | -22.43% | — | — | — | — | 动态池只做补漏，不做平权竞争 |

注：`20dRet + ScoreW` 和动态池补漏候选当前没有单独的 2018 / 2022 / 2024 年度拆分，因此保留 `—`。

## 4. 现在怎么读输出

推荐顺序：

1. [`outputs/etf_loop/README.md`](../outputs/etf_loop/README.md)
2. [`outputs/etf_loop/execution_fix_rerun_report.md`](../outputs/etf_loop/execution_fix_rerun_report.md)
3. [`outputs/etf_loop/validation_suite_report.md`](../outputs/etf_loop/validation_suite_report.md)
4. [`outputs/etf_loop/dynamic_fusion_capped_report.md`](../outputs/etf_loop/dynamic_fusion_capped_report.md)
5. [`outputs/etf_loop/F2_CAP_MA60_deep_dive/adaptive_holdings_reaudit_v1_report.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/adaptive_holdings_reaudit_v1_report.md)
6. [`outputs/etf_loop/F2_CAP_MA60_deep_dive/v3_multi_setting_diagnostics.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/v3_multi_setting_diagnostics.md)
7. [`outputs/etf_loop/F2_CAP_MA60_deep_dive/single_factor_followups_v1_report.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/single_factor_followups_v1_report.md)
