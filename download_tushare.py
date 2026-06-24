"""
从 tushare 拉取 A 股日线行情数据
用法: source activate.sh && python download_tushare.py

拉取范围:
  - 沪深 300 成分股 (当前 + 历史)
  - 2005-2025 日线数据
  - 输出: data/tushare_raw/all_stocks_day.csv
"""
import os, time, sys
sys.path.insert(0, '/Users/jingansun/Desktop/codex/quant/qlib')

import pandas as pd
import tushare as ts

# 读取 token (避免 set_token 写入 ~/ 目录的权限问题)
token_path = os.path.join(os.path.dirname(__file__), 'config', 'tushare_token.txt')
with open(token_path) as f:
    TOKEN = f.read().strip()

pro = ts.pro_api(token=TOKEN)

OUT_DIR = os.path.join(os.path.dirname(__file__), 'data', 'tushare_raw')
os.makedirs(OUT_DIR, exist_ok=True)

def get_csi300_stocks():
    """获取沪深300历史上所有成分股"""
    codes = set()
    # 每月拉取一次成分股名单，覆盖历史变化
    for year in range(2010, 2026):
        for month in ['01', '04', '07', '10']:
            try:
                df = pro.index_weight(
                    index_code='000300.SH',
                    trade_date=f'{year}{month}01'
                )
                if df is not None and not df.empty:
                    for code in df['con_code'].tolist():
                        codes.add(code)
            except Exception:
                pass
            time.sleep(0.3)  # API 频率限制
    return sorted(codes)

def download_daily(stock_list, start='20050101', end='20250620'):
    """下载所有股票的全部日线数据"""
    all_data = []
    total = len(stock_list)
    
    for i, code in enumerate(stock_list):
        try:
            # 分年拉取避免数据量过大
            for year in range(2005, 2026):
                start_d = f'{year}0101'
                end_d = f'{year}1231'
                if year == 2025:
                    end_d = '20250620'
                
                df = pro.daily(
                    ts_code=code,
                    start_date=start_d,
                    end_date=end_d,
                    fields='ts_code,trade_date,open,high,low,close,pre_close,vol,amount'
                )
                if df is not None and not df.empty:
                    all_data.append(df)
                time.sleep(0.4)  # tushare 免费接口每分钟 200 次
        except Exception as e:
            print(f'  ⚠ {code} 拉取失败: {e}')
        
        if (i + 1) % 50 == 0:
            print(f'  进度: {i+1}/{total}')
    
    if not all_data:
        print('没有拉到任何数据!')
        return None
    
    result = pd.concat(all_data, ignore_index=True)
    result['trade_date'] = result['trade_date'].astype(str)
    result = result.sort_values(['ts_code', 'trade_date']).drop_duplicates()
    return result

if __name__ == '__main__':
    print('获取沪深300成分股列表...')
    stocks = get_csi300_stocks()
    print(f'共 {len(stocks)} 只历史成分股')
    
    print('下载日线数据 (2005-2025)...')
    df = download_daily(stocks)
    
    if df is not None:
        out_path = os.path.join(OUT_DIR, 'all_stocks_day.csv')
        df.to_csv(out_path, index=False)
        size_mb = os.path.getsize(out_path) / 1024**2
        print(f'\n✓ 数据已保存: {out_path}')
        print(f'  文件大小: {size_mb:.1f} MB')
        print(f'  总行数: {len(df):,}')
        print(f'  股票数: {df["ts_code"].nunique()}')
        print(f'  日期范围: {df["trade_date"].min()} ~ {df["trade_date"].max()}')
        print(f'  样本预览:')
        print(df.head(5).to_string())

