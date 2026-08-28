#!/usr/bin/env python3
"""
Intraday Live Scalp Backtester (Today's Trading Session: Asian + London Open)
-----------------------------------------------------------------------------
Simulates the 5 Quantitative Scalping Gates candle-by-candle on M1 data
for today's session across all major Forex scalping assets.
"""

import sys
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from data_provider import DataProvider
from scalper_engine import compute_adx

# Key Forex pairs with tight spreads
SCALP_TARGET_SYMBOLS = [
    "EURUSD", "EURJPY", "USDCHF", "AUDUSD", "GBPUSD", "USDCAD", "USDJPY",
    "CADJPY", "AUDCAD", "CHFJPY", "AUDJPY"
]


def backtest_symbol_today(dp: DataProvider, symbol: str) -> Optional[Dict[str, Any]]:
    sym_info = dp.get_symbol_info(symbol)
    if not sym_info:
        return None

    pip_size = sym_info["pip_size"]
    spread_pips = sym_info["spread_pips"]
    digits = sym_info["digits"]

    # Fetch today's M1 bars (up to 800 M1 bars ~ 13 hours from 00:00 UTC)
    df_m1 = dp.get_rates(symbol, "M1", count=800)
    df_m15 = dp.get_rates(symbol, "M15", count=400)
    df_m5 = dp.get_rates(symbol, "M5", count=800)
    df_m1 = dp.get_rates(symbol, "M1", count=2500)

    if df_m5 is None or len(df_m5) < 50 or df_m1 is None or len(df_m1) < 100:
        return None

    today_date = df_m1['time'].iloc[-1].date()

    # M15 Trend
    if df_m15 is not None and len(df_m15) >= 20:
        df_m15['time'] = pd.to_datetime(df_m15['time']).astype('datetime64[ns]')
        df_m15['m15_ema9'] = df_m15['close'].ewm(span=9, adjust=False).mean()
        df_m15['m15_ema21'] = df_m15['close'].ewm(span=21, adjust=False).mean()
        df_m15['m15_bullish'] = df_m15['m15_ema9'] >= df_m15['m15_ema21']
        m15_cols = df_m15[['time', 'm15_bullish']].copy()
    else:
        m15_cols = None

    # Compute M5 Indicators
    df_m5['ema9'] = df_m5['close'].ewm(span=9, adjust=False).mean()
    df_m5['ema21'] = df_m5['close'].ewm(span=21, adjust=False).mean()
    df_m5['adx'] = compute_adx(df_m5, 14)
    df_m5['atr'] = (df_m5['high'] - df_m5['low']).rolling(14).mean().bfill()

    # Align M5 to M1 via merge_asof
    df_m1['time'] = pd.to_datetime(df_m1['time']).astype('datetime64[ns]')
    df_m5['time'] = pd.to_datetime(df_m5['time']).astype('datetime64[ns]')

    m5_cols = df_m5[['time', 'ema9', 'ema21', 'adx', 'atr']].copy()
    m5_cols.rename(columns={
        'ema9': 'm5_ema9',
        'ema21': 'm5_ema21',
        'adx': 'm5_adx',
        'atr': 'm5_atr'
    }, inplace=True)

    df_m1 = pd.merge_asof(df_m1.sort_values('time'), m5_cols.sort_values('time'), on='time')
    if m15_cols is not None:
        df_m1 = pd.merge_asof(df_m1.sort_values('time'), m15_cols.sort_values('time'), on='time')
        df_m1['m15_bullish'] = df_m1['m15_bullish'].fillna(True)
    else:
        df_m1['m15_bullish'] = True

    df_m1['m1_atr'] = (df_m1['high'] - df_m1['low']).rolling(10).mean().bfill()
    df_m1['m1_avg_vol'] = df_m1['volume'].rolling(12).mean().bfill()

    trades = []
    in_trade = False
    active = None
    last_exit_idx = -20

    # Start simulation from 07:00 UTC (London Open) or 01:00 UTC (Asian)
    m1_indices = df_m1.index[df_m1['time'].dt.date == today_date].tolist()

    for idx in m1_indices:
        bar = df_m1.loc[idx]
        b_time = bar['time']
        b_hour = b_time.hour
        b_min = b_time.minute

        # 1. TRADE MANAGEMENT
        if in_trade and active:
            is_buy = active['dir'] == "BUY"
            b_high = bar['high']
            b_low = bar['low']
            entry = active['entry']
            sl = active['sl']
            tp1 = active['tp1']
            tp2 = active['tp2']
            one_r = active['one_r']

            closed = False
            pnl_r = 0.0

            if is_buy:
                # Move to BE at +1.0R
                if b_high >= one_r and not active['be_activated']:
                    active['sl'] = entry + (spread_pips * pip_size)
                    active['be_activated'] = True

                # Check SL
                if b_low <= active['sl']:
                    if active['tp1_hit']:
                        pnl_r = 0.5 * 2.0
                        active['result'] = "WIN_BE (+1.0R)"
                    elif active['be_activated']:
                        pnl_r = 0.0
                        active['result'] = "BE (0.0R)"
                    else:
                        pnl_r = -1.0
                        active['result'] = "LOSS (-1.0R)"
                    closed = True

                # Check TP1
                elif b_high >= tp1 and not active['tp1_hit']:
                    active['tp1_hit'] = True
                    active['sl'] = entry + (spread_pips * pip_size)
                    active['be_activated'] = True

                # Check TP2
                elif b_high >= tp2:
                    pnl_r = 0.5 * 2.0 + 0.5 * 3.2
                    active['result'] = "WIN_MAX (+2.6R)"
                    closed = True

            else: # SELL
                if b_low <= one_r and not active['be_activated']:
                    active['sl'] = entry - (spread_pips * pip_size)
                    active['be_activated'] = True

                if b_high >= active['sl']:
                    if active['tp1_hit']:
                        pnl_r = 0.5 * 2.0
                        active['result'] = "WIN_BE (+1.0R)"
                    elif active['be_activated']:
                        pnl_r = 0.0
                        active['result'] = "BE (0.0R)"
                    else:
                        pnl_r = -1.0
                        active['result'] = "LOSS (-1.0R)"
                    closed = True

                elif b_low <= tp1 and not active['tp1_hit']:
                    active['tp1_hit'] = True
                    active['sl'] = entry - (spread_pips * pip_size)
                    active['be_activated'] = True

                elif b_low <= tp2:
                    pnl_r = 0.5 * 2.0 + 0.5 * 3.2
                    active['result'] = "WIN_MAX (+2.6R)"
                    closed = True

            # Scalp Timeout: 20 minutes max holding time
            if not closed and (idx - active['idx']) >= 20:
                c = bar['close']
                pips = (c - entry) / pip_size if is_buy else (entry - c) / pip_size
                pnl_r = round(pips / active['sl_pips'], 2)
                closed = True
                active['result'] = f"TIMEOUT ({pnl_r:+0.1f}R)"

            if closed:
                active['exit_time'] = b_time.strftime("%H:%M")
                active['pnl_r'] = pnl_r
                active['pnl_pips'] = round(pnl_r * active['sl_pips'], 1)
                trades.append(active)
                in_trade = False
                active = None
                last_exit_idx = idx
            continue

        # Cooldown between scalps (at least 5 bars)
        if idx - last_exit_idx < 5:
            continue

        # GATE 1: SPREAD COST CHECK
        m5_atr_p = bar['m5_atr'] / pip_size
        if m5_atr_p > 0 and (spread_pips / m5_atr_p) * 100 > 16.0:
            continue

        # GATE 2: M5 TREND & VOLATILITY (ADX >= 18)
        m5_adx = bar['m5_adx']
        m5_e9 = bar['m5_ema9']
        m5_e21 = bar['m5_ema21']
        c_price = bar['close']

        if pd.isna(m5_e9) or pd.isna(m5_e21) or m5_adx < 18.0:
            continue

        m5_bull = (c_price > m5_e9 > m5_e21)
        m5_bear = (c_price < m5_e9 < m5_e21)

        if not (m5_bull or m5_bear):
            continue

        # GATE 3: M1 DISPLACEMENT & VOLUME
        m1_atr = bar['m1_atr']
        if pd.isna(m1_atr) or m1_atr <= 0:
            continue

        cur_body = abs(bar['close'] - bar['open'])
        if cur_body < m1_atr * 0.9:
            continue

        prev_bar = df_m1.loc[idx - 1]
        recent_low = df_m1['low'].loc[max(0, idx-14):idx-2].min()
        recent_high = df_m1['high'].loc[max(0, idx-14):idx-2].max()

        setup_found = False
        direction = None
        setup_name = ""

        # M1 Bullish Trigger (Triple MTF Alignment: M1 + M5 + M15)
        if m5_bull and bar['m15_bullish']:
            if prev_bar['low'] <= recent_low and c_price > recent_low:
                direction = "BUY"
                setup_found = True
                setup_name = "M1 Liquidity Sweep"
            elif c_price > prev_bar['high'] and prev_bar['close'] <= prev_bar['open']:
                direction = "BUY"
                setup_found = True
                setup_name = "M1 Micro-CHoCH"

        # M1 Bearish Trigger (Triple MTF Alignment: M1 + M5 + M15)
        elif m5_bear and not bar['m15_bullish']:
            if prev_bar['high'] >= recent_high and c_price < recent_high:
                direction = "SELL"
                setup_found = True
                setup_name = "M1 Liquidity Sweep"
            elif c_price < prev_bar['low'] and prev_bar['close'] >= prev_bar['open']:
                direction = "SELL"
                setup_found = True
                setup_name = "M1 Micro-CHoCH"

        if setup_found and direction:
            entry_price = c_price + (spread_pips * pip_size) if direction == "BUY" else c_price

            if direction == "BUY":
                sl_raw = min(bar['low'], prev_bar['low']) - (m1_atr * 0.3)
                sl_pips = round((entry_price - sl_raw) / pip_size, 1)
                sl_pips = max(3.0, min(6.0, sl_pips))
                stop_loss = round(entry_price - (sl_pips * pip_size), digits)
                tp1 = round(entry_price + (sl_pips * 1.8 * pip_size), digits)
                tp2 = round(entry_price + (sl_pips * 3.0 * pip_size), digits)
                one_r = entry_price + (sl_pips * 0.9 * pip_size)
            else:
                sl_raw = max(bar['high'], prev_bar['high']) + (m1_atr * 0.3) + (spread_pips * pip_size)
                sl_pips = round((sl_raw - entry_price) / pip_size, 1)
                sl_pips = max(3.0, min(6.0, sl_pips))
                stop_loss = round(entry_price + (sl_pips * pip_size), digits)
                tp1 = round(entry_price - (sl_pips * 1.8 * pip_size), digits)
                tp2 = round(entry_price - (sl_pips * 3.0 * pip_size), digits)
                one_r = entry_price - (sl_pips * 0.9 * pip_size)

            active = {
                "symbol": symbol,
                "dir": direction,
                "setup": setup_name,
                "entry_time": b_time.strftime("%H:%M"),
                "entry": entry_price,
                "sl": stop_loss,
                "tp1": tp1,
                "tp2": tp2,
                "one_r": one_r,
                "sl_pips": sl_pips,
                "idx": idx,
                "be_activated": False,
                "tp1_hit": False
            }
            in_trade = True

    if not trades:
        return None

    tdf = pd.DataFrame(trades)
    wins = len(tdf[tdf['pnl_r'] > 0])
    losses = len(tdf[tdf['pnl_r'] < 0])
    bes = len(tdf[tdf['pnl_r'] == 0])
    tot = len(tdf)
    win_rate = round((wins / tot) * 100.0, 1)
    tot_r = round(tdf['pnl_r'].sum(), 2)

    return {
        "symbol": symbol,
        "total": tot,
        "wins": wins,
        "losses": losses,
        "bes": bes,
        "win_rate": win_rate,
        "total_r": tot_r,
        "trades": trades
    }


