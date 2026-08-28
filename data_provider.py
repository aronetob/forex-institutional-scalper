#!/usr/bin/env python3
"""
Data Provider & MT5 Interface  (Optimized v3.0)
------------------------------------------------
Handles connection to MetaTrader 5, fetches multi-timeframe OHLCV data,
calculates spreads, pip metrics, and maintains local data caching.

Optimizations v3.0:
  - threading.Lock() wraps every mt5.* call (thread-safe for ThreadPoolExecutor)
  - Unified cache: always fetches max(count, MIN_FETCH) bars, slices locally
    → eliminates duplicate MT5 calls for different `count` values on same symbol/TF
  - True ATR helper: TR = max(H-L, |H-prevC|, |L-prevC|) with Wilder RMA
  - Disk cache _save_to_cache() called after every successful fetch
  - W1 timeframe added to TIMEFRAME_MAP
"""

import os
import sys
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

from config import TARGET_SYMBOLS

logger = logging.getLogger("DataProvider")

# Mapping of string timeframes to MT5 constants
TIMEFRAME_MAP = {}
if MT5_AVAILABLE:
    TIMEFRAME_MAP = {
        "M1":  mt5.TIMEFRAME_M1,
        "M5":  mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1":  mt5.TIMEFRAME_H1,
        "H4":  mt5.TIMEFRAME_H4,
        "D1":  mt5.TIMEFRAME_D1,
        "W1":  mt5.TIMEFRAME_W1,
    }

# Minimum bars to always fetch per timeframe so one MT5 request serves all callers
_MIN_FETCH_COUNT = {
    "M1":  100,
    "M5":  120,
    "M15": 120,
    "M30": 100,
    "H1":  100,
    "H4":  100,
    "D1":  30,
    "W1":  20,
}


