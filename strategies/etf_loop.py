# 克隆自聚宽文章：https://www.joinquant.com/post/74852
# 标题：分享个策略，从大神处克隆稍改一下，搞了半年
# 作者：zadebg124

# 克隆自聚宽文章：https://www.joinquant.com/post/66703
# 标题：七星高照ETF轮动策略-V1.2（微调版）
# 作者：九条命

import numpy as np
import math
import pandas as pd
from jqdata import *

def initialize(context):
    """
    初始化函数
    """
    # ==================== 实盘交易设置 ====================
    set_option("avoid_future_data", True)
    set_option("use_real_price", True)
    
    # 设置滑点
    set_slippage(PriceRelatedSlippage(0.0001), type="fund")
    
    # 设置交易成本:ETF交易成本较低
    set_order_cost(
        OrderCost(
            open_tax=0,
            close_tax=0,
            open_commission=0.00005,
            close_commission=0.00005,
            close_today_commission=0,
            min_commission=0.01,
        ),
        type="fund",
    )

    # 设置日志级别
    log.set_level('order', 'error')
    log.set_level('system', 'error')
    log.set_level('strategy', 'debug')
    
    log.info("增强版策略初始化完成！")
    # 设置参考基准
    set_benchmark("000300.XSHG")  
    # ==================== ETF池设置 ====================
    g.etf_pool = [
        # 大宗商品ETF
        "518880.XSHG",  # 黄金ETF
        "159985.XSHE",  # 豆粕ETF（跟踪豆粕期货价格）
        "501018.XSHG",  # 南方原油（投资原油相关资产）
        # "161226.XSHE",  # 白银LOF
        # 国际ETF
        "513100.XSHG",  # 纳指ETF
        #"159941.XSHE",  # 纳指ETF
        # 中国ETF
        "159915.XSHE",  # 创业板ETF
        # 债券ETF
        "511220.XSHG",  # 城投债ETF
        # 防御ETF
        #"511880.XSHG" ,  # 货币基金ETF
    ]
    
    # 大ETF池
    g.etf_pool_bak  = [
        # 大宗商品ETF
        "518880.XSHG",  # 黄金ETF
        "159980.XSHE",  # 有色ETF（跟踪有色金属板块）
        "159985.XSHE",  # 豆粕ETF（跟踪豆粕期货价格）
        "501018.XSHG",  # 南方原油（投资原油相关资产）
        '161226.XSHE',  # 白银LOF
        "159981.XSHE",  # 能源化工ETF
        # 国际ETF
        "513100.XSHG",  # 纳指ETF
    
        "513500.XSHG",  # 标普500ETF
    
        "513400.XSHG",  # 道琼斯ETF
        "513520.XSHG",  # 日经225ETF

        "513310.XSHG",  # 中韩半导体ETF
        "513730.XSHG",  # 东南亚ETF
        # 香港ETF
        "159792.XSHE",  # 港股互联ETF
        "513130.XSHG",  # 恒生科技
        "513050.XSHG",  # 中概互联网ETF
        "159920.XSHE",  # 恒生ETF
        "513690.XSHG",  # 港股红利
        # 指数ETF
        "510300.XSHG",  # 沪深300ETF
        "510500.XSHG",  # 中证500ETF
    
        "159915.XSHE",  # 创业板ETF
        "588080.XSHG",  # 科创50
        "512100.XSHG",  # 中证1000ETF
        "563360.XSHG",  # A500-ETF
        "563300.XSHG",  # 中证2000ETF
        # 风格ETF
        "512890.XSHG",  # 红利低波ETF
        "159583.XSHE",  # 通信ETF
        "512040.XSHG",  # 价值ETF
        "159201.XSHE",  # 自由现金流ETF
        "159516.XSHE",  # 半导体设备ETF
        "159326.XSHE",  # 电网设备ETF
        "159611.XSHE",  # 电力ETF
        "159206.XSHE",  # 卫星ETF
        "159530.XSHE",  # 机器人ETF
        "516310.XSHG",  # 银行ETF
        # # 债券ETF
        "511380.XSHG",  # 可转债ETF
        "511010.XSHG",  # 国债ETF
        "511220.XSHG",  # 城投债ETF
        "511880.XSHG",  # 防御性ETF（货币ETF）
    ]
    g.etf_pool =g.etf_pool_bak   #启用完整大池
    '''这里修改过，注释一下'''
    # ==================== 核心策略参数 ====================
    # 动量计算参数
    g.lookback_days = 25  # 长期动量计算周期
    g.holdings_num = 2 # 持仓ETF数量,原作1
    g.defensive_etf = None   # 防御性ETF（货币ETF）
    g.min_money = 5000  # 最小交易金额
    
    # 风险控制参数
    g.stop_loss = 0.95    # 固定百分比止损线（下跌5%止损）
    g.loss = 0.97   # 近3日跌幅止损线
    
    # 得分阈值
    g.min_score_threshold = 0  # 最低得分阈值
    g.max_score_threshold = 500.0  # 最高得分阈值
    
    # ==================== 成交量过滤参数 ====================
    g.enable_volume_check = True  # 是否启用成交量过滤
    g.volume_lookback = 5  # 成交量历史参考天数
    g.volume_threshold = 2  # 放量阈值（大于设定值视为放量）
    g.volume_return_limit = 1  # 年化收益率过滤：当高于该值，则启用成交量过滤，回看天数和计算动量时一致
    
    # ==================== 新增：均线过滤参数（参考策略1） ====================
    g.enable_ma_filter = False  # 是否启用均线过滤，原作False
    '''这里修改过，注释一下,实际回测没有任何作用'''
    g.ma_filter_days = 20  # 均线过滤天数
    
    # ==================== 原有：短期动量过滤参数 ====================
    g.use_short_momentum_filter = True  # 是否启用短期动量过滤
    g.short_lookback_days = 10  # 短期动量计算周期
    g.short_momentum_threshold = 0.0  # 短期动量阈值
    
    # ==================== 原有：ATR动态止损参数 ====================
    g.use_atr_stop_loss = True  # 是否启用ATR动态止损,原作False
    '''这里修改过，注释一下'''
    g.atr_period = 14  # ATR计算周期
    g.atr_multiplier = 2  # ATR倍数
    g.atr_trailing_stop = False  # 是否使用跟踪止损
    g.atr_exclude_defensive = True  # 防御ETF是否豁免ATR止损
    
    # ==================== 原有：RSI过滤参数 ====================
    g.use_rsi_filter = True  # 是否启用RSI过滤
    g.rsi_period = 6  # RSI计算周期
    g.rsi_lookback_days = 1  # 检查RSI的历史天数
    g.rsi_threshold = 98  # RSI阈值
    
    # ==================== 持仓管理 ====================
    g.positions = {}  # 记录持仓
    g.position_highs = {}  # 记录持仓期间的最高价
    g.position_stop_prices = {}  # 记录持仓的ATR止损价
    
    # ==================== 交易调度 ====================
    # 每天开盘后检查持仓
    run_daily(check_positions, time='09:10')
    # 每天开盘后检查ATR动态止损
    run_daily(check_atr_stop_loss, time='10:31')
    # 执行卖出操作
    run_daily(etf_sell_trade, time='14:00')
    # 执行买入操作
    run_daily(etf_buy_trade, time='14:45')   #原作14:01
    
    log.info(f"""
    策略参数初始化完成:
    - ETF池大小: {len(g.etf_pool)} 只ETF
    - 动量周期: {g.lookback_days} 天
    - 持仓数量: {g.holdings_num} 只
    - 成交量过滤: {'启用' if g.enable_volume_check else '禁用'}
    - 均线过滤: {'启用' if g.enable_ma_filter else '禁用'}
    - RSI过滤: {'启用' if g.use_rsi_filter else '禁用'}
    - ATR止损: {'启用' if g.use_atr_stop_loss else '禁用'}
    - 防御ETF: {g.defensive_etf}
    """)
