#!/usr/bin/env python3
"""
Recommendation & Opportunity Scoring Engine (Tier 3)
-----------------------------------------------------
Synthesizes Tier 1 (Market Profiler) and Tier 2 (Confluence Scanner)
to generate high-precision institutional trade recommendation cards:
- Quality Scoring (0 - 100) & Letter Grades (A+, A, B)
- Exact Entry, Stop Loss, TP1 (1:2 R:R), TP2 (1:3.5+ R:R)
- Institutional Confluence Checklist & Invalidation Conditions
"""

import sys
import logging
import concurrent.futures
from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from config import (
    TARGET_SYMBOLS, CONFLUENCE_WEIGHTS, SCORE_THRESHOLDS,
    MIN_RR_RATIO, MAX_ADR_CONSUMED_PERCENT, MIN_SL_PIPS, MAX_SL_PIPS, ATR_SL_MULTIPLIER
)
from data_provider import DataProvider
from market_profiler import MarketProfiler
from confluence_scanner import ConfluenceScanner

logger = logging.getLogger("RecommendationEngine")


class RecommendationEngine:
    """Evaluates multi-factor market confluence and outputs structured trade proposals."""

    def __init__(self, data_provider: DataProvider):
        self.dp = data_provider
        self.profiler = MarketProfiler(data_provider)
        self.scanner = ConfluenceScanner(data_provider)

    def analyze_symbol(self, symbol: str, csm: Dict[str, float], session_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Performs deep institutional analysis and builds a trade proposal if confluences align."""
        sym_info = self.dp.get_symbol_info(symbol)
        if sym_info is None:
            return None

        pip_size = sym_info["pip_size"]
        digits = sym_info["digits"]
        current_bid = sym_info["bid"]
        current_ask = sym_info["ask"]
        spread_pips = sym_info["spread_pips"]

        # Fetch multi-timeframe candles
        df_d1 = self.dp.get_rates(symbol, "D1", count=25)
        df_h4 = self.dp.get_rates(symbol, "H4", count=50)
        df_h1 = self.dp.get_rates(symbol, "H1", count=50)
        df_m15 = self.dp.get_rates(symbol, "M15", count=100)
        df_m5 = self.dp.get_rates(symbol, "M5", count=100)

        if df_m15 is None or len(df_m15) < 30 or df_m5 is None or len(df_m5) < 30:
            return None

        # --------------------------------------------------------------
        # 1. TIER 1 METRICS
        # --------------------------------------------------------------
        div_info = self.profiler.get_pair_strength_divergence(symbol, csm)
        adr_info = self.profiler.calculate_adr_profile(symbol, df_d1)
        htf_info = self.profiler.get_htf_trend_bias(symbol)

        # --------------------------------------------------------------
        # 2. TIER 2 CONFLUENCES
        # --------------------------------------------------------------
        sweep_info = self.scanner.detect_liquidity_sweeps(symbol, df_m15, df_d1)
        vwap_info = self.scanner.calculate_session_vwap(df_m5)
        choch_info = self.scanner.detect_market_structure_shift(df_m5)
        fvg_info = self.scanner.detect_fair_value_gaps(df_m5)
        rsi_info = self.scanner.calculate_rsi_divergence(df_m15)

        # Calculate M15 ATR for dynamic buffer
        high_low = df_m15['high'] - df_m15['low']
        atr_price = float(high_low.tail(14).mean())
        atr_pips = round(atr_price / pip_size, 1)

        # --------------------------------------------------------------
        # 3. DIRECTIONAL ALIGNMENT & SCORING
        # --------------------------------------------------------------
        bullish_score = 0
        bearish_score = 0
        bullish_reasons = []
        bearish_reasons = []

        # A. Currency Strength Divergence (Max 30 pts)
        csm_div = div_info["net_divergence"]
        if csm_div >= 3.5:
            pts = min(30, int(abs(csm_div) * 4.0))
            bullish_score += pts
            bullish_reasons.append(f"Institutional Flow: {div_info['base_currency']} Strong vs {div_info['quote_currency']} Weak (Divergence: +{csm_div})")
        elif csm_div <= -3.5:
            pts = min(30, int(abs(csm_div) * 4.0))
            bearish_score += pts
            bearish_reasons.append(f"Institutional Flow: {div_info['base_currency']} Weak vs {div_info['quote_currency']} Strong (Divergence: {csm_div})")

        # B. Liquidity Sweeps (Max 25 pts)
        if "BULLISH" in sweep_info.get("sweep_type", ""):
            bullish_score += 25
            bullish_reasons.append(f"Liquidity Grab: {sweep_info['reason']}")
        elif "BEARISH" in sweep_info.get("sweep_type", ""):
            bearish_score += 25
            bearish_reasons.append(f"Liquidity Grab: {sweep_info['reason']}")

        # C. Market Structure Shift / CHoCH (Max 20 pts)
        if choch_info.get("type") == "BULLISH_CHOCH":
            bullish_score += 20
            bullish_reasons.append(f"Structure Shift: Bullish CHoCH on M5 (Broached: {choch_info['breakout_level']})")
        elif choch_info.get("type") == "BEARISH_CHOCH":
            bearish_score += 20
            bearish_reasons.append(f"Structure Shift: Bearish CHoCH on M5 (Broached: {choch_info['breakout_level']})")

        # D. Session VWAP Valuation (Max 15 pts)
        if vwap_info.get("bias") == "BULLISH_DISCOUNT":
            bullish_score += 15
            bullish_reasons.append(f"Valuation: Price in {vwap_info['zone']} relative to Session VWAP ({vwap_info['vwap']})")
        elif vwap_info.get("bias") == "BEARISH_PREMIUM":
            bearish_score += 15
            bearish_reasons.append(f"Valuation: Price in {vwap_info['zone']} relative to Session VWAP ({vwap_info['vwap']})")

        # E. Fair Value Gap / Imbalance (Max 15 pts)
        if fvg_info.get("type") == "BULLISH_FVG_TEST":
            bullish_score += 15
            bullish_reasons.append(f"Price Imbalance: Mitigating Bullish FVG [{fvg_info['bottom']} - {fvg_info['top']}]")
        elif fvg_info.get("type") == "BEARISH_FVG_TEST":
            bearish_score += 15
            bearish_reasons.append(f"Price Imbalance: Mitigating Bearish FVG [{fvg_info['bottom']} - {fvg_info['top']}]")

        # F. D1 + H4 + H1 HTF Trend Strict Alignment (Max 20 pts)
        if htf_info.get("is_triple_aligned"):
            if "BULLISH" in htf_info["bias"]:
                bullish_score += 20
                bullish_reasons.append(f"Triple HTF Alignment: D1 🟢 | H4 🟢 | H1 🟢 Macro Trend")
                bearish_score = max(0, bearish_score - 30)
            elif "BEARISH" in htf_info["bias"]:
                bearish_score += 20
                bearish_reasons.append(f"Triple HTF Alignment: D1 🔴 | H4 🔴 | H1 🔴 Macro Trend")
                bullish_score = max(0, bullish_score - 30)
        elif htf_info["bias"] in ("BULLISH", "STRONG_BULLISH"):
            bullish_score += 12
            bullish_reasons.append(f"HTF Trend Alignment: {htf_info['bias']} ({htf_info.get('alignment_label')})")
            bearish_score = max(0, bearish_score - 15)
        elif htf_info["bias"] in ("BEARISH", "STRONG_BEARISH"):
            bearish_score += 12
            bearish_reasons.append(f"HTF Trend Alignment: {htf_info['bias']} ({htf_info.get('alignment_label')})")
            bullish_score = max(0, bullish_score - 15)

        # G. RSI Divergence (Max +10 pts)
        if rsi_info.get("type") == "BULLISH_DIVERGENCE":
            bullish_score += 10
            bullish_reasons.append(f"RSI Bullish Divergence on M15 (price lower-low, RSI higher-low)")
        elif rsi_info.get("type") == "BEARISH_DIVERGENCE":
            bearish_score += 10
            bearish_reasons.append(f"RSI Bearish Divergence on M15 (price higher-high, RSI lower-high)")

        # H. Killzone Volume Multiplier
        if session_info["is_killzone"]:
            bullish_score = int(bullish_score * 1.15)
            bearish_score = int(bearish_score * 1.15)

        # Cap max score to 100
        bullish_score = min(100, bullish_score)
        bearish_score = min(100, bearish_score)

        # Quality Filter: Allow Score >= 55 (Grade B, A, A+)
        MIN_QUALITY_SCORE = 55

        # Determine winner
        if bullish_score >= bearish_score and bullish_score >= MIN_QUALITY_SCORE:
            direction = "BUY"
            final_score = bullish_score
            reasons = bullish_reasons
        elif bearish_score > bullish_score and bearish_score >= MIN_QUALITY_SCORE:
            direction = "SELL"
            final_score = bearish_score
            reasons = bearish_reasons
        else:
            return None

        # Hard Filter: ADR exhaustion > 75%
        if adr_info["pct_consumed"] > 75.0:
            return None

        # Assign Grade
        if final_score >= SCORE_THRESHOLDS["A+"]:
            grade = "GRADE A+ (Institutional Prime)"
        elif final_score >= SCORE_THRESHOLDS["A"]:
            grade = "GRADE A (High Conviction)"
        else:
            grade = "GRADE B (Moderate Opportunity)"

        # --------------------------------------------------------------
        # 4. TRADE EXECUTION PARAMETERS (Entry, SL, TP1, TP2, R:R)
        # --------------------------------------------------------------
        entry_price = current_ask if direction == "BUY" else current_bid
        
        # Stop Loss Placement
        if direction == "BUY":
            # Place SL below the sweep wick or below the recent swing low with ATR buffer
            base_ref = sweep_info.get("sweep_wick_extremum") or choch_info.get("recent_swing_low") or (entry_price - atr_price * ATR_SL_MULTIPLIER)
            raw_sl = base_ref - (atr_price * 0.3)
            sl_pips = round((entry_price - raw_sl) / pip_size, 1)

            # Clamp SL to reasonable day-trade bounds
            if "XAU" in symbol:
                sl_pips = max(50.0, min(150.0, sl_pips))
            else:
                sl_pips = max(MIN_SL_PIPS, min(MAX_SL_PIPS, sl_pips))
            
            stop_loss = round(entry_price - (sl_pips * pip_size), sym_info["digits"])
            
            # Targets
            tp1_pips = round(sl_pips * 2.0, 1)
            tp2_pips = round(sl_pips * 3.5, 1)
            take_profit_1 = round(entry_price + (tp1_pips * pip_size), sym_info["digits"])
            take_profit_2 = round(entry_price + (tp2_pips * pip_size), sym_info["digits"])
            rr_ratio = round(tp1_pips / sl_pips, 2)
            invalidation = f"H1 or M15 candle body close below {stop_loss} cancels setup."

        else: # SELL
            base_ref = sweep_info.get("sweep_wick_extremum") or choch_info.get("recent_swing_high") or (entry_price + atr_price * ATR_SL_MULTIPLIER)
            raw_sl = base_ref + (atr_price * 0.3)
            sl_pips = round((raw_sl - entry_price) / pip_size, 1)

            if "XAU" in symbol:
                sl_pips = max(50.0, min(150.0, sl_pips))
            else:
                sl_pips = max(MIN_SL_PIPS, min(MAX_SL_PIPS, sl_pips))

            stop_loss = round(entry_price + (sl_pips * pip_size), sym_info["digits"])

            # Targets
            tp1_pips = round(sl_pips * 2.0, 1)
            tp2_pips = round(sl_pips * 3.5, 1)
            take_profit_1 = round(entry_price - (tp1_pips * pip_size), sym_info["digits"])
            take_profit_2 = round(entry_price - (tp2_pips * pip_size), sym_info["digits"])
            rr_ratio = round(tp1_pips / sl_pips, 2)
            invalidation = f"H1 or M15 candle body close above {stop_loss} cancels setup."

        # Setup naming
        setup_name = "Institutional Confluence Setup"
        if sweep_info["sweep_detected"]:
            setup_name = f"Liquidity Sweep + {sweep_info['sweep_type'].replace('_', ' ').title()}"
        elif fvg_info["active_fvg"]:
            setup_name = f"Price Imbalance FVG Retest"
        elif vwap_info.get("bias") != "NEUTRAL":
            setup_name = f"Session VWAP Value Extension"

        return {
            "symbol": symbol,
            "direction": direction,
            "setup_name": setup_name,
            "quality_score": final_score,
            "grade": grade,
            "order_type": "MARKET" if abs(spread_pips) < 2.5 else "LIMIT",
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
            "sl_pips": sl_pips,
            "tp1_pips": tp1_pips,
            "tp2_pips": tp2_pips,
            "risk_reward": f"1:{MIN_RR_RATIO:.1f} (TP1) / 1:3.5 (TP2)",
            "spread_pips": spread_pips,
            "adr_pips": adr_info["adr_pips"],
            "adr_consumed_pct": adr_info["pct_consumed"],
            "adr_remaining_pips": adr_info.get("remaining_pips", 0.0),
            "htf_trend": htf_info,
            "session": session_info["killzone_name"] if session_info["is_killzone"] else "Standard Session",
            "reasons": reasons,
            "invalidation": invalidation,
            "timestamp": session_info["utc_time"]
        }

    def scan_all_opportunities(self, symbols: List[str] = None) -> List[Dict[str, Any]]:
        """Scans specified or all target symbols across the entire Forex and Metals market in parallel."""
        csm = self.profiler.calculate_currency_strength()
        session_info = self.profiler.get_current_session_info()
        target_list = symbols if symbols is not None else TARGET_SYMBOLS
        available_symbols = self.dp.get_all_available_symbols(target_list)

        opportunities = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            future_to_sym = {executor.submit(self.analyze_symbol, sym, csm, session_info): sym for sym in available_symbols}
            for future in concurrent.futures.as_completed(future_to_sym):
                sym = future_to_sym[future]
                try:
                    opp = future.result()
                    if opp is not None:
                        opportunities.append(opp)
                except Exception as e:
                    logger.error(f"Error scanning {sym}: {e}")

        # Sort by quality score descending
        opportunities.sort(key=lambda x: x["quality_score"], reverse=True)
        return opportunities


if __name__ == "__main__":
    dp = DataProvider()
    engine = RecommendationEngine(dp)
    print("Scanning entire Forex market for high-probability setups...")
    opps = engine.scan_all_opportunities()
    
    print(f"\n[FOUND {len(opps)} TRADE OPPORTUNITIES]")
    for i, op in enumerate(opps, 1):
        print(f"\n#{i} | {op['symbol']} [{op['direction']}] - {op['grade']} (Score: {op['quality_score']}/100)")
        print(f"    Setup: {op['setup_name']}")
        print(f"    Entry: {op['entry_price']} | SL: {op['stop_loss']} ({op['sl_pips']} pips) | TP1: {op['take_profit_1']} | TP2: {op['take_profit_2']}")
        print(f"    R:R: {op['risk_reward']} | ADR Used: {op['adr_consumed_pct']}%")
        print("    Institutional Confluences:")
        for r in op['reasons']:
            print(f"      ✔ {r}")
        print(f"    Invalidation: {op['invalidation']}")

    dp.shutdown()
