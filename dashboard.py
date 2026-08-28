#!/usr/bin/env python3
"""
Institutional Forex Strategy & Market Opportunity Dashboard
============================================================
Streamlit Interactive Web Application
Run with:
  streamlit run dashboard.py
"""

import os
import sys
import time
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# Ensure root folder is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import TARGET_SYMBOLS, CURRENCIES, SESSIONS_UTC
from data_provider import DataProvider
from market_profiler import MarketProfiler
from confluence_scanner import ConfluenceScanner
from recommendation_engine import RecommendationEngine

from scalper_engine import ScalperEngine, SCALP_TARGET_SYMBOLS
from news_shield import NewsShield
from order_flow_radar import OrderFlowRadar
from position_sizer import PositionSizer

# Streamlit Page Config
st.set_page_config(
    page_title="Institutional Forex & Scalper Analyser",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS styling
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        color: #1E88E5;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.0rem;
        color: #90A4AE;
        margin-bottom: 1.2rem;
    }
    .metric-card {
        background-color: #1E222D;
        border: 1px solid #2A2E39;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 10px;
    }
    .badge-buy {
        background-color: #26a69a;
        color: white;
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: bold;
    }
    .badge-sell {
        background-color: #ef5350;
        color: white;
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: bold;
    }
    .badge-scalp {
        background-color: #ff9800;
        color: black;
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: bold;
    }
    .badge-grade-aplus {
        background-color: #2e7d32;
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
    .badge-grade-a {
        background-color: #1565c0;
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
    .badge-grade-b {
        background-color: #f57f17;
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


def create_tradingview_pro_chart(df: pd.DataFrame, title: str, entry: float, sl: float, tp1: float, tp2: float, sl_pips: float, tp1_pips: float, tp2_pips: float, direction: str) -> go.Figure:
    """Builds a sleek TradingView-style dark pro chart with neon glowing candlesticks, EMAs, volume, and execution zones."""
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.80, 0.20]
    )

    df_c = df.copy()
    df_c['ema9'] = df_c['close'].ewm(span=9, adjust=False).mean()
    df_c['ema21'] = df_c['close'].ewm(span=21, adjust=False).mean()

    # 1. Candlestick Trace
    fig.add_trace(go.Candlestick(
        x=df_c['time'],
        open=df_c['open'],
        high=df_c['high'],
        low=df_c['low'],
        close=df_c['close'],
        increasing_line_color='#00E676',
        increasing_fillcolor='#00E676',
        decreasing_line_color='#FF1744',
        decreasing_fillcolor='#FF1744',
        name="Price Action",
        showlegend=False
    ), row=1, col=1)

    # 2. Dynamic EMA Overlays
    fig.add_trace(go.Scatter(
        x=df_c['time'], y=df_c['ema9'],
        line=dict(color='#00E5FF', width=1.5),
        name="EMA 9 (Momentum)",
        opacity=0.85
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df_c['time'], y=df_c['ema21'],
        line=dict(color='#FF9100', width=1.5),
        name="EMA 21 (Trend)",
        opacity=0.85
    ), row=1, col=1)

    # 3. Horizontal Levels & Annotations
    is_buy = direction == "BUY"

    fig.add_hline(
        y=entry, line_dash="dash", line_color="#FFFFFF", line_width=1.5,
        annotation_text=f"  ENTRY: {entry}", annotation_position="top left",
        annotation_font=dict(color="#FFFFFF", size=10, family="monospace"),
        row=1, col=1
    )

    fig.add_hline(
        y=sl, line_dash="solid", line_color="#FF1744", line_width=2.0,
        annotation_text=f"  SL: {sl} (-{sl_pips}p)",
        annotation_position="bottom left" if is_buy else "top left",
        annotation_font=dict(color="#FF5252", size=10, family="monospace"),
        row=1, col=1
    )

    fig.add_hline(
        y=tp1, line_dash="solid", line_color="#00E676", line_width=2.0,
        annotation_text=f"  TP1: {tp1} (+{tp1_pips}p)",
        annotation_position="top left" if is_buy else "bottom left",
        annotation_font=dict(color="#69F0AE", size=10, family="monospace"),
        row=1, col=1
    )

    fig.add_hline(
        y=tp2, line_dash="dot", line_color="#40C4FF", line_width=2.0,
        annotation_text=f"  TP2: {tp2} (+{tp2_pips}p)",
        annotation_position="top left" if is_buy else "bottom left",
        annotation_font=dict(color="#40C4FF", size=10, family="monospace"),
        row=1, col=1
    )

    # Shaded Zones
    profit_top = max(entry, tp2)
    profit_bottom = min(entry, tp2)
    fig.add_hrect(
        y0=profit_bottom, y1=profit_top,
        fillcolor="rgba(0, 230, 118, 0.08)",
        line_width=0, layer="below", row=1, col=1
    )

    risk_top = max(entry, sl)
    risk_bottom = min(entry, sl)
    fig.add_hrect(
        y0=risk_bottom, y1=risk_top,
        fillcolor="rgba(255, 23, 68, 0.08)",
        line_width=0, layer="below", row=1, col=1
    )

    # 4. Volume Bars Subplot
    vol_colors = np.where(df_c['close'] >= df_c['open'], '#00E676', '#FF1744')
    fig.add_trace(go.Bar(
        x=df_c['time'],
        y=df_c['volume'],
        marker_color=vol_colors,
        opacity=0.6,
        name="Tick Volume",
        showlegend=False
    ), row=2, col=1)

    # 5. TradingView Pro Theme Layout
    fig.update_layout(
        height=420,
        margin=dict(l=10, r=45, t=25, b=10),
        xaxis_rangeslider_visible=False,
        xaxis2_rangeslider_visible=False,
        template="plotly_dark",
        paper_bgcolor="#131722",
        plot_bgcolor="#131722",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=10, color="#90CAF9")
        ),
        xaxis=dict(showgrid=True, gridcolor="rgba(255, 255, 255, 0.05)"),
        yaxis=dict(showgrid=True, gridcolor="rgba(255, 255, 255, 0.05)", side="right"),
        xaxis2=dict(showgrid=False),
        yaxis2=dict(showgrid=False, showticklabels=False)
    )
    return fig


