# ETF Loop 输出目录索引

这个目录已经分成两层：

- `archive/`：已经被后续报告覆盖、只留历史追溯的旧产物。
- `legacy_pre_execution_fix/`：旧结果归档，只用于追溯，不作为当前结论。
- `F2_CAP_MA60_deep_dive/`：当前主研究分支，包含 V3、动态持仓、复审、诊断。

## 建议阅读顺序

1. [`../../docs/etf_loop_project_history.md`](../../docs/etf_loop_project_history.md)
2. [`execution_fix_rerun_report.md`](./execution_fix_rerun_report.md)
3. [`validation_suite_report.md`](./validation_suite_report.md)
4. [`dynamic_fusion_capped_report.md`](./dynamic_fusion_capped_report.md)
5. [`F2_CAP_MA60_deep_dive/adaptive_holdings_reaudit_v1_report.md`](./F2_CAP_MA60_deep_dive/adaptive_holdings_reaudit_v1_report.md)
6. [`F2_CAP_MA60_deep_dive/adaptive_sequence_v3_report.md`](./F2_CAP_MA60_deep_dive/adaptive_sequence_v3_report.md)
7. [`F2_CAP_MA60_deep_dive/v3_multi_setting_diagnostics.md`](./F2_CAP_MA60_deep_dive/v3_multi_setting_diagnostics.md)
8. [`F2_CAP_MA60_deep_dive/single_factor_followups_v1_report.md`](./F2_CAP_MA60_deep_dive/single_factor_followups_v1_report.md)
9. [`F2_CAP_MA60_deep_dive/adaptive_15d_v3_tuning_report.md`](./F2_CAP_MA60_deep_dive/adaptive_15d_v3_tuning_report.md)

## 当前结论的来源

如果只看少数几个文件，就看这几个：

- `execution_fix_rerun_report.md`：先确认所有结果都在修复后的交易规则下。
- `validation_suite_report.md`：确认样本外、逐年、成本和容量。
- `dynamic_fusion_capped_report.md`：确认动态池只做补漏是否有效。
- `F2_CAP_MA60_deep_dive/adaptive_holdings_reaudit_v1_report.md`：确认动态持仓模式在当前引擎下是否还成立。
- `F2_CAP_MA60_deep_dive/v3_multi_setting_diagnostics.md`：确认 V3 的“总仓位”和“持仓数”拆分是否合理。
- `F2_CAP_MA60_deep_dive/single_factor_followups_v1_report.md`：确认单因素扰动不是混合改动。

## 归档说明

`archive/` 里放的是被后续报告覆盖的中间产物，例如早期动态持仓记录、早期实验日志、部分一次性分析脚本输出。

`legacy_pre_execution_fix/` 里的报告只适合做历史对照。凡是涉及：

- 信号日收盘价成交 fallback
- next open 不精确
- friend_mode 污染
- 旧动态池单位 / 旧部分成交逻辑

这些内容都应该以当前主线报告为准，不再回看旧结论。
