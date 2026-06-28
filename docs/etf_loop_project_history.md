# ETF Loop 项目总记录

这份文档把整个 ETF 轮动项目按真实演化顺序重新整理了一遍。目标不是罗列所有实验，而是把关键节点、关键修复、关键结论和可复现入口连成一条完整链路，方便别人从零读懂并复现。

`outputs/etf_loop/legacy_pre_execution_fix/` 里的旧结果只保留历史参考，不再作为当前结论依据。凡是涉及信号日收盘成交、next open 回退、friend mode 污染、旧动态池单位、旧部分成交逻辑的结果，都已经被后续修复覆盖。

关键参数释义见 [`docs/etf_loop_setting_glossary.md`](etf_loop_setting_glossary.md)。

## 1. 项目主线

这条策略线最终收敛到三个层次。

1. 一个稳定的核心池策略：`F2_CAP_MA60` 作为 baseline。
2. 一个受限动态补漏策略：动态 PIT 只作为 capped supplement，不和静态精选池平权竞争。
3. 一个更细的仓位管理层：把“总仓位暴露”和“持仓数量”拆开，而不是用一个 `N` 同时控制两件事。

## 2. 时间线

| 阶段 | 目标 | 代表报告 | 核心结论 |
|---|---|---|---|
| 早期池子筛选 | 先找出能稳定跑赢简单基准的静态策略 | [`hyperparam_ablation_report.md`](../outputs/etf_loop/hyperparam_ablation_report.md) | F2 系列优于静态等权和原始 38 池，MA60 过热惩罚是有效增益项 |
| 基准对比 | 证明不是只对内部池子有效 | [`benchmark_comparison_report.md`](../outputs/etf_loop/benchmark_comparison_report.md) | `F2_CAP_MA60` 跑赢 HS300、宽基 buy-hold 和简单动量 Top1/Top3 |
| 样本外验证 | 防止只是在全区间过拟合 | [`validation_suite_report.md`](../outputs/etf_loop/validation_suite_report.md) | `F2_CAP_MA60` 是当前固定样本外里最稳的 F2_CAP 候选 |
| 执行修复 | 消除未来函数和成交回退 | [`execution_fix_rerun_report.md`](../outputs/etf_loop/execution_fix_rerun_report.md) | 信号日收盘只负责出信号，成交必须是 next open；旧结果大批失效 |
| 动态池研究 | 判断动态 PIT 是否能增强主策略 | [`dynamic_fusion_capped_report.md`](../outputs/etf_loop/dynamic_fusion_capped_report.md) | 动态池能补漏，但不能平权竞争；单独动态池很弱 |
| 动态持仓研究 | 判断“市场弱时少买几只”是否有效 | [`adaptive_holdings_reaudit_v1_report.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/adaptive_holdings_reaudit_v1_report.md) | `20dRet` 明显优于 `MA60` / `Vol` / `DD` |
| V3 拆分 | 把风险暴露和持仓数量拆开 | [`v3_multi_setting_diagnostics.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/v3_multi_setting_diagnostics.md) | `target_exposure` 和 `target_holdings` 可以独立调，较弱市场不应被迫压到 1 只 |
| 单因素复审 | 防止混合改动污染结论 | [`single_factor_followups_v1_report.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/single_factor_followups_v1_report.md) | 只改一个轴时，15d 窗口和更宽松的阈值更稳定 |
| 2026 复盘 | 找出买高卖低的具体标的 | [`2026_nowarmup_comprehensive_report.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/2026_nowarmup_comprehensive_report.md) | 回撤主要集中在半导体、创业板、原油、纳指等高 beta 热点轮动 |

## 3. baseline 为什么最终落在 `F2_CAP_MA60`

这不是拍脑袋选的。早期我们先做了 family ablation，再做基准对比和样本外验证。

### 3.1 family ablation

报告：[`hyperparam_ablation_report.md`](../outputs/etf_loop/hyperparam_ablation_report.md)

复现命令：

```bash
source activate.sh
python runs/etf_loop/run_etf_loop_hyperparam_ablation.py
```

这里比较了 `F2_STATIC`、`F2_CAP`、`F2O_CAP` 三个 profile 下的基础版、HOLD、LOOKBACK、ATR、MA_OVERHEAT、STOP 等变体。关键观察是：

- `F2_CAP` 系列整体比 `F2_STATIC` 更强，说明“核心池 + 受控动态补充”的方向可行。
- `MA_OVERHEAT` 是最稳定的提升项之一，说明“追高惩罚”有实际价值。
- `F2O_CAP` 和 `F2_STATIC` 也能做出不错结果，但风险收益不如 `F2_CAP` 主线平衡。