def before_trading_start(context):
    """
    每个交易日开盘前运行（约 09:00-09:15）
    用于确认策略当天是否被触发
    """
    log.info(f"✅ 策略已启动 | 日期: {context.current_dt.strftime('%Y-%m-%d')} | 当前持仓数: {len(context.portfolio.positions)}")
def check_positions(context):
    """每日开盘后检查持仓状态"""
    current_data = get_current_data()
    for security in context.portfolio.positions:
        position = context.portfolio.positions[security]
        if position.total_amount > 0:
            security_name = get_security_name(security)
            log.info(f"📊 持仓检查: {security} {security_name}, 数量: {position.total_amount}, 成本: {position.avg_cost:.3f}, 当前价: {position.price:.3f}")
            if current_data[security].paused:
                log.info(f"⚠️ {security} {security_name} 今日停牌")

# ==================== 卖出函数 ====================
def etf_sell_trade(context):
    """
    卖出函数
    功能：卖出不符合条件的持仓
    """
    log.info("========== 卖出操作开始 ==========")
    
    # 获取当前持仓
    current_positions = list(context.portfolio.positions.keys())
    
    # 如果没有持仓，直接返回
    if not current_positions:
        log.info("当前无持仓，无需卖出")
        return
    
    # 获取符合条件的ETF排名
    ranked_etfs = get_ranked_etfs(context)
    
    # ========== 修复点1：构建目标ETF列表（最多g.holdings_num只） ==========
    target_etfs = []
    for metrics in ranked_etfs:
        if len(target_etfs) >= g.holdings_num:
            break
        if metrics['score'] >= g.min_score_threshold:
            target_etfs.append(metrics['etf'])
        else:
            break  # 因为已按得分降序排序，后续得分更低，可提前退出
    
    # ========== 如果无合格标的，尝试使用防御ETF ==========
    defensive_etf_available = False
    if not target_etfs:
        log.info("💤 无符合条件的ETF，进入空仓模式（防御ETF已禁用）")
    # 不添加任何防御标的
    
    target_etfs_set = set(target_etfs)
    
    # ========== 卖出不在目标列表中的持仓 ==========
    for security in current_positions:
        # 只处理ETF池中的标的或防御ETF
        if (security in g.etf_pool or security == g.defensive_etf) and security not in target_etfs_set:
            position = context.portfolio.positions[security]
            if position.total_amount > 0:
                success = smart_order_target_value(security, 0, context)
                if success:
                    security_name = get_security_name(security)
                    log.info(f"📤 卖出不在目标列表的持仓: {security} {security_name}")
                    
                    # 清除相关记录
                    if security in g.position_highs:
                        del g.position_highs[security]
                    if security in g.position_stop_prices:
                        del g.position_stop_prices[security]
    
    # ========== 检查并执行固定止损 ==========
    for security in list(context.portfolio.positions.keys()):
        if security in g.etf_pool:
            position = context.portfolio.positions[security]
            if position.total_amount > 0:
                current_price = position.price
                cost_price = position.avg_cost
                
                if current_price <= cost_price * g.stop_loss:
                    success = smart_order_target_value(security, 0, context)
                    if success:
                        security_name = get_security_name(security)
                        loss_percent = (current_price/cost_price-1)*100
                        log.info(f"🚨 固定百分比止损卖出: {security} {security_name}，亏损: {loss_percent:.2f}%")
                        
                        # 清除记录
                        if security in g.position_highs:
                            del g.position_highs[security]
                        if security in g.position_stop_prices:
                            del g.position_stop_prices[security]
    current_positions = list(context.portfolio.positions.keys())

