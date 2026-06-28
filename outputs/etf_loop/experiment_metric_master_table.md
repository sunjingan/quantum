# ETF Loop 实验指标总表

生成日期：2026-06-28

## 口径说明

- 默认排除 `outputs/etf_loop/legacy_pre_execution_fix` 中的旧结果。
- 年化、Sharpe、最大回撤优先读取各实验 `summary.csv`。
- 胜率统一为“日度净值收益率 > 0 的交易日占比”；如果 summary 自带 `win_rate` 则直接使用。
- 分钟执行表里的年化/Sharpe/DD 是执行层压力测试结果，不等同于日线信号回测。
- 全量机器可读表见 `outputs/etf_loop/experiment_metric_master_table.csv`。

## 核心/关键日线实验表

|Setting|Start|End|年化|CAGR|Sharpe|最大DD|日胜率|总收益|最终权益|交易/调仓|订单数|均滑点bp|容量受限|仓位偏离|来源|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|SEQ_LONG_2013_2026_WideA|2013-07-01|2026-06-25|37.12%||1.62|-19.66%|52.60%|7372.70%|37363494||||||etf_loop_summary_SEQ_LONG_2013_2026_WideA_h5_20130701_20260625.csv|
|POSMGT_FIX1_LONG_2013_2026_DynHold___ScoreW|2013-07-01|2026-06-25|35.86%||1.39|-31.03%|55.23%|5744.58%|29222876||||||etf_loop_summary_POSMGT_FIX1_LONG_2013_2026_DynHold___ScoreW_h5_20130701_20260625.csv|
|V3EXP_Exp+Hold分离|2013-07-01|2026-06-25|35.27%||1.65|-19.88%|53.49%|6073.31%|30866555||||||etf_loop_summary_V3EXP_Exp+Hold分离_h5_20130701_20260625.csv|
|V3EXP_Exp+Hold分离+禁N=|2013-07-01|2026-06-25|35.27%||1.65|-19.88%|53.49%|6073.31%|30866555||||||etf_loop_summary_V3EXP_Exp+Hold分离+禁N=_h5_20130701_20260625.csv|
|FINAL3_A15_Wide B_SW|2013-07-01|2026-06-25|34.79%||1.42|-24.29%|55.46%|5224.45%|26622270||||||etf_loop_summary_FINAL3_A15_Wide B_SW_h5_20130701_20260625.csv|
|SF_WIDEA_RET_TIGHTER|2013-07-01|2026-06-25|33.73%||1.47|-26.14%|50.86%|4785.56%|24427802||||||etf_loop_summary_SF_WIDEA_RET_TIGHTER_h5_20130701_20260625.csv|
|LONGRUN_Exph_v3|2013-07-01|2026-06-25|33.42%|||-20.16%|||18443203||||||etf_loop_summary_LONGRUN_Exph_v3_h5_20130701_20260625.csv|
|ADAPT_REAUDIT_LONG_2013_2026_MA60_scorew_thresh01|2013-07-01|2026-06-25|33.39%||1.29|-29.44%|54.12%|4186.83%|21434138||||||etf_loop_summary_ADAPT_REAUDIT_LONG_2013_2026_MA60_scorew_thresh01_h5_20130701_20260625.csv|
|SEQ_LONG_2013_2026_WideB|2013-07-01|2026-06-25|32.81%||1.52|-21.80%|53.74%|4418.03%|22590142||||||etf_loop_summary_SEQ_LONG_2013_2026_WideB_h5_20130701_20260625.csv|
|LONGRUN_F2_CAP_MA60_Baseline|2013-07-01|2026-06-25|31.53%||1.59|-18.34%|57.58%|3928.67%|20143336||||||etf_loop_summary_LONGRUN_F2_CAP_MA60_Baseline_h5_20130701_20260625.csv|
|LONGPERIOD_F2_CAP_MA60_Baseline|2013-07-01|2026-06-25|31.53%||1.59|-18.34%|57.58%|3928.67%|20143336||||||etf_loop_summary_LONGPERIOD_F2_CAP_MA60_Baseline_h5_20130701_20260625.csv|
|LONGRUN_F2_STATIC_BASE_Baseline|2013-07-01|2026-06-25|29.99%||1.54|-18.36%|57.77%|3249.76%|16748780||||||etf_loop_summary_LONGRUN_F2_STATIC_BASE_Baseline_h5_20130701_20260625.csv|
|DYNFUSE_F2v3_CAP1_W10_M05_H10P50|2013-07-01|2026-06-25|29.70%||1.41|-22.43%|56.73%|3003.21%|15516027||||||etf_loop_summary_DYNFUSE_F2v3_CAP1_W10_M05_H10P50_h5_20130701_20260625.csv|
|DYNFUSE_F2v3_CAP1_W20_M10_H10P50|2013-07-01|2026-06-25|29.69%||1.41|-22.94%|56.38%|2997.68%|15488393||||||etf_loop_summary_DYNFUSE_F2v3_CAP1_W20_M10_H10P50_h5_20130701_20260625.csv|
|DYNFUSE_F2v3_CAP1_W20_M05_H10P50|2013-07-01|2026-06-25|29.63%||1.40|-22.94%|56.41%|2975.57%|15377827||||||etf_loop_summary_DYNFUSE_F2v3_CAP1_W20_M05_H10P50_h5_20130701_20260625.csv|
|DYNFUSE_F2v3_CAP1_W20_M05|2013-07-01|2026-06-25|29.44%||1.39|-23.86%|56.57%|2889.92%|14949622||||||etf_loop_summary_DYNFUSE_F2v3_CAP1_W20_M05_h5_20130701_20260625.csv|
|DYNFUSE_F2v3_CAP1_W20_M00|2013-07-01|2026-06-25|29.31%||1.38|-23.86%|56.60%|2844.76%|14723803||||||etf_loop_summary_DYNFUSE_F2v3_CAP1_W20_M00_h5_20130701_20260625.csv|
|FINAL13_F2v3|2013-07-01|2026-06-25|28.72%||1.41|-25.10%|56.95%|2691.98%|13959908||||||etf_loop_summary_FINAL13_F2v3_h5_20130701_20260625.csv|
|DYNFUSE_F2v3_CAP2_W20_M05_H15P50|2013-07-01|2026-06-25|28.09%||1.31|-24.20%|56.28%|2417.05%|12585263||||||etf_loop_summary_DYNFUSE_F2v3_CAP2_W20_M05_H15P50_h5_20130701_20260625.csv|
|SEQ_LONG_2013_2026_Exph_v4_smoother|2013-07-01|2026-06-25|26.94%||1.45|-17.65%|53.39%|2237.49%|11687466||||||etf_loop_summary_SEQ_LONG_2013_2026_Exph_v4_smoother_h5_20130701_20260625.csv|
|FINAL13_F2v3_ORIG38|2013-07-01|2026-06-25|26.84%||1.36|-19.75%|54.92%|2143.79%|11218953||||||etf_loop_summary_FINAL13_F2v3_ORIG38_h5_20130701_20260625.csv|
|FINAL13_POOL19|2013-07-01|2026-06-25|26.66%||1.56|-28.90%|52.70%|2234.01%|11670051||||||etf_loop_summary_FINAL13_POOL19_h5_20130701_20260625.csv|
|DYNFUSE_F2v3_ORIG38_CAP1_W20_M10_H10P50|2013-07-01|2026-06-25|26.58%||1.29|-22.32%|54.38%|2030.28%|10651376||||||etf_loop_summary_DYNFUSE_F2v3_ORIG38_CAP1_W20_M10_H10P50_h5_20130701_20260625.csv|
|DYNFUSE_F2v3_ORIG38_CAP1_W20_M05_H10P50|2013-07-01|2026-06-25|26.57%||1.29|-22.32%|54.47%|2029.85%|10649229||||||etf_loop_summary_DYNFUSE_F2v3_ORIG38_CAP1_W20_M05_H10P50_h5_20130701_20260625.csv|
|DYNFUSE_F2v3_ORIG38_CAP1_W20_M00|2013-07-01|2026-06-25|26.47%||1.28|-22.32%|54.44%|2000.12%|10500576||||||etf_loop_summary_DYNFUSE_F2v3_ORIG38_CAP1_W20_M00_h5_20130701_20260625.csv|
|DYNFUSE_F2v3_ORIG38_CAP1_W20_M05|2013-07-01|2026-06-25|26.45%||1.28|-22.32%|54.57%|1992.91%|10464526||||||etf_loop_summary_DYNFUSE_F2v3_ORIG38_CAP1_W20_M05_h5_20130701_20260625.csv|
|FINAL13_F2v3_G2PIT|2013-07-01|2026-06-25|26.40%||1.25|-23.21%|56.15%|1950.47%|10252364||||||etf_loop_summary_FINAL13_F2v3_G2PIT_h5_20130701_20260625.csv|
|DYNFUSE_F2v3_ORIG38_CAP1_W10_M05_H10P50|2013-07-01|2026-06-25|26.31%||1.29|-20.35%|54.73%|1969.30%|10346476||||||etf_loop_summary_DYNFUSE_F2v3_ORIG38_CAP1_W10_M05_H10P50_h5_20130701_20260625.csv|
|SEQ_LONG_2013_2026_Exph_v3|2013-07-01|2026-06-25|26.14%||1.47|-17.53%|53.33%|2057.99%|10789967||||||etf_loop_summary_SEQ_LONG_2013_2026_Exph_v3_h5_20130701_20260625.csv|
|SEQ_LONG_2013_2026_Exph_base|2013-07-01|2026-06-25|26.07%||1.43|-18.29%|53.49%|2014.62%|10573093||||||etf_loop_summary_SEQ_LONG_2013_2026_Exph_base_h5_20130701_20260625.csv|
|FINAL13_F2v3_ORIG38_G2PIT|2013-07-01|2026-06-25|25.30%||1.22|-21.60%|54.19%|1705.75%|9028767||||||etf_loop_summary_FINAL13_F2v3_ORIG38_G2PIT_h5_20130701_20260625.csv|
|DYNFUSE_F2v3_ORIG38_CAP2_W20_M05_H15P50|2013-07-01|2026-06-25|25.12%||1.22|-21.07%|54.03%|1673.40%|8866998||||||etf_loop_summary_DYNFUSE_F2v3_ORIG38_CAP2_W20_M05_H15P50_h5_20130701_20260625.csv|
|SEQ_LONG_2013_2026_Exph_v6_very_high_div|2013-07-01|2026-06-25|24.96%||1.42|-18.26%|52.95%|1768.47%|9342331||||||etf_loop_summary_SEQ_LONG_2013_2026_Exph_v6_very_high_div_h5_20130701_20260625.csv|
|SEQ_LONG_2013_2026_Exph_v5_div_lowbear|2013-07-01|2026-06-25|23.46%||1.37|-17.29%|53.01%|1462.36%|7811795||||||etf_loop_summary_SEQ_LONG_2013_2026_Exph_v5_div_lowbear_h5_20130701_20260625.csv|
|SEQ_LONG_2013_2026_Exph_v2_lower_bear|2013-07-01|2026-06-25|23.37%||1.33|-19.29%|53.30%|1433.75%|7668726||||||etf_loop_summary_SEQ_LONG_2013_2026_Exph_v2_lower_bear_h5_20130701_20260625.csv|
|FINAL13_ORIG38_G2PIT|2013-07-01|2026-06-25|22.93%||1.21|-19.11%|55.77%|1303.62%|7018123||||||etf_loop_summary_FINAL13_ORIG38_G2PIT_h5_20130701_20260625.csv|
|FINAL13_ORIG38|2013-07-01|2026-06-25|22.26%||1.42|-15.15%|56.60%|1286.04%|6930202||||||etf_loop_summary_FINAL13_ORIG38_h5_20130701_20260625.csv|
|FINAL13_G2PIT|2013-07-01|2026-06-25|11.08%||0.68|-25.95%|32.93%|237.90%|1689493||||||etf_loop_summary_FINAL13_G2PIT_h5_20130701_20260625.csv|

