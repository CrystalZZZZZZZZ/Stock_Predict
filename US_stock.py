import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
import sqlite3
import os
import json
from pathlib import Path
import pickle
import warnings
warnings.filterwarnings('ignore')

# 页面配置
st.set_page_config(
    page_title="美股量化分析系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 创建必要的目录
DATA_DIR = Path("data")
MODELS_DIR = Path("models")
DATA_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)

class DataManager:
    """数据管理类"""
    
    def __init__(self):
        self.db_path = DATA_DIR / "stocks.db"
        self.init_database()
    
    def init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建股票数据表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            date DATE NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            dividends REAL,
            stock_splits REAL,
            UNIQUE(symbol, date)
        )
        ''')
        
        # 创建股票信息表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_info (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            sector TEXT,
            industry TEXT,
            market_cap REAL,
            last_updated DATE
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def fetch_stock_data(self, symbols, start_date, end_date, interval='1d'):
        """从yfinance获取股票数据"""
        try:
            # 处理多个股票代码
            if isinstance(symbols, str):
                symbols = [s.strip().upper() for s in symbols.split(',')]
            
            all_data = {}
            
            for symbol in symbols:
                try:
                    ticker = yf.Ticker(symbol)
                    
                    # 获取历史数据
                    data = ticker.history(start=start_date, end=end_date, interval=interval)
                    
                    if not data.empty:
                        data['Symbol'] = symbol
                        all_data[symbol] = data
                        
                        # 获取股票基本信息
                        info = ticker.info
                        stock_info = {
                            'symbol': symbol,
                            'name': info.get('longName', symbol),
                            'sector': info.get('sector', 'Unknown'),
                            'industry': info.get('industry', 'Unknown'),
                            'market_cap': info.get('marketCap', 0),
                            'last_updated': datetime.now().date()
                        }
                        
                        # 保存股票信息
                        self.save_stock_info(stock_info)
                        
                        st.success(f"成功获取 {symbol} 的数据 ({len(data)} 条记录)")
                    else:
                        st.warning(f"未找到 {symbol} 的数据")
                        
                except Exception as e:
                    st.error(f"获取 {symbol} 数据时出错: {str(e)}")
            
            return all_data
            
        except Exception as e:
            st.error(f"获取数据时发生错误: {str(e)}")
            return {}
    
    def save_stock_data(self, symbol, data):
        """保存股票数据到数据库"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # 准备数据
            data = data.reset_index()
            if 'Date' in data.columns:
                data['date'] = data['Date'].dt.date
            elif 'Datetime' in data.columns:
                data['date'] = data['Datetime'].dt.date
            
            data['symbol'] = symbol

            rename_map = {
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume',
                'Dividends': 'dividends',
                'Stock Splits': 'stock_splits'
            }
            data.rename(columns=rename_map, inplace=True)
            
            # 筛选出数据库中存在的列
            db_columns = ['symbol', 'date', 'open', 'high', 'low', 'close', 'volume', 'dividends', 'stock_splits']
            data_to_save = data[[col for col in db_columns if col in data.columns]]
            
            # 保存到数据库
            data.to_sql('stocks', conn, if_exists='append', index=False, 
                       method='multi', chunksize=1000)
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            st.error(f"保存数据时出错: {str(e)}")
            return False
    
    def save_stock_info(self, stock_info):
        """保存股票信息"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            cursor = conn.cursor()
            cursor.execute('''
            INSERT OR REPLACE INTO stock_info 
            (symbol, name, sector, industry, market_cap, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                stock_info['symbol'],
                stock_info['name'],
                stock_info['sector'],
                stock_info['industry'],
                stock_info['market_cap'],
                stock_info['last_updated']
            ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            return False
    
    def get_stored_symbols(self):
        """获取数据库中已存储的股票代码"""
        try:
            conn = sqlite3.connect(self.db_path)
            query = "SELECT DISTINCT symbol FROM stocks ORDER BY symbol"
            symbols = pd.read_sql_query(query, conn)
            conn.close()
            return symbols['symbol'].tolist()
        except:
            return []
    
    def get_stock_data(self, symbol, start_date=None, end_date=None):
        """从数据库获取股票数据"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            query = f"SELECT * FROM stocks WHERE symbol = '{symbol}'"
            if start_date:
                query += f" AND date >= '{start_date}'"
            if end_date:
                query += f" AND date <= '{end_date}'"
            query += " ORDER BY date"
            
            data = pd.read_sql_query(query, conn)
            
            if not data.empty:
                data['date'] = pd.to_datetime(data['date'])
                data.set_index('date', inplace=True)
                data.index.name = 'Date'
            
            conn.close()
            return data
            
        except Exception as e:
            st.error(f"读取数据时出错: {str(e)}")
            return pd.DataFrame()
    
    def get_stock_info(self, symbol):
        """获取股票信息"""
        try:
            conn = sqlite3.connect(self.db_path)
            query = f"SELECT * FROM stock_info WHERE symbol = '{symbol}'"
            info = pd.read_sql_query(query, conn)
            conn.close()
            return info.iloc[0].to_dict() if not info.empty else {}
        except:
            return {}
    
    def delete_stock_data(self, symbol):
        """删除指定股票的所有数据"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM stocks WHERE symbol = ?", (symbol,))
            cursor.execute("DELETE FROM stock_info WHERE symbol = ?", (symbol,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            st.error(f"删除数据时出错: {str(e)}")
            return False
    
    def get_data_summary(self):
        """获取数据统计摘要"""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # 获取股票数量
            stock_count = pd.read_sql_query(
                "SELECT COUNT(DISTINCT symbol) as count FROM stocks", conn
            ).iloc[0]['count']
            
            # 获取记录总数
            record_count = pd.read_sql_query(
                "SELECT COUNT(*) as count FROM stocks", conn
            ).iloc[0]['count']
            
            # 获取数据日期范围
            date_range = pd.read_sql_query(
                "SELECT MIN(date) as start_date, MAX(date) as end_date FROM stocks", conn
            )
            
            conn.close()
            
            return {
                'stock_count': stock_count,
                'record_count': record_count,
                'start_date': date_range.iloc[0]['start_date'],
                'end_date': date_range.iloc[0]['end_date']
            }
            
        except:
            return {}

class StockVisualizer:
    """股票数据可视化类"""
    
    @staticmethod
    def plot_price_chart(data, symbol):
        """绘制价格图表"""
        if data.empty:
            return None
            
        fig = go.Figure()
        
        # 添加收盘价线
        fig.add_trace(go.Scatter(
            x=data.index,
            y=data['Close'],
            mode='lines',
            name='Close Price',
            line=dict(color='#1f77b4', width=2)
        ))
        
        # 添加移动平均线
        if len(data) > 20:
            data['MA20'] = data['Close'].rolling(window=20).mean()
            fig.add_trace(go.Scatter(
                x=data.index,
                y=data['MA20'],
                mode='lines',
                name='20-Day MA',
                line=dict(color='orange', width=1.5, dash='dash')
            ))
        
        fig.update_layout(
            title=f"{symbol} 价格走势",
            xaxis_title="日期",
            yaxis_title="价格 (USD)",
            hovermode='x unified',
            template='plotly_white',
            height=500,
            showlegend=True
        )
        
        return fig
    
    @staticmethod
    def plot_volume_chart(data, symbol):
        """绘制交易量图表"""
        if data.empty:
            return None
            
        fig = go.Figure()
        
        # 创建颜色映射：上涨为绿色，下跌为红色
        colors = ['red' if data['Close'].iloc[i] < data['Open'].iloc[i] else 'green' 
                 for i in range(len(data))]
        
        fig.add_trace(go.Bar(
            x=data.index,
            y=data['Volume'],
            name='Volume',
            marker_color=colors,
            opacity=0.7
        ))
        
        fig.update_layout(
            title=f"{symbol} 交易量",
            xaxis_title="日期",
            yaxis_title="交易量",
            template='plotly_white',
            height=300,
            showlegend=False
        )
        
        return fig
    
    @staticmethod
    def plot_technical_indicators(data, symbol):
        """绘制技术指标"""
        if data.empty or len(data) < 50:
            return None
            
        fig = go.Figure()
        
        # 计算RSI
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        data['RSI'] = 100 - (100 / (1 + rs))
        
        fig.add_trace(go.Scatter(
            x=data.index,
            y=data['RSI'],
            mode='lines',
            name='RSI',
            line=dict(color='purple', width=2)
        ))
        
        # 添加超买超卖线
        fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5)
        fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5)
        
        fig.update_layout(
            title=f"{symbol} RSI指标",
            xaxis_title="日期",
            yaxis_title="RSI",
            hovermode='x unified',
            template='plotly_white',
            height=400,
            yaxis_range=[0, 100]
        )
        
        return fig
    
    @staticmethod
    def display_stock_info(info):
        """显示股票信息卡片"""
        if not info:
            return
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("股票代码", info.get('symbol', 'N/A'))
        with col2:
            st.metric("公司名称", info.get('name', 'N/A')[:20])
        with col3:
            st.metric("行业板块", info.get('sector', 'N/A'))
        with col4:
            market_cap = info.get('market_cap', 0)
            if market_cap > 1e9:
                market_cap = f"${market_cap/1e9:.2f}B"
            elif market_cap > 1e6:
                market_cap = f"${market_cap/1e6:.2f}M"
            st.metric("市值", market_cap)

