# ETF Loop on Friend9 Pool

- window: `2020-01-01` to `2026-06-25`
- engine: our daily ETF Loop engine
- changed variable: static ETF pool is replaced by friend's original 9-ETF cross-asset pool
- signal/execution: T close signal, T+1 open execution; no signal-day price fallback
- cost: commission 1.5bp/side + slippage 2bp/side, roundtrip 7bp

## Reproduce

```bash
source activate.sh && python runs/etf_loop/run_etf_loop_friend9_pool.py --start 2020-01-01 --end 2026-06-25
```

## Results

| variant | N | ann | sharpe | DD | total | final | trades |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 1 | 31.93% | 1.16 | -21.45% | 472.57% | 2862870 | 731 |
| ma60 | 1 | 30.54% | 1.12 | -26.12% | 428.01% | 2640053 | 777 |
| widea | 1 | 24.87% | 1.29 | -25.13% | 315.91% | 2079539 | 1653 |
| base | 5 | 19.29% | 1.18 | -19.29% | 204.48% | 1522381 | 1822 |
| ma60 | 5 | 19.29% | 1.18 | -19.29% | 204.48% | 1522381 | 1822 |
| widea | 5 | 24.87% | 1.29 | -25.13% | 315.91% | 2079539 | 1653 |

## Notes

- This test does not use friend intraday 09:50 execution; it uses our daily engine.
- Compare with friend-style pool ablation separately: friend9 works especially well with same-day intraday Top1.