### 3.2 基准对比

报告：[`benchmark_comparison_report.md`](../outputs/etf_loop/benchmark_comparison_report.md)

复现命令：

```bash
source activate.sh
python runs/etf_loop/run_benchmark_comparison.py
```

这一步把策略放到更直观的基准下看：

- `F2_CAP_MA60` 的 Sharpe 和收益都明显高于 HS300。
- 它也跑赢了常见 buy-hold ETF，比如黄金、纳指 100、标普 500。
- 简单动量 Top1 虽然年化看起来不低，但回撤非常大，说明“只看收益”不够。

### 3.3 固定样本外

报告：[`validation_suite_report.md`](../outputs/etf_loop/validation_suite_report.md)

复现命令：

```bash
source activate.sh
python runs/etf_loop/run_etf_loop_validation_suite.py
```

验证用的是固定样本外和逐年拆分，而不是只看全区间：

- `F2_CAP_MA60` 在 `2023-2026` 样本外优于 `F2_CAP_BASE` 和 `F2_CAP_ATR3`。
- `2018` 仍然弱，这是早期就暴露出的结构性短板。
- `2025` 和 `2026` 是收益主来源，后面必须做归因，不能只看总年化。

### 3.4 结论

`F2_CAP_MA60` 成为 baseline 的理由很简单：

- 它在 family ablation 里不是最差。
- 它在基准对比里明显跑赢常见替代方案。
- 它在样本外里比更朴素的 `F2_CAP_BASE` 更稳定。
- 它保留了后续加动态补漏、动态持仓、暴露拆分的接口空间。
- 它不是从 `dynamic_fusion_capped_report` 里“选出来”的，而是先经过 family ablation、基准对比和固定样本外验证后，才作为后续所有动态仓位实验的共同基座。
- `dynamic_fusion_capped_report` 只回答“动态 PIT 是否值得作为补漏层”，结论是“可以补漏，但不值得推翻 baseline 选择”。

## 4. 执行修复

报告：[`execution_fix_rerun_report.md`](../outputs/etf_loop/execution_fix_rerun_report.md)

复现命令：

```bash
source activate.sh
python runs/etf_loop/rerun_etf_loop_core.py
python analysis/etf_loop/analyze_dynamic_pool_impact.py
python analysis/etf_loop/analyze_etf_loop_deep_dive.py
```

这一阶段最重要的不是收益，而是把交易规则修正正确。

修复后必须满足：

- 信号只使用 `signal_date` 及以前数据。
- 买卖都在 `next_date` 精确开盘执行。
- 无 next open 就跳过，不再 fallback 到信号日收盘。
- 动态池和静态池的覆盖范围、单位、部分成交逻辑一致。

修复结论直接影响了后面所有实验。旧的 `friend_mode`、旧动态池、旧成交回退结果都不能再当最终证据。

## 5. 动态池研究

报告：[`dynamic_fusion_capped_report.md`](../outputs/etf_loop/dynamic_fusion_capped_report.md)

复现命令：

```bash
source activate.sh
python runs/etf_loop/run_dynamic_fusion_experiments.py
python analysis/etf_loop/analyze_dynamic_fusion_experiment_results.py
```

这里的核心问题是：动态 PIT 池到底应该怎么和静态核心池共存。

结果很明确：

- 纯 G1/G2 PIT 动态池弱于静态精选池。
- 把动态池和静态池简单并集后统一 top 5，会引入太多噪声。
- 更合理的是给动态池一个很小的补漏预算，比如最多 1 个席位或 10% 到 20% 的权重。
- 动态候选要加“过热惩罚”，否则很容易追到阶段高位。
- 这一段并没有重新选择 baseline；它只是在 `F2_CAP_MA60` 已确定为主线之后，确认“动态补漏层应该长什么样”。

这一步把“动态池补热点”从一个抽象想法变成了可控机制。

## 6. 动态持仓研究

这条线的目标，是解决“市场弱时不要硬打满 5 只”的问题。

### 6.1 初版动态持仓

报告：[`adaptive_holdings_experiment.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/adaptive_holdings_experiment.md)

复现命令：

```bash
source activate.sh
python runs/etf_loop/run_adaptive_holdings_full.py
```

这份报告记录了四种市场环境指标：

- `bench_ma60`
- `bench_20d_ret`
- `bench_vol`
- `portfolio_dd`

它的初步结论是：

- `20dRet` 最强。
- `MA60` 太慢。
- `Vol` 太弱。
- `DD` 太保守，且和 `ScoreW` 叠加后会失真。

### 6.2 重审版本

报告：[`adaptive_holdings_reaudit_v1_report.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/adaptive_holdings_reaudit_v1_report.md)

