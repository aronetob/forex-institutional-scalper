#!/usr/bin/env python3
"""
Session Liquidity Range Target Engine
-------------------------------------
Core Concept:
- Buy after Asian Low Sweep -> Target: Asian High
- Sell after Asian High Sweep -> Target: Asian Low
- Hard Stop Loss: Beyond the sweep wick (10-15 pips)
- Strict Session: London Open Only (07:00 - 10:30 UTC)
- Asian Range Filter: 15 <= Range <= 45 pips
"""

import sys
import numpy as np
import pandas as pd

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from data_provider import DataProvider


def test_session_range_target(dp: DataProvider, symbol: str, bars_count: int = 2500):
    sym_info = dp.get_symbol_info(symbol)
    pip_size = sym_info["pip_size"] if sym_info else 0.0001
    spread_pips = sym_info["spread_pips"] if sym_info else 1.0

    df = dp.get_rates(symbol, "M15", count=bars_count)
    if df is None or len(df) < 200:
        return None

    close = df['close']
    high = df['high']
    low = df['low']

    df['ema50'] = close.ewm(span=50, adjust=False).mean()
    df['ema200'] = close.ewm(span=200, adjust=False).mean()
    df['atr'] = (high - low).rolling(14).mean().bfill()

    trades = []
    equity = 10000.0
    equity_curve = [equity]

    in_trade = False
    active = None
    last_trade_date = None

    for i in range(50, len(df) - 5):
        bar = df.iloc[i]
        b_time = bar['time']
        b_hour = b_time.hour
        b_min = b_time.minute
        b_date = b_time.date()

        # Trade Management
        if in_trade and active:
            is_buy = active['dir'] == "BUY"
            b_high = bar['high']
            b_low = bar['low']
            sl = active['sl']
            tp = active['tp']
            entry = active['entry']
            mid_target = active['mid_target']

            closed = False
            pnl_r = 0.0

            if is_buy:
                # Move SL to BE at 50% to target (Asian Midpoint)
                if b_high >= mid_target and not active['be_activated']:
                    active['sl'] = entry + (spread_pips * pip_size)
                    active['be_activated'] = True

                # Check SL
                if b_low <= active['sl']:
                    if active['be_activated']:
                        pnl_r = 0.0
                        active['status'] = "BE"
                    else:
                        pnl_r = -1.0
                        active['status'] = "LOSS"
                    closed = True

                # Check TP (Asian High)
                elif b_high >= tp:
                    pnl_r = active['rr_ratio']
                    active['status'] = "WIN"
                    closed = True

            else: # SELL
                if b_low <= mid_target and not active['be_activated']:
                    active['sl'] = entry - (spread_pips * pip_size)
                    active['be_activated'] = True

                if b_high >= active['sl']:
                    if active['be_activated']:
                        pnl_r = 0.0
                        active['status'] = "BE"
                    else:
                        pnl_r = -1.0
                        active['status'] = "LOSS"
                    closed = True

                elif b_low <= tp:
                    pnl_r = active['rr_ratio']
                    active['status'] = "WIN"
                    closed = True

            # Session close timeout (End of London session ~ 16:00 UTC)
            if not closed and (b_hour >= 16 or (i - active['idx']) >= 28):
                c = bar['close']
                pips = (c - entry) / pip_size if is_buy else (entry - c) / pip_size
                pnl_r = pips / active['sl_pips']
                closed = True
                active['status'] = "SESSION_CLOSE"

            if closed:
                risk_cash = equity * 0.01
                pnl_cash = risk_cash * pnl_r
                equity += pnl_cash
                equity_curve.append(round(equity, 2))
                active['pnl_r'] = round(pnl_r, 2)
                active['pnl_cash'] = round(pnl_cash, 2)
                trades.append(active)
                in_trade = False
                active = None
            continue

        # London Open Execution Window: 07:00 - 09:30 UTC
        if not (7 <= b_hour < 9 or (b_hour == 9 and b_min <= 30)):
            continue

        if last_trade_date == b_date:
            continue

        # Asian Range (00:00 - 07:00 UTC)
        today_asian = df[(df['time'].dt.date == b_date) & (df['time'].dt.hour < 7)]
        if len(today_asian) < 4:
            continue

        asian_high = today_asian['high'].max()
        asian_low = today_asian['low'].min()
        asian_range_pips = (asian_high - asian_low) / pip_size

        # Asian Range Quality Filter: Must be between 12 and 40 pips
        if asian_range_pips < 12.0 or asian_range_pips > 40.0:
            continue

        prev = df.iloc[i-1]
        c_close = bar['close']
        c_open = bar['open']
        c_low = bar['low']
        c_high = bar['high']
        c_atr = bar['atr']
        ema50 = bar['ema50']
        ema200 = bar['ema200']

        # --------------------------------------------------------------
        # 1. BULLISH SWEEP -> TARGET ASIAN HIGH
        # --------------------------------------------------------------
        # Asian low swept, candle closed back inside
        if (prev['low'] < asian_low or c_low < asian_low) and c_close > asian_low and c_close > c_open:
            entry = c_close + (spread_pips * pip_size)
            sweep_low = min(prev['low'], c_low)
            sl = sweep_low - (c_atr * 0.3)
            sl_pips = (entry - sl) / pip_size

            # Target is the Asian High minus 2 pips buffer
            tp = asian_high - (2.0 * pip_size)
            tp_pips = (tp - entry) / pip_size

            if sl_pips >= 6.0 and tp_pips >= sl_pips * 1.5:
                rr = round(tp_pips / sl_pips, 2)
                mid_target = entry + (tp_pips * 0.5 * pip_size)

                active = {
                    "sym": symbol,
                    "dir": "BUY",
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "mid_target": mid_target,
                    "sl_pips": sl_pips,
                    "tp_pips": tp_pips,
                    "rr_ratio": rr,
                    "idx": i,
                    "be_activated": False,
                    "time": b_time
                }
                in_trade = True
                last_trade_date = b_date

        # --------------------------------------------------------------
        # 2. BEARISH SWEEP -> TARGET ASIAN LOW
        # --------------------------------------------------------------
        elif not in_trade and (prev['high'] > asian_high or c_high > asian_high) and c_close < asian_high and c_close < c_open:
            entry = c_close
            sweep_high = max(prev['high'], c_high)
            sl = sweep_high + (c_atr * 0.3) + (spread_pips * pip_size)
            sl_pips = (sl - entry) / pip_size

            # Target is the Asian Low plus 2 pips buffer
            tp = asian_low + (2.0 * pip_size)
            tp_pips = (entry - tp) / pip_size

            if sl_pips >= 6.0 and tp_pips >= sl_pips * 1.5:
                rr = round(tp_pips / sl_pips, 2)
                mid_target = entry - (tp_pips * 0.5 * pip_size)

                active = {
                    "sym": symbol,
                    "dir": "SELL",
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "mid_target": mid_target,
                    "sl_pips": sl_pips,
                    "tp_pips": tp_pips,
                    "rr_ratio": rr,
                    "idx": i,
                    "be_activated": False,
                    "time": b_time
                }
                in_trade = True
                last_trade_date = b_date

    if not trades:
        return None

    tdf = pd.DataFrame(trades)
    wins = len(tdf[tdf['pnl_r'] > 0])
    losses = len(tdf[tdf['pnl_r'] < 0])
    bes = len(tdf[tdf['pnl_r'] == 0])
    total = len(tdf)

    win_rate = round((wins / total) * 100.0, 1)
    tot_gain = tdf[tdf['pnl_cash'] > 0]['pnl_cash'].sum()
    tot_loss = abs(tdf[tdf['pnl_cash'] < 0]['pnl_cash'].sum())
    pf = round(tot_gain / tot_loss, 2) if tot_loss > 0 else round(tot_gain, 2)
    net_pct = round(((equity - 10000.0) / 10000.0) * 100.0, 2)

    return {
        "symbol": symbol,
        "total": total,
        "wins": wins,
        "losses": losses,
        "bes": bes,
        "win_rate": win_rate,
        "profit_factor": pf,
        "net_gain_pct": net_pct,
        "net_gain_cash": round(equity - 10000.0, 2),
        "trades": tdf
    }