if __name__ == "__main__":
    dp = DataProvider()
    print("=" * 85)
    print(f"      TODAY'S INTRADAY LIVE SCALPER BACKTEST ({datetime.now().strftime('%Y-%m-%d')} SESSION)")
    print("=" * 85)

    all_trades = []
    tot_w = 0
    tot_l = 0
    tot_b = 0
    tot_trades = 0
    tot_r_portfolio = 0.0

    for sym in SCALP_TARGET_SYMBOLS:
        res = backtest_symbol_today(dp, sym)
        if res:
            tot_trades += res['total']
            tot_w += res['wins']
            tot_l += res['losses']
            tot_b += res['bes']
            tot_r_portfolio += res['total_r']
            print(f"\n💎 {sym:7s} | Trades: {res['total']:2d} | Win: {res['wins']:2d} | Loss: {res['losses']:2d} | BE: {res['bes']:2d} | Win Rate: {res['win_rate']:5.1f}% | Net: {res['total_r']:+5.2f}R")
            for t in res['trades']:
                print(f"    • [{t['entry_time']} -> {t.get('exit_time', 'NOW')}] {t['dir']:4s} @ {t['entry']:.5f} | SL: {t['sl_pips']}p | Result: {t['result']:15s} | PnL: {t['pnl_r']:+4.1f}R ({t['pnl_pips']:+4.1f}p)")

    print("\n" + "=" * 85)
    comb_wr = round((tot_w / tot_trades) * 100.0, 1) if tot_trades > 0 else 0.0
    print(f"🏆 TODAY'S PORTFOLIO TOTAL: {tot_trades} Trades | {tot_w} Wins / {tot_l} Losses / {tot_b} Break-Evens")
    print(f"🔥 COMBINED WIN RATE: {comb_wr}% | NET RETURN: {tot_r_portfolio:+0.2f}R (e.g. +{tot_r_portfolio:.1f}% on 1% risk per trade)")
    print("=" * 85)

    dp.shutdown()