def create_interactive_custom_chart(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    show_ema_fast: bool = True,
    show_ema_slow: bool = True,
    show_vwap: bool = True,
    show_bb: bool = False,
    show_volume: bool = True
) -> go.Figure:
    """Builds an interactive Studio chart with customizable indicator overlays."""
    fig = make_subplots(
        rows=2 if show_volume else 1,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.80, 0.20] if show_volume else [1.0]
    )

    df_c = df.copy()

    # 1. Candlesticks
    fig.add_trace(go.Candlestick(
        x=df_c['time'],
        open=df_c['open'],
        high=df_c['high'],
        low=df_c['low'],
        close=df_c['close'],
        increasing_line_color='#00E676',
        increasing_fillcolor='#00E676',
        decreasing_line_color='#FF1744',
        decreasing_fillcolor='#FF1744',
        name="Price Action",
        showlegend=False
    ), row=1, col=1)

    # 2. Fast EMAs
    if show_ema_fast:
        df_c['ema9'] = df_c['close'].ewm(span=9, adjust=False).mean()
        df_c['ema21'] = df_c['close'].ewm(span=21, adjust=False).mean()
        fig.add_trace(go.Scatter(x=df_c['time'], y=df_c['ema9'], line=dict(color='#00E5FF', width=1.5), name="EMA 9 (Momentum)"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_c['time'], y=df_c['ema21'], line=dict(color='#FF9100', width=1.5), name="EMA 21 (Trend)"), row=1, col=1)

    # 3. Macro EMAs
    if show_ema_slow:
        df_c['ema50'] = df_c['close'].ewm(span=50, adjust=False).mean()
        df_c['ema200'] = df_c['close'].ewm(span=200, adjust=False).mean() if len(df_c) >= 200 else df_c['ema50']
        fig.add_trace(go.Scatter(x=df_c['time'], y=df_c['ema50'], line=dict(color='#E040FB', width=1.5), name="EMA 50 (Dynamic S/R)"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_c['time'], y=df_c['ema200'], line=dict(color='#FFD600', width=2.0, dash="dot"), name="EMA 200 (Macro)"), row=1, col=1)

    # 4. Bollinger Bands
    if show_bb:
        sma20 = df_c['close'].rolling(20).mean()
        std20 = df_c['close'].rolling(20).std()
        df_c['bb_upper'] = sma20 + (std20 * 2.0)
        df_c['bb_lower'] = sma20 - (std20 * 2.0)
        fig.add_trace(go.Scatter(x=df_c['time'], y=df_c['bb_upper'], line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash="dash"), name="BB Upper (2σ)"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_c['time'], y=df_c['bb_lower'], line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash="dash"), name="BB Lower (2σ)", fill="tonexty", fillcolor="rgba(255, 255, 255, 0.03)"), row=1, col=1)

    # 5. Volume Subplot
    if show_volume:
        vol_colors = np.where(df_c['close'] >= df_c['open'], '#00E676', '#FF1744')
        fig.add_trace(go.Bar(
            x=df_c['time'],
            y=df_c['volume'],
            marker_color=vol_colors,
            opacity=0.6,
            name="Tick Volume",
            showlegend=False
        ), row=2, col=1)

    fig.update_layout(
        title=f"📈 {symbol} — {timeframe} Interactive Candle Chart",
        height=520,
        margin=dict(l=10, r=45, t=40, b=10),
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        paper_bgcolor="#131722",
        plot_bgcolor="#131722",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10, color="#90CAF9")),
        xaxis=dict(showgrid=True, gridcolor="rgba(255, 255, 255, 0.05)"),
        yaxis=dict(showgrid=True, gridcolor="rgba(255, 255, 255, 0.05)", side="right")
    )
    return fig



dp = DataProvider()
profiler = MarketProfiler(dp)
scanner = ConfluenceScanner(dp)
engine = RecommendationEngine(dp)
scalper = ScalperEngine(dp)
news_shield = NewsShield()
order_flow = OrderFlowRadar(dp)
position_sizer = PositionSizer(dp)

# ----------------------------------------------------------------------
# SIDEBAR
# ----------------------------------------------------------------------
st.sidebar.image("https://img.icons8.com/fluency/96/bullish.png", width=64)
st.sidebar.markdown("### ⚡ Live Forex Scalper & Analyser")
st.sidebar.markdown("---")

auto_refresh = st.sidebar.checkbox("⚡ Live Auto-Refresh", value=True)
refresh_interval = st.sidebar.select_slider(
    "⏱️ Scan Interval:",
    options=[5, 8, 12, 20, 30],
    value=8,
    format_func=lambda x: f"{x}s"
)