# 新增：输出当前持仓详情
    log.info(f"📋 卖出操作前当前持仓: {[(sec, get_security_name(sec), context.portfolio.positions[sec].total_amount, round(context.portfolio.positions[sec].price, 3)) for sec in current_positions]}")

    log.info("========== 卖出操作完成 ==========")

# ==================== 获取ETF排名函数 ====================
def get_ranked_etfs(context):
    """
    获取符合条件的ETF排名
    返回结果：应用所有过滤条件，返回满足条件的ETF列表，按得分降序
    """
    etf_metrics = []
    
    # 可选：先进行均线过滤（减少计算量）
    filtered_pool = g.etf_pool

    for etf in filtered_pool:
        # ========== 新增：停牌过滤 ==========
        current_data = get_current_data()
        if current_data[etf].paused:
            log.debug(f"{etf}: 今日停牌，跳过计算")
            continue

        metrics = calculate_momentum_metrics(context, etf)
        if metrics is not None:
            # 过滤掉得分异常的ETF
            if 0 < metrics['score'] < g.max_score_threshold:
            #if 0 < metrics['score']:
                etf_metrics.append(metrics)
            else: 
                log.info(f"⚠️ {etf} 得分不满足要求！")
                
                
    
    # 按得分降序排序
    etf_metrics.sort(key=lambda x: x['score'], reverse=True)
    return etf_metrics

