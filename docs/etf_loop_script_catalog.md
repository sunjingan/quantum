# ETF Loop 脚本目录索引

目的不是把所有脚本都展开，而是把“当前还值得继续跑”的入口和“历史/一次性分析”的入口分开，避免混乱。

运行入口总览见 [`runs/etf_loop/README.md`](../runs/etf_loop/README.md)，分析脚本总览见 [`analysis/etf_loop/README.md`](../analysis/etf_loop/README.md)，数据准备总览见 [`tools/data_prep/README.md`](../tools/data_prep/README.md)。

## 1. 当前主入口

### 策略与引擎

- `strategies/etf_loop_engine.py`：主回测引擎，信号、选池、执行、止损、仓位管理都在这里。
- `strategies/etf_loop_strategy.py`：策略定义和参数入口。
- `strategies/etf_loop_experiments.py`：实验配置与组合入口。

### 当前关键实验脚本

- `runs/etf_loop/run_adaptive_sequence_v3.py`：V3 主线，窗口扫描、阈值、WideA/WideB、exp/hold split。
- `runs/etf_loop/run_v3_attribution_tables.py`：V3 三张诊断表，逐年收益 / N 分布 / 最大回撤路径。
- `runs/etf_loop/run_single_factor_followups_v1.py`：单因素扰动，保证“只改一个轴”。
- `runs/etf_loop/run_15d_behavior_v3_tuning.py`：15d 主窗口下的行为诊断和局部精调。
- `runs/etf_loop/run_adaptive_holdings_reaudit.py`：动态持仓模式重审，确保旧结论在当前引擎下仍成立。
- `runs/etf_loop/run_adaptive_holdings_full.py`：动态持仓全量测试入口。
- `runs/etf_loop/run_dynamic_fusion_experiments.py`：动态池 capped 补漏实验。
- `runs/etf_loop/run_etf_loop_validation_suite.py`：固定样本外、逐年、成本/容量验证。
- `runs/etf_loop/run_2026_nowarmup.py`：2026 nowarmup 主回测入口。
- `runs/etf_loop/run_adjusted_core_setting_comparison.py`：调整后核心设置对比。
- `runs/etf_loop/run_benchmark_comparison.py`：基准对比。
- `runs/etf_loop/run_multi_setting_pressure_tests.py`：压力测试总入口。
- `runs/etf_loop/run_execution_mode_experiments.py`：成交价模式 / 延迟模式实验。
- `runs/etf_loop/run_detailed_trade_log.py`：对指定候选策略生成回测内原生日志，包括每日账户、每日持仓、TopN 信号快照和下一交易日操作建议。
- `runs/etf_loop/run_minute_execution_backtest.py`：独立分钟级执行层回测，复用日线候选信号，测试 T+1 09:35-10:30 VWAP/TWAP、尾盘 VWAP、T+2、容量、参与率、涨跌停和 actual exposure。
- `runs/etf_loop/run_friend_intraday_replication.py`：使用本地 ETF 1 分钟/5 分钟数据复现 friend 9-ETF 单仓策略，测试 09:50 信号和不同 T+0/T+1 成交假设。
- `runs/etf_loop/run_friend_f2pit_strategy.py`：独立 friend-style 优化实验，使用 friend 的 09:50 加权回归动量思想，但替换为 F2_v3 静态核心池 + G2 PIT 动态池，并加入成本、滑点、溢价惩罚、动态池过热惩罚和止损等风控；不修改主 ETF Loop 策略。

## 2. 结果分析脚本

- `analysis/etf_loop/analyze_dynamic_pool_impact.py`：动态池拖累归因。
- `analysis/etf_loop/analyze_dynamic_fusion_experiment_results.py`：dynamic fusion 结果汇总。
- `analysis/etf_loop/analyze_etf_loop_deep_dive.py`：逐月/逐笔深挖。
- `analysis/etf_loop/analyze_2026_nowarmup_monthly_attribution.py`：2026 月度归因。
- `analysis/etf_loop/analyze_annual_monthly.py`：年度/月度统计。
- `analysis/etf_loop/analyze_signal_stability.py`：信号稳定性。
- `analysis/etf_loop/analyze_f2_cap_ma60_deep_dive.py`：F2_CAP_MA60 深挖。
- `analysis/etf_loop/analyze_f2_cap_ma60_charts.py`：图表生成。
- `analysis/etf_loop/analyze_2026_comprehensive.py`、`analysis/etf_loop/analyze_2026_deep.py`：2026 综合/深度分析。
- `analysis/etf_loop/analyze_etf_loop_attribution.py`：ETF 轮动归因。
- `analysis/etf_loop/visualize_etf_trade_points.py`：交易点可视化。
- `analysis/etf_loop/reconcile_paper_vs_backtest.py`：模拟盘/实盘与回测对账。

## 3. 数据准备

- `tools/data_prep/download_benchmarks.py`：下载宽基基准。
- `tools/data_prep/download_a_share_10y.py`：A 股历史数据下载。
- `tools/data_prep/download_tushare.py`：Tushare 相关下载。
- `tools/data_prep/prefetch_enrichment.py`、`tools/data_prep/prefetch_theme_etf_data.py`、`tools/data_prep/prefetch_fundamental.py`：本地缓存预热脚本。
- `run_qlib.sh`：Qlib 环境入口。

## 4. 低优先级或历史入口

这些脚本不是“删掉”，但默认不再作为主线实验入口。已归档脚本放在 `archive/etf_loop/`：

- `archive/etf_loop/run_experiments_v2.py`
- `archive/etf_loop/run_research.py`
- `archive/etf_loop/run_long_period_optimization_compare.py`
- `archive/etf_loop/run_position_mgmt_experiments.py`
- `archive/etf_loop/run_filtered_dynamic_observation_experiments.py`
- `archive/etf_loop/run_theme_etf_experiments.py`
- `archive/etf_loop/run_wyckoff_prefilter_tests.py`
- `archive/etf_loop/run_wyckoff_v2_tests.py`
- `archive/etf_loop/run_permanent_hold_experiments.py`
- `archive/etf_loop/run_static_pool_2026_charts.py`
- `archive/etf_loop/replicate_friend_baseline.py`
- `archive/etf_loop/replicate_friend_strategy.py`

仍留在主线根目录、但属于辅助实验的脚本：

- `runs/etf_loop/run_cost_stress_f2_cap_ma60.py`
- `runs/etf_loop/run_cost_stress_f2_cap_ma60_tiers.py`
- `runs/etf_loop/run_adjusted_core_setting_comparison.py`

## 5. 建议的日常使用顺序

1. 先看 `docs/etf_loop_research_index.md`。
2. 需要总览时，先跑 `runs/etf_loop/run_adaptive_sequence_v3.py` 和 `runs/etf_loop/run_v3_attribution_tables.py`。
3. 只改一件事时，用 `runs/etf_loop/run_single_factor_followups_v1.py`。
4. 要确认候选是否还能上实盘，跑 `runs/etf_loop/run_etf_loop_validation_suite.py`。
5. 要看动态池、动态持仓是否真的有效，分别看 `runs/etf_loop/run_dynamic_fusion_experiments.py` 和 `runs/etf_loop/run_adaptive_holdings_reaudit.py`。