class StockAnalysisSystem:
    """主系统类"""
    
    def __init__(self):
        self.data_manager = DataManager()
        self.visualizer = StockVisualizer()
        
    def run(self):
        """运行应用"""
        # 侧边栏
        with st.sidebar:
            st.title("📊 美股量化分析系统")
            st.markdown("---")
            
            # 系统状态
            st.subheader("系统状态")
            summary = self.data_manager.get_data_summary()
            st.info(f"已存储股票: {summary.get('stock_count', 0)}")
            st.info(f"数据记录: {summary.get('record_count', 0)}")
            
            st.markdown("---")
            
            # 导航
            st.subheader("导航")
            page = st.radio(
                "选择功能",
                ["数据获取", "数据查看", "数据管理", "系统设置"]
            )
            
            st.markdown("---")
            
            # 数据更新选项
            st.subheader("数据更新")
            auto_update = st.checkbox("自动检查更新")
            
            if auto_update:
                update_freq = st.selectbox(
                    "更新频率",
                    ["每日", "每周", "每月"]
                )
        
        # 主页面
        if page == "数据获取":
            self.data_acquisition_page()
        elif page == "数据查看":
            self.data_view_page()
        elif page == "数据管理":
            self.data_management_page()
        elif page == "系统设置":
            self.system_settings_page()
    
    def data_acquisition_page(self):
        """数据获取页面"""
        st.title("📥 股票数据获取")
        
        # 输入区域
        col1, col2 = st.columns([2, 1])
        
        with col1:
            symbols_input = st.text_input(
                "输入股票代码 (多个用逗号分隔)",
                placeholder="例如: AAPL, MSFT, GOOGL",
                help="可以输入一个或多个股票代码，用逗号分隔"
            )
        
        with col2:
            default_end = datetime.now()
            default_start = default_end - timedelta(days=365)
            
            col2_1, col2_2 = st.columns(2)
            with col2_1:
                start_date = st.date_input(
                    "开始日期",
                    value=default_start,
                    max_value=datetime.now().date()
                )
            with col2_2:
                end_date = st.date_input(
                    "结束日期",
                    value=default_end,
                    max_value=datetime.now().date()
                )
        
        # 数据间隔选择
        interval = st.selectbox(
            "数据间隔",
            ["1d", "1wk", "1mo"],
            help="选择数据的间隔频率"
        )
        
        # 获取数据按钮
        if st.button("获取数据", type="primary", use_container_width=True):
            if symbols_input:
                with st.spinner("正在获取数据..."):
                    # 获取数据
                    data_dict = self.data_manager.fetch_stock_data(
                        symbols_input, start_date, end_date, interval
                    )
                    
                    # 保存数据
                    for symbol, data in data_dict.items():
                        if not data.empty:
                            success = self.data_manager.save_stock_data(symbol, data)
                            if success:
                                st.success(f"{symbol} 数据已保存到数据库")
                            else:
                                st.error(f"{symbol} 数据保存失败")
                    
                    # 显示获取的股票列表
                    if data_dict:
                        st.subheader("获取的股票列表")
                        stocks_df = pd.DataFrame([
                            {
                                'Symbol': symbol,
                                '记录数': len(data),
                                '开始日期': data.index.min().date(),
                                '结束日期': data.index.max().date(),
                                '状态': '✅ 成功'
                            }
                            for symbol, data in data_dict.items()
                        ])
                        st.dataframe(stocks_df, use_container_width=True)
            else:
                st.warning("请输入股票代码")
        
        # 显示已存储的股票
        st.subheader("已存储的股票")
        stored_symbols = self.data_manager.get_stored_symbols()
        
        if stored_symbols:
            cols = st.columns(4)
            for idx, symbol in enumerate(stored_symbols):
                with cols[idx % 4]:
                    if st.button(f"📈 {symbol}", key=f"btn_{symbol}"):
                        st.session_state['selected_symbol'] = symbol
                        st.rerun()
        else:
            st.info("暂无存储的股票数据")
    
    def data_view_page(self):
        """数据查看页面"""
        st.title("📊 数据查看与分析")
        
        # 选择股票
        stored_symbols = self.data_manager.get_stored_symbols()
        
        if not stored_symbols:
            st.warning("请先获取股票数据")
            return
        
        selected_symbol = st.selectbox(
            "选择股票代码",
            stored_symbols,
            key="data_view_symbol"
        )
        
        if selected_symbol:
            # 获取数据
            data = self.data_manager.get_stock_data(selected_symbol)
            
            if not data.empty:
                # 显示股票信息
                info = self.data_manager.get_stock_info(selected_symbol)
                self.visualizer.display_stock_info(info)
                
                st.markdown("---")
                
                # 显示数据摘要
                col1, col2, col3, col4, col5 = st.columns(5)
                
                with col1:
                    st.metric("数据点数量", len(data))
                with col2:
                    st.metric("开始日期", data.index.min().date())
                with col3:
                    st.metric("结束日期", data.index.max().date())
                with col4:
                    returns = (data['Close'].iloc[-1] / data['Close'].iloc[0] - 1) * 100
                    st.metric("期间收益率", f"{returns:.2f}%")
                with col5:
                    volatility = data['Close'].pct_change().std() * np.sqrt(252) * 100
                    st.metric("年化波动率", f"{volatility:.2f}%")
                
                st.markdown("---")
                
                # 标签页显示不同内容
                tab1, tab2, tab3, tab4 = st.tabs(["价格走势", "数据表格", "技术指标", "统计分析"])
                
                with tab1:
                    # 价格图表
                    fig_price = self.visualizer.plot_price_chart(data, selected_symbol)
                    if fig_price:
                        st.plotly_chart(fig_price, use_container_width=True)
                    
                    # 交易量图表
                    fig_volume = self.visualizer.plot_volume_chart(data, selected_symbol)
                    if fig_volume:
                        st.plotly_chart(fig_volume, use_container_width=True)
                
                with tab2:
                    # 数据显示
                    st.dataframe(data, use_container_width=True)
                    
                    # 数据统计
                    st.subheader("数据统计")
                    st.dataframe(data.describe(), use_container_width=True)
                
                with tab3:
                    # 技术指标
                    fig_indicators = self.visualizer.plot_technical_indicators(data, selected_symbol)
                    if fig_indicators:
                        st.plotly_chart(fig_indicators, use_container_width=True)
                    
                    # 计算更多技术指标
                    st.subheader("技术指标计算")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # 移动平均
                        ma_period = st.slider("移动平均周期", 5, 200, 50)
                        data[f'MA{ma_period}'] = data['Close'].rolling(window=ma_period).mean()
                        
                        fig_ma = go.Figure()
                        fig_ma.add_trace(go.Scatter(
                            x=data.index, y=data['Close'], name='Close', line=dict(color='blue')
                        ))
                        fig_ma.add_trace(go.Scatter(
                            x=data.index, y=data[f'MA{ma_period}'], 
                            name=f'MA{ma_period}', line=dict(color='red', dash='dash')
                        ))
                        fig_ma.update_layout(title=f"{selected_symbol} 移动平均线", height=400)
                        st.plotly_chart(fig_ma, use_container_width=True)
                    
                    with col2:
                        # 布林带
                        bb_period = st.slider("布林带周期", 10, 100, 20)
                        data['BB_Middle'] = data['Close'].rolling(window=bb_period).mean()
                        bb_std = data['Close'].rolling(window=bb_period).std()
                        data['BB_Upper'] = data['BB_Middle'] + 2 * bb_std
                        data['BB_Lower'] = data['BB_Middle'] - 2 * bb_std
                        
                        fig_bb = go.Figure()
                        fig_bb.add_trace(go.Scatter(
                            x=data.index, y=data['Close'], name='Close', line=dict(color='blue')
                        ))
                        fig_bb.add_trace(go.Scatter(
                            x=data.index, y=data['BB_Upper'], 
                            name='Upper Band', line=dict(color='gray', dash='dash')
                        ))
                        fig_bb.add_trace(go.Scatter(
                            x=data.index, y=data['BB_Middle'], 
                            name='Middle Band', line=dict(color='red', dash='dash')
                        ))
                        fig_bb.add_trace(go.Scatter(
                            x=data.index, y=data['BB_Lower'], 
                            name='Lower Band', line=dict(color='gray', dash='dash'),
                            fill='tonexty', fillcolor='rgba(128, 128, 128, 0.1)'
                        ))
                        fig_bb.update_layout(title=f"{selected_symbol} 布林带", height=400)
                        st.plotly_chart(fig_bb, use_container_width=True)
                
                with tab4:
                    # 统计分析
                    st.subheader("收益率分布")
                    
                    returns = data['Close'].pct_change().dropna()
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # 收益率直方图
                        fig_hist = px.histogram(
                            returns, 
                            nbins=50,
                            title="收益率分布直方图",
                            labels={'value': '收益率', 'count': '频率'}
                        )
                        fig_hist.update_layout(height=400)
                        st.plotly_chart(fig_hist, use_container_width=True)
                    
                    with col2:
                        # 统计指标
                        stats_df = pd.DataFrame({
                            '指标': ['均值', '标准差', '偏度', '峰度', '最小', '最大', '夏普比率'],
                            '值': [
                                f"{returns.mean()*100:.4f}%",
                                f"{returns.std()*100:.4f}%",
                                f"{returns.skew():.4f}",
                                f"{returns.kurtosis():.4f}",
                                f"{returns.min()*100:.4f}%",
                                f"{returns.max()*100:.4f}%",
                                f"{returns.mean()/returns.std()*np.sqrt(252):.4f}" if returns.std() > 0 else "N/A"
                            ]
                        })
                        st.dataframe(stats_df, use_container_width=True, hide_index=True)
                        
                        # Q-Q图
                        st.subheader("正态性检验 - Q-Q图")
                        import scipy.stats as stats
                        
                        fig_qq = go.Figure()
                        
                        # 计算理论分位数
                        (osm, osr), (slope, intercept, r) = stats.probplot(returns, dist="norm")
                        
                        fig_qq.add_trace(go.Scatter(
                            x=osm, y=osr, mode='markers', name='样本分位数'
                        ))
                        fig_qq.add_trace(go.Scatter(
                            x=osm, y=slope*osm + intercept, 
                            mode='lines', name='理论正态分布'
                        ))
                        
                        fig_qq.update_layout(
                            title="Q-Q图 (正态性检验)",
                            xaxis_title="理论分位数",
                            yaxis_title="样本分位数",
                            height=400
                        )
                        st.plotly_chart(fig_qq, use_container_width=True)
            else:
                st.warning(f"未找到 {selected_symbol} 的数据")
    
    def data_management_page(self):
        """数据管理页面"""
        st.title("🗃️ 数据管理")
        
        tab1, tab2, tab3 = st.tabs(["数据清理", "数据导出", "系统维护"])
        
        with tab1:
            st.subheader("数据清理")
            
            stored_symbols = self.data_manager.get_stored_symbols()
            
            if stored_symbols:
                selected_for_deletion = st.multiselect(
                    "选择要删除的股票数据",
                    stored_symbols
                )
                
                if selected_for_deletion:
                    if st.button("删除选中数据", type="secondary"):
                        for symbol in selected_for_deletion:
                            if self.data_manager.delete_stock_data(symbol):
                                st.success(f"已删除 {symbol} 的所有数据")
                            else:
                                st.error(f"删除 {symbol} 数据失败")
                        st.rerun()
                
                # 显示数据统计
                st.subheader("数据统计")
                summary = self.data_manager.get_data_summary()
                
                if summary:
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("股票数量", summary['stock_count'])
                    col2.metric("总记录数", summary['record_count'])
                    col3.metric("开始日期", summary['start_date'])
                    col4.metric("结束日期", summary['end_date'])
            else:
                st.info("暂无存储的股票数据")
        
        with tab2:
            st.subheader("数据导出")
            
            stored_symbols = self.data_manager.get_stored_symbols()
            
            if stored_symbols:
                export_symbol = st.selectbox("选择要导出的股票", stored_symbols)
                
                if export_symbol:
                    data = self.data_manager.get_stock_data(export_symbol)
                    
                    if not data.empty:
                        st.info(f"{export_symbol} 共有 {len(data)} 条记录")
                        
                        # 导出格式选择
                        export_format = st.radio(
                            "选择导出格式",
                            ["CSV", "Excel", "JSON"]
                        )
                        
                        if st.button("导出数据"):
                            if export_format == "CSV":
                                csv = data.to_csv()
                                st.download_button(
                                    label="下载CSV文件",
                                    data=csv,
                                    file_name=f"{export_symbol}_stock_data.csv",
                                    mime="text/csv"
                                )
                            elif export_format == "Excel":
                                excel_buffer = pd.ExcelWriter("temp.xlsx", engine='openpyxl')
                                data.to_excel(excel_buffer, sheet_name=export_symbol)
                                excel_buffer.close()
                                
                                with open("temp.xlsx", "rb") as f:
                                    st.download_button(
                                        label="下载Excel文件",
                                        data=f,
                                        file_name=f"{export_symbol}_stock_data.xlsx",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                    )
                            elif export_format == "JSON":
                                json_str = data.to_json(orient='records', date_format='iso')
                                st.download_button(
                                    label="下载JSON文件",
                                    data=json_str,
                                    file_name=f"{export_symbol}_stock_data.json",
                                    mime="application/json"
                                )
            else:
                st.info("暂无存储的股票数据")
        
        with tab3:
            st.subheader("系统维护")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("数据库大小", f"{os.path.getsize(self.data_manager.db_path)/1024/1024:.2f} MB")
            
            with col2:
                st.metric("数据目录", str(DATA_DIR))
            
            # 数据库优化选项
            if st.button("优化数据库", type="secondary"):
                try:
                    conn = sqlite3.connect(self.data_manager.db_path)
                    conn.execute("VACUUM")
                    conn.close()
                    st.success("数据库优化完成")
                except Exception as e:
                    st.error(f"优化失败: {str(e)}")
            
            # 清空所有数据
            if st.button("清空所有数据", type="primary"):
                if st.checkbox("确认要清空所有数据？此操作不可恢复！"):
                    try:
                        conn = sqlite3.connect(self.data_manager.db_path)
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM stocks")
                        cursor.execute("DELETE FROM stock_info")
                        conn.commit()
                        conn.close()
                        st.success("已清空所有数据")
                        st.rerun()
                    except Exception as e:
                        st.error(f"清空失败: {str(e)}")
    
    def system_settings_page(self):
        """系统设置页面"""
        st.title("⚙️ 系统设置")
        
        tab1, tab2 = st.tabs(["常规设置", "关于"])
        
        with tab1:
            st.subheader("数据获取设置")
            
            # API设置
            st.selectbox(
                "数据源",
                ["Yahoo Finance", "Alpha Vantage (待实现)", "IEX Cloud (待实现)"],
                disabled=True
            )
            
            # 缓存设置
            cache_enabled = st.checkbox("启用数据缓存", value=True)
            cache_duration = st.slider("缓存时间(天)", 1, 30, 7)
            
            # 自动更新设置
            auto_update = st.checkbox("启用自动数据更新")
            if auto_update:
                update_time = st.time_input("每日更新时间", value=datetime.strptime("16:00", "%H:%M").time())
            
            # 保存设置
            if st.button("保存设置"):
                settings = {
                    'cache_enabled': cache_enabled,
                    'cache_duration': cache_duration,
                    'auto_update': auto_update,
                    'update_time': str(update_time) if auto_update else None
                }
                
                with open(DATA_DIR / "settings.json", "w") as f:
                    json.dump(settings, f)
                
                st.success("设置已保存")
        
        with tab2:
            st.subheader("关于")
            
            st.markdown("""
            ### 美股量化分析系统 v1.0
            
            **功能特性：**
            - 📥 多股票数据获取与存储
            - 📊 交互式数据可视化
            - 📈 技术指标计算
            - 📋 数据管理与导出
            - 🗃️ SQLite数据库存储
            
            **技术栈：**
            - Python 3.x
            - Streamlit (GUI框架)
            - yfinance (数据获取)
            - Plotly (可视化)
            - SQLite (数据存储)
            
            **后续功能规划：**
            1. 机器学习预测模型
            2. 回测系统
            3. 实时数据更新
            4. 多因子分析
            5. 投资组合优化
            
            **使用说明：**
            1. 在"数据获取"页面输入股票代码
            2. 选择日期范围获取数据
            3. 在"数据查看"页面进行分析
            4. 使用"数据管理"进行维护
            
            **注意事项：**
            - 数据来源于Yahoo Finance
            - 数据可能存在延迟
            - 仅供学习研究使用
            """)

def main():
    """主函数"""
    # 应用标题
    st.title("📈 美股量化分析系统")
    st.markdown("---")
    
    # 初始化系统
    if 'system' not in st.session_state:
        st.session_state.system = StockAnalysisSystem()
    
    # 运行系统
    st.session_state.system.run()

if __name__ == "__main__":
    main()