class DataProvider:
    """Robust MT5 Data Provider — Thread-Safe, Unified Cache, True ATR."""

    def __init__(self, cache_dir: str = "data_cache"):
        self.cache_dir = cache_dir
        self.connected = False
        self._selected_symbols: set = set()
        # Unified cache: key = (symbol, timeframe_str) — NOT including count
        self._rates_cache: Dict[Tuple[str, str], Tuple[float, pd.DataFrame]] = {}
        self._info_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        # Single lock for ALL MT5 API calls — prevents race conditions
        self._mt5_lock = threading.Lock()
        self._ensure_cache_dir()
        self._init_mt5()

    def _ensure_cache_dir(self):
        if not os.path.exists(self.cache_dir):
            try:
                os.makedirs(self.cache_dir, exist_ok=True)
            except Exception:
                pass

    def _init_mt5(self) -> bool:
        """Initializes MT5 connection with retry resilience."""
        if not MT5_AVAILABLE:
            logger.warning("MetaTrader5 python module is not available.")
            return False

        for attempt in range(3):
            with self._mt5_lock:
                if mt5.initialize():
                    self.connected = True
                    logger.info("MetaTrader 5 API connected successfully.")
                    return True
            time.sleep(0.5)

        logger.error("MT5 initialize failed after 3 attempts.")
        self.connected = False
        return False

    def ensure_connection(self) -> bool:
        """Ensures MT5 is connected, re-initializing if needed."""
        if not self.connected:
            return self._init_mt5()
        return True

    def _fetch_from_cloud(self, symbol: str, timeframe_str: str = "M15", count: int = 100) -> Optional[pd.DataFrame]:
        """Cloud fallback to fetch live OHLCV data using yfinance when MT5 is not connected (e.g. Streamlit Cloud / Linux)."""
        try:
            import yfinance as yf
            tf_map = {
                "M1": ("1d", "1m"),
                "M5": ("5d", "5m"),
                "M15": ("5d", "15m"),
                "M30": ("1mo", "30m"),
                "H1": ("1mo", "1h"),
                "H4": ("3mo", "1h"),
                "D1": ("1y", "1d"),
                "W1": ("2y", "1wk")
            }
            period, interval = tf_map.get(timeframe_str.upper(), ("5d", "15m"))
            
            if symbol in ("XAUUSD", "GOLD"):
                ticker_sym = "GC=F"
            elif symbol in ("XAGUSD", "SILVER"):
                ticker_sym = "SI=F"
            else:
                ticker_sym = f"{symbol}=X"

            t = yf.Ticker(ticker_sym)
            df = t.history(period=period, interval=interval)
            if df is None or df.empty:
                return self._load_from_cache(symbol, timeframe_str)
                
            df = df.reset_index()
            time_col = "Datetime" if "Datetime" in df.columns else "Date"
            df.rename(columns={time_col: "time", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}, inplace=True)
            if hasattr(df['time'].dt, 'tz') and df['time'].dt.tz is not None:
                df['time'] = df['time'].dt.tz_localize(None)
            cols = ["time", "open", "high", "low", "close", "volume"]
            res_df = df[[c for c in cols if c in df.columns]]
            return res_df.tail(count).copy()
        except Exception as e:
            logger.debug(f"Cloud fetch error for {symbol}: {e}")
            return self._load_from_cache(symbol, timeframe_str)

    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Retrieves live symbol specifications with 1.5s in-memory caching."""
        now = time.time()
        if symbol in self._info_cache:
            ts, val = self._info_cache[symbol]
            if now - ts < 1.5:
                return val

        if not self.ensure_connection():
            # Cloud fallback symbol info
            digits = 3 if "JPY" in symbol else (2 if "XAU" in symbol else 5)
            pip_size = 0.01 if "JPY" in symbol else (0.10 if "XAU" in symbol else 0.0001)
            df_m1 = self.get_rates(symbol, "M15", count=2)
            if df_m1 is not None and not df_m1.empty:
                last_price = float(df_m1['close'].iloc[-1])
            else:
                last_price = 1.0
            
            spread_pips = 1.2
            res = {
                "symbol":        symbol,
                "bid":           last_price,
                "ask":           last_price + (spread_pips * pip_size),
                "spread_points": 12,
                "spread_pips":   spread_pips,
                "point":         pip_size / 10.0,
                "digits":        digits,
                "pip_size":      pip_size,
                "tick_value":    1.0,
                "tick_size":     pip_size,
                "volume_min":    0.01,
                "volume_step":   0.01,
                "visible":       True,
                "contract_size": 100000,
            }
            self._info_cache[symbol] = (now, res)
            return res

        with self._mt5_lock:
            if symbol not in self._selected_symbols:
                mt5.symbol_select(symbol, True)
                self._selected_symbols.add(symbol)
            info = mt5.symbol_info(symbol)

        if info is None:
            return None

        # Determine Pip Scale
        digits = info.digits
        point  = info.point
        if "JPY" in symbol:
            pip_size = 0.01
        elif "XAU" in symbol or "GOLD" in symbol:
            pip_size = 0.10
        elif "XAG" in symbol or "SILVER" in symbol:
            pip_size = 0.01
        elif digits in (5, 3):
            pip_size = point * 10.0
        else:
            pip_size = point

        spread_pips = (info.ask - info.bid) / pip_size if pip_size > 0 else 0.0

        res = {
            "symbol":        symbol,
            "bid":           info.bid,
            "ask":           info.ask,
            "spread_points": info.spread,
            "spread_pips":   round(spread_pips, 2),
            "point":         point,
            "digits":        digits,
            "pip_size":      pip_size,
            "tick_value":    info.trade_tick_value,
            "tick_size":     info.trade_tick_size,
            "volume_min":    info.volume_min,
            "volume_step":   info.volume_step,
            "visible":       info.visible,
            "contract_size": info.trade_contract_size,
        }
        self._info_cache[symbol] = (now, res)
        return res

    def get_rates(self, symbol: str, timeframe_str: str = "M15", count: int = 300) -> Optional[pd.DataFrame]:
        """
        Fetches OHLCV bars for symbol/timeframe.

        Cache strategy (v3.0):
          - Key is (symbol, timeframe) — NOT (symbol, timeframe, count).
          - Always fetches max(count, _MIN_FETCH_COUNT[tf]) bars from MT5 / Cloud.
          - Returns tail-sliced copy so every caller gets exactly `count` rows.
        """
        tf_key = timeframe_str.upper()
        cache_key = (symbol, tf_key)
        min_fetch = _MIN_FETCH_COUNT.get(tf_key, 100)
        actual_fetch = max(count, min_fetch)

        now = time.time()
        if cache_key in self._rates_cache:
            ts, df_cached = self._rates_cache[cache_key]
            if now - ts < 1.5:
                return df_cached.tail(count).copy()

        if not self.ensure_connection():
            df_cloud = self._fetch_from_cloud(symbol, timeframe_str, actual_fetch)
            if df_cloud is not None and not df_cloud.empty:
                self._rates_cache[cache_key] = (now, df_cloud)
                return df_cloud.tail(count).copy()
            return self._load_from_cache(symbol, timeframe_str)

        tf = TIMEFRAME_MAP.get(tf_key)
        if tf is None:
            logger.error(f"Invalid timeframe: {timeframe_str}")
            return None

        with self._mt5_lock:
            if symbol not in self._selected_symbols:
                mt5.symbol_select(symbol, True)
                self._selected_symbols.add(symbol)
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, actual_fetch)

        if rates is None or len(rates) == 0:
            df_cloud = self._fetch_from_cloud(symbol, timeframe_str, actual_fetch)
            if df_cloud is not None and not df_cloud.empty:
                self._rates_cache[cache_key] = (now, df_cloud)
                return df_cloud.tail(count).copy()
            return self._load_from_cache(symbol, timeframe_str)

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.rename(columns={'tick_volume': 'volume'}, inplace=True)
        cols = ['time', 'open', 'high', 'low', 'close', 'volume']
        df = df[[c for c in cols if c in df.columns]]

        # Store full fetch; callers get sliced views
        self._rates_cache[cache_key] = (now, df)
        # Persist to disk for offline fallback
        self._save_to_cache(symbol, timeframe_str, df)

        return df.tail(count).copy()

    def get_atr(self, symbol: str, timeframe_str: str = "M5", period: int = 14) -> float:
        """
        Calculates True ATR using Wilder's RMA:
          TR  = max(H-L, |H - prev_Close|, |L - prev_Close|)
          ATR = seed with mean(TR[:period]), then iterate:
                ATR = ATR*(1 - 1/period) + TR_i*(1/period)

        Returns ATR in price units (divide by pip_size for pips).
        """
        df = self.get_rates(symbol, timeframe_str, count=max(period + 10, 60))
        if df is None or len(df) < period + 1:
            return 0.0

        high  = df['high'].values
        low   = df['low'].values
        close = df['close'].values

        prev_close = close[:-1]
        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - prev_close),
                np.abs(low[1:]  - prev_close)
            )
        )

        # Wilder's RMA
        alpha = 1.0 / period
        atr_val = float(tr[:period].mean())
        for v in tr[period:]:
            atr_val = atr_val * (1.0 - alpha) + v * alpha

        return float(atr_val)

    def get_multi_timeframe_rates(self, symbol: str, timeframes: List[str] = None, count: int = 200) -> Dict[str, pd.DataFrame]:
        """Fetches candles for multiple timeframes in sequence."""
        if timeframes is None:
            timeframes = ["D1", "H4", "H1", "M15", "M5"]
        mtf_data = {}
        for tf in timeframes:
            df = self.get_rates(symbol, tf, count=count)
            if df is not None and not df.empty:
                mtf_data[tf] = df
        return mtf_data

    def get_all_available_symbols(self, symbols: List[str] = None) -> List[str]:
        """Returns symbols that are available and active in MT5."""
        if symbols is None:
            symbols = TARGET_SYMBOLS
        if not self.ensure_connection():
            return symbols

        active = []
        for s in symbols:
            with self._mt5_lock:
                info = mt5.symbol_info(s)
            if info is not None:
                active.append(s)
            else:
                with self._mt5_lock:
                    if mt5.symbol_select(s, True):
                        active.append(s)
        return active

    def _save_to_cache(self, symbol: str, timeframe: str, df: pd.DataFrame):
        """Saves dataframe snapshot to CSV cache for offline fallback."""
        try:
            filepath = os.path.join(self.cache_dir, f"{symbol}_{timeframe}.csv")
            df.to_csv(filepath, index=False)
        except Exception:
            pass

    def _load_from_cache(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Loads dataframe from local cache if available."""
        try:
            filepath = os.path.join(self.cache_dir, f"{symbol}_{timeframe}.csv")
            if os.path.exists(filepath):
                df = pd.read_csv(filepath)
                df['time'] = pd.to_datetime(df['time'])
                return df
        except Exception:
            pass
        return None

    def shutdown(self):
        """Disconnects MT5."""
        if MT5_AVAILABLE and self.connected:
            with self._mt5_lock:
                mt5.shutdown()
            self.connected = False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    dp = DataProvider()
    print("MT5 Connected:", dp.connected)
    symbols = dp.get_all_available_symbols()
    print(f"Available symbols ({len(symbols)}):", symbols[:10])

    if symbols:
        test_sym = symbols[0]
        info = dp.get_symbol_info(test_sym)
        print(f"Symbol info for {test_sym}:", info)
        df_m15 = dp.get_rates(test_sym, "M15", 10)
        print(f"Latest 10 M15 bars for {test_sym}:")
        print(df_m15.tail(3))
        atr = dp.get_atr(test_sym, "M5", 14)
        print(f"True ATR (M5, 14): {atr:.6f}")
    dp.shutdown()
