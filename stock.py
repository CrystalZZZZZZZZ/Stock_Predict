import streamlit as st
import akshare as ak
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import os
import time
import random
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# -------------------------- 全局配置 --------------------------
# 配置参数
REQUEST_CONFIG = {
    'min_delay': 3,      # 最小延迟秒数
    'max_delay': 5,      # 最大延迟秒数
    'max_retries': 3,    # 最大重试次数
    'timeout': 30,       # 请求超时时间
}

# -------------------------- 反爬虫配置（优化版） --------------------------
def create_session_with_retry():
    """创建带重试机制的requests会话"""
    session = requests.Session()
    
    # 设置随机User-Agent
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36 Edg/111.0.1661.41"
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    ]
    
    # 设置请求头
    session.headers.update({
        'User-Agent': random.choice(user_agents),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Connection': 'close',  # 每次请求后关闭连接
        'Upgrade-Insecure-Requests': '1',
    })
    
    # 设置重试机制（优化版）
    retry_strategy = Retry(
        total=REQUEST_CONFIG['max_retries'],
        backoff_factor=2,  # 增加退避因子
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False
    )
    
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,
        pool_maxsize=10
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session

def add_random_delay(min_seconds=None, max_seconds=None):
    """添加随机延迟以避免频繁请求"""
    min_sec = min_seconds or REQUEST_CONFIG['min_delay']
    max_sec = max_seconds or REQUEST_CONFIG['max_delay']
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)

# 初始化session
session = create_session_with_retry()

# -------------------------- 数据库配置（优化版） --------------------------
def init_db(db_path="quant_data.db"):
    """初始化数据库，创建股票数据表格"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 股票历史数据表（添加索引提高查询性能）
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS stock_zh_a_hist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        date DATE NOT NULL,
        open REAL,
        close REAL,
        high REAL,
        low REAL,
        volume REAL,
        amount REAL,
        amplitude REAL,
        change_percent REAL,
        change REAL,
        turnover REAL,
        period TEXT DEFAULT 'daily',
        adjust TEXT DEFAULT 'qfq',
        create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, date, period, adjust)
    )
    ''')
    
    # 创建索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol_date ON stock_zh_a_hist(symbol, date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol ON stock_zh_a_hist(symbol)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_date ON stock_zh_a_hist(date)')
    
    conn.commit()
    conn.close()

def get_db_connection(db_path="quant_data.db"):
    """获取数据库连接"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# -------------------------- 核心数据获取函数（优化版） --------------------------
def safe_fetch_stock_data(symbol, start_date, end_date, period="daily", adjust="qfq", max_retries=None):
    """
    安全的股票数据获取函数，包含完整的错误处理和重试机制
    """
    max_retries = max_retries or REQUEST_CONFIG['max_retries']
    
    for attempt in range(max_retries):
        try:
            # 添加随机延迟（每次请求前都延迟）
            add_random_delay()
            
            # 准备参数
            adjust_param = adjust if adjust != "None" else ""
            
            # 使用akshare获取数据（添加超时控制）
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period=period,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust_param
            )
            
            # 检查数据是否有效
            if df is None or df.empty:
                return None
            
            return process_stock_data(df, symbol, period, adjust)
            
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** (attempt + 1)  # 指数退避
                st.warning(f"第{attempt+1}次请求失败，{wait_time}秒后重试: {str(e)[:100]}")
                time.sleep(wait_time)
            else:
                st.error(f"获取股票{symbol}数据失败（已重试{max_retries}次）")
                return None
        except Exception as e:
            st.error(f"获取股票{symbol}数据时发生错误: {str(e)[:100]}")
            return None