复现命令：

```bash
source activate.sh
python runs/etf_loop/run_adaptive_holdings_reaudit.py
```

这个版本重新跑了非 20dRet 的模式，避免之前引擎变化后继续引用旧结果。

结论没有变：

- `20dRet` 仍然最好。
- `MA60` 还是滞后。
- `Vol` 仍然偏弱。
- `DD + ScoreW` 是明显不稳定项，长周期上不建议用。

### 6.3 动态持仓的含义

这条线的本质不是“少买几只就更安全”，而是：

- 市场弱时降低总仓位。
- 持仓数量不要压得过低。
- 让 `target_exposure` 决定买多少，让 `target_holdings` 决定分散度。

这也是后面 V3 拆分的起点。

## 7. V3：把总仓位和持仓数拆开

### 7.1 V3 主线

报告：

- [`adaptive_sequence_v3_report.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/adaptive_sequence_v3_report.md)
- [`v3_multi_setting_diagnostics.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/v3_multi_setting_diagnostics.md)

复现命令：

```bash
source activate.sh
python runs/etf_loop/run_adaptive_sequence_v3.py
python runs/etf_loop/run_v3_attribution_tables.py
```

这一阶段的重点是把 `N` 拆开：

- `target_holdings` 只控制持仓只数。
- `target_exposure` 只控制总仓位。

这比“市场差就把 N 砍到 1”更合理。弱市可以降总仓位，但不应该把分散度也一起打掉。

### 7.2 V3 的单因素复审

报告：[`single_factor_followups_v1_report.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/single_factor_followups_v1_report.md)

复现命令：

```bash
source activate.sh
python runs/etf_loop/run_single_factor_followups_v1.py
```

这部分最重要的原则是控制变量：

- 只改窗口，不改别的。
- 只改阈值，不改池子。
- 只改 exposure，不改 N。
- 只改 N，不改 exposure。
- `use_score_weighting` 和 `switch_score_margin` 只在固定池子里单独测。

结果说明：

- `adaptive_window=15` 是甜点区。
- 更宽松的 exposure 档位比过于保守的版本更稳。
- `score_weighting` 和 `switch_score_margin` 不是万能增益，只在特定设置下有边际改善。

### 7.3 15d 行为诊断

报告：[`adaptive_15d_v3_tuning_report.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/adaptive_15d_v3_tuning_report.md)

复现命令：

```bash
source activate.sh
python runs/etf_loop/run_15d_behavior_v3_tuning.py
```

这一段的结论是：

- 15d 是最灵敏的窗口。
- `N<5` 的日子很多，但这并不等于信号错了，它更多反映的是市场状态确实在切换。
- 15d 上降仓不一定预测未来收益，但能降低风险暴露。

## 8. 2026 no-warmup 复盘