if st.sidebar.button("🔄 Rescan Market Now", use_container_width=True, type="primary"):
    st.cache_data.clear()
    st.rerun()

session_info = profiler.get_current_session_info()
st.sidebar.markdown(f"**⏰ UTC Time:** `{session_info['utc_time']}`")
if session_info["is_killzone"]:
    st.sidebar.success(f"⚡ **{session_info['killzone_name']}**")
else:
    st.sidebar.info(f"🌐 **{', '.join(session_info['active_sessions'])}**")
st.sidebar.markdown(f"**Volume Status:** {session_info['volume_status']}")
st.sidebar.markdown("---")

# 🛡️ Economic News Shield Status
st.sidebar.markdown("### 🛡️ High-Impact News Shield")
upcoming_news = news_shield.get_upcoming_high_impact_events(hours_ahead=12)
if upcoming_news:
    next_ev = upcoming_news[0]
    st.sidebar.info(f"📅 **Next:** `{next_ev['Currency']}` {next_ev['Event Title']} ({next_ev['Minutes Away']})")
    with st.sidebar.expander("📋 Upcoming Red Folder Events", expanded=False):
        st.dataframe(pd.DataFrame(upcoming_news)[["Time (UTC)", "Currency", "Event Title", "Minutes Away"]], use_container_width=True)
else:
    st.sidebar.success("🟢 No High-Impact News in next 12h")
st.sidebar.markdown("---")

# Position Sizing Calculator
st.sidebar.markdown("### 🎯 Position Size Calculator")
account_balance = st.sidebar.number_input(
    "Account Balance (€):",
    min_value=100.0,
    max_value=1_000_000.0,
    value=10_000.0,
    step=500.0,
    format="%.0f"
)
risk_pct_input = st.sidebar.slider(
    "Risk per Trade (%):",
    min_value=0.25,
    max_value=3.0,
    value=1.0,
    step=0.25,
    format="%.2f%%"
)
st.sidebar.caption(f"Max Risk Amount: **€{account_balance * risk_pct_input / 100:.2f}** per trade")
st.sidebar.markdown("---")

# Filters
st.sidebar.markdown("### 🔍 Filter Opportunities")
search_sym = st.sidebar.text_input("🔎 Search Symbol:", placeholder="e.g. EUR, USD, JPY, XAU").strip().upper()
killzone_only = st.sidebar.checkbox("⚡ Show Only Killzone Setups", value=False)
grade_filter = st.sidebar.multiselect(
    "Quality Grade:",
    ["GRADE A+ (Institutional Prime)", "GRADE A (High Conviction)", "GRADE B (Moderate Opportunity)"],
    default=["GRADE A+ (Institutional Prime)", "GRADE A (High Conviction)", "GRADE B (Moderate Opportunity)"]
)
dir_filter = st.sidebar.radio("Direction:", ["ALL", "BUY Only", "SELL Only"])

# ----------------------------------------------------------------------
# HEADER
# ----------------------------------------------------------------------
st.markdown("<div class='main-title'>⚡ Institutional Forex Strategy & Live Scalper</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-title'>Real-Time Market Confluences, Liquidity Sweeps, Session VWAP & High-Probability Execution</div>", unsafe_allow_html=True)

# ----------------------------------------------------------------------
# PRE-SCAN FOR DYNAMIC NOTIFICATIONS
# ----------------------------------------------------------------------
csm = profiler.calculate_currency_strength()
opps = engine.scan_all_opportunities()
scalp_opps = scalper.scan_all_scalps()

# Top Live Opportunity Alert
if opps:
    best_op = opps[0]
    st.info(f"🔥 **Top Institutional Setup:** `{best_op['symbol']}` **{best_op['direction']}** ({best_op['grade']} — Score: `{best_op['quality_score']}/100`) | R:R: `{best_op['risk_reward']}`")

# ----------------------------------------------------------------------
# MAIN TABS INTERFACE (6 Interactive Modules)
# ----------------------------------------------------------------------
tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs([
    f"🎯 Day-Trade Setups ({len(opps)} Active)",
    f"⚡ Live Scalping Radar ({len(scalp_opps)} Scalps)",
    "📊 Currency Strength Matrix",
    "📈 Daily ADR & Market Profiler",
    "🧪 Strategy Backtester",
    "📈 Interactive Chart Studio (Live)"
])

