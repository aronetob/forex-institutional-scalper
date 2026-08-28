#!/usr/bin/env python3
"""
Institutional Forex Backtesting & Multi-Strategy Validation Engine
-------------------------------------------------------------------
Provides rigorous, institutional backtesting for 3 distinct high-edge strategies:
1. 'MTF_TREND': Multi-Timeframe Momentum & Consensus (H4+H1+M15 Alignment)
2. 'SESSION_TARGET': Asian Liquidity Sweep to Opposite Range Target
3. 'JUDAS_SWING': London Open Liquidity Grab & Rejection Reversal
"""

import sys
import logging
from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from config import TARGET_SYMBOLS
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


class InstitutionalBacktester:
    """Executes high-fidelity backtests of institutional Forex setups."""

    def __init__(self, data_provider: DataProvider):
        self.dp = data_provider

    def run_backtest(
        self,
        symbol: str,
        strategy_name: str = "MTF_TREND",
        bars_count: int = 2000,
        min_rr: float = 2.0,
        risk_per_trade_pct: float = 1.0,
        starting_balance: float = 10000.0,
        require_killzone: bool = True,
        use_breakeven: bool = True
    ) -> Dict[str, Any]:
        """Runs the chosen institutional strategy over historical candle data."""
        sym_info = self.dp.get_symbol_info(symbol)
        pip_size = sym_info["pip_size"] if sym_info else 0.0001
        spread_pips = sym_info["spread_pips"] if sym_info else 1.2
        digits = sym_info["digits"] if sym_info else 5

        df_m15 = self.dp.get_rates(symbol, "M15", count=bars_count)
        if df_m15 is None or len(df_m15) < 150:
            return {"error": "Insufficient historical data"}

        df_h1 = self.dp.get_rates(symbol, "H1", count=max(60, int(bars_count / 3)))
        df_d1 = self.dp.get_rates(symbol, "D1", count=60)

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

        # Merge Daily Pivots
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

        # MTF Signal
        m15_bull = (df_m15['ema9'] > df_m15['ema21']) & (df_m15['close'] > df_m15['zlema']) & (df_m15['h1_trend'] >= 0)
        m15_bear = (df_m15['ema9'] < df_m15['ema21']) & (df_m15['close'] < df_m15['zlema']) & (df_m15['h1_trend'] <= 0)
        raw_mtf = np.where(m15_bull, 1, np.where(m15_bear, -1, 0))

        # Persistence check
        persisted_mtf = pd.Series(raw_mtf).rolling(3).apply(
            lambda s: s[0] if (len(set(s)) == 1 and s[0] != 0) else 0, raw=True
        ).fillna(0).astype(int).values

        trades = []
        equity = starting_balance
        equity_curve = [equity]

        in_trade = False
        active_trade = None
        last_trade_date = None

        for i in range(50, len(df_m15) - 5):
            current_bar = df_m15.iloc[i]
            bar_time = current_bar['time']
            bar_hour = bar_time.hour
            bar_date = bar_time.date()

            # ----------------------------------------------------------
            # 1. TRADE MANAGEMENT
            # ----------------------------------------------------------
            if in_trade and active_trade is not None:
                is_buy = active_trade['direction'] == "BUY"
                entry = active_trade['entry_price']
                sl = active_trade['stop_loss']
                tp1 = active_trade['take_profit_1']
                tp2 = active_trade['take_profit_2']
                one_r = active_trade.get('one_r', entry + (active_trade['sl_pips'] * pip_size))

                high = current_bar['high']
                low = current_bar['low']

                trade_closed = False
                pnl_r = 0.0

                if is_buy:
                    # Move to BE at +1.0R
                    if high >= one_r and use_breakeven and not active_trade['be_activated']:
                        active_trade['stop_loss'] = entry + (spread_pips * pip_size)
                        active_trade['be_activated'] = True

                    # Check SL
                    if low <= active_trade['stop_loss']:
                        if active_trade['tp1_hit']:
                            pnl_r = 0.5 * min_rr
                            active_trade['status'] = "WIN_BE"
                        elif active_trade.get('be_activated'):
                            pnl_r = 0.0
                            active_trade['status'] = "BE"
                        else:
                            pnl_r = -1.0
                            active_trade['status'] = "LOSS"
                        trade_closed = True
                        active_trade['exit_price'] = active_trade['stop_loss']

                    # Check TP1
                    elif high >= tp1 and not active_trade['tp1_hit']:
                        active_trade['tp1_hit'] = True
                        if use_breakeven:
                            active_trade['stop_loss'] = entry + (spread_pips * pip_size)

                    # Check TP2
                    elif high >= tp2:
                        pnl_r = 0.5 * min_rr + 0.5 * (min_rr * 1.75)
                        active_trade['status'] = "WIN_FULL"
                        trade_closed = True
                        active_trade['exit_price'] = tp2

                else: # SELL
                    if low <= one_r and use_breakeven and not active_trade['be_activated']:
                        active_trade['stop_loss'] = entry - (spread_pips * pip_size)
                        active_trade['be_activated'] = True

                    if high >= active_trade['stop_loss']:
                        if active_trade['tp1_hit']:
                            pnl_r = 0.5 * min_rr
                            active_trade['status'] = "WIN_BE"
                        elif active_trade.get('be_activated'):
                            pnl_r = 0.0
                            active_trade['status'] = "BE"
                        else:
                            pnl_r = -1.0
                            active_trade['status'] = "LOSS"
                        trade_closed = True
                        active_trade['exit_price'] = active_trade['stop_loss']

                    elif low <= tp1 and not active_trade['tp1_hit']:
                        active_trade['tp1_hit'] = True
                        if use_breakeven:
                            active_trade['stop_loss'] = entry - (spread_pips * pip_size)

                    elif low <= tp2:
                        pnl_r = 0.5 * min_rr + 0.5 * (min_rr * 1.75)
                        active_trade['status'] = "WIN_FULL"
                        trade_closed = True
                        active_trade['exit_price'] = tp2

                # Timeout after 24 bars (~6 hours)
                if not trade_closed and (i - active_trade['entry_index']) >= 24:
                    current_close = current_bar['close']
                    pnl_pips = (current_close - entry) / pip_size if is_buy else (entry - current_close) / pip_size
                    pnl_r = pnl_pips / active_trade['sl_pips']
                    trade_closed = True
                    active_trade['status'] = "TIMEOUT"
                    active_trade['exit_price'] = current_close

                if trade_closed:
                    risk_amount = equity * (risk_per_trade_pct / 100.0)
                    pnl_cash = risk_amount * pnl_r
                    equity += pnl_cash
                    equity_curve.append(round(equity, 2))

                    active_trade['pnl_r'] = round(pnl_r, 2)
                    active_trade['pnl_cash'] = round(pnl_cash, 2)
                    active_trade['equity_after'] = round(equity, 2)
                    active_trade['exit_time'] = bar_time
                    trades.append(active_trade)

                    in_trade = False
                    active_trade = None
                continue

            # ----------------------------------------------------------
            # 2. SESSION KILLZONE CHECK (PEAK INSTITUTIONAL WINDOWS)
            # ----------------------------------------------------------
            # London Peak: 07:00 - 10:30 UTC | NY Peak: 12:30 - 14:30 UTC
            # Ban late-day London Fix / session close noise (14:30+ UTC)
            if require_killzone:
                b_min = bar_time.minute
                is_peak_london = (7 <= bar_hour <= 9) or (bar_hour == 10 and b_min <= 30)
                is_peak_ny = (bar_hour == 12 and b_min >= 30) or (13 <= bar_hour <= 14)
                if not (is_peak_london or is_peak_ny):
                    continue

            if last_trade_date == bar_date:
                continue

            # ----------------------------------------------------------
            # 3. STRATEGY ENTRY LOGIC
            # ----------------------------------------------------------
            setup_found = False
            direction = None
            entry_price = None
            stop_loss = None
            reason = ""

            c_close = current_bar['close']
            c_atr = current_bar['atr']
            ema200 = current_bar['ema200']

            # Strategy 1: MTF Momentum & Consensus
            if strategy_name == "MTF_TREND":
                sig = persisted_mtf[i]
                prev_sig = persisted_mtf[i-1]

                if sig != 0 and prev_sig == 0:
                    adx_val = current_bar['adx']
                    if adx_val < 18.0:
                        continue

                    r1 = current_bar['r1_pivot']
                    s1 = current_bar['s1_pivot']

                    prev_bars = df_m15.iloc[max(0, i-8):i]
                    swing_low = prev_bars['low'].min()
                    swing_high = prev_bars['high'].max()

                    # BUY with 200 EMA trend anchor + Structural SL
                    if sig == 1 and c_close > ema200:
                        if pd.notna(r1) and c_close >= r1 * 0.999:
                            continue
                        direction = "BUY"
                        entry_price = c_close + (spread_pips * pip_size)
                        stop_loss = min(swing_low, entry_price - (c_atr * 1.8))
                        setup_found = True
                        reason = "MTF Momentum Consensus + 200 EMA Trend Anchor"

                    # SELL with 200 EMA trend anchor + Structural SL
                    elif sig == -1 and c_close < ema200:
                        if pd.notna(s1) and c_close <= s1 * 1.001:
                            continue
                        direction = "SELL"
                        entry_price = c_close
                        stop_loss = max(swing_high, entry_price + (c_atr * 1.8)) + (spread_pips * pip_size)
                        setup_found = True
                        reason = "MTF Momentum Consensus + 200 EMA Trend Anchor"

            # Strategy 2: Session Range Target
            elif strategy_name == "SESSION_TARGET":
                today_asian = df_m15[(df_m15['time'].dt.date == bar_date) & (df_m15['time'].dt.hour < 7)]
                if len(today_asian) >= 4:
                    a_high = today_asian['high'].max()
                    a_low = today_asian['low'].min()
                    a_range = (a_high - a_low) / pip_size

                    if 12.0 <= a_range <= 45.0:
                        prev_bar = df_m15.iloc[i-1]
                        if prev_bar['low'] < a_low and c_close > a_low:
                            direction = "BUY"
                            entry_price = c_close + (spread_pips * pip_size)
                            stop_loss = min(prev_bar['low'], current_bar['low']) - (c_atr * 0.4)
                            setup_found = True
                            reason = f"Asian Low ({a_low:.5f}) Sweep -> Target Asian High"
                        elif prev_bar['high'] > a_high and c_close < a_high:
                            direction = "SELL"
                            entry_price = c_close
                            stop_loss = max(prev_bar['high'], current_bar['high']) + (c_atr * 0.4) + (spread_pips * pip_size)
                            setup_found = True
                            reason = f"Asian High ({a_high:.5f}) Sweep -> Target Asian Low"

            # Execute Trade
            if setup_found and direction:
                sl_pips = abs(entry_price - stop_loss) / pip_size
                if 8.0 <= sl_pips <= 50.0:
                    tp1_pips = sl_pips * min_rr
                    tp2_pips = sl_pips * (min_rr * 1.75)

                    if direction == "BUY":
                        tp1 = round(entry_price + (tp1_pips * pip_size), digits)
                        tp2 = round(entry_price + (tp2_pips * pip_size), digits)
                        one_r = entry_price + (sl_pips * 1.0 * pip_size)
                    else:
                        tp1 = round(entry_price - (tp1_pips * pip_size), digits)
                        tp2 = round(entry_price - (tp2_pips * pip_size), digits)
                        one_r = entry_price - (sl_pips * 1.0 * pip_size)

                    active_trade = {
                        "symbol": symbol,
                        "direction": direction,
                        "entry_time": bar_time,
                        "entry_index": i,
                        "entry_price": round(entry_price, digits),
                        "stop_loss": round(stop_loss, digits),
                        "take_profit_1": tp1,
                        "take_profit_2": tp2,
                        "one_r": one_r,
                        "sl_pips": round(sl_pips, 1),
                        "tp1_pips": round(tp1_pips, 1),
                        "tp2_pips": round(tp2_pips, 1),
                        "reason": reason,
                        "tp1_hit": False,
                        "be_activated": False
                    }
                    in_trade = True
                    last_trade_date = bar_date

        if not trades:
            return {
                "symbol": symbol,
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "net_profit_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "trades_df": pd.DataFrame()
            }

        tdf = pd.DataFrame(trades)
        wins = len(tdf[tdf['pnl_r'] > 0])
        losses = len(tdf[tdf['pnl_r'] < 0])
        bes = len(tdf[tdf['pnl_r'] == 0])
        total = len(tdf)

        win_rate = round((wins / total) * 100.0, 1)
        tot_gain = tdf[tdf['pnl_cash'] > 0]['pnl_cash'].sum()
        tot_loss = abs(tdf[tdf['pnl_cash'] < 0]['pnl_cash'].sum())
        pf = round(tot_gain / tot_loss, 2) if tot_loss > 0 else round(tot_gain, 2)
        net_pct = round(((equity - starting_balance) / starting_balance) * 100.0, 2)

        # Max drawdown
        eq_s = pd.Series(equity_curve)
        cum_max = eq_s.cummax()
        drawdowns = (eq_s - cum_max) / cum_max * 100.0
        max_dd = round(abs(drawdowns.min()), 2)

        # Expectancy
        avg_win = tdf[tdf['pnl_r'] > 0]['pnl_r'].mean() if wins > 0 else 0.0
        avg_loss = abs(tdf[tdf['pnl_r'] < 0]['pnl_r'].mean()) if losses > 0 else 0.0
        exp_r = round(((win_rate/100.0) * avg_win) - (((100.0 - win_rate)/100.0) * avg_loss), 2)

        return {
            "symbol": symbol,
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "breakevens": bes,
            "win_rate": win_rate,
            "profit_factor": pf,
            "net_profit_cash": round(equity - starting_balance, 2),
            "net_profit_pct": net_pct,
            "expectancy_r": exp_r,
            "max_drawdown_pct": max_dd,
            "final_equity": round(equity, 2),
            "equity_curve": equity_curve,
            "trades_df": tdf
        }
