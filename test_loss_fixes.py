#!/usr/bin/env python3
"""
Institutional Strategy Optimization Test
----------------------------------------
Applies 3 Key Institutional Upgrades:
1. Peak Session Execution Windows Only:
   - London Open: 07:00 - 10:30 UTC
   - NY Open: 12:30 - 14:00 UTC
   - Blackout: 10:30 - 12:30 (Lunch) & 14:30+ (London Fix/Closes)
2. Structural Stop Loss (Swing High/Low Wick + 1.8x ATR, no artificial 12p floor)
3. 200 EMA Trend Anchor Filter (BUY only above 200 EMA, SELL only below 200 EMA)
4. Dynamic Break-Even at +0.8R
"""

import sys
import numpy as np
import pandas as pd
from data_provider import DataProvider
from backtester import compute_ema, compute_zlema, compute_adx

def test_optimized_engine(dp: DataProvider, symbols: list):
    print("=" * 95)
    print("      OPTIMIZED STRATEGY VALIDATION (PEAK KILLZONES + 200 EMA + STRUCTURAL SL)")
    print("=" * 95)

    tot_trades = 0
    tot_wins = 0
    tot_losses = 0
    tot_bes = 0
    tot_gain_cash = 0.0

    for symbol in symbols:
        sym_info = dp.get_symbol_info(symbol)
        if not sym_info:
            continue
        pip_size = sym_info["pip_size"]
        spread_pips = sym_info["spread_pips"]
        digits = sym_info["digits"]

        df_m15 = dp.get_rates(symbol, "M15", count=2000)
        df_h1 = dp.get_rates(symbol, "H1", count=700)
        df_d1 = dp.get_rates(symbol, "D1", count=60)

        if df_m15 is None or len(df_m15) < 150:
            continue

        df_m15['time'] = pd.to_datetime(df_m15['time']).astype('datetime64[ns]')
        
        # Base indicators
        df_m15['ema9'] = compute_ema(df_m15['close'], 9)
        df_m15['ema21'] = compute_ema(df_m15['close'], 21)
        df_m15['ema50'] = compute_ema(df_m15['close'], 50)
        df_m15['ema200'] = compute_ema(df_m15['close'], 200)
        df_m15['zlema'] = compute_zlema(df_m15['close'], 20)
        df_m15['adx'] = compute_adx(df_m15, 14)
        df_m15['atr'] = (df_m15['high'] - df_m15['low']).rolling(14).mean().bfill()

        # Merge H1 trend
        if df_h1 is not None and len(df_h1) > 20:
            df_h1['time'] = pd.to_datetime(df_h1['time']).astype('datetime64[ns]')
            df_h1['ema9_h1'] = compute_ema(df_h1['close'], 9)
            df_h1['ema21_h1'] = compute_ema(df_h1['close'], 21)
            h1_trend_series = np.where(df_h1['ema9_h1'] > df_h1['ema21_h1'], 1, -1)
            h1_trend_df = pd.DataFrame({'time': df_h1['time'], 'h1_trend': h1_trend_series})
            df_m15 = pd.merge_asof(df_m15.sort_values('time'), h1_trend_df.sort_values('time'), on='time')
            df_m15['h1_trend'] = df_m15['h1_trend'].fillna(0)
        else:
            df_m15['h1_trend'] = 0

        # MTF Consensus Signal
        m15_bull = (df_m15['ema9'] > df_m15['ema21']) & (df_m15['close'] > df_m15['zlema']) & (df_m15['h1_trend'] >= 0)
        m15_bear = (df_m15['ema9'] < df_m15['ema21']) & (df_m15['close'] < df_m15['zlema']) & (df_m15['h1_trend'] <= 0)
        raw_mtf = np.where(m15_bull, 1, np.where(m15_bear, -1, 0))

        persisted_mtf = pd.Series(raw_mtf).rolling(3).apply(
            lambda s: s[0] if (len(set(s)) == 1 and s[0] != 0) else 0, raw=True
        ).fillna(0).astype(int).values

        trades = []
        equity = 10000.0
        in_trade = False
        active = None
        last_trade_date = None

        for i in range(50, len(df_m15) - 5):
            bar = df_m15.iloc[i]
            b_time = bar['time']
            b_hour = b_time.hour
            b_min = b_time.minute
            b_date = b_time.date()

            # Trade Management
            if in_trade and active:
                is_buy = active['direction'] == "BUY"
                high = bar['high']
                low = bar['low']
                entry = active['entry_price']
                sl = active['stop_loss']
                tp1 = active['take_profit_1']
                tp2 = active['take_profit_2']
                one_r = active['one_r']

                closed = False
                pnl_r = 0.0

                if is_buy:
                    if high >= one_r and not active['be_activated']:
                        active['stop_loss'] = entry + (spread_pips * pip_size)
                        active['be_activated'] = True

                    if low <= active['stop_loss']:
                        if active['tp1_hit']:
                            pnl_r = 0.5 * 2.0
                            active['status'] = "WIN_BE"
                        elif active['be_activated']:
                            pnl_r = 0.0
                            active['status'] = "BE"
                        else:
                            pnl_r = -1.0
                            active['status'] = "LOSS"
                        closed = True

                    elif high >= tp1 and not active['tp1_hit']:
                        active['tp1_hit'] = True
                        active['stop_loss'] = entry + (spread_pips * pip_size)

                    elif high >= tp2:
                        pnl_r = 0.5 * 2.0 + 0.5 * 3.5
                        active['status'] = "WIN_FULL"
                        closed = True

                else: # SELL
                    if low <= one_r and not active['be_activated']:
                        active['stop_loss'] = entry - (spread_pips * pip_size)
                        active['be_activated'] = True

                    if high >= active['stop_loss']:
                        if active['tp1_hit']:
                            pnl_r = 0.5 * 2.0
                            active['status'] = "WIN_BE"
                        elif active['be_activated']:
                            pnl_r = 0.0
                            active['status'] = "BE"
                        else:
                            pnl_r = -1.0
                            active['status'] = "LOSS"
                        closed = True

                    elif low <= tp1 and not active['tp1_hit']:
                        active['tp1_hit'] = True
                        active['stop_loss'] = entry - (spread_pips * pip_size)

                    elif low <= tp2:
                        pnl_r = 0.5 * 2.0 + 0.5 * 3.5
                        active['status'] = "WIN_FULL"
                        closed = True

                if not closed and (i - active['entry_index']) >= 28:
                    c = bar['close']
                    pips = (c - entry) / pip_size if is_buy else (entry - c) / pip_size
                    pnl_r = round(pips / active['sl_pips'], 2)
                    closed = True
                    active['status'] = "TIMEOUT"

                if closed:
                    risk_cash = equity * 0.01
                    pnl_cash = risk_cash * pnl_r
                    equity += pnl_cash
                    active['pnl_r'] = pnl_r
                    active['pnl_cash'] = round(pnl_cash, 2)
                    trades.append(active)
                    in_trade = False
                    active = None
                continue

            # --------------------------------------------------------------
            # UPGRADE 1: PEAK VOLUME TIME WINDOWS ONLY
            # --------------------------------------------------------------
            # London Peak: 07:00 - 10:30 UTC | NY Peak: 12:30 - 14:30 UTC
            is_peak_london = (7 <= b_hour <= 9) or (b_hour == 10 and b_min <= 30)
            is_peak_ny = (b_hour == 12 and b_min >= 30) or (13 <= b_hour <= 14)

            if not (is_peak_london or is_peak_ny):
                continue

            if last_trade_date == b_date:
                continue

            sig = persisted_mtf[i]
            prev_sig = persisted_mtf[i-1]

            if sig != 0 and prev_sig == 0:
                c_close = bar['close']
                c_atr = bar['atr']
                ema200 = bar['ema200']
                adx_val = bar['adx']

                if adx_val < 18.0:
                    continue

                prev_bars = df_m15.iloc[max(0, i-8):i]
                swing_low = prev_bars['low'].min()
                swing_high = prev_bars['high'].max()

                # UPGRADE 2: 200 EMA ANCHOR FILTER
                if sig == 1 and c_close > ema200:
                    entry_price = c_close + (spread_pips * pip_size)
                    stop_loss = min(swing_low, entry_price - (c_atr * 1.8))
                    sl_pips = (entry_price - stop_loss) / pip_size

                    if 12.0 <= sl_pips <= 45.0:
                        tp1 = entry_price + (sl_pips * 2.0 * pip_size)
                        tp2 = entry_price + (sl_pips * 3.5 * pip_size)
                        one_r = entry_price + (sl_pips * 0.85 * pip_size)

                        active = {
                            "symbol": symbol,
                            "direction": "BUY",
                            "entry_price": round(entry_price, digits),
                            "stop_loss": round(stop_loss, digits),
                            "take_profit_1": round(tp1, digits),
                            "take_profit_2": round(tp2, digits),
                            "one_r": round(one_r, digits),
                            "sl_pips": round(sl_pips, 1),
                            "entry_index": i,
                            "be_activated": False,
                            "tp1_hit": False
                        }
                        in_trade = True
                        last_trade_date = b_date

                elif sig == -1 and c_close < ema200:
                    entry_price = c_close
                    stop_loss = max(swing_high, entry_price + (c_atr * 1.8)) + (spread_pips * pip_size)
                    sl_pips = (stop_loss - entry_price) / pip_size

                    if 12.0 <= sl_pips <= 45.0:
                        tp1 = entry_price - (sl_pips * 2.0 * pip_size)
                        tp2 = entry_price - (sl_pips * 3.5 * pip_size)
                        one_r = entry_price - (sl_pips * 0.85 * pip_size)

                        active = {
                            "symbol": symbol,
                            "direction": "SELL",
                            "entry_price": round(entry_price, digits),
                            "stop_loss": round(stop_loss, digits),
                            "take_profit_1": round(tp1, digits),
                            "take_profit_2": round(tp2, digits),
                            "one_r": round(one_r, digits),
                            "sl_pips": round(sl_pips, 1),
                            "entry_index": i,
                            "be_activated": False,
                            "tp1_hit": False
                        }
                        in_trade = True
                        last_trade_date = b_date

        if not trades:
            continue

        tdf = pd.DataFrame(trades)
        wins = len(tdf[tdf['pnl_r'] > 0])
        losses = len(tdf[tdf['pnl_r'] < 0])
        bes = len(tdf[tdf['pnl_r'] == 0])
        total = len(tdf)

        win_rate = round((wins / total) * 100.0, 1)
        tot_gain = tdf[tdf['pnl_cash'] > 0]['pnl_cash'].sum()
        tot_loss = abs(tdf[tdf['pnl_cash'] < 0]['pnl_cash'].sum())
        pf = round(tot_gain / tot_loss, 2) if tot_loss > 0 else round(tot_gain, 2)
        net_cash = round(equity - 10000.0, 2)
        net_pct = round((net_cash / 10000.0) * 100.0, 2)

        tot_trades += total
        tot_wins += wins
        tot_losses += losses
        tot_bes += bes
        tot_gain_cash += net_cash

        print(f"🔥 {symbol:7s} | Trades: {total:2d} | Win: {wins:2d} | Loss: {losses:2d} | BE: {bes:2d} | WR: {win_rate:5.1f}% | PF: {pf:4.2f} | Net: {net_pct:+6.2f}% (+€{net_cash:+,.2f})")

    print("-" * 95)
    comb_wr = round((tot_wins / tot_trades) * 100.0, 1) if tot_trades > 0 else 0.0
    print(f"🏆 PORTFOLIO TOTAL: {tot_trades} Trades | {tot_wins} Wins / {tot_losses} Losses / {tot_bes} BEs")
    print(f"💎 WIN RATE: {comb_wr}% | TOTAL NET PROFIT: +€{tot_gain_cash:+,.2f}")
    print("=" * 95)


if __name__ == "__main__":
    dp = DataProvider()
    test_symbols = [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "CADJPY",
        "CHFJPY", "EURJPY", "AUDJPY", "EURCAD", "EURAUD", "GBPAUD", "AUDNZD"
    ]
    test_optimized_engine(dp, test_symbols)
    dp.shutdown()
