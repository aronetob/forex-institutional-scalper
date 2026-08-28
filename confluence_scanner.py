#!/usr/bin/env python3
"""
Institutional Confluence & Structure Scanner (Tier 2)
------------------------------------------------------
Scans multi-timeframe price action for high-conviction institutional setups:
1. Asian Session High/Low & Prior Day High/Low (PDH/PDL) Liquidity Sweeps
2. Session VWAP and Standard Deviation Bands (±1.5σ, ±2.0σ)
3. Lower Timeframe Market Structure Shifts (CHoCH / BOS on M15 & M5)
4. Fair Value Gaps (FVG) and Institutional Supply/Demand Imbalances
5. RSI Momentum and Multi-Bar Divergences
"""

import sys
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import pandas as pd

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from data_provider import DataProvider

logger = logging.getLogger("ConfluenceScanner")


class ConfluenceScanner:
    """Detects institutional liquidity footprints, structure shifts, and pricing imbalances."""

    def __init__(self, data_provider: DataProvider):
        self.dp = data_provider

    # ------------------------------------------------------------------
    # 1. ASIAN RANGE & PRIOR DAY LIQUIDITY SWEEPS
    # ------------------------------------------------------------------
    def detect_liquidity_sweeps(self, symbol: str, df_m15: pd.DataFrame, df_d1: pd.DataFrame) -> Dict[str, Any]:
        """
        Identifies Asian Session (00:00-07:00 UTC) range and checks if price
        executed a Liquidity Grab (Judas Swing) during London/NY open.
        Also checks Prior Day High/Low (PDH/PDL) sweeps.
        """
        if df_m15 is None or len(df_m15) < 30:
            return {"sweep_detected": False, "type": "NONE"}

        sym_info = self.dp.get_symbol_info(symbol)
        if sym_info and sym_info.get("pip_size"):
            pip_size = sym_info["pip_size"]
        elif "JPY" in symbol:
            pip_size = 0.01
        elif "XAU" in symbol or "GOLD" in symbol:
            pip_size = 0.10
        elif "XAG" in symbol or "SILVER" in symbol:
            pip_size = 0.01
        else:
            pip_size = 0.0001

        # Extract today's M15 bars
        last_time = df_m15['time'].iloc[-1]
        today_date = last_time.date()
        today_bars = df_m15[df_m15['time'].dt.date == today_date].copy()

        if len(today_bars) < 4:
            # Not enough bars today, look at last 24 hours
            today_bars = df_m15.tail(32).copy()

        # Asian Session bars (00:00 to 07:00 UTC)
        asian_bars = today_bars[(today_bars['time'].dt.hour >= 0) & (today_bars['time'].dt.hour < 7)]
        
        asian_high = asian_bars['high'].max() if len(asian_bars) > 0 else today_bars['high'].iloc[0]
        asian_low = asian_bars['low'].min() if len(asian_bars) > 0 else today_bars['low'].iloc[0]
        asian_range_pips = round((asian_high - asian_low) / pip_size, 1)

        # Prior Day High and Low (PDH / PDL)
        pdh = None
        pdl = None
        if df_d1 is not None and len(df_d1) >= 2:
            pdh = float(df_d1['high'].iloc[-2])
            pdl = float(df_d1['low'].iloc[-2])

        # Current & recent bars (post-Asian / current session)
        post_asian = today_bars[today_bars['time'].dt.hour >= 7] if len(today_bars[today_bars['time'].dt.hour >= 7]) > 0 else today_bars.tail(8)
        
        current_price = float(df_m15['close'].iloc[-1])
        latest_bars = post_asian.tail(6)  # Last 1.5 hours

        sweep_type = "NONE"
        sweep_level = None
        sweep_wick_extremum = None
        sweep_pips = 0.0
        reason = ""

        # Check for Bullish Liquidity Sweep (Price dropped below Asian Low / PDL, took liquidity, and reversed back up)
        for idx, bar in latest_bars.iterrows():
            # Asian Low Sweep
            if bar['low'] < asian_low and bar['close'] > asian_low:
                sweep_type = "BULLISH_ASIAN_LOW_SWEEP"
                sweep_level = asian_low
                sweep_wick_extremum = bar['low']
                sweep_pips = round((asian_low - bar['low']) / pip_size, 1)
                reason = f"Asian Low ({asian_low:.5f}) swept by {sweep_pips} pips; closed back inside."
                break
            # PDL Sweep
            elif pdl and bar['low'] < pdl and bar['close'] > pdl:
                sweep_type = "BULLISH_PDL_SWEEP"
                sweep_level = pdl
                sweep_wick_extremum = bar['low']
                sweep_pips = round((pdl - bar['low']) / pip_size, 1)
                reason = f"Prior Day Low ({pdl:.5f}) swept by {sweep_pips} pips; strong bullish rejection."
                break

        # Check for Bearish Liquidity Sweep (Price wicked above Asian High / PDH, took liquidity, and rejected down)
        if sweep_type == "NONE":
            for idx, bar in latest_bars.iterrows():
                # Asian High Sweep
                if bar['high'] > asian_high and bar['close'] < asian_high:
                    sweep_type = "BEARISH_ASIAN_HIGH_SWEEP"
                    sweep_level = asian_high
                    sweep_wick_extremum = bar['high']
                    sweep_pips = round((bar['high'] - asian_high) / pip_size, 1)
                    reason = f"Asian High ({asian_high:.5f}) swept by {sweep_pips} pips; closed back inside."
                    break
                # PDH Sweep
                elif pdh and bar['high'] > pdh and bar['close'] < pdh:
                    sweep_type = "BEARISH_PDH_SWEEP"
                    sweep_level = pdh
                    sweep_wick_extremum = bar['high']
                    sweep_pips = round((bar['high'] - pdh) / pip_size, 1)
                    reason = f"Prior Day High ({pdh:.5f}) swept by {sweep_pips} pips; strong bearish rejection."
                    break

        return {
            "sweep_detected": sweep_type != "NONE",
            "sweep_type": sweep_type,
            "sweep_level": sweep_level,
            "sweep_wick_extremum": sweep_wick_extremum,
            "sweep_pips": sweep_pips,
            "asian_high": round(asian_high, 5),
            "asian_low": round(asian_low, 5),
            "asian_range_pips": asian_range_pips,
            "pdh": round(pdh, 5) if pdh else None,
            "pdl": round(pdl, 5) if pdl else None,
            "reason": reason
        }

    # ------------------------------------------------------------------
    # 2. SESSION VWAP & STANDARD DEVIATION BANDS
    # ------------------------------------------------------------------
    def calculate_session_vwap(self, df_m5: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculates intraday Session VWAP with ±1.0σ and ±2.0σ Standard Deviation Bands.
        Identifies whether current price is at Institutional Discount or Premium.
        """
        if df_m5 is None or len(df_m5) < 20:
            return {"status": "NEUTRAL", "vwap": None}

        # Calculate Typical Price
        tp = (df_m5['high'] + df_m5['low'] + df_m5['close']) / 3.0
        vol = df_m5['volume'].replace(0, 1.0)  # avoid division by zero

        # Intraday cumulative VWAP (last 100 bars ~ 8.3 hours)
        recent_bars = min(120, len(df_m5))
        tp_recent = tp.tail(recent_bars)
        vol_recent = vol.tail(recent_bars)

        cum_vol = vol_recent.cumsum()
        cum_tp_vol = (tp_recent * vol_recent).cumsum()
        vwap_series = cum_tp_vol / cum_vol

        current_vwap = float(vwap_series.iloc[-1])
        current_close = float(df_m5['close'].iloc[-1])

        # Standard Deviation calculation
        variance = ((tp_recent - vwap_series) ** 2 * vol_recent).cumsum() / cum_vol
        std = np.sqrt(variance).iloc[-1]
        if std == 0 or np.isnan(std):
            std = current_close * 0.001

        upper_1s = current_vwap + 1.0 * std
        upper_2s = current_vwap + 2.0 * std
        lower_1s = current_vwap - 1.0 * std
        lower_2s = current_vwap - 2.0 * std

        # Valuation Zone
        z_score = (current_close - current_vwap) / std

        if z_score <= -1.8:
            zone = "DEEP_DISCOUNT (Institutional Buy Zone)"
            bias = "BULLISH_DISCOUNT"
        elif z_score <= -0.8:
            zone = "DISCOUNT"
            bias = "BULLISH_DISCOUNT"
        elif z_score >= 1.8:
            zone = "DEEP_PREMIUM (Institutional Sell Zone)"
            bias = "BEARISH_PREMIUM"
        elif z_score >= 0.8:
            zone = "PREMIUM"
            bias = "BEARISH_PREMIUM"
        else:
            zone = "FAIR_VALUE"
            bias = "NEUTRAL"

        return {
            "vwap": round(current_vwap, 5),
            "upper_2s": round(upper_2s, 5),
            "upper_1s": round(upper_1s, 5),
            "lower_1s": round(lower_1s, 5),
            "lower_2s": round(lower_2s, 5),
            "z_score": round(z_score, 2),
            "zone": zone,
            "bias": bias
        }

    # ------------------------------------------------------------------
    # 3. MARKET STRUCTURE SHIFT (CHoCH / BOS)
    # ------------------------------------------------------------------
    def detect_market_structure_shift(self, df_m5: pd.DataFrame, lookback: int = 40) -> Dict[str, Any]:
        """
        Identifies Swing Highs and Swing Lows on M5/M15 to detect Change of Character (CHoCH).
        Bullish CHoCH: Price breaks above the most recent lower swing high.
        Bearish CHoCH: Price breaks below the most recent higher swing low.
        """
        if df_m5 is None or len(df_m5) < lookback:
            return {"choch_detected": False, "type": "NONE"}

        df = df_m5.tail(lookback).reset_index(drop=True)
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values

        # Find 3-bar swing pivots
        swing_highs = []
        swing_lows = []

        for i in range(2, len(df) - 2):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                swing_highs.append((i, highs[i]))
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                swing_lows.append((i, lows[i]))

        current_close = closes[-1]
        choch_type = "NONE"
        breakout_level = None

        # Check Bullish CHoCH: Last bar breaks above previous swing high
        if swing_highs:
            last_sh_idx, last_sh_price = swing_highs[-1]
            if current_close > last_sh_price and last_sh_idx < len(df) - 1:
                choch_type = "BULLISH_CHOCH"
                breakout_level = last_sh_price

        # Check Bearish CHoCH: Last bar breaks below previous swing low
        if choch_type == "NONE" and swing_lows:
            last_sl_idx, last_sl_price = swing_lows[-1]
            if current_close < last_sl_price and last_sl_idx < len(df) - 1:
                choch_type = "BEARISH_CHOCH"
                breakout_level = last_sl_price

        return {
            "choch_detected": choch_type != "NONE",
            "type": choch_type,
            "breakout_level": round(breakout_level, 5) if breakout_level else None,
            "recent_swing_high": round(swing_highs[-1][1], 5) if swing_highs else None,
            "recent_swing_low": round(swing_lows[-1][1], 5) if swing_lows else None
        }

    # ------------------------------------------------------------------
    # 4. FAIR VALUE GAPS (FVG) & ORDER BLOCKS
    # ------------------------------------------------------------------
    def detect_fair_value_gaps(self, df_m5: pd.DataFrame) -> Dict[str, Any]:
        """
        Detects unmitigated Fair Value Gaps (3-candle institutional price imbalances).
        Bullish FVG: Low of candle 3 > High of candle 1.
        Bearish FVG: High of candle 3 < Low of candle 1.
        """
        if df_m5 is None or len(df_m5) < 15:
            return {"active_fvg": False, "type": "NONE"}

        df = df_m5.tail(15).reset_index(drop=True)
        current_close = float(df['close'].iloc[-1])

        unmitigated_fvgs = []

        # Scan for 3-candle gaps in last 12 bars
        for i in range(2, len(df) - 1):
            c1_high = df['high'].iloc[i-2]
            c1_low = df['low'].iloc[i-2]
            c3_high = df['high'].iloc[i]
            c3_low = df['low'].iloc[i]

            # Bullish FVG: Gap between C1 High and C3 Low
            if c3_low > c1_high:
                gap_top = c3_low
                gap_bottom = c1_high
                gap_size = gap_top - gap_bottom
                # Check if current price is retesting/mitigating inside the gap
                if gap_bottom <= current_close <= gap_top * 1.001:
                    unmitigated_fvgs.append({
                        "type": "BULLISH_FVG_TEST",
                        "top": round(gap_top, 5),
                        "bottom": round(gap_bottom, 5),
                        "midpoint": round((gap_top + gap_bottom) / 2.0, 5),
                        "bar_index": i
                    })

            # Bearish FVG: Gap between C3 High and C1 Low
            elif c3_high < c1_low:
                gap_top = c1_low
                gap_bottom = c3_high
                gap_size = gap_top - gap_bottom
                if gap_bottom * 0.999 <= current_close <= gap_top:
                    unmitigated_fvgs.append({
                        "type": "BEARISH_FVG_TEST",
                        "top": round(gap_top, 5),
                        "bottom": round(gap_bottom, 5),
                        "midpoint": round((gap_top + gap_bottom) / 2.0, 5),
                        "bar_index": i
                    })

        if unmitigated_fvgs:
            best_fvg = unmitigated_fvgs[-1]
            return {
                "active_fvg": True,
                "type": best_fvg["type"],
                "top": best_fvg["top"],
                "bottom": best_fvg["bottom"],
                "midpoint": best_fvg["midpoint"],
                "desc": f"{best_fvg['type']}: Zone [{best_fvg['bottom']:.5f} - {best_fvg['top']:.5f}]"
            }

        return {"active_fvg": False, "type": "NONE"}

    # ------------------------------------------------------------------
    # 5. RSI MOMENTUM & DIVERGENCE
    # ------------------------------------------------------------------
    def calculate_rsi_divergence(self, df_m15: pd.DataFrame, period: int = 14) -> Dict[str, Any]:
        """Calculates 14-period RSI and detects regular bullish/bearish divergences."""
        if df_m15 is None or len(df_m15) < period + 15:
            return {"rsi": 50.0, "divergence": "NONE"}

        close = df_m15['close']
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -1 * delta.clip(upper=0)

        avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, 1e-9)
        rsi = 100 - (100 / (1 + rs))
        current_rsi = round(float(rsi.iloc[-1]), 1)

        # Divergence detection in last 20 bars
        recent_close = close.tail(20).values
        recent_rsi = rsi.tail(20).values

        divergence = "NONE"
        # Bullish Divergence: Price Lower Low, RSI Higher Low
        if recent_close[-1] < np.min(recent_close[:-5]) and recent_rsi[-1] > np.min(recent_rsi[:-5]) and recent_rsi[-1] < 45:
            divergence = "BULLISH_DIVERGENCE"
        # Bearish Divergence: Price Higher High, RSI Lower High
        elif recent_close[-1] > np.max(recent_close[:-5]) and recent_rsi[-1] < np.max(recent_rsi[:-5]) and recent_rsi[-1] > 55:
            divergence = "BEARISH_DIVERGENCE"

        return {
            "rsi": current_rsi,
            "divergence": divergence
        }


if __name__ == "__main__":
    dp = DataProvider()
    scanner = ConfluenceScanner(dp)

    for sym in ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "GBPJPY"]:
        df_d1 = dp.get_rates(sym, "D1", 20)
        df_m15 = dp.get_rates(sym, "M15", 100)
        df_m5 = dp.get_rates(sym, "M5", 100)

        sweeps = scanner.detect_liquidity_sweeps(sym, df_m15, df_d1)
        vwap = scanner.calculate_session_vwap(df_m5)
        choch = scanner.detect_market_structure_shift(df_m5)
        fvg = scanner.detect_fair_value_gaps(df_m5)
        rsi = scanner.calculate_rsi_divergence(df_m15)

        print(f"\n--- CONFLUENCE SCAN FOR {sym} ---")
        print(f"  Liquidity Sweep: {sweeps['sweep_type']} ({sweeps['reason']})")
        print(f"  Session VWAP: {vwap['vwap']} | Zone: {vwap['zone']} (z: {vwap.get('z_score')})")
        print(f"  Structure Shift: {choch['type']} (Break: {choch['breakout_level']})")
        print(f"  Fair Value Gap: {fvg['type']}")
        print(f"  RSI (14): {rsi['rsi']} | Divergence: {rsi['divergence']}")

    dp.shutdown()
