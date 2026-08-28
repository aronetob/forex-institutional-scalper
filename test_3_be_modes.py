#!/usr/bin/env python3
"""
Test 3 Models:
1. Aggressive Early BE (at +0.9R)
2. Hybrid Institutional BE (BE only after TP1 is hit at +1.8R)
3. No BE (Pure SL/TP)
"""

import sys
import pandas as pd
import numpy as np

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from data_provider import DataProvider
from scalper_engine import compute_wilder_adx as compute_adx

SCALP_SYMBOLS = [
    "EURUSD", "EURJPY", "USDJPY", "USDCHF", "GBPUSD", "AUDUSD", "USDCAD", "AUDJPY"
]

def simulate_mode(dp: DataProvider, mode: str):
    # mode: 'EARLY_BE', 'TP1_THEN_BE', 'NO_BE'
    tot_trades = 0
    wins = 0
    losses = 0
    bes = 0
    net_r = 0.0

    for symbol in SCALP_SYMBOLS:
        sym_info = dp.get_symbol_info(symbol)
        if not sym_info:
            continue
        pip_size = sym_info["pip_size"]
        spread_pips = sym_info["spread_pips"]
        digits = sym_info["digits"]

        df_m15 = dp.get_rates(symbol, "M15", count=400)
        df_m5 = dp.get_rates(symbol, "M5", count=800)
        df_m1 = dp.get_rates(symbol, "M1", count=2500)

        if df_m5 is None or len(df_m5) < 50 or df_m1 is None or len(df_m1) < 100:
            continue

        today_date = df_m1['time'].iloc[-1].date()

        if df_m15 is not None and len(df_m15) >= 20:
            df_m15['time'] = pd.to_datetime(df_m15['time']).astype('datetime64[ns]')
            df_m15['m15_ema9'] = df_m15['close'].ewm(span=9, adjust=False).mean()
            df_m15['m15_ema21'] = df_m15['close'].ewm(span=21, adjust=False).mean()
            df_m15['m15_bullish'] = df_m15['m15_ema9'] >= df_m15['m15_ema21']
            m15_cols = df_m15[['time', 'm15_bullish']].copy()
        else:
            m15_cols = None

        df_m5['ema9'] = df_m5['close'].ewm(span=9, adjust=False).mean()
        df_m5['ema21'] = df_m5['close'].ewm(span=21, adjust=False).mean()
        df_m5['adx'] = compute_adx(df_m5, 14)
        df_m5['atr'] = (df_m5['high'] - df_m5['low']).rolling(14).mean().bfill()

        df_m1['time'] = pd.to_datetime(df_m1['time']).astype('datetime64[ns]')
        df_m5['time'] = pd.to_datetime(df_m5['time']).astype('datetime64[ns]')

        m5_cols = df_m5[['time', 'ema9', 'ema21', 'adx', 'atr']].copy()
        m5_cols.rename(columns={'ema9': 'm5_ema9', 'ema21': 'm5_ema21', 'adx': 'm5_adx', 'atr': 'm5_atr'}, inplace=True)

        df_m1 = pd.merge_asof(df_m1.sort_values('time'), m5_cols.sort_values('time'), on='time')
        if m15_cols is not None:
            df_m1 = pd.merge_asof(df_m1.sort_values('time'), m15_cols.sort_values('time'), on='time')
            df_m1['m15_bullish'] = df_m1['m15_bullish'].fillna(True)
        else:
            df_m1['m15_bullish'] = True

        df_m1['m1_atr'] = (df_m1['high'] - df_m1['low']).rolling(10).mean().bfill()

        in_trade = False
        active = None
        last_exit_idx = -20
        m1_indices = df_m1.index[df_m1['time'].dt.date == today_date].tolist()

        for idx in m1_indices:
            bar = df_m1.loc[idx]

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
                    # Early BE
                    if mode == "EARLY_BE" and b_high >= one_r and not active['be_activated']:
                        active['sl'] = entry + (spread_pips * pip_size)
                        active['be_activated'] = True

                    if b_low <= active['sl']:
                        if active['tp1_hit']:
                            pnl_r = 0.5 * 1.8  # Secured 50% TP1 (+0.9R)
                            wins += 1
                        elif active['be_activated']:
                            pnl_r = 0.0
                            bes += 1
                        else:
                            pnl_r = -1.0
                            losses += 1
                        closed = True

                    elif b_high >= tp1 and not active['tp1_hit']:
                        active['tp1_hit'] = True
                        if mode in ("EARLY_BE", "TP1_THEN_BE"):
                            active['sl'] = entry + (spread_pips * pip_size)
                            active['be_activated'] = True

                    elif b_high >= tp2:
                        pnl_r = 0.5 * 1.8 + 0.5 * 3.0
                        wins += 1
                        closed = True

                else: # SELL
                    if mode == "EARLY_BE" and b_low <= one_r and not active['be_activated']:
                        active['sl'] = entry - (spread_pips * pip_size)
                        active['be_activated'] = True

                    if b_high >= active['sl']:
                        if active['tp1_hit']:
                            pnl_r = 0.5 * 1.8
                            wins += 1
                        elif active['be_activated']:
                            pnl_r = 0.0
                            bes += 1
                        else:
                            pnl_r = -1.0
                            losses += 1
                        closed = True

                    elif b_low <= tp1 and not active['tp1_hit']:
                        active['tp1_hit'] = True
                        if mode in ("EARLY_BE", "TP1_THEN_BE"):
                            active['sl'] = entry - (spread_pips * pip_size)
                            active['be_activated'] = True

                    elif b_low <= tp2:
                        pnl_r = 0.5 * 1.8 + 0.5 * 3.0
                        wins += 1
                        closed = True

                if not closed and (idx - active['idx']) >= 20:
                    c = bar['close']
                    pips = (c - entry) / pip_size if is_buy else (entry - c) / pip_size
                    pnl_r = round(pips / active['sl_pips'], 2)
                    closed = True
                    if pnl_r > 0:
                        wins += 1
                    elif pnl_r < 0:
                        losses += 1
                    else:
                        bes += 1

                if closed:
                    net_r += pnl_r
                    tot_trades += 1
                    in_trade = False
                    active = None
                    last_exit_idx = idx
                continue

            if idx - last_exit_idx < 5:
                continue

            m5_atr_p = bar['m5_atr'] / pip_size
            if m5_atr_p > 0 and (spread_pips / m5_atr_p) * 100 > 16.0:
                continue

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

            if m5_bull and bar['m15_bullish']:
                if prev_bar['low'] <= recent_low and c_price > recent_low:
                    direction = "BUY"
                    setup_found = True
                elif c_price > prev_bar['high'] and prev_bar['close'] <= prev_bar['open']:
                    direction = "BUY"
                    setup_found = True

            elif m5_bear and not bar['m15_bullish']:
                if prev_bar['high'] >= recent_high and c_price < recent_high:
                    direction = "SELL"
                    setup_found = True
                elif c_price < prev_bar['low'] and prev_bar['close'] >= prev_bar['open']:
                    direction = "SELL"
                    setup_found = True

            if setup_found and direction:
                entry_price = c_price + (spread_pips * pip_size) if direction == "BUY" else c_price

                if direction == "BUY":
                    sl_raw = min(bar['low'], prev_bar['low']) - (m1_atr * 0.3)
                    sl_pips = max(3.0, min(6.0, round((entry_price - sl_raw) / pip_size, 1)))
                    stop_loss = round(entry_price - (sl_pips * pip_size), digits)
                    tp1 = round(entry_price + (sl_pips * 1.8 * pip_size), digits)
                    tp2 = round(entry_price + (sl_pips * 3.0 * pip_size), digits)
                    one_r = entry_price + (sl_pips * 0.9 * pip_size)
                else:
                    sl_raw = max(bar['high'], prev_bar['high']) + (m1_atr * 0.3) + (spread_pips * pip_size)
                    sl_pips = max(3.0, min(6.0, round((sl_raw - entry_price) / pip_size, 1)))
                    stop_loss = round(entry_price + (sl_pips * pip_size), digits)
                    tp1 = round(entry_price - (sl_pips * 1.8 * pip_size), digits)
                    tp2 = round(entry_price - (sl_pips * 3.0 * pip_size), digits)
                    one_r = entry_price - (sl_pips * 0.9 * pip_size)

                active = {
                    "dir": direction,
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

    win_rate = round((wins / tot_trades) * 100.0, 1) if tot_trades > 0 else 0.0
    return {
        "trades": tot_trades,
        "wins": wins,
        "losses": losses,
        "bes": bes,
        "win_rate": win_rate,
        "net_r": round(net_r, 2)
    }

if __name__ == "__main__":
    dp = DataProvider()
    print("=" * 88)
    print("      QUANTITATIVE COMPARISON: 3 STRATEGIES OF BREAK-EVEN MANAGEMENT")
    print("=" * 88)

    m1 = simulate_mode(dp, "EARLY_BE")
    m2 = simulate_mode(dp, "TP1_THEN_BE")
    m3 = simulate_mode(dp, "NO_BE")

    print(f"{'STRATEGY MODEL':<28s} | {'TRADES':<8s} | {'WINS':<6s} | {'LOSS':<6s} | {'BE':<5s} | {'WIN %':<8s} | {'NET RETURN'}")
    print("-" * 88)
    print(f"{'1. Early BE (at +0.9R)':<28s} | {m1['trades']:<8d} | {m1['wins']:<6d} | {m1['losses']:<6d} | {m1['bes']:<5d} | {m1['win_rate']:<7.1f}% | {m1['net_r']:+8.2f}R")
    print(f"{'2. Hybrid (BE only after TP1)':<28s} | {m2['trades']:<8d} | {m2['wins']:<6d} | {m2['losses']:<6d} | {m2['bes']:<5d} | {m2['win_rate']:<7.1f}% | {m2['net_r']:+8.2f}R 🏆")
    print(f"{'3. No BE (Static SL / TP)':<28s} | {m3['trades']:<8d} | {m3['wins']:<6d} | {m3['losses']:<6d} | {m3['bes']:<5d} | {m3['win_rate']:<7.1f}% | {m3['net_r']:+8.2f}R")
    print("=" * 88)

    dp.shutdown()
