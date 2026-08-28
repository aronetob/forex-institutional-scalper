#!/usr/bin/env python3
"""
Market Profiler & Daily Intelligence Engine (Tier 1)
----------------------------------------------------
Analyzes daily market personality and conditions for all Forex pairs:
1. Currency Strength Matrix (CSM across 8 major currencies).
2. Average Daily Range (ADR) calculation and exhaustion tracking.
3. Institutional Session & Killzone tracker.
4. Daily Trend Bias & Volatility Regime Detection.
"""

import sys
import os
import concurrent.futures
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import pandas as pd

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from config import CURRENCIES, SESSIONS_UTC, TARGET_SYMBOLS, MAX_ADR_CONSUMED_PERCENT
from data_provider import DataProvider


class MarketProfiler:
    """Computes macroeconomic and statistical daily profiles for currency pairs."""

    def __init__(self, data_provider: DataProvider):
        self.dp = data_provider

    # ------------------------------------------------------------------
    # 1. CURRENCY STRENGTH MATRIX (CSM)
    # ------------------------------------------------------------------
    def calculate_currency_strength(self) -> Dict[str, float]:
        """
        Calculates relative institutional strength for the 8 major currencies.
        Returns a dictionary mapping currency code to score (-10.0 to +10.0).
        """
        currency_scores = {c: [] for c in CURRENCIES}

        def _process_csm_pair(sym):
            if sym in ("XAUUSD", "XAGUSD"):
                return None
            base = sym[:3]
            quote = sym[3:]
            if base not in CURRENCIES or quote not in CURRENCIES:
                return None

            df_h1 = self.dp.get_rates(sym, "H1", count=50)
            if df_h1 is None or len(df_h1) < 25:
                return None

            close = df_h1['close'].values
            current_price = close[-1]
            ema20 = pd.Series(close).ewm(span=20, adjust=False).mean().values[-1]
            pct_from_ema = ((current_price - ema20) / ema20) * 100.0
            roc_8 = ((current_price - close[-8]) / close[-8]) * 100.0 if len(close) >= 8 else 0.0
            roc_24 = ((current_price - close[-24]) / close[-24]) * 100.0 if len(close) >= 24 else 0.0
            pair_momentum = (pct_from_ema * 0.4) + (roc_8 * 0.3) + (roc_24 * 0.3)
            return base, quote, pair_momentum

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(_process_csm_pair, TARGET_SYMBOLS))

        for res in results:
            if res:
                base, quote, pair_momentum = res
                currency_scores[base].append(pair_momentum)
                currency_scores[quote].append(-pair_momentum)

        # Average and normalize scores on a -10 to +10 scale
        normalized_scores = {}
        raw_averages = {}
        for c in CURRENCIES:
            vals = currency_scores[c]
            raw_averages[c] = float(np.mean(vals)) if len(vals) > 0 else 0.0

        max_val = max(abs(v) for v in raw_averages.values()) if raw_averages else 1.0
        if max_val == 0:
            max_val = 1.0

        for c, avg in raw_averages.items():
            # Scale to [-10, +10]
            normalized_scores[c] = round((avg / max_val) * 10.0, 2)

        return dict(sorted(normalized_scores.items(), key=lambda item: item[1], reverse=True))

    def get_pair_strength_divergence(self, symbol: str, csm: Dict[str, float]) -> Dict[str, Any]:
        """
        Calculates the net currency divergence score for a given symbol.
        e.g. for GBPJPY: Strength(GBP) - Strength(JPY).
        """
        if symbol in ("XAUUSD", "XAGUSD"):
            usd_score = csm.get("USD", 0.0)
            net = -usd_score  # In general, metal moves inversely to USD
            return {
                "base_currency": symbol[:3],
                "quote_currency": "USD",
                "base_score": round(net, 2),
                "quote_score": usd_score,
                "net_divergence": round(net, 2),
                "bias": "BULLISH" if net > 2.0 else ("BEARISH" if net < -2.0 else "NEUTRAL")
            }

        base = symbol[:3]
        quote = symbol[3:]
        base_score = csm.get(base, 0.0)
        quote_score = csm.get(quote, 0.0)
        net_divergence = round(base_score - quote_score, 2)

        if net_divergence >= 4.0:
            bias = "STRONG_BULLISH"
        elif net_divergence >= 2.0:
            bias = "BULLISH"
        elif net_divergence <= -4.0:
            bias = "STRONG_BEARISH"
        elif net_divergence <= -2.0:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        return {
            "base_currency": base,
            "quote_currency": quote,
            "base_score": base_score,
            "quote_score": quote_score,
            "net_divergence": net_divergence,
            "bias": bias
        }

    # ------------------------------------------------------------------
    # 2. ADR & VOLATILITY EXHAUSTION
    # ------------------------------------------------------------------
    def calculate_adr_profile(self, symbol: str, df_d1: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """
        Calculates 14-day Average Daily Range (ADR), today's range, and expansion capacity.
        """
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

        if df_d1 is None:
            df_d1 = self.dp.get_rates(symbol, "D1", count=20)

        if df_d1 is None or len(df_d1) < 2:
            return {
                "adr_pips": 70.0,
                "today_range_pips": 30.0,
                "pct_consumed": 42.8,
                "remaining_pips": 40.0,
                "status": "OPTIMAL"
            }

        # Last 14 completed days for ADR
        hist_days = df_d1.iloc[:-1].tail(14)
        daily_ranges = (hist_days['high'] - hist_days['low']) / pip_size
        adr_pips = round(float(daily_ranges.mean()), 1)
        if adr_pips <= 0:
            adr_pips = 70.0

        # Current day
        today_bar = df_d1.iloc[-1]
        today_range_pips = round(float((today_bar['high'] - today_bar['low']) / pip_size), 1)

        pct_consumed = round((today_range_pips / adr_pips) * 100.0, 1)
        remaining_pips = round(max(0.0, adr_pips - today_range_pips), 1)

        if pct_consumed > MAX_ADR_CONSUMED_PERCENT:
            status = "EXHAUSTED"
        elif pct_consumed > 55.0:
            status = "MODERATE"
        else:
            status = "FRESH"

        return {
            "adr_pips": adr_pips,
            "today_range_pips": today_range_pips,
            "pct_consumed": pct_consumed,
            "remaining_pips": remaining_pips,
            "today_high": today_bar['high'],
            "today_low": today_bar['low'],
            "status": status
        }

    # ------------------------------------------------------------------
    # 3. SESSION & KILLZONE CLOCK
    # ------------------------------------------------------------------
    @staticmethod
    def get_current_session_info() -> Dict[str, Any]:
        """Identifies current active session and institutional killzone window."""
        now_utc = datetime.now(timezone.utc)
        current_minute = now_utc.hour * 60 + now_utc.minute

        active_sessions = []
        is_killzone = False
        killzone_name = "None"

        for key, conf in SESSIONS_UTC.items():
            start_min = conf["start"][0] * 60 + conf["start"][1]
            end_min = conf["end"][0] * 60 + conf["end"][1]

            if start_min <= current_minute <= end_min:
                active_sessions.append(conf["name"])
                if "Killzone" in key or "Fix" in key:
                    is_killzone = True
                    killzone_name = conf["name"]

        # Institutional volume weighting
        if is_killzone:
            vol_multiplier = 1.5
            vol_label = "HIGH (Institutional Window)"
        elif any("London" in s or "NY" in s for s in active_sessions):
            vol_multiplier = 1.2
            vol_label = "MODERATE-HIGH"
        else:
            vol_multiplier = 0.7
            vol_label = "LOW (Asian / Off-Hours)"

        return {
            "utc_time": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "current_hour_utc": now_utc.hour,
            "active_sessions": active_sessions if active_sessions else ["Off-Hours / Market Transition"],
            "is_killzone": is_killzone,
            "killzone_name": killzone_name,
            "volatility_multiplier": vol_multiplier,
            "volume_status": vol_label
        }

    # ------------------------------------------------------------------
    # 4. HIGHER TIMEFRAME (HTF) TREND BIAS (D1 + H4 + H1 ALIGNMENT)
    # ------------------------------------------------------------------
    def get_htf_trend_bias(self, symbol: str) -> Dict[str, Any]:
        """Evaluates Daily (D1), 4-Hour (H4), and 1-Hour (H1) structural trend alignment."""
        df_d1 = self.dp.get_rates(symbol, "D1", count=40)
        df_h4 = self.dp.get_rates(symbol, "H4", count=60)
        df_h1 = self.dp.get_rates(symbol, "H1", count=60)

        if df_h4 is None or len(df_h4) < 30 or df_h1 is None or len(df_h1) < 30:
            return {
                "bias": "NEUTRAL",
                "d1_trend": "NEUTRAL",
                "h4_trend": "NEUTRAL",
                "h1_trend": "NEUTRAL",
                "aligned_timeframes": 0,
                "is_triple_aligned": False,
                "alignment_label": "No Alignment"
            }

        # 1. D1 Trend (Daily Macro Trend)
        if df_d1 is not None and len(df_d1) >= 20:
            d1_close = df_d1['close'].values
            d1_ema20 = pd.Series(d1_close).ewm(span=20, adjust=False).mean().values[-1]
            d1_ema50 = pd.Series(d1_close).ewm(span=50, adjust=False).mean().values[-1] if len(d1_close) >= 50 else d1_ema20
            d1_trend = "BULLISH" if d1_close[-1] > d1_ema20 else ("BEARISH" if d1_close[-1] < d1_ema20 else "CHOP")
            if d1_close[-1] > d1_ema20 > d1_ema50:
                d1_trend = "BULLISH"
            elif d1_close[-1] < d1_ema20 < d1_ema50:
                d1_trend = "BEARISH"
        else:
            d1_trend = "NEUTRAL"

        # 2. H4 Trend (Swing Intermediate Trend)
        h4_close = df_h4['close'].values
        h4_ema20 = pd.Series(h4_close).ewm(span=20, adjust=False).mean().values[-1]
        h4_ema50 = pd.Series(h4_close).ewm(span=50, adjust=False).mean().values[-1]
        h4_trend = "BULLISH" if h4_close[-1] > h4_ema20 > h4_ema50 else ("BEARISH" if h4_close[-1] < h4_ema20 < h4_ema50 else "CHOP")

        # 3. H1 Trend (Intraday Trend Momentum)
        h1_close = df_h1['close'].values
        h1_ema20 = pd.Series(h1_close).ewm(span=20, adjust=False).mean().values[-1]
        h1_ema50 = pd.Series(h1_close).ewm(span=50, adjust=False).mean().values[-1]
        h1_trend = "BULLISH" if h1_close[-1] > h1_ema20 > h1_ema50 else ("BEARISH" if h1_close[-1] < h1_ema20 < h1_ema50 else "CHOP")

        # Alignment calculation (D1 + H4 + H1)
        bull_count = sum(1 for t in [d1_trend, h4_trend, h1_trend] if t == "BULLISH")
        bear_count = sum(1 for t in [d1_trend, h4_trend, h1_trend] if t == "BEARISH")

        is_triple_aligned = False
        if bull_count == 3:
            overall = "STRONG_BULLISH"
            alignment_label = "TRIPLE ALIGNED (D1 🟢 | H4 🟢 | H1 🟢)"
            is_triple_aligned = True
            aligned_count = 3
        elif bear_count == 3:
            overall = "STRONG_BEARISH"
            alignment_label = "TRIPLE ALIGNED (D1 🔴 | H4 🔴 | H1 🔴)"
            is_triple_aligned = True
            aligned_count = 3
        elif bull_count == 2:
            overall = "BULLISH"
            alignment_label = f"PARTIAL ALIGNED (Bullish 2/3)"
            aligned_count = 2
        elif bear_count == 2:
            overall = "BEARISH"
            alignment_label = f"PARTIAL ALIGNED (Bearish 2/3)"
            aligned_count = 2
        else:
            overall = "NEUTRAL"
            alignment_label = "CHOP / CONFLICTING (D1 vs H4 vs H1)"
            aligned_count = 0

        return {
            "bias": overall,
            "d1_trend": d1_trend,
            "h4_trend": h4_trend,
            "h1_trend": h1_trend,
            "aligned_timeframes": aligned_count,
            "is_triple_aligned": is_triple_aligned,
            "alignment_label": alignment_label,
            "h1_ema20": round(float(h1_ema20), 5),
            "h1_ema50": round(float(h1_ema50), 5)
        }


if __name__ == "__main__":
    dp = DataProvider()
    profiler = MarketProfiler(dp)
    
    print("\n--- 1. ACTIVE SESSIONS & KILLZONES ---")
    ses = profiler.get_current_session_info()
    for k, v in ses.items():
        print(f"  {k}: {v}")

    print("\n--- 2. CURRENCY STRENGTH MATRIX ---")
    csm = profiler.calculate_currency_strength()
    for curr, score in csm.items():
        bar = "█" * int(abs(score))
        sign = "+" if score > 0 else ""
        color_indicator = f"[{sign}{score:5.2f}] {'▲' if score > 0 else '▼'} {bar}"
        print(f"  {curr:4s}: {color_indicator}")

    print("\n--- 3. SAMPLE PAIR PROFILES ---")
    for sym in ["EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "XAUUSD"]:
        div = profiler.get_pair_strength_divergence(sym, csm)
        adr = profiler.calculate_adr_profile(sym)
        htf = profiler.get_htf_trend_bias(sym)
        print(f"\n{sym}:")
        print(f"  CSM Divergence: {div['net_divergence']} ({div['bias']})")
        print(f"  ADR: {adr['today_range_pips']} / {adr['adr_pips']} pips ({adr['pct_consumed']}% - {adr['status']})")
        print(f"  HTF Trend Bias: {htf['bias']}")
    
    dp.shutdown()