## 分钟执行关键表

|Setting|Start|End|年化|CAGR|Sharpe|最大DD|日胜率|总收益|最终权益|交易/调仓|订单数|均滑点bp|容量受限|仓位偏离|来源|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|WideA_tiered_long_50k_exec_modes | execution_mode=twap_1000_1430|2013-07-01|2026-06-25|25.93%|26.69%|1.22|-36.69%||1783.30%|941652||12315|3.28|0.99%|3.67%|minute_execution_summary_WideA_tiered_long_50k_exec_modes_20130701_20260625.csv|
|WideA_tiered_long_50k_exec_modes | execution_mode=split_0935_1455|2013-07-01|2026-06-25|25.33%|25.99%|1.20|-34.32%||1657.29%|878643||12288|3.69|1.60%|3.98%|minute_execution_summary_WideA_tiered_long_50k_exec_modes_20130701_20260625.csv|
|WideA_tiered_long_50k_exec_modes | execution_mode=tail_vwap_1430_1455|2013-07-01|2026-06-25|23.82%|23.99%|1.11|-33.18%||1340.97%|720483||12710|5.69|6.66%|5.53%|minute_execution_summary_WideA_tiered_long_50k_exec_modes_20130701_20260625.csv|
|WideA_sqrt_k40_long_50k_all_penalties | execution_mode=twap_1000_1430|2013-07-01|2026-06-25|23.18%|23.26%|1.09|-37.01%||1239.85%|669926||12287|5.73|0.92%|3.65%|minute_execution_summary_WideA_sqrt_k40_long_50k_all_penalties_20130701_20260625.csv|
|WideA_tiered_long_50k_exec_modes | execution_mode=twap_0935_1030|2013-07-01|2026-06-25|22.86%|22.99%|1.10|-34.78%||1203.62%|651811||12406|4.14|2.59%|4.54%|minute_execution_summary_WideA_tiered_long_50k_exec_modes_20130701_20260625.csv|
|WideA_tiered_long_50k_exec_modes | execution_mode=vwap_0935_1030|2013-07-01|2026-06-25|22.71%|22.79%|1.09|-35.14%||1177.79%|638894||12397|4.11|2.52%|4.55%|minute_execution_summary_WideA_tiered_long_50k_exec_modes_20130701_20260625.csv|
|WideA_sqrt_k40_long_50k_all_penalties | execution_mode=tail_vwap_1430_1455|2013-07-01|2026-06-25|21.76%|21.45%|1.01|-33.55%||1015.46%|557731||12696|8.21|6.51%|5.47%|minute_execution_summary_WideA_sqrt_k40_long_50k_all_penalties_20130701_20260625.csv|
|WideA_sqrt_k40_long_50k_all_penalties | execution_mode=split_0935_1455|2013-07-01|2026-06-25|20.06%|19.52%|0.95|-36.30%||813.93%|456967||12212|8.30|1.37%|3.84%|minute_execution_summary_WideA_sqrt_k40_long_50k_all_penalties_20130701_20260625.csv|
|WideA_tiered_long_50k_exec_modes | execution_mode=t2_open_0935|2013-07-01|2026-06-25|18.41%|16.88%|0.75|-37.28%||592.52%|346259||14894|10.51|22.62%|14.16%|minute_execution_summary_WideA_tiered_long_50k_exec_modes_20130701_20260625.csv|
|WideA | execution_mode=vwap_0935_1030|2013-07-01|2026-06-25|17.79%|17.07%|0.88|-32.13%||607.09%|7070927||13971|8.39|19.08%|8.33%|minute_execution_summary_WideA_20130701_20260625.csv|
|WideA_sqrt_k40_long_50k_all_penalties | execution_mode=vwap_0935_1030|2013-07-01|2026-06-25|17.35%|16.39%|0.83|-40.54%||557.60%|328800||12247|8.83|2.29%|4.50%|minute_execution_summary_WideA_sqrt_k40_long_50k_all_penalties_20130701_20260625.csv|
|F2_CAP_MA60 | execution_mode=vwap_0935_1030|2013-07-01|2026-06-25|16.43%|15.67%|0.85|-32.26%||509.06%|6090589||17478|7.30|15.44%|5.93%|minute_execution_summary_F2_CAP_MA60_20130701_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2013-07-01|2026-06-25|16.12%|15.72%|0.92|-32.13%||511.86%|6118579||15324|7.40|15.87%|6.38%|minute_execution_summary_Exph_v3_exp_looser_20130701_20260625.csv|
|WideA_tiered_long_50k_exec_modes | execution_mode=open_0935|2013-07-01|2026-06-25|15.77%|14.86%|0.81|-31.83%||457.98%|278988||14302|9.94|19.93%|12.50%|minute_execution_summary_WideA_tiered_long_50k_exec_modes_20130701_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|85.46%|127.43%|3.38|-10.29%||42.21%|1440011||597|1.08|0.00%|13.05%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|84.54%|125.35%|3.35|-10.34%||41.65%|1434193||594|2.06|0.00%|13.04%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|84.52%|125.29%|3.34|-10.31%||41.64%|4302557||592|1.57|0.00%|13.06%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|83.65%|123.35%|3.31|-10.36%||41.11%|4286221||590|2.48|0.00%|13.07%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|83.53%|123.07%|3.30|-10.35%||41.04%|7140602||589|2.08|0.00%|13.07%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|83.02%|121.92%|3.28|-10.41%||40.73%|14249607||589|3.01|0.17%|13.04%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|83.00%|121.89%|3.28|-10.42%||40.72%|1424517||594|3.54|0.00%|13.05%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|82.75%|121.35%|3.27|-10.39%||40.57%|7116249||592|2.93|0.00%|13.08%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|82.42%|120.60%|3.25|-10.44%||40.36%|14211596||592|3.78|0.17%|13.04%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|82.34%|120.44%|3.25|-10.43%||40.32%|4261559||594|3.83|0.00%|13.08%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|81.62%|118.86%|3.23|-10.45%||39.89%|7080680||592|4.21|0.00%|13.09%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|81.48%|118.53%|3.21|-10.50%||39.80%|14152281||592|4.95|0.17%|13.04%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|80.38%|116.16%|3.17|-10.55%||39.15%|1408271||593|6.01|0.00%|13.07%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|WideA_tiered_50k_exec_modes | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|80.07%|111.84%|2.55|-13.19%||37.95%|69822||495|2.00|0.00%|9.70%|minute_execution_summary_WideA_tiered_50k_exec_modes_20251001_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|80.03%|115.41%|3.16|-10.55%||38.94%|4218532||589|6.15|0.00%|13.09%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|WideA_sqrt_k20_50k_sqrt20 | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|79.91%|111.49%|2.54|-13.19%||37.85%|69773||499|2.11|0.00%|9.70%|minute_execution_summary_WideA_sqrt_k20_50k_sqrt20_20251001_20260625.csv|
|WideA_sqrt_k40_50k_sqrt40 | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|79.77%|111.21%|2.54|-13.20%||37.77%|69732||501|2.22|0.00%|9.71%|minute_execution_summary_WideA_sqrt_k40_50k_sqrt40_20251001_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|79.77%|114.82%|3.14|-10.59%||38.78%|14045326||587|6.97|0.17%|13.05%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|79.54%|114.35%|3.14|-10.56%||38.65%|7016068||589|6.41|0.00%|13.09%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|WideA_sqrt_k60_50k_sqrt60 | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|79.53%|110.68%|2.53|-13.22%||37.62%|69657||505|2.32|0.00%|9.70%|minute_execution_summary_WideA_sqrt_k60_50k_sqrt60_20251001_20260625.csv|
|WideA_sqrt_k40_50k_commodity_only | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|79.29%|110.19%|2.52|-13.22%||37.49%|69588||506|2.33|0.00%|9.70%|minute_execution_summary_WideA_sqrt_k40_50k_commodity_only_20251001_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|79.18%|113.53%|3.11|-10.66%||38.42%|42022597||596|5.70|2.85%|13.10%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|WideA_sqrt_k40_50k_cross_only | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|79.03%|109.63%|2.51|-13.23%||37.33%|69508||503|2.51|0.00%|9.68%|minute_execution_summary_WideA_sqrt_k40_50k_cross_only_20251001_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|78.87%|112.88%|3.10|-10.67%||38.24%|41966210||595|6.31|2.86%|13.10%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|Exph_v3_exp_looser | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|78.42%|111.91%|3.08|-10.70%||37.97%|41883248||597|7.18|2.85%|13.10%|minute_execution_summary_Exph_v3_exp_looser_20251001_20260625.csv|
|WideA | execution_mode=vwap_0935_1030|2025-10-01|2026-06-25|77.92%|107.28%|2.47|-13.18%||36.67%|1383887||529|1.35|0.00%|9.10%|minute_execution_summary_WideA_20251001_20260625.csv|

## 全量表位置

- CSV: `outputs/etf_loop/experiment_metric_master_table.csv`
- Markdown: `outputs/etf_loop/experiment_metric_master_table.md`
- 全量行数: `1299`