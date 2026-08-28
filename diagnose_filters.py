#!/usr/bin/env python3
"""
Diagnostic Inspector: See why setups are filtered out across all pairs
"""

import sys
from data_provider import DataProvider
from scalper_engine import ScalperEngine, SCALP_TARGET_SYMBOLS
from recommendation_engine import RecommendationEngine
from market_profiler import MarketProfiler

dp = DataProvider()
scalper = ScalperEngine(dp)
profiler = MarketProfiler(dp)
rec_engine = RecommendationEngine(dp)

print("=" * 80)
print("             SCALPER ENGINE DIAGNOSTIC (M1 / M5 GATES)")
print("=" * 80)

for sym in SCALP_TARGET_SYMBOLS:
    sym_info = dp.get_symbol_info(sym)
    if not sym_info:
        continue
    spread_pips = sym_info["spread_pips"]
    pip_size = sym_info["pip_size"]
    
    df_m5 = dp.get_rates(sym, "M5", 60)
    df_m1 = dp.get_rates(sym, "M1", 80)
    
    if df_m5 is None or df_m1 is None:
        print(f"❌ {sym}: No candle data")
        continue

    # M5 metrics
    m5_tr = df_m5['high'] - df_m5['low']
    m5_atr_pips = float(m5_tr.tail(14).mean()) / pip_size
    spread_cost_pct = round((spread_pips / m5_atr_pips) * 100.0, 1) if m5_atr_pips > 0 else 999

    close = df_m5['close']
    ema9 = close.ewm(span=9, adjust=False).mean().iloc[-1]
    ema21 = close.ewm(span=21, adjust=False).mean().iloc[-1]
    cur_close = close.iloc[-1]
    slope = (ema9 - close.ewm(span=9, adjust=False).mean().iloc[-4]) / (3 * pip_size)
    
    # M1 metrics
    cur_m1 = df_m1.iloc[-1]
    prev_m1 = df_m1.iloc[-2]
    cur_body_pips = abs(cur_m1['close'] - cur_m1['open']) / pip_size
    m1_atr_pips = float((df_m1['high'] - df_m1['low']).tail(10).mean()) / pip_size
    
    # Check trigger
    res = scalper.analyze_scalp_symbol(sym)
    status = f"🔥 TRIGGERED ({res['setup_name']} - {res['grade']})" if res else "❌ Filtered"

    print(f"🔹 {sym:7s} | Spread: {spread_pips:.1f}p (Cost: {spread_cost_pct:4.1f}%) | M5 EMA9-21: {ema9 > ema21} | M5 Slope: {slope:+5.2f}p | M1 Body: {cur_body_pips:.1f}p (ATR: {m1_atr_pips:.1f}p) -> {status}")

print("\n" + "=" * 80)
print("          DAY-TRADE RECOMMENDATION ENGINE DIAGNOSTIC (M15 / H1)")
print("=" * 80)

session_info = profiler.get_current_session_info()
csm = profiler.calculate_currency_strength()
opps = rec_engine.scan_all_opportunities()
print(f"Active Day-Trade Setups: {len(opps)}")
for op in opps:
    print(f"  🎯 {op['symbol']:7s} [{op['direction']}] - {op['grade']} (Score: {op['quality_score']}/100) | SL: {op['sl_pips']}p | TP1: {op['take_profit_1']} | Reasons: {len(op['reasons'])}")

dp.shutdown()
