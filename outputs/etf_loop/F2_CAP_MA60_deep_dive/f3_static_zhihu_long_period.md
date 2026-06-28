# F3 Static Zhihu Theme Pool Long-Period Backtest

- start: `2013-07-01`
- end: `2026-06-25`
- F3 definition: F2_v3 static pool union Zhihu theme ETF list
- isolation: new pool file and new experiment tags only; existing F2 files/reports are not overwritten

## Pool Construction
- F2 size: 44
- Zhihu list unique: 38
- Newly added vs F2: 31
- F3 total size: 75
- pool file: `data/tushare_cache/sector_prosperity/etf_pool_F3_static_zhihu.csv`

## Added Theme ETF Codes
| code | name | already_in_F2 |
|---|---|---:|
| 159206.SZ | 永赢国证商用卫星通信产业ETF | False |
| 159326.SZ | 华夏中证电网设备主题ETF | False |
| 159611.SZ | 广发中证全指电力公用事业ETF | False |
| 159732.SZ | 华夏国证消费电子主题ETF | False |
| 159745.SZ | 国泰中证全指建筑材料ETF | False |
| 159766.SZ | 富国中证旅游主题ETF | False |
| 159796.SZ | 汇添富中证电池主题ETF | False |
| 159819.SZ | 易方达中证人工智能主题ETF | False |
| 159825.SZ | 富国中证农业主题ETF | False |
| 159851.SZ | 华宝中证金融科技主题ETF | False |
| 159852.SZ | 嘉实中证软件服务ETF | False |
| 159865.SZ | 国泰中证畜牧养殖ETF | False |
| 159869.SZ | 华夏中证动漫游戏ETF | False |
| 159870.SZ | 鹏华中证细分化工产业主题ETF | True |
| 159928.SZ | 汇添富中证主要消费ETF | False |
| 159995.SZ | 华夏国证半导体芯片ETF | True |
| 159996.SZ | 国泰中证全指家用电器ETF | False |
| 512170.SH | 华宝中证医疗ETF | False |
| 512200.SH | 南方中证全指房地产ETF | False |
| 512400.SH | 南方中证申万有色金属ETF | True |
| 512480.SH | 国联安中证全指半导体产品与设备ETF | True |
| 512660.SH | 国泰中证军工ETF | False |
| 512690.SH | 鹏华中证酒ETF | False |
| 512800.SH | 华宝中证银行ETF | False |
| 512880.SH | 国泰中证全指证券公司ETF | True |
| 512980.SH | 广发中证传媒ETF | False |
| 513360.SH | 博时中证全球中国教育主题ETF(QDII) | False |
| 515210.SH | 国泰中证钢铁ETF | False |
| 515220.SH | 国泰中证煤炭ETF | False |
| 515790.SH | 华泰柏瑞中证光伏产业ETF | False |
| 515880.SH | 国泰中证全指通信设备ETF | True |
| 516160.SH | 南方中证新能源ETF | False |
| 516970.SH | 广发中证基建工程ETF | False |
| 560080.SH | 汇添富中证中药ETF | False |
| 560280.SH | 广发中证工程机械主题ETF | False |
| 561360.SH | 国泰中证油气产业ETF | False |
| 562500.SH | 华夏中证机器人ETF | True |
| 562800.SH | 嘉实中证稀有金属主题ETF | False |

## Results
| pool | variant | annual | sharpe | max_dd | total_return | final |
|---|---|---:|---:|---:|---:|---:|
| F2_CAP_MA60_Baseline | reference | 30.54% | 1.54 | -18.45% | 3465.56% | 17,827,823 |
| F2_STATIC_Baseline | reference | 28.59% | 1.48 | -17.39% | 2723.31% | 14,116,550 |
| F3_STATIC_ZHIHU | Baseline | 23.39% | 1.11 | -26.27% | 1313.27% | 7,066,366 |
| F3_STATIC_ZHIHU | Premiumsoft | 23.00% | 1.09 | -25.47% | 1246.08% | 6,730,386 |
| F3_STATIC_ZHIHU | Premiumsoft_VolW | 20.53% | 1.08 | -20.90% | 937.66% | 5,188,304 |
| ORIG38_STATIC_Baseline | reference | 22.34% | 1.46 | -16.43% | 1312.18% | 7,060,913 |