# ==================== 动量指标计算函数 ====================
def calculate_momentum_metrics(context, etf):
    """
    计算ETF的动量指标，整合所有过滤条件
    返回包含各项指标和过滤结果的字典
    """
    try:

        # 获取历史价格数据
        lookback = max(g.lookback_days, g.short_lookback_days, 
                      g.rsi_period + g.rsi_lookback_days) + 20
        prices = attribute_history(etf, lookback, '1d', ['close', 'high'])
        current_data = get_current_data()
        
        if len(prices) < g.lookback_days:
            log.debug(f"{etf}: 历史数据不足，跳过计算")
            return None
        
        # 获取当前价格并添加到价格序列中
        current_price = current_data[etf].last_price
        price_series = np.append(prices["close"].values, current_price)
        
        # ========== 新增：成交量过滤检查 ==========
        if g.enable_volume_check and len(price_series) > g.lookback_days:
            volume_ratio = get_volume_ratio(context, etf)
            volume_annualized = get_annualized_returns(price_series,g.lookback_days)
            if volume_ratio is not None:
                if volume_annualized > g.volume_return_limit:
                    log.debug(f"{etf}: 成交量放大{volume_ratio:.2f}倍且折合年化收益{volume_annualized:.2f}超过设置值{g.volume_return_limit}，属于“高位放量”，过滤掉")
                    return None
        
        # ========== RSI过滤检查 ==========
        rsi_filter_pass = True
        current_rsi = 0
        max_rsi = 0
        
        if g.use_rsi_filter and len(price_series) >= g.rsi_period + g.rsi_lookback_days:
            rsi_values = calculate_rsi(price_series, g.rsi_period)
            
            if len(rsi_values) >= g.rsi_lookback_days:
                recent_rsi = rsi_values[-g.rsi_lookback_days:]
                rsi_ever_above_threshold = np.any(recent_rsi > g.rsi_threshold)
                
                # 检查当前价格是否在MA5之下
                if len(price_series) >= 5:
                    ma5 = np.mean(price_series[-5:])
                    current_below_ma5 = current_price < ma5
                else:
                    current_below_ma5 = True
                
                if rsi_ever_above_threshold and current_below_ma5:
                    rsi_filter_pass = False
                    max_rsi = np.max(recent_rsi)
                    current_rsi = recent_rsi[-1] if len(recent_rsi) > 0 else 0
                    log.info(f"⛔ RSI过滤: {etf} 近{g.rsi_lookback_days}日RSI曾达{max_rsi:.1f}，当前价{current_price:.3f}<MA5，当前RSI={current_rsi:.1f}")
                else:
                    max_rsi = np.max(recent_rsi) if len(recent_rsi) > 0 else 0
                    current_rsi = recent_rsi[-1] if len(recent_rsi) > 0 else 0
        
        if not rsi_filter_pass:
            return None
        
        # ========== 原有：短期动量计算 ==========
        if len(price_series) >= g.short_lookback_days + 1:
            short_return = price_series[-1] / price_series[-(g.short_lookback_days + 1)] - 1
            short_annualized = (1 + short_return) ** (250 / g.short_lookback_days) - 1
            #short_annualized = get_annualized_returns(price_series,g.short_lookback_days)
        else:
            short_return = 0
            short_annualized = 0
        
        # ========== 短期动量过滤 ==========
        if g.use_short_momentum_filter and short_annualized < g.short_momentum_threshold:
            log.debug(f"{etf}: 短期动量{short_annualized:.4f} < 阈值{g.short_momentum_threshold}，过滤掉")
            return None
        
        # ========== 长期动量计算（参考策略1的加权回归） ==========
        # 使用最后g.lookback_days+1天的数据
        
        recent_price_series = price_series[-(g.lookback_days + 1):]
        y = np.log(recent_price_series)
        x = np.arange(len(y))
        weights = np.linspace(1, 2, len(y))  # 加权回归，近期权重更高
        
        # 计算年化收益率
        slope, intercept = np.polyfit(x, y, 1, w=weights)
        annualized_returns = math.exp(slope * 250) - 1
        
        #annualized_returns = get_annualized_returns(price_series,g.lookback_days)
        # 计算R²（拟合优度）
        ss_res = np.sum(weights * (y - (slope * x + intercept)) ** 2)
        ss_tot = np.sum(weights * (y - np.mean(y)) ** 2)
        r_squared = 1 - ss_res / ss_tot if ss_tot else 0
        
        # 综合得分 = 年化收益率 * 趋势稳定性
        score = annualized_returns * r_squared
        
        # ========== 短期风控过滤 ==========
        if len(price_series) >= 4:
            day1_ratio = price_series[-1] / price_series[-2]
            day2_ratio = price_series[-2] / price_series[-3]
            day3_ratio = price_series[-3] / price_series[-4]
            
            if min(day1_ratio, day2_ratio, day3_ratio) < g.loss:
                score = 0
                log.info(f"⚠️ {etf} 近3日有单日跌幅超设定值，已排除")
        
        return {
            'etf': etf,
            'annualized_returns': annualized_returns,
            'r_squared': r_squared,
            'score': score,
            'slope': slope,
            'current_price': current_price,
            'short_return': short_return,
            'short_annualized': short_annualized,
            'short_momentum_pass': short_return >= g.short_momentum_threshold,
            'rsi_filter_pass': rsi_filter_pass,
            'current_rsi': current_rsi,
            'max_recent_rsi': max_rsi,
        }
        
    except Exception as e:
        log.warning(f"计算{etf}动量指标时出错: {e}")
        return None
   