# ----------------------------------------------------------------------
# TAB 0: DAY-TRADE SETUPS (M15 / H1) - PRIMARY VIEW
# ----------------------------------------------------------------------
with tab0:
    # Filter opportunities
    filtered_opps = []
    for op in opps:
        if search_sym and search_sym not in op["symbol"]:
            continue
        if killzone_only and "Killzone" not in op.get("session", ""):
            continue
        if any(g.split()[0] in op["grade"] for g in grade_filter):
            if dir_filter == "ALL" or (dir_filter == "BUY Only" and op["direction"] == "BUY") or (dir_filter == "SELL Only" and op["direction"] == "SELL"):
                filtered_opps.append(op)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Pairs Scanned", len(TARGET_SYMBOLS))
    with col2:
        st.metric("Total Setups Found", len(opps))
    with col3:
        st.metric("Filtered Setups", len(filtered_opps))
    with col4:
        st.metric("Active Session", session_info["active_sessions"][0].split()[0])

    st.markdown("---")

    if not filtered_opps:
        st.info("💡 No setups match your current filter at this moment. The market is being monitored.")
    else:
        for idx, opp in enumerate(filtered_opps, 1):
            sym = opp["symbol"]
            is_buy = opp["direction"] == "BUY"
            badge_class = "badge-buy" if is_buy else "badge-sell"
            
            grade = opp["grade"]
            if "A+" in grade:
                grade_class = "badge-grade-aplus"
            elif "A" in grade:
                grade_class = "badge-grade-a"
            else:
                grade_class = "badge-grade-b"

            with st.expander(f"#{idx} | **{sym}** [{opp['direction']}] — {grade} (Score: {opp['quality_score']}/100)", expanded=(idx == 1)):
                st.markdown(f"""
                <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 12px;">
                    <span class='{badge_class}'>{opp['direction']}</span>
                    <span class='{grade_class}'>{grade}</span>
                    <span style='color: #CFD8DC; font-weight: 500;'>{opp['setup_name']}</span>
                </div>
                """, unsafe_allow_html=True)

                # Key Metrics Cards
                kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
                kpi1.metric("Entry Price", f"{opp['entry_price']}")
                kpi2.metric("Stop Loss", f"{opp['stop_loss']}", f"-{opp['sl_pips']} pips", delta_color="inverse")
                kpi3.metric("Take Profit 1 (1:2)", f"{opp['take_profit_1']}", f"+{opp['tp1_pips']} pips")
                kpi4.metric("Take Profit 2 (1:3.5)", f"{opp['take_profit_2']}", f"+{opp['tp2_pips']} pips")
                kpi5.metric("ADR Consumed", f"{opp.get('adr_consumed_pct', 0)}%", f"{opp.get('adr_remaining_pips', 0)} pips left")

                # Interactive Risk & PnL Simulator
                with st.expander(f"🧮 Interactive Risk & PnL Simulator for {sym}", expanded=False):
                    calc_col1, calc_col2 = st.columns(2)
                    with calc_col1:
                        sim_risk_pct = st.slider("Simulate Risk per Trade (%):", 0.25, 5.0, float(risk_pct_input), 0.25, key=f"sim_r_dt_{sym}_{idx}")
                        sim_ps = position_sizer.calculate_lot_size(sym, opp['sl_pips'], account_balance, sim_risk_pct)
                    with calc_col2:
                        sim_risk_eur = sim_ps['risk_amount']
                        sim_tp1_eur = round(sim_risk_eur * 2.0, 2)
                        sim_tp2_eur = round(sim_risk_eur * 3.5, 2)
                        st.markdown(f"**Recommended Size:** `{sim_ps['lot_size']} lots` | **Max Loss (SL):** `-€{sim_risk_eur:.2f}`")
                        st.markdown(f"**Target TP1 Profit (1:2.0):** `+€{sim_tp1_eur:.2f}` (+{sim_risk_pct * 2.0:.1f}%)")
                        st.markdown(f"**Target TP2 Profit (1:3.5):** `+€{sim_tp2_eur:.2f}` (+{sim_risk_pct * 3.5:.1f}%)")

                # Confluences & Chart Layout
                chart_col, details_col = st.columns([3, 2])

                with details_col:
                    htf = opp.get('htf_trend', {})
                    d1_t = htf.get('d1_trend', 'NEUTRAL')
                    h4_t = htf.get('h4_trend', 'NEUTRAL')
                    h1_t = htf.get('h1_trend', 'NEUTRAL')
                    align_lbl = htf.get('alignment_label', 'N/A')
                    
                    st.markdown("#### 🧭 Trend Alignment (D1 / H4 / H1)")
                    st.info(f"**D1:** `{d1_t}` ➔ **H4:** `{h4_t}` ➔ **H1:** `{h1_t}`  \n🏷️ **{align_lbl}**")

                    st.markdown("#### 🔍 Institutional Confluences")
                    for r in opp["reasons"]:
                        st.markdown(f"✅ **{r}**")

                with details_col:
                    st.markdown("#### 📋 Setup Specifications")
                    st.markdown(f"* **Order Type:** `{opp.get('order_type', 'MARKET')}`")
                    st.markdown(f"* **Risk:Reward:** `{opp.get('risk_reward', '1:2.0')}`")
                    st.markdown(f"* **Current Spread:** `{opp.get('spread_pips', 0)} pips`")
                    st.markdown(f"* **Session Window:** `{opp.get('session', 'Active')}`")
                    st.warning(f"⚠️ **Invalidation:** {opp.get('invalidation', 'N/A')}")

                with chart_col:
                    st.markdown(f"#### 📈 {sym} M15 Institutional Pro Chart")
                    df_chart = dp.get_rates(sym, "M15", count=60)
                    if df_chart is not None and not df_chart.empty:
                        fig = create_tradingview_pro_chart(
                            df=df_chart,
                            title=f"{sym} M15 Pro Chart",
                            entry=opp['entry_price'],
                            sl=opp['stop_loss'],
                            tp1=opp['take_profit_1'],
                            tp2=opp['take_profit_2'],
                            sl_pips=opp['sl_pips'],
                            tp1_pips=opp['tp1_pips'],
                            tp2_pips=opp['tp2_pips'],
                            direction=opp['direction']
                        )
                        st.plotly_chart(fig, use_container_width=True)