def process_stock_data(df, symbol, period, adjust):
    """统一处理股票数据格式"""
    # 重置索引
    if "date" not in df.columns:
        df = df.reset_index()
    
    # 统一列名
    column_mapping = {
        "日期": "date", "trade_date": "date", "index": "date",
        "开盘": "open", "收盘": "close", "最高": "high", "最低": "low",
        "成交量": "volume", "成交额": "amount", "振幅": "amplitude",
        "涨跌幅": "change_percent", "涨跌额": "change", "换手率": "turnover"
    }
    
    df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})
    
    # 处理日期列
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors='coerce')
        df = df.dropna(subset=["date"])
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    
    # 添加元数据
    df["symbol"] = symbol
    df["period"] = period
    df["adjust"] = adjust if adjust != "" else "None"
    
    # 确保必要的列存在
    required_columns = ["date", "open", "close", "high", "low", "volume"]
    for col in required_columns:
        if col not in df.columns:
            df[col] = None
    
    return df

# -------------------------- 批量操作函数（优化版） --------------------------
def process_symbols(symbols_str):
    """处理股票代码字符串，返回清理后的列表"""
    symbols = symbols_str.replace('，', ',').replace(';', ',').replace(' ', ',')
    symbols = [s.strip() for s in symbols.split(',') if s.strip()]
    return list(set(symbols))

def fetch_multiple_stocks(symbols_str, start_date, end_date, period="daily", adjust="qfq"):
    """批量获取多个股票的数据"""
    symbols = process_symbols(symbols_str)
    if not symbols:
        st.error("请输入有效的股票代码")
        return []
    
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, symbol in enumerate(symbols):
        progress = i / len(symbols)
        progress_bar.progress(progress)
        status_text.text(f"正在获取 {symbol} ({i+1}/{len(symbols)})...")
        
        df = safe_fetch_stock_data(symbol, start_date, end_date, period, adjust)
        
        if df is not None and not df.empty:
            results.append(df)
        
        # 额外的请求间延迟
        if i < len(symbols) - 1:
            add_random_delay(2, 4)
    
    progress_bar.progress(1.0)
    success_count = len(results)
    status_text.text(f"完成！成功获取 {success_count}/{len(symbols)} 个股票的数据")
    
    return results

