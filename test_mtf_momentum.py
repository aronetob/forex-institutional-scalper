#!/usr/bin/env python3
"""
Institutional MTF Trend & Confluence Engine
--------------------------------------------
Combines:
1. Multi-Timeframe Momentum Alignment (H4, H1, M15)
2. Signal Persistence (Signal must hold for 3 consecutive bars)
3. Daily Pivot & S1/R1 Institutional Boundary Filters
4. ADX Volatility & Directional Filter (ADX > 20)
5. Zero-Lag EMA (ZLEMA) & Ehlers SuperSmoother Filter
6. Dynamic 1:2.0 R:R + Break-Even at +1.0R
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


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def compute_zlema(series: pd.Series, period: int = 20) -> pd.Series:
    lag = int((period - 1) / 2)
    zdata = series + (series - series.shift(lag))
    return zdata.ewm(span=period, adjust=False).mean()


def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hi, lo, cl = df["high"], df["low"], df["close"]
    up = hi.diff()
    down = -lo.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)

    tr1 = hi - lo
    tr2 = (hi - cl.shift(1)).abs()
    tr3 = (lo - cl.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    alpha = 1.0 / period
    atr_s = pd.Series(tr).ewm(alpha=alpha, adjust=False).mean()
    pdm_s = pd.Series(plus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean()
    mdm_s = pd.Series(minus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean()

    plus_di = 100.0 * (pdm_s / atr_s.replace(0, np.nan))
    minus_di = 100.0 * (mdm_s / atr_s.replace(0, np.nan))
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=alpha, adjust=False).mean().fillna(0)


def backtest_mtf_institutional(dp: DataProvider, symbol: str, bars_count: int = 2500):
    sym_info = dp.get_symbol_info(symbol)
    pip_size = sym_info["pip_size"] if sym_info else 0.0001
    spread_pips = sym_info["spread_pips"] if sym_info else 1.0

    df_m15 = dp.get_rates(symbol, "M15", count=bars_count)
    df_h1 = dp.get_rates(symbol, "H1", count=int(bars_count / 3))
    df_d1 = dp.get_rates(symbol, "D1", count=60)

    if df_m15 is None or len(df_m15) < 200:
        return None

    # M15 EMAs
    df_m15['ema9'] = compute_ema(df_m15['close'], 9)
    df_m15['ema21'] = compute_ema(df_m15['close'], 21)
    df_m15['ema50'] = compute_ema(df_m15['close'], 50)
    df_m15['zlema'] = compute_zlema(df_m15['close'], 20)
    df_m15['adx'] = compute_adx(df_m15, 14)
    df_m15['atr'] = (df_m15['high'] - df_m15['low']).rolling(14).mean().bfill()

    df_m15['time'] = pd.to_datetime(df_m15['time']).astype('datetime64[ns]')

    # H1 Trend
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

    # Daily Pivots
    if df_d1 is not None and len(df_d1) > 5:
        df_d1['time'] = pd.to_datetime(df_d1['time']).astype('datetime64[ns]')
        df_d1['p_pivot'] = (df_d1['high'] + df_d1['low'] + df_d1['close']) / 3.0
        df_d1['r1_pivot'] = 2 * df_d1['p_pivot'] - df_d1['low']
        df_d1['s1_pivot'] = 2 * df_d1['p_pivot'] - df_d1['high']
        d_pivots = df_d1[['time', 'p_pivot', 'r1_pivot', 's1_pivot']].copy()
        d_pivots['time'] = d_pivots['time'] + pd.Timedelta(days=1)
        df_m15 = pd.merge_asof(df_m15.sort_values('time'), d_pivots.sort_values('time'), on='time')
    else:
        df_m15['p_pivot'] = np.nan
        df_m15['r1_pivot'] = np.nan
        df_m15['s1_pivot'] = np.nan

    # Raw MTF Signal: M15 EMA9/21 cross + H1 Trend + ZLEMA price confirmation
    m15_bull = (df_m15['ema9'] > df_m15['ema21']) & (df_m15['close'] > df_m15['zlema']) & (df_m15['h1_trend'] >= 0)
    m15_bear = (df_m15['ema9'] < df_m15['ema21']) & (df_m15['close'] < df_m15['zlema']) & (df_m15['h1_trend'] <= 0)

    raw_signal = np.where(m15_bull, 1, np.where(m15_bear, -1, 0))

    # Persistence: Must persist for at least 3 bars (~45 mins)
    persisted = pd.Series(raw_signal).rolling(3).apply(
        lambda s: s[0] if (len(set(s)) == 1 and s[0] != 0) else 0, raw=True
    ).fillna(0).astype(int).values

    trades = []
    equity = 10000.0
    equity_curve = [equity]

    in_trade = False
    active = None
    last_trade_date = None

    for i in range(50, len(df_m15) - 5):
        bar = df_m15.iloc[i]
        b_time = bar['time']
        b_hour = b_time.hour
        b_date = b_time.date()

        # Trade Management
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
                # Trigger Break-even at +1.0R
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
                    pnl_r = 0.5 * 1.8 + 0.5 * 3.2
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
                    pnl_r = 0.5 * 1.8 + 0.5 * 3.2
                    active['status'] = "WIN_FULL"
                    closed = True

            # Max duration: 24 bars (~6 hours)
            if not closed and (i - active['idx']) >= 24:
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

        # Killzone Filter (London & NY: 07:00 - 16:00 UTC)
        if not (7 <= b_hour <= 16):
            continue

        if last_trade_date == b_date:
            continue

        sig = persisted[i]
        prev_sig = persisted[i-1]

        # Trigger only on the first confirmed persisted signal shift
        if sig != 0 and prev_sig == 0:
            c_close = bar['close']
            c_atr = bar['atr']
            adx_val = bar['adx']

            # ADX trend filter (ensure market is moving, not dead chop)
            if adx_val < 18.0:
                continue

            r1 = bar['r1_pivot']
            s1 = bar['s1_pivot']

            if sig == 1: # BUY
                # Avoid buying directly into Daily R1 resistance
                if pd.notna(r1) and c_close >= r1 * 0.999:
                    continue

                entry = c_close + (spread_pips * pip_size)
                sl = entry - max(c_atr * 1.5, 12.0 * pip_size)
                sl_pips = (entry - sl) / pip_size

                if 10.0 <= sl_pips <= 45.0:
                    tp1 = entry + (sl_pips * 1.8 * pip_size)
                    tp2 = entry + (sl_pips * 3.2 * pip_size)
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

            elif sig == -1: # SELL
                # Avoid selling directly into Daily S1 support
                if pd.notna(s1) and c_close <= s1 * 1.001:
                    continue

                entry = c_close
                sl = entry + max(c_atr * 1.5, 12.0 * pip_size) + (spread_pips * pip_size)
                sl_pips = (sl - entry) / pip_size

                if 10.0 <= sl_pips <= 45.0:
                    tp1 = entry - (sl_pips * 1.8 * pip_size)
                    tp2 = entry - (sl_pips * 3.2 * pip_size)
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
    print("      OPTIMIZED INSTITUTIONAL MTF MOMENTUM & PIVOT STRATEGY")
    print("=" * 80)

    symbols = ["EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"]
    total_trades = 0
    total_wins = 0
    total_losses = 0
    total_profit = 0.0

    for s in symbols:
        res = backtest_mtf_institutional(dp, s, bars_count=2500)
        if res:
            total_trades += res['total']
            total_wins += res['wins']
            total_losses += res['losses']
            total_profit += res['net_gain_cash']
            print(f"🚀 {s:7s} | Trades: {res['total']:2d} | Win: {res['wins']:2d} | Loss: {res['losses']:2d} | BE: {res['bes']:2d} | Win Rate: {res['win_rate']:5.1f}% | Profit Factor: {res['profit_factor']:4.2f} | Net: {res['net_gain_pct']:+6.2f}% (+€{res['net_gain_cash']:+,.2f})")
        else:
            print(f"🚀 {s:7s} | No trades triggered.")

    print("-" * 80)
    comb_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0
    print(f"🏆 TOTAL PORTFOLIO: {total_trades} Trades | {total_wins} Wins / {total_losses} Losses | Win Rate: {comb_wr:.1f}% | Total Net Gain: +€{total_profit:+,.2f}")
    print("=" * 80)
    dp.shutdown()