# ==================== 新增：成交量过滤函数（参考策略1） ====================
def get_volume_ratio(context, security, lookback_days=None, threshold=None):
    """
    计算成交量比值（当日成交量/历史平均成交量）
    返回：若放量（>threshold）则返回比值，否则返回None
    """
    if lookback_days is None:
        lookback_days = g.volume_lookback
    if threshold is None:
        threshold = g.volume_threshold
    
    try:
        # 1. 获取历史成交量（N天平均）
        hist_data = attribute_history(security, lookback_days, '1d', ['volume'])
        if hist_data.empty or len(hist_data) < lookback_days:
            log.debug(f"{security}: 历史成交量数据不足")
            return None
        
        avg_volume = hist_data['volume'].mean()
        
        # 2. 获取当日实时成交量（分钟数据累加）
        today = context.current_dt.date()
        df_vol = get_price(
            security,
            start_date=today,
            end_date=context.current_dt,
            frequency='1m',
            fields=['volume'],
            skip_paused=False,
            fq='pre',
            panel=True,
            fill_paused=False
        )
        
        if df_vol is None or df_vol.empty:
            log.debug(f"{security}: 当日成交量数据为空")
            return None
        
        current_volume = df_vol['volume'].sum()
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        
        # 3. 超过阈值视为放量
        etf_name = get_security_name(security)
        if volume_ratio > threshold:
            log.debug(f"⚠️ {security}-{etf_name}: 成交量比值 {volume_ratio:.2f} > 阈值 {threshold}")
            return volume_ratio
        else:
            log.debug(f"{security}-{etf_name}: 成交量比值 {volume_ratio:.2f} <= 阈值 {threshold}")
            return None
            
    except Exception as e:
        log.warning(f"成交量检测失败 {security}: {e}")
        return None

# ==================== 新增：均线过滤函数（参考策略1） ====================
def filter_below_ma(stocks, days=None):
    """
    过滤掉当前价格小于N日均价的股票/ETF
    返回过滤后的标的列表（仅保留当前价 >= N日均价的标的）
    """
    if days is None:
        days = g.ma_filter_days
    
    if not stocks:
        return []
    
    current_data = get_current_data()
    filtered = []
    
    for stock in stocks:
        try:
            # 获取N日历史收盘价数据
            hist = attribute_history(stock, days, "1d", ["close"])
            if len(hist) < days:
                log.debug(f"{stock}: 历史数据不足{days}天，跳过过滤")
                continue
                
            # 计算N日均价
            ma_n = hist["close"].mean()
            # 获取当前价格
            current_price = current_data[stock].last_price
            
            # 保留当前价 >= N日均价的标的
            if current_price >= ma_n:
                filtered.append(stock)
                log.debug(f"{stock}: 通过{days}日均线过滤，当前价 {current_price:.2f} >= 均线 {ma_n:.2f}")
            else:
                log.debug(f"{stock}: 未通过{days}日均线过滤，当前价 {current_price:.2f} < 均线 {ma_n:.2f}")
                
        except Exception as e:
            log.warning(f"计算{stock} {days}日均价失败: {e}")
            continue
            
    return filtered