# ----------------------------------------------------------------------
# TAB 1: LIVE SCALPING RADAR (M1/M5)
# ----------------------------------------------------------------------
with tab1:
    st.markdown("### ⚡ Live Precision Forex Scalper (M1 / M5 High-Frequency Radar)")
    st.markdown("Identifies high-speed institutional micro-structure breakouts, liquidity grabs, and volume surges with tight **3 - 6 pip Stop Losses**.")

    # Filter scalps by search if entered
    filtered_scalps = [s for s in scalp_opps if not search_sym or search_sym in s["symbol"]]

    sc_col1, sc_col2, sc_col3, sc_col4 = st.columns(4)
    sc_col1.metric("Scalp Target Pairs", len(SCALP_TARGET_SYMBOLS))
    sc_col2.metric("Active Scalps Found", len(filtered_scalps))
    sc_col3.metric("Max Spread Filter", "<= 1.5 pips")
    sc_col4.metric("Avg Trade Duration", "3 - 15 min")

    st.markdown("---")

    if not filtered_scalps:
        st.info("💡 No high-conviction M1/M5 scalps active right this second. Continuous Auto-Refresh is scanning live candle by candle.")
    else:
        for idx, sc in enumerate(filtered_scalps, 1):
            sym = sc["symbol"]
            is_buy = sc["direction"] == "BUY"
            badge_class = "badge-buy" if is_buy else "badge-sell"

            with st.expander(f"⚡ SCALP #{idx} | **{sym}** [{sc['direction']}] — {sc['grade']} (Score: {sc['quality_score']}/100)", expanded=True):
                st.markdown(f"""
                <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 12px;">
                    <span class='{badge_class}'>{sc['direction']} SCALP</span>
                    <span class='badge-scalp'>{sc['setup_name']}</span>
                    <span style='color: #81C784; font-weight: bold;'>⏱️ Duration: {sc['est_duration']} | Spread: {sc['spread_pips']}p</span>
                </div>
                """, unsafe_allow_html=True)

                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric("Entry Price", f"{sc['entry_price']}")
                k2.metric("Tight SL", f"{sc['stop_loss']}", f"-{sc['sl_pips']} pips", delta_color="inverse")
                k3.metric("Quick TP1 (1:2)", f"{sc['take_profit_1']}", f"+{sc['tp1_pips']} pips")
                k4.metric("Runner TP2 (1:3.2)", f"{sc['take_profit_2']}", f"+{sc['tp2_pips']} pips")
                k5.metric("Signal Time", f"{sc['timestamp']}")

                # Position size row
                ps = position_sizer.get_size_for_signal(sc, account_balance, risk_pct_input)
                ps_col1, ps_col2, ps_col3 = st.columns(3)
                ps_col1.metric("📊 Lot Size (1% Risk)", f"{ps['lot_size']:.2f} lots", f"Risk: €{ps['risk_amount']:.2f}", delta_color="off")
                ps_col2.metric("💰 Pip Value / Lot", f"€{ps['pip_value']:.3f}")
                ps_col3.metric("⚖️ Risk/Pip at Size", f"€{ps['risk_per_pip']:.3f}")

                # Interactive Risk & PnL Simulator for Scalp
                with st.expander(f"🧮 Interactive Scalp Risk & PnL Simulator for {sym}", expanded=False):
                    calc_col1, calc_col2 = st.columns(2)
                    with calc_col1:
                        sim_risk_pct = st.slider("Simulate Risk %:", 0.25, 5.0, float(risk_pct_input), 0.25, key=f"sim_r_sc_{sym}_{idx}")
                        sim_ps = position_sizer.calculate_lot_size(sym, sc['sl_pips'], account_balance, sim_risk_pct)
                    with calc_col2:
                        sim_risk_eur = sim_ps['risk_amount']
                        sim_tp1_eur = round(sim_risk_eur * 2.0, 2)
                        sim_tp2_eur = round(sim_risk_eur * 3.2, 2)
                        st.markdown(f"**Lots:** `{sim_ps['lot_size']} lots` | **Max Loss:** `-€{sim_risk_eur:.2f}`")
                        st.markdown(f"**Quick TP1 Gain (1:2.0):** `+€{sim_tp1_eur:.2f}` (+{sim_risk_pct * 2.0:.1f}%)")
                        st.markdown(f"**Runner TP2 Gain (1:3.2):** `+€{sim_tp2_eur:.2f}` (+{sim_risk_pct * 3.2:.1f}%)")

                sc_chart_col, sc_det_col = st.columns([3, 2])

                with sc_det_col:
                    st.markdown("#### 📋 Gate Verification Checklist")
                    if "gate_checklist" in sc:
                        for g in sc["gate_checklist"]:
                            st.markdown(f"✅ **{g['gate']}**: `{g['detail']}`")
                    else:
                        for r in sc["reasons"]:
                            st.markdown(f"🔥 **{r}**")

                    st.markdown("#### 🎯 Execution & Trailing Roadmap")
                    if "execution_roadmap" in sc:
                        rm = sc["execution_roadmap"]
                        st.info(f"⚪ **Entry:** `{rm['entry_price']}` ➔ 🛡️ **BE Lock:** `{rm['be_price']}` (+{rm['be_pips']}p) ➔ 🟢 **TP1:** `{rm['tp1_price']}` (+{rm['tp1_pips']}p) ➔ 🚀 **TP2:** `{rm['tp2_price']}` (+{rm['tp2_pips']}p)")
                    else:
                        st.markdown(f"* **Order:** `MARKET {sc['direction']}` | **R:R:** `{sc['risk_reward']}`")

                with sc_chart_col:
                    st.markdown(f"#### 📈 {sym} M1 Sniper Scalp Pro Chart")
                    df_m1_c = dp.get_rates(sym, "M1", count=50)
                    if df_m1_c is not None and not df_m1_c.empty:
                        fig_sc = create_tradingview_pro_chart(
                            df=df_m1_c,
                            title=f"{sym} M1 Scalp Chart",
                            entry=sc['entry_price'],
                            sl=sc['stop_loss'],
                            tp1=sc['take_profit_1'],
                            tp2=sc['take_profit_2'],
                            sl_pips=sc['sl_pips'],
                            tp1_pips=sc['tp1_pips'],
                            tp2_pips=sc['tp2_pips'],
                            direction=sc['direction']
                        )
                        st.plotly_chart(fig_sc, use_container_width=True)

    # ------------------------------------------------------------------
    # M1 ORDER FLOW & TICK VELOCITY MICRO-HEATMAP
    # ------------------------------------------------------------------
    st.markdown("---")
    st.markdown("### 🎯 Live M1 Order Flow & Tick Velocity Micro-Heatmap")
    st.markdown("Real-time tick accumulation speed and intra-bar buyer/seller delta pressure across key scalping assets:")

    of_matrix = order_flow.get_order_flow_matrix()
    if of_matrix:
        of_rows = []
        for r in of_matrix:
            delta_bar = f"🟢 Buy {r['buyer_delta_pct']:.0f}% / 🔴 Sell {r['seller_delta_pct']:.0f}%"
            of_rows.append({
                "Symbol": r["symbol"],
                "Live Price": f"{r['current_price']:.5f}",
                "Spread": f"{r['spread_pips']:.1f} p",
                "1m Tick Vol": r["tick_volume"],
                "Tick Velocity": f"{r['velocity_ratio']:.2f}x",
                "M1 Body": f"{r['body_pips']:.1f} p",
                "Buyer / Seller Delta": delta_bar,
                "Liquidity State": r["state"]
            })

        of_df = pd.DataFrame(of_rows)
        st.dataframe(of_df, use_container_width=True, hide_index=True)