def save_stocks_to_db(df_list, db_path="quant_data.db"):
    """将股票数据批量存入数据库"""
    if not df_list:
        st.warning("无数据可存储")
        return 0
    
    total_inserted = 0
    conn = get_db_connection(db_path)
    
    for df in df_list:
        if df.empty:
            continue
        
        symbol = df["symbol"].iloc[0]
        inserted = 0
        
        try:
            # 使用批量插入提高性能
            data_to_insert = []
            for _, row in df.iterrows():
                data_to_insert.append((
                    row.get("symbol"),
                    row.get("date"),
                    row.get("open"), row.get("close"),
                    row.get("high"), row.get("low"),
                    row.get("volume"), row.get("amount"),
                    row.get("amplitude"), row.get("change_percent"),
                    row.get("change"), row.get("turnover"),
                    row.get("period", "daily"),
                    row.get("adjust", "qfq")
                ))
            
            # 使用INSERT OR IGNORE避免重复
            conn.executemany('''
            INSERT OR IGNORE INTO stock_zh_a_hist 
            (symbol, date, open, close, high, low, volume, amount, 
             amplitude, change_percent, change, turnover, period, adjust)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', data_to_insert)
            
            inserted = conn.total_changes
            total_inserted += inserted
            
            if inserted > 0:
                st.success(f"{symbol}: 新增 {inserted} 条数据")
                
        except Exception as e:
            st.error(f"{symbol} 存储失败: {str(e)[:100]}")
            conn.rollback()
    
    conn.commit()
    conn.close()
    
    st.info(f"总计新增 {total_inserted} 条数据")
    return total_inserted

def update_stock_data(symbol, period="daily", adjust="qfq", db_path="quant_data.db"):
    """增量更新单个股票数据"""
    conn = get_db_connection(db_path)
    
    # 查询最新日期
    cursor = conn.execute('''
    SELECT MAX(date) as max_date FROM stock_zh_a_hist 
    WHERE symbol=? AND period=? AND adjust=?
    ''', (symbol, period, adjust if adjust != "None" else ""))
    
    result = cursor.fetchone()
    conn.close()
    
    if result and result["max_date"]:
        last_date = result["max_date"]
        start_date = (datetime.strptime(last_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        start_date = "1990-01-01"  # 如果数据库为空，从最早开始
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    
    if start_date > end_date:
        st.info(f"{symbol}: 数据已是最新")
        return None
    
    st.info(f"{symbol}: 获取增量数据 ({start_date} 至 {end_date})")
    return safe_fetch_stock_data(symbol, start_date, end_date, period, adjust)

def update_multiple_stocks(symbols_str, period="daily", adjust="qfq", db_path="quant_data.db"):
    """批量更新股票数据"""
    symbols = process_symbols(symbols_str)
    if not symbols:
        return []
    
    results = []
    progress_bar = st.progress(0)
    
    for i, symbol in enumerate(symbols):
        progress = i / len(symbols)
        progress_bar.progress(progress)
        
        df = update_stock_data(symbol, period, adjust, db_path)
        if df is not None and not df.empty:
            results.append(df)
        
        if i < len(symbols) - 1:
            add_random_delay(2, 4)
    
    progress_bar.progress(1.0)
    return results

# -------------------------- 数据查询函数（优化版） --------------------------
def query_stocks_data(symbols_str, start_date=None, end_date=None, period="daily", adjust="qfq", db_path="quant_data.db"):
    """从数据库查询股票数据"""
    symbols = process_symbols(symbols_str)
    if not symbols:
        return pd.DataFrame()
    
    placeholders = ','.join(['?'] * len(symbols))
    query = f'''
    SELECT * FROM stock_zh_a_hist 
    WHERE symbol IN ({placeholders}) AND period=? AND adjust=?
    '''
    
    params = symbols + [period, adjust if adjust != "None" else ""]
    
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    
    query += " ORDER BY symbol, date ASC"
    
    conn = get_db_connection(db_path)
    try:
        df = pd.read_sql(query, conn, params=params)
    except Exception as e:
        st.error(f"查询失败: {str(e)}")
        df = pd.DataFrame()
    finally:
        conn.close()
    
    return df

# -------------------------- Streamlit界面（优化版） --------------------------
def main():
    st.set_page_config(page_title="量化分析系统", layout="wide")
    st.title("📊 量化分析系统 - 数据获取模块")
    
    # 侧边栏配置
    st.sidebar.header("⚙️ 系统配置")
    db_path = st.sidebar.text_input("数据库路径", value="quant_data.db")
    
    # 初始化数据库
    if st.sidebar.button("初始化数据库"):
        init_db(db_path)
        st.sidebar.success("数据库初始化完成")
    
    # 反爬虫设置
    st.sidebar.subheader("🛡️ 反爬虫设置")
    enable_antispider = st.sidebar.checkbox("启用反爬虫保护", value=True)
    if enable_antispider:
        REQUEST_CONFIG['min_delay'] = st.sidebar.slider("最小延迟(秒)", 1.0, 5.0, 3.0, 0.5)
        REQUEST_CONFIG['max_delay'] = st.sidebar.slider("最大延迟(秒)", 2.0, 10.0, 5.0, 0.5)
        REQUEST_CONFIG['max_retries'] = st.sidebar.slider("最大重试次数", 1, 5, 3)
    
    # 主功能选择
    st.sidebar.header("📋 功能选择")
    func_option = st.sidebar.selectbox(
        "选择功能",
        ["📥 A股数据抓取", "🔍 数据查询与显示", "🔄 数据更新"]
    )
    
    # 通用输入区域
    st.header("📝 股票代码输入")
    st.info("支持多个股票代码，用逗号、分号或空格分隔，例如：600000,000001,002415")
    symbols_input = st.text_input("股票代码", value="600000,000001")
    
    # 通用参数选择
    col1, col2 = st.columns(2)
    with col1:
        period = st.selectbox("数据周期", ["daily", "weekly", "monthly"], index=0)
    with col2:
        adjust_options = {"前复权": "qfq", "后复权": "hfq", "不复权": "None"}
        adjust_display = st.selectbox("复权类型", list(adjust_options.keys()), index=0)
        adjust = adjust_options[adjust_display]
    
    # 功能实现
    if func_option == "📥 A股数据抓取":
        st.header("📥 A股历史数据抓取")
        
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("开始日期", value=datetime.now() - timedelta(days=365))
        with col2:
            end_date = st.date_input("结束日期", value=datetime.now())
        
        if st.button("🚀 开始抓取数据", type="primary"):
            with st.spinner("正在抓取数据..."):
                df_list = fetch_multiple_stocks(
                    symbols_input,
                    start_date.strftime("%Y-%m-%d"),
                    end_date.strftime("%Y-%m-%d"),
                    period,
                    adjust
                )
            
            if df_list:
                total_rows = sum(len(df) for df in df_list)
                st.success(f"✅ 成功抓取 {len(df_list)} 个股票，共 {total_rows} 条数据")
                
                # 数据预览
                for df in df_list[:3]:  # 只显示前3个
                    symbol = df["symbol"].iloc[0]
                    with st.expander(f"📈 {symbol} 数据预览 ({len(df)} 条)"):
                        st.dataframe(df.head(10), use_container_width=True)
                
                # 存储选项
                if st.button("💾 保存到数据库"):
                    save_stocks_to_db(df_list, db_path)
                
                # 可视化
                if df_list:
                    st.subheader("📊 价格走势图")
                    chart_data = pd.concat(df_list[:5])  # 最多显示5个股票
                    pivot_df = chart_data.pivot_table(
                        index='date', 
                        columns='symbol', 
                        values='close'
                    )
                    st.line_chart(pivot_df)
    
    elif func_option == "🔍 数据查询与显示":
        st.header("🔍 数据查询与显示")
        
        col1, col2 = st.columns(2)
        with col1:
            query_start = st.date_input("开始日期（可选）", value=None)
        with col2:
            query_end = st.date_input("结束日期（可选）", value=None)
        
        query_start_str = query_start.strftime("%Y-%m-%d") if query_start else None
        query_end_str = query_end.strftime("%Y-%m-%d") if query_end else None
        
        if st.button("🔎 查询数据", type="primary"):
            df = query_stocks_data(
                symbols_input,
                query_start_str,
                query_end_str,
                period,
                adjust,
                db_path
            )
            
            if not df.empty:
                st.success(f"✅ 查询到 {len(df)} 条数据，来自 {df['symbol'].nunique()} 个股票")
                
                # 显示数据
                with st.expander("📋 数据详情"):
                    st.dataframe(df, use_container_width=True)
                
                # 统计信息
                st.subheader("📊 统计信息")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("股票数量", df['symbol'].nunique())
                with col2:
                    st.metric("日期范围", f"{df['date'].min()} 至 {df['date'].max()}")
                with col3:
                    st.metric("总交易额", f"{df['amount'].sum():,.0f}")
                
                # 可视化
                if df['symbol'].nunique() <= 10:
                    st.subheader("📈 多股票对比")
                    pivot_df = df.pivot_table(index='date', columns='symbol', values='close')
                    st.line_chart(pivot_df)
            else:
                st.warning("⚠️ 未查询到数据")
    
    elif func_option == "🔄 数据更新":
        st.header("🔄 股票数据增量更新")
        
        if st.button("🔄 开始更新数据", type="primary"):
            with st.spinner("正在更新数据..."):
                df_list = update_multiple_stocks(symbols_input, period, adjust, db_path)
            
            if df_list:
                total_rows = sum(len(df) for df in df_list)
                st.success(f"✅ 成功更新 {len(df_list)} 个股票，共 {total_rows} 条数据")
                
                # 保存更新数据
                if st.button("💾 保存更新到数据库"):
                    save_stocks_to_db(df_list, db_path)
            else:
                st.info("ℹ️ 所有股票数据都已是最新")

if __name__ == "__main__":
    main()