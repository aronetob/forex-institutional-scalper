#!/usr/bin/env python3
"""
Institutional Position Sizer  (v1.0)
--------------------------------------
Calculates optimal lot size based on:
  - Account balance (in account currency)
  - Risk % per trade (default 1%)
  - Stop Loss in pips
  - Symbol pip value from MT5 symbol_info

Formula:
  Risk Amount      = Balance * risk_pct / 100
  Pip Value / lot  = (pip_size / tick_size) * tick_value
  Lot Size         = Risk Amount / (SL_pips * Pip Value per lot)
  Lot Size         = rounded DOWN to broker volume_step
"""

import math
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("PositionSizer")


class PositionSizer:
    """Calculates risk-adjusted lot sizes for scalp and swing trades."""

    def __init__(self, data_provider):
        self.dp = data_provider

    def calculate_lot_size(
        self,
        symbol: str,
        sl_pips: float,
        account_balance: float,
        risk_pct: float = 1.0
    ) -> Dict[str, Any]:
        """
        Calculates the optimal lot size.

        Args:
            symbol:          e.g. 'EURUSD'
            sl_pips:         Stop Loss distance in pips
            account_balance: Account equity in account currency (e.g. EUR)
            risk_pct:        Max risk per trade as % of balance (default 1.0%)

        Returns dict with:
            lot_size:        Recommended lots (rounded to broker step)
            risk_amount:     Account currency amount risked
            pip_value:       Value per pip per standard lot
            risk_per_pip:    Amount risked per pip at recommended lot
            breakdown:       Human-readable explanation
        """
        info = self.dp.get_symbol_info(symbol)
        if info is None:
            return {"lot_size": 0.01, "error": "Symbol info unavailable", "risk_amount": 0}

        pip_size      = info["pip_size"]
        tick_value    = info.get("tick_value", 0)
        tick_size     = info.get("tick_size", pip_size)
        volume_min    = info.get("volume_min", 0.01)
        volume_step   = info.get("volume_step", 0.01)
        contract_size = info.get("contract_size", 100000)

        # Risk amount in account currency
        risk_amount = round(account_balance * risk_pct / 100.0, 2)

        # Pip value per standard lot (1.0 lot)
        if tick_size > 0 and tick_value > 0:
            pip_value_per_lot = (pip_size / tick_size) * tick_value
        else:
            # Fallback approximation for XXXUSD pairs
            pip_value_per_lot = pip_size * contract_size

        if pip_value_per_lot <= 0 or sl_pips <= 0:
            return {
                "lot_size":   volume_min,
                "risk_amount": risk_amount,
                "pip_value":  0,
                "risk_per_pip": 0,
                "breakdown":  f"Could not calculate pip value for {symbol}"
            }

        # Ideal lot size
        raw_lots = risk_amount / (sl_pips * pip_value_per_lot)

        # Round DOWN to nearest volume_step (never exceed risk budget)
        lot_size = math.floor(raw_lots / volume_step) * volume_step
        lot_size = round(max(volume_min, lot_size), 2)

        actual_risk_per_pip = lot_size * pip_value_per_lot
        actual_total_risk   = round(actual_risk_per_pip * sl_pips, 2)

        breakdown = (
            f"Balance: {account_balance:,.0f} | Risk: {risk_pct}% = {risk_amount:.2f} | "
            f"SL: {sl_pips}p | Pip Value: {pip_value_per_lot:.3f}/lot | "
            f"=> {lot_size:.2f} lots (actual risk: {actual_total_risk:.2f})"
        )

        return {
            "lot_size":       lot_size,
            "risk_amount":    actual_total_risk,
            "risk_pct":       risk_pct,
            "pip_value":      round(pip_value_per_lot, 4),
            "risk_per_pip":   round(actual_risk_per_pip, 4),
            "breakdown":      breakdown,
        }

    def get_size_for_signal(
        self,
        signal: Dict[str, Any],
        account_balance: float,
        risk_pct: float = 1.0
    ) -> Dict[str, Any]:
        """Convenience wrapper: takes a signal dict from scalper/recommendation engine."""
        symbol  = signal.get("symbol", "")
        sl_pips = float(signal.get("sl_pips", 4.0))
        return self.calculate_lot_size(symbol, sl_pips, account_balance, risk_pct)


if __name__ == "__main__":
    from data_provider import DataProvider
    dp = DataProvider()
    sizer = PositionSizer(dp)

    test_cases = [
        ("EURUSD", 5.0,  10000, 1.0),
        ("GBPJPY", 8.0,  10000, 1.0),
        ("XAUUSD", 30.0, 10000, 1.0),
        ("USDJPY", 5.0,  5000,  0.5),
    ]

    print("=" * 90)
    print("         INSTITUTIONAL POSITION SIZER v1.0")
    print("=" * 90)
    for sym, sl, bal, rp in test_cases:
        res = sizer.calculate_lot_size(sym, sl, bal, rp)
        print(f"  {sym:8s} | SL {sl:5.1f}p | Bal {bal:8,.0f} | Risk {rp:.1f}%  =>  {res['lot_size']:.2f} lots  (risk: {res['risk_amount']:.2f})")
    print("=" * 90)
    dp.shutdown()
