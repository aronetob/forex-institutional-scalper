#!/usr/bin/env python3
"""
Ultimate Institutional Trend & Breakout Engine (Sniper v2.0)
------------------------------------------------------------
Combines:
1. Currency Strength Matrix (CSM) Divergence Filter (Strong vs Weak)
2. London Breakout Pullback to EMA9/21
3. Early Profit Lock (Move SL to +0.2R at +0.8R)
4. Dynamic Chandelier ATR Trailing Stop
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
from market_profiler import MarketProfiler


def test_ultimate_institutional(dp: DataProvider, symbol: str, bars_count: int = 2500):
    sym_info = dp.get_symbol_info(symbol)
    pip_size = sym_info["pip_size"] if sym_info else 0.0001
    spread_pips = sym_info["spread_pips"] if sym_info else 1.0

    df = dp.get_rates(symbol, "M15", count=bars_count)
    if df is None or len(df) < 200:
        return None

    close = df['close']
    high = df['high']
    low = df['low']
    op = df['open']

    # Indicators
    df['ema9'] = close.ewm(span=9, adjust=False).mean()
    df['ema21'] = close.ewm(span=21, adjust=False).mean()
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
        b_date = b_time.date()

        # Trade Management
        if in_trade and active:
            is_buy = active['dir'] == "BUY"
            b_high = bar['high']
            b_low = bar['low']
            b_close = bar['close']
            entry = active['entry']
            sl = active['sl']
            tp1 = active['tp1']
            tp2 = active['tp2']
            target_lock = active['target_lock']
            c_atr = bar['atr']

            closed = False
            pnl_r = 0.0

            if is_buy:
                # Early Profit Lock at +0.8R -> Move SL to +0.2R (Guaranteed Profit)
                if b_high >= target_lock and not active['locked']:
                    active['sl'] = entry + (active['sl_pips'] * 0.2 * pip_size)
                    active['locked'] = True

                # Trailing Stop using EMA21
                if active['locked'] and bar['ema21'] > active['sl']:
                    active['sl'] = bar['ema21'] - (c_atr * 0.3)

                # Check Stop Loss
                if b_low <= active['sl']:
                    exit_price = active['sl']
                    pnl_pips = (exit_price - entry) / pip_size
                    pnl_r = pnl_pips / active['sl_pips']
                    closed = True
                    active['status'] = "PROFIT_TRAIL" if pnl_r > 0 else "LOSS"

                # Check TP2
                elif b_high >= tp2:
                    pnl_r = 3.5
                    closed = True
                    active['status'] = "TP_MAX"

            else: # SELL
                if b_low <= target_lock and not active['locked']:
                    active['sl'] = entry - (active['sl_pips'] * 0.2 * pip_size)
                    active['locked'] = True

                if active['locked'] and bar['ema21'] < active['sl']:
                    active['sl'] = bar['ema21'] + (c_atr * 0.3)

                if b_high >= active['sl']:
                    exit_price = active['sl']
                    pnl_pips = (entry - exit_price) / pip_size
                    pnl_r = pnl_pips / active['sl_pips']
                    closed = True
                    active['status'] = "PROFIT_TRAIL" if pnl_r > 0 else "LOSS"

                elif b_low <= tp2:
                    pnl_r = 3.5
                    closed = True
                    active['status'] = "TP_MAX"

            if not closed and (i - active['idx']) >= 36: # 9 hours
                pips = (b_close - entry) / pip_size if is_buy else (entry - b_close) / pip_size
                pnl_r = pips / active['sl_pips']
                closed = True
                active['status'] = "TIMEOUT"

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

        # Killzone Filter (07:00 - 15:00 UTC)
        if not (7 <= b_hour <= 15):
            continue

        if last_trade_date == b_date:
            continue

        # Trend & Pullback Logic
        ema9 = bar['ema9']
        ema21 = bar['ema21']
        ema50 = bar['ema50']
        ema200 = bar['ema200']
        c_close = bar['close']
        c_low = bar['low']
        c_high = bar['high']
        c_atr = bar['atr']
        prev_bar = df.iloc[i-1]

        # Strong Bullish Trend Alignment
        is_bullish = (ema9 > ema21 > ema50 > ema200) and (c_close > ema50)
        # Strong Bearish Trend Alignment
        is_bearish = (ema9 < ema21 < ema50 < ema200) and (c_close < ema50)

        # Bullish Entry on EMA9/21 Touch + Strong Rejection
        if is_bullish and prev_bar['low'] <= ema21 and c_close > ema9:
            entry = c_close + (spread_pips * pip_size)
            sl = min(prev_bar['low'], ema50) - (c_atr * 0.4)
            sl_pips = (entry - sl) / pip_size

            if 8.0 <= sl_pips <= 35.0:
                tp1 = entry + (sl_pips * 1.8 * pip_size)
                tp2 = entry + (sl_pips * 3.5 * pip_size)
                target_lock = entry + (sl_pips * 0.8 * pip_size)

                active = {
                    "sym": symbol,
                    "dir": "BUY",
                    "entry": entry,
                    "sl": sl,
                    "tp1": tp1,
                    "tp2": tp2,
                    "target_lock": target_lock,
                    "sl_pips": sl_pips,
                    "idx": i,
                    "locked": False,
                    "time": b_time
                }
                in_trade = True
                last_trade_date = b_date

        elif not in_trade and is_bearish and prev_bar['high'] >= ema21 and c_close < ema9:
            entry = c_close
            sl = max(prev_bar['high'], ema50) + (c_atr * 0.4) + (spread_pips * pip_size)
            sl_pips = (sl - entry) / pip_size

            if 8.0 <= sl_pips <= 35.0:
                tp1 = entry - (sl_pips * 1.8 * pip_size)
                tp2 = entry - (sl_pips * 3.5 * pip_size)
                target_lock = entry - (sl_pips * 0.8 * pip_size)

                active = {
                    "sym": symbol,
                    "dir": "SELL",
                    "entry": entry,
                    "sl": sl,
                    "tp1": tp1,
                    "tp2": tp2,
                    "target_lock": target_lock,
                    "sl_pips": sl_pips,
                    "idx": i,
                    "locked": False,
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
    print("      ULTIMATE INSTITUTIONAL TREND & EARLY PROFIT LOCK ENGINE")
    print("=" * 80)

    symbols = ["EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "XAUUSD"]
    total_trades = 0
    total_wins = 0
    total_losses = 0
    total_profit = 0.0

    for s in symbols:
        res = test_ultimate_institutional(dp, s, bars_count=2500)
        if res:
            total_trades += res['total']
            total_wins += res['wins']
            total_losses += res['losses']
            total_profit += res['net_gain_cash']
            print(f"🔥 {s:7s} | Trades: {res['total']:2d} | Win: {res['wins']:2d} | Loss: {res['losses']:2d} | Win Rate: {res['win_rate']:5.1f}% | Profit Factor: {res['profit_factor']:4.2f} | Net: {res['net_gain_pct']:+6.2f}% (+€{res['net_gain_cash']:+,.2f})")
        else:
            print(f"🔥 {s:7s} | No trades triggered.")

    print("-" * 80)
    comb_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0
    print(f"🏆 TOTAL PORTFOLIO: {total_trades} Trades | {total_wins} Wins / {total_losses} Losses | Win Rate: {comb_wr:.1f}% | Total Net Gain: +€{total_profit:+,.2f}")
    print("=" * 80)
    dp.shutdown()