# ----------------------------------------------------------------------
# TAB 2: CURRENCY STRENGTH MATRIX (CSM)
# ----------------------------------------------------------------------
with tab2:
    st.markdown("### 📊 Real-Time Institutional Currency Strength Matrix (CSM)")
    st.markdown("Evaluates capital rotation across the **8 Major Currencies** by analyzing 28 Forex cross pairs.")

    csm_scores = profiler.calculate_currency_strength()
    csm_df = pd.DataFrame(list(csm_scores.items()), columns=["Currency", "Strength Score"])
    csm_df["Color"] = csm_df["Strength Score"].apply(lambda x: "#26a69a" if x > 0 else "#ef5350")

    col_csm1, col_csm2 = st.columns([3, 2])

    with col_csm1:
        # Bar Chart
        fig_bar = go.Figure(go.Bar(
            x=csm_df["Currency"],
            y=csm_df["Strength Score"],
            marker_color=csm_df["Color"],
            text=csm_df["Strength Score"].apply(lambda x: f"{x:+.2f}"),
            textposition="auto"
        ))
        fig_bar.update_layout(
            title="Relative Currency Strength (-10 to +10 Scale)",
            height=380,
            template="plotly_dark",
            paper_bgcolor="#131722",
            plot_bgcolor="#131722",
            yaxis=dict(range=[-11, 11])
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_csm2:
        # Currency ranking table
        st.markdown("#### 🏆 Currency Ranking & Flow")
        for rank, (curr, score) in enumerate(csm_scores.items(), 1):
            color = "#26a69a" if score > 0 else "#ef5350"
            status = "STRONG ACCUMULATION" if score >= 3.0 else ("DISTRIBUTION" if score <= -3.0 else "NEUTRAL")
            st.markdown(f"**#{rank} {curr}**: `{score:+.2f}` — <span style='color: {color}; font-weight: bold;'>{status}</span>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 🌐 Top Currency Pair Divergences (Strong vs Weak Matchups)")
    divergences = []
    for sym in TARGET_SYMBOLS:
        if sym in ("XAUUSD", "XAGUSD"):
            continue
        d = profiler.get_pair_strength_divergence(sym, csm_scores)
        divergences.append({
            "Pair": sym,
            "Base Curr": d["base_currency"],
            "Base Score": d["base_score"],
            "Quote Curr": d["quote_currency"],
            "Quote Score": d["quote_score"],
            "Net Divergence": d["net_divergence"],
            "Institutional Bias": d["bias"]
        })

    div_df = pd.DataFrame(divergences).sort_values(by="Net Divergence", key=abs, ascending=False)
    st.dataframe(div_df, use_container_width=True)

    st.markdown("---")
    st.markdown("### 🔄 Interactive Currency Pair Matchmaker")
    m_col1, m_col2, m_col3 = st.columns(3)
    with m_col1:
        base_curr = st.selectbox("Base Currency (Primary):", CURRENCIES, index=0, key="match_base")
    with m_col2:
        quote_options = [c for c in CURRENCIES if c != base_curr]
        quote_curr = st.selectbox("Quote Currency (Opposing):", quote_options, index=min(3, len(quote_options)-1), key="match_quote")
    with m_col3:
        b_score = csm_scores.get(base_curr, 0.0)
        q_score = csm_scores.get(quote_curr, 0.0)
        net_diff = round(b_score - q_score, 2)
        if net_diff >= 3.0:
            bias_res = "🟢 STRONG BUY"
        elif net_diff >= 1.2:
            bias_res = "🟢 MODERATE BUY"
        elif net_diff <= -3.0:
            bias_res = "🔴 STRONG SELL"
        elif net_diff <= -1.2:
            bias_res = "🔴 MODERATE SELL"
        else:
            bias_res = "⚪ NEUTRAL / RANGE"
        st.metric(f"Matchup: {base_curr}/{quote_curr}", bias_res, f"Net Divergence: {net_diff:+.2f}")

# ----------------------------------------------------------------------
# TAB 3: DAILY MARKET & ADR PROFILER
# ----------------------------------------------------------------------
with tab3:
    st.markdown("### 📈 Daily Volatility & ADR (Average Daily Range) Profiler")
    st.markdown("Monitors ADR capacity to ensure you never trade into exhausted daily moves.")

    adr_records = []
    for sym in TARGET_SYMBOLS:
        adr = profiler.calculate_adr_profile(sym)
        htf = profiler.get_htf_trend_bias(sym)
        adr_records.append({
            "Symbol": sym,
            "ADR (14 Days)": f"{adr['adr_pips']} p",
            "Today's Range": f"{adr['today_range_pips']} p",
            "% ADR Consumed": adr['pct_consumed'],
            "Remaining Capacity": f"{adr['remaining_pips']} p",
            "D1 Trend": htf.get('d1_trend', 'NEUTRAL'),
            "H4 Trend": htf.get('h4_trend', 'NEUTRAL'),
            "H1 Trend": htf.get('h1_trend', 'NEUTRAL'),
            "HTF Alignment": htf.get('alignment_label', htf['bias']),
            "Status": adr['status']
        })

    adr_df = pd.DataFrame(adr_records).sort_values(by="% ADR Consumed", ascending=False)
    st.dataframe(adr_df, use_container_width=True)

# ----------------------------------------------------------------------
# TAB 4: STRATEGY BACKTESTER / VALIDATOR
# ----------------------------------------------------------------------
with tab4:
    st.markdown("### 🧪 Institutional Strategy Backtester & Performance Validator")
    st.markdown("Simulate high-probability institutional setups over historical MT5 data with realistic Killzones, Spread costs, MTF consensus, and Breakeven management.")

    from backtester import InstitutionalBacktester
    bt = InstitutionalBacktester(dp)

    b_col1, b_col2, b_col3, b_col4, b_col5 = st.columns(5)
    with b_col1:
        strategy_choice = st.selectbox("Strategy Model:", [
            "MTF Momentum Consensus (High Edge)",
            "Asian Sweep & Range Target"
        ], index=0)
        strat_key = "MTF_TREND" if "Momentum" in strategy_choice else "SESSION_TARGET"
    with b_col2:
        test_symbol = st.selectbox("Asset / Pair:", TARGET_SYMBOLS, index=0) # Default EURUSD
    with b_col3:
        test_bars = st.slider("Historical M15 Bars:", 500, 3000, 2000, step=250)
    with b_col4:
        min_rr = st.selectbox("Target R:R at TP1:", [1.5, 1.8, 2.0, 2.5], index=2)
    with b_col5:
        risk_pct = st.number_input("Risk Per Trade (%):", min_value=0.5, max_value=3.0, value=1.0, step=0.5)

    c_opt1, c_opt2 = st.columns(2)
    with c_opt1:
        req_kz = st.checkbox("Enforce Session Killzones (London & NY only)", value=True)
    with c_opt2:
        use_be = st.checkbox("Move Stop Loss to Break-Even at +1.0R", value=True)

    if st.button("🚀 Run Institutional Simulation", type="primary", use_container_width=True):
        with st.spinner(f"Running event-driven simulation for {test_symbol} ({strategy_choice})..."):
            res = bt.run_backtest(
                symbol=test_symbol,
                strategy_name=strat_key,
                bars_count=test_bars,
                min_rr=min_rr,
                risk_per_trade_pct=risk_pct,
                require_killzone=req_kz,
                use_breakeven=use_be
            )

            if "error" in res or res.get("total_trades", 0) == 0:
                st.warning("⚠️ No trades triggered matching these exact criteria in the selected historical period. Try increasing the number of bars or adjusting the R:R.")
            else:
                # KPI Summary
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Total Trades", res["total_trades"])
                m2.metric("Win Rate", f"{res['win_rate']}%", f"{res['wins']}W / {res['losses']}L")
                
                pf_color = "normal" if res["profit_factor"] >= 1.5 else "inverse"
                m3.metric("Profit Factor", f"{res['profit_factor']:.2f}")
                
                net_gain_str = f"+{res['net_profit_pct']}%" if res['net_profit_pct'] >= 0 else f"{res['net_profit_pct']}%"
                m4.metric("Net Profit", f"{net_gain_str}", f"€{res['net_profit_cash']:+,.2f}")
                m5.metric("Max Drawdown", f"-{res['max_drawdown_pct']}%", f"Expectancy: +{res['expectancy_r']}R")

                # Equity Curve Chart
                st.markdown("#### 📈 Account Equity Growth Curve")
                eq_df = pd.DataFrame({
                    "Trade": list(range(len(res["equity_curve"]))),
                    "Equity": res["equity_curve"]
                })
                fig_eq = go.Figure()
                fig_eq.add_trace(go.Scatter(
                    x=eq_df["Trade"],
                    y=eq_df["Equity"],
                    mode="lines+markers",
                    name="Account Equity (€)",
                    line=dict(color="#26a69a" if res["net_profit_pct"] >= 0 else "#ef5350", width=2.5),
                    fill="tozeroy",
                    fillcolor="rgba(38, 166, 154, 0.1)" if res["net_profit_pct"] >= 0 else "rgba(239, 83, 80, 0.1)"
                ))
                fig_eq.update_layout(
                    height=380,
                    margin=dict(l=10, r=10, t=20, b=10),
                    template="plotly_dark",
                    paper_bgcolor="#131722",
                    plot_bgcolor="#131722",
                    yaxis_title="Account Balance (€)",
                    xaxis_title="Trade Number"
                )
                st.plotly_chart(fig_eq, use_container_width=True)

                # Trade History Table
                st.markdown("#### 📋 Executed Trades Log")
                if not res["trades_df"].empty:
                    display_df = res["trades_df"][[
                        "entry_time", "direction", "entry_price", "stop_loss",
                        "sl_pips", "take_profit_1", "status", "pnl_r", "pnl_cash", "equity_after"
                    ]].copy()
                    display_df.rename(columns={
                        "entry_time": "Time",
                        "direction": "Type",
                        "entry_price": "Entry",
                        "stop_loss": "SL",
                        "sl_pips": "SL (Pips)",
                        "take_profit_1": "TP1",
                        "status": "Result",
                        "pnl_r": "PnL (R)",
                        "pnl_cash": "Profit/Loss (€)",
                        "equity_after": "Balance (€)"
                    }, inplace=True)
                    st.dataframe(display_df, use_container_width=True)

# ----------------------------------------------------------------------
# TAB 5: INTERACTIVE CHART STUDIO (LIVE DEEP-DIVE)
# ----------------------------------------------------------------------
with tab5:
    st.markdown("### 📈 Interactive Multi-Timeframe Chart Studio & Technical Inspector")
    st.markdown("Select any Forex pair or commodity to inspect live candlestick price action, customize indicator overlays, and view real-time technical metrics.")

    studio_col1, studio_col2, studio_col3, studio_col4 = st.columns([2, 2, 2, 2])
    with studio_col1:
        studio_sym = st.selectbox("Select Asset / Symbol:", TARGET_SYMBOLS, index=0, key="studio_symbol_select")
    with studio_col2:
        studio_tf = st.selectbox("Timeframe:", ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"], index=2, key="studio_tf_select")
    with studio_col3:
        studio_bars = st.slider("Candles Count:", 30, 300, 100, step=10, key="studio_bars_slider")
    with studio_col4:
        st.caption("⚡ Live Snapshot")
        sym_info_st = dp.get_symbol_info(studio_sym)
        if sym_info_st:
            st.markdown(f"**Bid:** `{sym_info_st['bid']}` | **Ask:** `{sym_info_st['ask']}` | **Spread:** `{sym_info_st['spread_pips']}p`")

    # Indicator Toggles
    ind_col1, ind_col2, ind_col3, ind_col4, ind_col5 = st.columns(5)
    with ind_col1:
        t_ema_fast = st.checkbox("EMA 9 & 21 (Ribbon)", value=True, key="t_ema_fast")
    with ind_col2:
        t_ema_slow = st.checkbox("EMA 50 & 200 (Macro)", value=True, key="t_ema_slow")
    with ind_col3:
        t_bb = st.checkbox("Bollinger Bands (20, 2)", value=False, key="t_bb")
    with ind_col4:
        t_vol = st.checkbox("Volume Subplot", value=True, key="t_vol")
    with ind_col5:
        if st.button("🔄 Refresh Chart", key="refresh_studio_btn", use_container_width=True):
            st.rerun()

    # Load & Render Chart
    df_studio = dp.get_rates(studio_sym, studio_tf, count=studio_bars)
    if df_studio is not None and not df_studio.empty:
        fig_studio = create_interactive_custom_chart(
            df=df_studio,
            symbol=studio_sym,
            timeframe=studio_tf,
            show_ema_fast=t_ema_fast,
            show_ema_slow=t_ema_slow,
            show_bb=t_bb,
            show_volume=t_vol
        )
        st.plotly_chart(fig_studio, use_container_width=True)

        # Technical Metrics Bar
        st.markdown("#### 🔍 Real-Time Technical Health & Structural Metrics")
        st_m1, st_m2, st_m3, st_m4 = st.columns(4)
        
        atr_val = dp.get_atr(studio_sym, studio_tf, period=14)
        pip_sz = sym_info_st['pip_size'] if sym_info_st else 0.0001
        atr_pips = round(atr_val / pip_sz, 1) if pip_sz > 0 else 0.0
        
        htf_st = profiler.get_htf_trend_bias(studio_sym)
        csm_div = profiler.get_pair_strength_divergence(studio_sym, csm)
        
        with st_m1:
            st.metric("ATR Volatility (14)", f"{atr_pips} pips")
        with st_m2:
            st.metric("CSM Net Flow", f"{csm_div['net_divergence']:+.2f}", f"{csm_div['bias']}")
        with st_m3:
            st.metric("HTF Structure", f"{htf_st['bias']}", f"D1: {htf_st['d1_trend']} | H4: {htf_st['h4_trend']}")
        with st_m4:
            st.metric("D1/H4/H1 Consensus", f"{htf_st['alignment_label']}")
    else:
        st.warning(f"⚠️ Could not load data for {studio_sym} at timeframe {studio_tf}. Please try another timeframe.")

# ----------------------------------------------------------------------
# LIVE AUTO-REFRESH TRIGGER
# ----------------------------------------------------------------------
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()