# ==================== 原有：ATR计算函数（保持不变） ====================
def calculate_atr(security, period=14):
    """
    计算ATR（平均真实波幅）指标
    """
    try:
        needed_days = period + 20
        hist_data = attribute_history(security, needed_days, '1d', 
                                     ['high', 'low', 'close'])
        
        if len(hist_data) < period + 1:
            return 0, [], False, f"数据不足{period+1}天"
        
        high_prices = hist_data['high'].values
        low_prices = hist_data['low'].values
        close_prices = hist_data['close'].values
        
        tr_values = np.zeros(len(high_prices))
        for i in range(1, len(high_prices)):
            tr1 = high_prices[i] - low_prices[i]
            tr2 = abs(high_prices[i] - close_prices[i-1])
            tr3 = abs(low_prices[i] - close_prices[i-1])
            tr_values[i] = max(tr1, tr2, tr3)
        
        atr_values = np.zeros(len(tr_values))
        for i in range(period, len(tr_values)):
            atr_values[i] = np.mean(tr_values[i-period+1:i+1])
        
        current_atr = atr_values[-1] if len(atr_values) > 0 else 0
        valid_atr = atr_values[period:] if len(atr_values) > period else atr_values
        
        return current_atr, valid_atr, True, "计算成功"
    
    except Exception as e:
        log.warning(f"计算{security} ATR时出错: {e}")
        return 0, [], False, f"计算出错:{str(e)}"

# ==================== 原有：RSI计算函数（保持不变） ====================
def calculate_rsi(prices, period=6):
    """
    计算RSI指标
    """
    if len(prices) < period + 1:
        return []
    
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gains = np.zeros_like(prices)
    avg_losses = np.zeros_like(prices)
    avg_gains[period] = np.mean(gains[:period])
    avg_losses[period] = np.mean(losses[:period])
    
    rsi_values = np.zeros(len(prices))
    rsi_values[:period] = 50
    
    for i in range(period + 1, len(prices)):
        avg_gains[i] = (avg_gains[i-1] * (period - 1) + gains[i-1]) / period
        avg_losses[i] = (avg_losses[i-1] * (period - 1) + losses[i-1]) / period
        
        if avg_losses[i] == 0:
            rsi_values[i] = 100
        else:
            rs = avg_gains[i] / avg_losses[i]
            rsi_values[i] = 100 - (100 / (1 + rs))
    
    return rsi_values[period:]

     
# ===================计算年化收益===================
def get_annualized_returns(price_series,lookback_days):
    # 使用最后g.lookback_days+1天的数据
    recent_price_series = price_series[-(lookback_days + 1):]
    y = np.log(recent_price_series)
    x = np.arange(len(y))
    weights = np.linspace(1, 2, len(y))  # 加权回归，近期权重更高
    
    # 计算年化收益率
    slope, intercept = np.polyfit(x, y, 1, w=weights)
    annualized_returns = math.exp(slope * 250) - 1
    return annualized_returns




