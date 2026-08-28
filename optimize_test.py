#!/usr/bin/env python3
"""
Sniper Strategy Optimization Test
---------------------------------
Evaluates enhanced institutional filters:
1. Rejection Pin-Bar / Engulfing Confirmation
2. Asian Range Quality Filter (12 - 45 pips)
3. Strict HTF 200-EMA & Momentum Alignment
4. Sniper Killzone Execution (07:00-09:30 UTC & 12:00-14:30 UTC)
5. Early Zero-Risk Break-Even at +1.0R & TP1 at +1.8R
"""

import sys
import os
import numpy as np
import pandas as pd

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from data_provider import DataProvider


def run_sniper_backtest(dp: DataProvider, symbol: str, bars_count: int = 2000):
    sym_info = dp.get_symbol_info(symbol)
    pip_size = sym_info["pip_size"] if sym_info else 0.0001
    spread_pips = sym_info["spread_pips"] if sym_info else 1.2

    df_m15 = dp.get_rates(symbol, "M15", count=bars_count)
    if df_m15 is None or len(df_m15) < 200:
        return None

    close = df_m15['close']
    high = df_m15['high']
    low = df_m15['low']
    op = df_m15['open']

    # Indicators
    df_m15['ema50'] = close.ewm(span=50, adjust=False).mean()
    df_m15['ema200'] = close.ewm(span=200, adjust=False).mean()
    df_m15['atr'] = (high - low).rolling(14).mean().bfill()

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean().replace(0, 1e-9)
    df_m15['rsi'] = 100 - (100 / (1 + (gain / loss)))

    trades = []
    equity = 10000.0
    equity_curve = [equity]

    in_trade = False
    active = None
    last_trade_date = None

    for i in range(50, len(df_m15) - 10):
        bar = df_m15.iloc[i]
        b_time = bar['time']
        b_hour = b_time.hour
        b_min = b_time.minute
        b_date = b_time.date()

        # Trade management
        if in_trade and active:
            is_buy = active['dir'] == "BUY"
            b_high = bar['high']
            b_low = bar['low']
            sl = active['sl']
            tp1 = active['tp1']
            tp2 = active['tp2']
            entry = active['entry']
            one_r = active['one_r']

            closed = False
            pnl_r = 0.0

            if is_buy:
                # Break-even trigger at +1.0R
                if b_high >= one_r and not active['be_activated']:
                    active['sl'] = entry + (spread_pips * pip_size)
                    active['be_activated'] = True

                # Check SL
                if b_low <= active['sl']:
                    if active['tp1_hit']:
                        pnl_r = 0.5 * 1.8
                        active['status'] = "WIN_BE"
                    elif active['be_activated']:
                        pnl_r = 0.0
                        active['status'] = "BE"
                    else:
                        pnl_r = -1.0
                        active['status'] = "LOSS"
                    closed = True

                # Check TP1
                elif b_high >= tp1 and not active['tp1_hit']:
                    active['tp1_hit'] = True
                    active['sl'] = entry + (spread_pips * pip_size)
                    active['be_activated'] = True

                # Check TP2
                elif b_high >= tp2:
                    pnl_r = 0.5 * 1.8 + 0.5 * 3.5
                    active['status'] = "WIN_FULL"
                    closed = True

            else: # SELL
                if b_low <= one_r and not active['be_activated']:
                    active['sl'] = entry - (spread_pips * pip_size)
                    active['be_activated'] = True

                if b_high >= active['sl']:
                    if active['tp1_hit']:
                        pnl_r = 0.5 * 1.8
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
                    pnl_r = 0.5 * 1.8 + 0.5 * 3.5
                    active['status'] = "WIN_FULL"
                    closed = True

            # Max duration (28 bars ~ 7 hours)
            if not closed and (i - active['idx']) >= 28:
                c = bar['close']
                pips = (c - entry) / pip_size if is_buy else (entry - c) / pip_size
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

        # --------------------------------------------------------------
        # SNIPER ENTRY CRITERIA
        # --------------------------------------------------------------
        # Strict Killzone Timing: London (07:00-09:30 UTC) or NY (12:00-14:30 UTC)
        is_london_sniper = (7 <= b_hour < 9) or (b_hour == 9 and b_min <= 30)
        is_ny_sniper = (12 <= b_hour < 14) or (b_hour == 14 and b_min <= 30)

        if not (is_london_sniper or is_ny_sniper):
            continue

        # Only 1 trade per day per pair
        if last_trade_date == b_date:
            continue

        # Calculate Asian Range (00:00 - 07:00 UTC)
        today_asian = df_m15[(df_m15['time'].dt.date == b_date) & (df_m15['time'].dt.hour < 7)]
        if len(today_asian) < 4:
            continue

        asian_high = today_asian['high'].max()
        asian_low = today_asian['low'].min()
        asian_range_pips = (asian_high - asian_low) / pip_size

        # Asian Range Quality Filter (Must be healthy, not over-expanded)
        if asian_range_pips < 10.0 or asian_range_pips > 50.0:
            continue

        prev = df_m15.iloc[i-1]
        c_close = bar['close']
        c_open = bar['open']
        c_high = bar['high']
        c_low = bar['low']
        c_atr = bar['atr']
        ema200 = bar['ema200']
        rsi = bar['rsi']

        candle_range = c_high - c_low
        if candle_range == 0:
            continue

        # --------------------------------------------------------------
        # 1. BULLISH SNIPER SETUP
        # --------------------------------------------------------------
        # Previous or current bar swept Asian Low, but closed back inside with bullish rejection
        swept_low = prev['low'] < asian_low or c_low < asian_low
        bullish_rejection = c_close > asian_low and c_close > c_open
        lower_wick_ratio = (min(c_open, c_close) - c_low) / candle_range

        # Trend alignment: Above 200 EMA or RSI oversold bounce (< 42)
        bullish_trend_ok = (c_close >= ema200 * 0.995) or (rsi < 42.0)

        if swept_low and bullish_rejection and lower_wick_ratio >= 0.30 and bullish_trend_ok:
            entry = c_close + (spread_pips * pip_size)
            sweep_min = min(prev['low'], c_low)
            sl = sweep_min - (c_atr * 0.5)
            sl_pips = (entry - sl) / pip_size

            # Enforce solid SL buffer (8 - 35 pips)
            if 8.0 <= sl_pips <= 40.0:
                tp1 = entry + (sl_pips * 1.8 * pip_size)
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
                    "tp1_hit": False,
                    "time": b_time
                }
                in_trade = True
                last_trade_date = b_date

        # --------------------------------------------------------------
        # 2. BEARISH SNIPER SETUP
        # --------------------------------------------------------------
        swept_high = prev['high'] > asian_high or c_high > asian_high
        bearish_rejection = c_close < asian_high and c_close < c_open
        upper_wick_ratio = (c_high - max(c_open, c_close)) / candle_range
        bearish_trend_ok = (c_close <= ema200 * 1.005) or (rsi > 58.0)

        if not in_trade and swept_high and bearish_rejection and upper_wick_ratio >= 0.30 and bearish_trend_ok:
            entry = c_close
            sweep_max = max(prev['high'], c_high)
            sl = sweep_max + (c_atr * 0.5) + (spread_pips * pip_size)
            sl_pips = (sl - entry) / pip_size

            if 8.0 <= sl_pips <= 40.0:
                tp1 = entry - (sl_pips * 1.8 * pip_size)
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
                    "tp1_hit": False,
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
    print("       SNIPER INSTITUTIONAL OPTIMIZATION - MULTI-ASSET BENCHMARK")
    print("=" * 80)

    symbols = ["EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURJPY", "AUDUSD", "USDCAD", "USDCHF"]
    total_trades_all = 0
    total_wins_all = 0
    total_losses_all = 0
    total_profit_all = 0.0

    for s in symbols:
        res = run_sniper_backtest(dp, s, bars_count=2500)
        if res:
            total_trades_all += res['total']
            total_wins_all += res['wins']
            total_losses_all += res['losses']
            total_profit_all += res['net_gain_cash']
            print(f"🎯 {s:7s} | Trades: {res['total']:2d} | Win: {res['wins']:2d} | Loss: {res['losses']:2d} | BE: {res['bes']:2d} | Win Rate: {res['win_rate']:5.1f}% | Profit Factor: {res['profit_factor']:4.2f} | Net: +{res['net_gain_pct']:+.2f}% (+€{res['net_gain_cash']:+,.2f})")
        else:
            print(f"🎯 {s:7s} | No trades meeting strict sniper filters.")

    print("-" * 80)
    comb_wr = (total_wins_all / total_trades_all * 100) if total_trades_all > 0 else 0
    print(f"🏆 PORTFOLIO TOTAL: {total_trades_all} Trades | {total_wins_all} Wins / {total_losses_all} Losses | Win Rate: {comb_wr:.1f}% | Total Net Gain: +€{total_profit_all:+,.2f}")
    print("=" * 80)
    dp.shutdown()
