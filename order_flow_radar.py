#!/usr/bin/env python3
"""
Dynamic M1 Order Flow & Tick Velocity Micro-Heatmap
---------------------------------------------------
Calculates live 1-minute order flow metrics across all major scalping assets:
1. Tick Velocity Ratio: Current volume vs 10-bar moving average.
2. Displacement Intensity: Candle body relative to 14-bar M1 ATR.
3. Micro-Delta: Intra-bar buying vs selling pressure percentage.
4. Liquidity Surge State: Identifies expanding momentum vs dead chop.
"""

import sys
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from data_provider import DataProvider
from config import FOREX_MAJORS, FOREX_CROSSES


class OrderFlowRadar:
    """Sub-second M1 Order Flow & Tick Velocity Profiler."""

    def __init__(self, data_provider: DataProvider):
        self.dp = data_provider

    def analyze_order_flow(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Calculates granular M1 order flow velocity metrics for a single symbol."""
        sym_info = self.dp.get_symbol_info(symbol)
        if sym_info is None:
            return None

        pip_size = sym_info["pip_size"]
        spread_pips = sym_info["spread_pips"]

        df_m1 = self.dp.get_rates(symbol, "M1", count=25)
        if df_m1 is None or len(df_m1) < 15:
            return None

        cur_bar = df_m1.iloc[-1]
        prev_bar = df_m1.iloc[-2]

        # 1. Tick Volume Velocity
        vol_series = df_m1['volume']
        avg_vol_10 = float(vol_series.tail(10).mean())
        cur_vol = float(cur_bar['volume'])
        velocity_ratio = round(cur_vol / max(1.0, avg_vol_10), 2)

        # 2. Candle Displacement & Range
        c_open = cur_bar['open']
        c_high = cur_bar['high']
        c_low = cur_bar['low']
        c_close = cur_bar['close']

        bar_range = c_high - c_low
        bar_range_pips = round(bar_range / pip_size, 1)
        body = abs(c_close - c_open)
        body_pips = round(body / pip_size, 1)

        # 14-bar M1 ATR
        m1_atr = float((df_m1['high'] - df_m1['low']).tail(14).mean())
        atr_ratio = round(body / max(1e-6, m1_atr), 2)

        # 3. Micro-Delta (Buyer vs Seller dominance within bar)
        if bar_range > 0:
            # Fraction of bar where close is positioned from the low
            buyer_delta_pct = round(((c_close - c_low) / bar_range) * 100.0, 1)
        else:
            buyer_delta_pct = 50.0

        seller_delta_pct = round(100.0 - buyer_delta_pct, 1)
        net_delta_bias = "BULLISH" if buyer_delta_pct >= 60.0 else ("BEARISH" if buyer_delta_pct <= 40.0 else "BALANCED")

        # 4. Momentum State Classification
        if velocity_ratio >= 1.75 and atr_ratio >= 1.1:
            state = "🔥 LIQUIDITY SURGE"
            state_code = "SURGE"
        elif velocity_ratio >= 1.15 and atr_ratio >= 0.8:
            state = "⚡ MOMENTUM EXPANSION"
            state_code = "EXPANDING"
        elif velocity_ratio <= 0.65 or bar_range_pips <= 0.5:
            state = "🧊 DEAD CHOP / SQUEEZE"
            state_code = "CHOP"
        else:
            state = "⚖️ NORMAL FLOW"
            state_code = "NORMAL"

        return {
            "symbol": symbol,
            "current_price": c_close,
            "spread_pips": spread_pips,
            "tick_volume": int(cur_vol),
            "avg_volume_10": round(avg_vol_10, 1),
            "velocity_ratio": velocity_ratio,
            "bar_range_pips": bar_range_pips,
            "body_pips": body_pips,
            "displacement_ratio": atr_ratio,
            "buyer_delta_pct": buyer_delta_pct,
            "seller_delta_pct": seller_delta_pct,
            "delta_bias": net_delta_bias,
            "state": state,
            "state_code": state_code
        }

    def get_order_flow_matrix(self, symbols: List[str] = None) -> List[Dict[str, Any]]:
        """Generates real-time M1 order flow matrix across all target pairs."""
        if symbols is None:
            symbols = [
                "EURUSD", "EURJPY", "USDJPY", "GBPUSD", "AUDUSD",
                "USDCAD", "USDCHF", "CADJPY", "AUDJPY", "GBPJPY"
            ]

        matrix = []
        for s in symbols:
            res = self.analyze_order_flow(s)
            if res:
                matrix.append(res)

        # Sort by highest tick velocity ratio descending
        return sorted(matrix, key=lambda x: x["velocity_ratio"], reverse=True)


if __name__ == "__main__":
    dp = DataProvider()
    radar = OrderFlowRadar(dp)

    print("=" * 95)
    print("           REAL-TIME M1 ORDER FLOW & TICK VELOCITY MICRO-HEATMAP")
    print("=" * 95)

    matrix = radar.get_order_flow_matrix()
    print(f"{'Symbol':<8s} | {'Price':<10s} | {'Spread':<7s} | {'Ticks (1m)':<10s} | {'Velocity':<9s} | {'Body (p)':<9s} | {'Delta Flow':<16s} | {'State':<20s}")
    print("-" * 95)
    for r in matrix:
        delta_str = f"Buy {r['buyer_delta_pct']:.0f}% / Sell {r['seller_delta_pct']:.0f}%"
        print(f"{r['symbol']:<8s} | {r['current_price']:<10.5f} | {r['spread_pips']:>4.1f} p  | {r['tick_volume']:>10d} | {r['velocity_ratio']:>7.2f}x | {r['body_pips']:>7.1f}p | {delta_str:<16s} | {r['state']}")

    print("=" * 95)
    dp.shutdown()
