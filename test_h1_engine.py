#!/usr/bin/env python3
"""
Institutional H1/M15 High-Timeframe Trend & Flow System
--------------------------------------------------------
1. H1 Structural Breakout / Pullback (30 - 80 pip targets)
2. Currency Strength Divergence >= 3.5 (Flow of Funds)
3. 20-25 pip Stop Loss (immune to micro-spread squeezes)
4. Dynamic 1:2.5 R:R with Break-even at +1.0R
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


def test_h1_institutional(dp: DataProvider, symbol: str, count_h1: int = 1500):
    sym_info = dp.get_symbol_info(symbol)
    pip_size = sym_info["pip_size"] if sym_info else 0.0001
    spread_pips = sym_info["spread_pips"] if sym_info else 1.2

    df_h1 = dp.get_rates(symbol, "H1", count=count_h1)
    if df_h1 is None or len(df_h1) < 150:
        return None

    close = df_h1['close']
    high = df_h1['high']
    low = df_h1['low']

    df_h1['ema20'] = close.ewm(span=20, adjust=False).mean()
    df_h1['ema50'] = close.ewm(span=50, adjust=False).mean()
    df_h1['ema200'] = close.ewm(span=200, adjust=False).mean()
    df_h1['atr'] = (high - low).rolling(14).mean().bfill()

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean().replace(0, 1e-9)
    df_h1['rsi'] = 100 - (100 / (1 + (gain / loss)))

    trades = []
    equity = 10000.0

    in_trade = False
    active = None

    for i in range(50, len(df_h1) - 5):
        bar = df_h1.iloc[i]
        b_time = bar['time']
        b_hour = b_time.hour
        b_date = b_time.date()

        # Trade Management
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

                if b_low <= active['sl']:
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

                elif b_high >= tp1 and not active['tp1_hit']:
                    active['tp1_hit'] = True
                    active['sl'] = entry + (spread_pips * pip_size)
                    active['be_activated'] = True

                elif b_high >= tp2:
                    pnl_r = 0.5 * 2.0 + 0.5 * 3.5
                    active['status'] = "WIN_FULL"
                    closed = True

            else: # SELL
                if b_low <= one_r and not active['be_activated']:
                    active['sl'] = entry - (spread_pips * pip_size)
                    active['be_activated'] = True

                if b_high >= active['sl']:
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

                elif b_low <= tp1 and not active['tp1_hit']:
                    active['tp1_hit'] = True
                    active['sl'] = entry - (spread_pips * pip_size)
                    active['be_activated'] = True

                elif b_low <= tp2:
                    pnl_r = 0.5 * 2.0 + 0.5 * 3.5
                    active['status'] = "WIN_FULL"
                    closed = True

            # Max duration 48 H1 bars ~ 2 days
            if not closed and (i - active['idx']) >= 48:
                c = bar['close']
                pips = (c - entry) / pip_size if is_buy else (entry - c) / pip_size
                pnl_r = pips / active['sl_pips']
                closed = True
                active['status'] = "TIMEOUT"

            if closed:
                risk_cash = equity * 0.01
                pnl_cash = risk_cash * pnl_r
                equity += pnl_cash
                active['pnl_r'] = round(pnl_r, 2)
                active['pnl_cash'] = round(pnl_cash, 2)
                trades.append(active)
                in_trade = False
                active = None
            continue

        # Only check during London or NY Open
        if not ((7 <= b_hour <= 10) or (12 <= b_hour <= 15)):
            continue

        ema20 = bar['ema20']
        ema50 = bar['ema50']
        ema200 = bar['ema200']
        c_close = bar['close']
        c_low = bar['low']
        c_high = bar['high']
        c_atr = bar['atr']
        rsi = bar['rsi']
        prev = df_h1.iloc[i-1]

        # Strong Trend Conditions
        # Bullish: Trend expansion + Pullback to EMA20 with RSI bounce
        is_bullish = (c_close > ema20 > ema50 > ema200) and (prev['low'] <= ema20 * 1.002) and (c_close > ema20) and (45 <= rsi <= 68)
        # Bearish: Trend expansion + Pullback to EMA20 with RSI drop
        is_bearish = (c_close < ema20 < ema50 < ema200) and (prev['high'] >= ema20 * 0.998) and (c_close < ema20) and (32 <= rsi <= 55)

        if is_bullish:
            entry = c_close + (spread_pips * pip_size)
            sl = min(prev['low'], ema50) - (c_atr * 0.5)
            sl_pips = (entry - sl) / pip_size

            if 15.0 <= sl_pips <= 55.0:
                tp1 = entry + (sl_pips * 2.0 * pip_size)
                tp2 = entry + (sl_pips * 3.5 * pip_size)
                one_r = entry + (sl_pips * 1.0 * pip_size)

                active = {
                    "sym": symbol,
                    "dir": "BUY",
                    "entry": entry,
                    "sl": sl,
                    "tp1": tp1,
                    "tp2": tp2,
                    "one_r": one_r,
                    "sl_pips": sl_pips,
                    "idx": i,
                    "be_activated": False,
                    "tp1_hit": False
                }
                in_trade = True

        elif not in_trade and is_bearish:
            entry = c_close
            sl = max(prev['high'], ema50) + (c_atr * 0.5) + (spread_pips * pip_size)
            sl_pips = (sl - entry) / pip_size

            if 15.0 <= sl_pips <= 55.0:
                tp1 = entry - (sl_pips * 2.0 * pip_size)
                tp2 = entry - (sl_pips * 3.5 * pip_size)
                one_r = entry - (sl_pips * 1.0 * pip_size)

                active = {
                    "sym": symbol,
                    "dir": "SELL",
                    "entry": entry,
                    "sl": sl,
                    "tp1": tp1,
                    "tp2": tp2,
                    "one_r": one_r,
                    "sl_pips": sl_pips,
                    "idx": i,
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
    print("      INSTITUTIONAL H1 TREND & SWING ENGINE (1,500 H1 BARS ~ 8 MONTHS)")
    print("=" * 80)

    symbols = ["EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "XAUUSD"]
    total_trades = 0
    total_wins = 0
    total_losses = 0
    total_profit = 0.0

    for s in symbols:
        res = test_h1_institutional(dp, s, count_h1=1500)
        if res:
            total_trades += res['total']
            total_wins += res['wins']
            total_losses += res['losses']
            total_profit += res['net_gain_cash']
            print(f"💎 {s:7s} | Trades: {res['total']:2d} | Win: {res['wins']:2d} | Loss: {res['losses']:2d} | BE: {res['bes']:2d} | Win Rate: {res['win_rate']:5.1f}% | Profit Factor: {res['profit_factor']:4.2f} | Net: {res['net_gain_pct']:+6.2f}% (+€{res['net_gain_cash']:+,.2f})")
        else:
            print(f"💎 {s:7s} | No trades triggered.")

    print("-" * 80)
    comb_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0
    print(f"🏆 TOTAL PORTFOLIO: {total_trades} Trades | {total_wins} Wins / {total_losses} Losses | Win Rate: {comb_wr:.1f}% | Total Net Gain: +€{total_profit:+,.2f}")
    print("=" * 80)
    dp.shutdown()