if __name__ == "__main__":
    dp = DataProvider()
    print("=" * 80)
    print("      SESSION LIQUIDITY RANGE TARGET (JUDAS SWING TO OPPOSITE LIQUIDITY)")
    print("=" * 80)

    symbols = ["EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"]
    total_trades = 0
    total_wins = 0
    total_losses = 0
    total_profit = 0.0

    for s in symbols:
        res = test_session_range_target(dp, s, bars_count=2500)
        if res:
            total_trades += res['total']
            total_wins += res['wins']
            total_losses += res['losses']
            total_profit += res['net_gain_cash']
            print(f"🎯 {s:7s} | Trades: {res['total']:2d} | Win: {res['wins']:2d} | Loss: {res['losses']:2d} | BE: {res['bes']:2d} | Win Rate: {res['win_rate']:5.1f}% | Profit Factor: {res['profit_factor']:4.2f} | Net: {res['net_gain_pct']:+6.2f}% (+€{res['net_gain_cash']:+,.2f})")
        else:
            print(f"🎯 {s:7s} | No trades triggered.")

    print("-" * 80)
    comb_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0
    print(f"🏆 TOTAL PORTFOLIO: {total_trades} Trades | {total_wins} Wins / {total_losses} Losses | Win Rate: {comb_wr:.1f}% | Total Net Gain: +€{total_profit:+,.2f}")
    print("=" * 80)
    dp.shutdown()
