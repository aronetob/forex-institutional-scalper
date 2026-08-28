#!/usr/bin/env python3
"""
Institutional Forex Strategy & Market Opportunity Analyser
-----------------------------------------------------------
Configuration & System Settings
"""

from typing import List, Dict, Any

# ----------------------------------------------------------------------
# 1. TARGET ASSETS & CURRENCIES
# ----------------------------------------------------------------------
FOREX_MAJORS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"
]

FOREX_CROSSES = [
    "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "CHFJPY", "NZDJPY",
    "EURAUD", "EURCAD", "EURCHF", "EURNZD", "GBPAUD", "GBPCAD", "GBPCHF",
    "GBPNZD", "AUDCAD", "AUDCHF", "AUDNZD", "CADCHF", "NZDCAD", "NZDCHF"
]

METALS = [
    "XAUUSD", "XAGUSD"
]

# All active symbols to scan
TARGET_SYMBOLS: List[str] = FOREX_MAJORS + FOREX_CROSSES + METALS

# Whitelist for Sniper Elite Mode (High-conviction, low-noise pairs)
SNIPER_ELITE_SYMBOLS: List[str] = [
    "EURUSD", "USDJPY", "CADJPY", "AUDJPY", "USDCAD", "USDCHF", "AUDUSD", "XAUUSD"
]

# 8 Major global currencies for Strength Meter Matrix
CURRENCIES: List[str] = ["EUR", "USD", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]

# ----------------------------------------------------------------------
# 2. SESSIONS & INSTITUTIONAL KILLZONES (UTC / GMT Times)
# ----------------------------------------------------------------------
# Format: (start_hour, start_minute, end_hour, end_minute)
SESSIONS_UTC = {
    "Asian": {
        "start": (0, 0),
        "end": (7, 0),
        "name": "Asian Session (Accumulation / Range)"
    },
    "London_Killzone": {
        "start": (7, 0),
        "end": (10, 0),
        "name": "London Open Killzone (Institutional Sweeps & High Volatility)"
    },
    "London_Session": {
        "start": (7, 0),
        "end": (15, 30),
        "name": "London Full Session"
    },
    "NY_Killzone": {
        "start": (12, 0),
        "end": (15, 0),
        "name": "New York Open Killzone (High Volume & Trend Expansions)"
    },
    "London_NY_Overlap": {
        "start": (12, 0),
        "end": (15, 30),
        "name": "London-NY Overlap (Peak Global Liquidity)"
    },
    "London_Fix": {
        "start": (15, 30),
        "end": (16, 30),
        "name": "London 4 PM Fix (Institutional Portfolio Rebalancing)"
    }
}

# ----------------------------------------------------------------------
# 3. CONFLUENCE & QUALITY SCORING SETTINGS
# ----------------------------------------------------------------------
CONFLUENCE_WEIGHTS = {
    "currency_divergence": 25,     # Strong vs Weak currency alignment
    "liquidity_sweep": 25,         # Asian High/Low or Prior Day High/Low Sweep
    "structure_shift": 20,         # M15/M5 CHoCH or BOS in alignment
    "vwap_confluence": 15,         # Price at Institutional Premium/Discount (< -1.5σ / > +1.5σ)
    "fvg_imbalance": 15            # Fair Value Gap / Order Block retest zone
}

SCORE_THRESHOLDS = {
    "A+": 85,   # Prime Institutional Setup (Highest conviction)
    "A":  70,   # High Quality Setup
    "B":  55    # Moderate Quality Setup
}

# ----------------------------------------------------------------------
# 4. RISK & OPPORTUNITY FILTERS
# ----------------------------------------------------------------------
MIN_RR_RATIO = 2.0                 # Minimum acceptable Risk:Reward (1:2.0)
MAX_ADR_CONSUMED_PERCENT = 85.0   # Reject trend breakouts if > 85% daily ADR used
MIN_SL_PIPS = 6.0                  # Minimum SL buffer in pips (avoid tight broker spreads)
MAX_SL_PIPS = 40.0                 # Max SL for day-trade setups (scales for XAUUSD)
ATR_SL_MULTIPLIER = 1.2            # Buffer added beyond sweep wick / FVG
SCAN_INTERVAL_SECONDS = 30         # Live loop scan interval