# ==================== 优化：买入函数（下午14:20执行） ====================
def etf_buy_trade(context):
    """
    买入函数
    功能：买入符合条件的ETF
    """
    log.info("========== 买入操作开始 ==========")
    
    # 获取符合条件的ETF排名
    ranked_etfs = get_ranked_etfs(context)
    
    # 记录所有ETF的指标（用于调试）
    if ranked_etfs:
        log.info("=== 符合条件的ETF指标 ===")
        for metrics in ranked_etfs[:5]:  # 只显示前5名
            etf_name = get_security_name(metrics['etf'])
            log.info(f"{metrics['etf']} {etf_name}: 得分={metrics['score']:.4f}, 年化={metrics['annualized_returns']:.4f}, R²={metrics['r_squared']:.4f}, 短期动量={metrics['short_return']:.4f}, RSI={metrics['current_rsi']:.1f}")
    
    # ========== 修复点2：选择前g.holdings_num只合格ETF ==========
    target_etfs = []
    for metrics in ranked_etfs:
        if len(target_etfs) >= g.holdings_num:
            break
        if metrics['score'] >= g.min_score_threshold:
            target_etfs.append(metrics['etf'])
        else:
            break  # 排序后提前退出
    
    # 如果没有合格标的，尝试使用防御ETF
    if not target_etfs:
        log.info("💤 无符合条件的ETF，进入空仓模式（防御ETF已禁用）")
        return
    else:
        # 显示选中的ETF
        selected_names = [f"{etf} {get_security_name(etf)}" for etf in target_etfs]
        log.info(f"🎯 选择前{len(target_etfs)}名ETF: {', '.join(selected_names)}")
    
    # ========== 检查是否有其他非目标持仓未清空 ==========
    current_positions = list(context.portfolio.positions.keys())
    current_etf_positions = [pos for pos in current_positions if pos in g.etf_pool or pos == g.defensive_etf]
    other_positions = [pos for pos in current_etf_positions if pos not in target_etfs]
    if other_positions:
        for pos in other_positions:
            position = context.portfolio.positions[pos]
            if position.total_amount > 0:
                log.info(f"⚠️ 尚有其他持仓 {get_security_name(pos)} 未卖出，等待卖出完成后再买入新标的")
                return
    
    # ========== 等权重分配资金 ==========
    total_value = context.portfolio.total_value
    target_value_per_etf = total_value / len(target_etfs)
    
    # 对每个目标ETF下单
    for etf in target_etfs:
        success = smart_order_target_value(etf, target_value_per_etf, context)
        if success:
            etf_name = get_security_name(etf)
            # 判断是买入还是调仓
            current_pos = context.portfolio.positions.get(etf)
            current_val = current_pos.total_amount * current_pos.price if current_pos else 0
            action = "调仓" if current_val > 0 else "买入"
            log.info(f"📦 {action}: {etf} {etf_name}，目标金额: {target_value_per_etf:.2f}")
    
    log.info("========== 买入操作完成 ==========")

# ==================== 原有辅助函数（保持不变） ====================
def get_security_name(security):
    """获取证券名称"""
    current_data = get_current_data()
    #return current_data[security].name if security in current_data else security
    return current_data[security].name

def check_defensive_etf_available(context):
    """检查防御ETF是否可交易"""
    current_data = get_current_data()
    defensive_etf = g.defensive_etf
    
    #if defensive_etf not in g.etf_pool:
    #    return False
        
    if current_data[defensive_etf].paused:
        log.info(f"防御性ETF {defensive_etf} 今日停牌")
        return False
        
    if current_data[defensive_etf].last_price >= current_data[defensive_etf].high_limit:
        log.info(f"防御性ETF {defensive_etf} 当前涨停")
        return False
        
    if current_data[defensive_etf].last_price <= current_data[defensive_etf].low_limit:
        log.info(f"防御性ETF {defensive_etf} 当前跌停")
        return False
        
    return True