报告：[`2026_nowarmup_comprehensive_report.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/2026_nowarmup_comprehensive_report.md)

复现命令：

```bash
source activate.sh
python runs/etf_loop/run_2026_nowarmup.py
```

这份报告的价值在于把“为什么某些月份特别差”说清楚了。

结论非常直接：

- 亏损主要集中在半导体、创业板、纳指、原油、黄金等高 beta 热点轮动上。
- 6 月是最差月份，连续出现高位接力后快速止损。
- 这说明问题不是完全错过热点，而是热点切换太快时，策略在高位继续追同一批强势行业。

月度和逐笔复盘告诉我们，后续要重点防：

- 过热后继续追高。
- 买入后很快反转的热点切换。
- 只看 rank，不看接近阶段高位的风险。

## 9. 信号稳定性与压力测试

报告：

- [`signal_stability_report.md`](../outputs/etf_loop/signal_stability_report.md)
- [`multi_setting_pressure_report.md`](../outputs/etf_loop/multi_setting_pressure_report.md)

复现命令：

```bash
source activate.sh
python analysis/etf_loop/analyze_signal_stability.py
python runs/etf_loop/run_multi_setting_pressure_tests.py
```

这里补了两个关键问题：

- 信号是不是一抖就翻转。
- 执行成本和成交模式一变，策略会不会立刻崩。

结论是：

- Top1 和 Top2 的边际在某些日期很小，换仓风险真实存在。
- 成交模式变化对回撤和收益影响非常明显。
- adverse open、延迟成交、VWAP/close 这类扰动必须看，不能只看理想 next open。

## 10. 当前最可信的候选

这里不强行给一个单一冠军，而是按用途分层。

| 候选 | 定位 | 长周期年化 | 长周期 Sharpe | 长周期 DD | 2018 / 2022 / 2024 | 2026 nowarmup 年化 | 2026 nowarmup Sharpe | 2026 nowarmup DD | 备注 |
|---|---|---:|---:|---:|---|---:|---:|---:|---|
| `F2_CAP_MA60` | 当前 baseline | 30.54% | 1.54 | -18.45% | -14.07% / -3.22% / 27.87% | 93.34% | 3.35 | -15.61% | 适合作为主对照 |
| `Current` | 进攻型候选 | 39.81% | 1.57 | -25.44% | 5.26% / 2.81% / 11.32% | 144.20% | 3.60 | -19.00% | 收益优先时可用 |
| `WideA` | 防守型候选 | 37.12% | 1.62 | -19.66% | -0.62% / 31.21% / 29.58% | 115.15% | 3.39 | -16.33% | 更适合稳健实盘 |
| `Exph_v3_exp_looser` | 暴露拆分候选 | 27.33% | 1.51 | -17.30% | -9.31% / 14.53% / 31.20% | 81.43% | 3.20 | -18.57% | 最符合“弱市降仓但不压死分散度” |
| `20dRet + ScoreW` | 动态持仓候选 | 36.81% | 1.40 | -23.99% | — | 102.95% | 2.67 | -20.51% | 作为补充候选 |
| `DYNFUSE_F2v3_CAP1_W10_M05_H10P50` | 动态池补漏候选 | 29.70% | 1.41 | -22.43% | — | — | — | — | 只作为补漏，不做主仓位 |

注：`20dRet + ScoreW` 和 `DYNFUSE_F2v3_CAP1_W10_M05_H10P50` 的当前主报告没有单独给出 2018 / 2022 / 2024 的逐年拆分，所以这里先保留为 `—`。

### 推荐顺序

如果现在只保留少数实盘候选，我会按这个顺序看：

1. `F2_CAP_MA60` 作为稳定 baseline。
2. `Exph_v3_exp_looser` 作为最接近“风险暴露和持仓数分离”的候选。
3. `WideA` 作为更稳健的防守版。
4. `Current` 作为进攻版。
5. `DYNFUSE_F2v3_CAP1_W10_M05_H10P50` 作为动态池补漏版。

## 11. 已经明确不该再用的东西

这些不是“从未有用”，而是已经被修复版本和后续复审覆盖了：

- 信号日收盘价直接成交的旧结果。
- next open 失败时回退到历史 open 或 signal close 的结果。
- friend_mode 相关输出。
- 旧动态池单位未统一、部分成交分支有误的结果。
- 没有控制变量地混合改动的实验结论。

## 12. 复现顺序

如果别人要从头复现，我建议按下面顺序跑。

```bash
source activate.sh
python runs/etf_loop/run_etf_loop_hyperparam_ablation.py
python runs/etf_loop/run_benchmark_comparison.py
python runs/etf_loop/run_etf_loop_validation_suite.py
python runs/etf_loop/rerun_etf_loop_core.py
python runs/etf_loop/run_dynamic_fusion_experiments.py
python runs/etf_loop/run_adaptive_holdings_full.py
python runs/etf_loop/run_adaptive_holdings_reaudit.py
python runs/etf_loop/run_adaptive_sequence_v3.py
python runs/etf_loop/run_v3_attribution_tables.py
python runs/etf_loop/run_single_factor_followups_v1.py
python runs/etf_loop/run_15d_behavior_v3_tuning.py
python runs/etf_loop/run_2026_nowarmup.py
```

如果只想快速确认主线，先看这四个文件就够了：

- [`execution_fix_rerun_report.md`](../outputs/etf_loop/execution_fix_rerun_report.md)
- [`validation_suite_report.md`](../outputs/etf_loop/validation_suite_report.md)
- [`dynamic_fusion_capped_report.md`](../outputs/etf_loop/dynamic_fusion_capped_report.md)
- [`v3_multi_setting_diagnostics.md`](../outputs/etf_loop/F2_CAP_MA60_deep_dive/v3_multi_setting_diagnostics.md)

## 13. 结论

这个项目最终不是“找到一个永远最优的参数”，而是建立了一个可复现、可审计、可迭代的策略演化链：

- 先用静态 F2 系列打出稳定 baseline。
- 再把执行层修正到真实可成交。
- 再证明动态池只能做补漏，不能平权竞争。
- 再把动态持仓从“只改 N”推进到“暴露和数量拆分”。
- 最后通过 2026 逐月逐笔复盘，确认策略真正的痛点是追高杀低，而不是简单的池子不够大。