def smart_order_target_value(security, target_value, context):
    """
    智能下单函数
    """
    current_data = get_current_data()
    
    # 检查标的是否停牌
    if current_data[security].paused:
        log.info(f"{security} {get_security_name(security)}: 今日停牌，跳过交易")
        return False

    # 检查涨停
    if current_data[security].last_price >= current_data[security].high_limit:
        log.info(f"{security} {get_security_name(security)}: 当前涨停，跳过买入")
        return False

    # 检查跌停
    if current_data[security].last_price <= current_data[security].low_limit:
        log.info(f"{security} {get_security_name(security)}: 当前跌停，跳过卖出")
        return False

    # 获取当前价格
    current_price = current_data[security].last_price
    if current_price == 0:
        log.info(f"{security} {get_security_name(security)}: 当前价格为0，跳过交易")
        return False

    # 计算目标数量
    target_amount = int(target_value / current_price)
    
    # 对于ETF，按100股整数倍调整
    target_amount = (target_amount // 100) * 100
    if target_amount <= 0 and target_value > 0:
        target_amount = 100
    
    # 获取当前持仓
    current_position = context.portfolio.positions.get(security, None)
    current_amount = current_position.total_amount if current_position else 0
    
    # 计算需要调整的数量
    amount_diff = target_amount - current_amount
    
    # 检查最小交易金额
    trade_value = abs(amount_diff) * current_price
    if 0 < trade_value < g.min_money:
        log.info(f"{security} {get_security_name(security)}: 交易金额{trade_value:.2f}小于最小交易额{g.min_money}，跳过交易")
        return False

    # 检查T+1限制
    if amount_diff < 0:  # 卖出操作
        closeable_amount = current_position.closeable_amount if current_position else 0
        if closeable_amount == 0:
            log.info(f"{security} {get_security_name(security)}: 当天买入不可卖出(T+1)")
            return False
        amount_diff = -min(abs(amount_diff), closeable_amount)

    # 执行下单
    if amount_diff != 0:
        order_result = order(security, amount_diff)
        if order_result:
            # 更新持仓记录
            g.positions[security] = target_amount
            
            # 如果买入操作，初始化最高价记录和ATR止损价
            if amount_diff > 0 and security in g.etf_pool:
                g.position_highs[security] = current_price
                
                # 计算ATR止损价
                if g.use_atr_stop_loss and not (g.atr_exclude_defensive and security == g.defensive_etf):
                    current_atr, _, success, _ = calculate_atr(security, g.atr_period)
                    if success:
                        if g.atr_trailing_stop:
                            g.position_stop_prices[security] = current_price - g.atr_multiplier * current_atr
                        else:
                            g.position_stop_prices[security] = current_price - g.atr_multiplier * current_atr
            
            security_name = get_security_name(security)
            if amount_diff > 0:
                log.info(f"📥 买入 {security} {security_name}，数量: {amount_diff}，价格: {current_price:.3f}")
            else:
                log.info(f"📤 卖出 {security} {security_name}，数量: {abs(amount_diff)}，价格: {current_price:.3f}")
            return True
        else:
            log.warning(f"下单失败: {security} {get_security_name(security)}，数量: {amount_diff}")
            return False
    
    return False


        
def check_atr_stop_loss(context):
    """
    检查并执行ATR动态止损
    """
    if not g.use_atr_stop_loss:
        return
    
    current_data = get_current_data()
    
    for security in list(context.portfolio.positions.keys()):
        if security not in g.etf_pool:
            continue
            
        position = context.portfolio.positions[security]
        if position.total_amount <= 0:
            continue
        
        # 防御ETF豁免检查
        if g.atr_exclude_defensive and security == g.defensive_etf:
            continue
        
        try:
            current_price = current_data[security].last_price
            if current_price == 0:
                continue
            
            cost_price = position.avg_cost
            
            # 计算当前ATR值
            current_atr, atr_values, success, atr_info = calculate_atr(security, g.atr_period)
            
            if not success:
                continue
            
            # 更新持仓期间的最高价
            if security not in g.position_highs:
                g.position_highs[security] = current_price
            else:
                g.position_highs[security] = max(g.position_highs[security], current_price)
            
            position_high = g.position_highs[security]
            
            # 计算ATR止损价
            if g.atr_trailing_stop:
                atr_stop_price = position_high - g.atr_multiplier * current_atr
            else:
                atr_stop_price = cost_price - g.atr_multiplier * current_atr
            
            g.position_stop_prices[security] = atr_stop_price
            
            # 检查是否触发ATR止损
            if current_price <= atr_stop_price:
                success = smart_order_target_value(security, 0, context)
                if success:
                    security_name = get_security_name(security)
                    loss_percent = (current_price/cost_price - 1) * 100
                    atr_stop_type = "跟踪" if g.atr_trailing_stop else "固定"
                    log.info(f"🚨 ATR动态止损({atr_stop_type})卖出: {security} {security_name}，亏损: {loss_percent:.2f}%")
                    
                    # 清除记录
                    if security in g.position_highs:
                        del g.position_highs[security]
                    if security in g.position_stop_prices:
                        del g.position_stop_prices[security]
        
        except Exception as e:
            log.warning(f"检查{security} ATR止损时出错: {e}")

# ==================== 主交易函数（保持兼容性） ====================
def trade(context):
    """主交易函数，为了兼容性保留"""
    # 在原有策略二中，trade函数调用了etf_trade
    # 现在我们已经拆分为两个函数，这里可以保持为空或调用买入函数
    pass