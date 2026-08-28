#!/usr/bin/env python3
"""
Multi-Pair Cross-Section Backtest (Majors, Yen Crosses & Commodity Crosses)
---------------------------------------------------------------------------
Evaluates institutional setups across diverse Forex asset classes.
"""

import sys
import pandas as pd
import numpy as np

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from data_provider import DataProvider
from backtester import InstitutionalBacktester

TEST_PORTFOLIO = [
    # Majors
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    # High-Edge Yen Crosses
    "CADJPY", "CHFJPY", "EURJPY", "AUDJPY",
    # Euro & Commodity Crosses
    "EURCAD", "EURAUD", "GBPAUD", "AUDNZD"
]

if __name__ == "__main__":
    dp = DataProvider()
    bt = InstitutionalBacktester(dp)

    print("=" * 95)
    print("      MULTI-PAIR INSTITUTIONAL BACKTEST (MAJORS, YEN CROSSES & COMMODITY CROSSES)")
    print("=" * 95)

    results = []
    tot_trades = 0
    tot_wins = 0
    tot_losses = 0
    tot_bes = 0
    tot_profit_cash = 0.0

    for sym in TEST_PORTFOLIO:
        res = bt.run_backtest(
            symbol=sym,
            strategy_name="MTF_TREND",
            bars_count=2000, # ~4-5 weeks of M15 data
            min_rr=2.0,
            risk_per_trade_pct=1.0,
            starting_balance=10000.0,
            require_killzone=True,
            use_breakeven=True
        )

        if "error" not in res and res["total_trades"] > 0:
            tot_trades += res["total_trades"]
            tot_wins += res["wins"]
            tot_losses += res["losses"]
            tot_bes += res["breakevens"]
            tot_profit_cash += res["net_profit_cash"]

            results.append({
                "Symbol": sym,
                "Trades": res["total_trades"],
                "Win": res["wins"],
                "Loss": res["losses"],
                "BE": res["breakevens"],
                "Win Rate": f"{res['win_rate']:.1f}%",
                "Profit Factor": f"{res['profit_factor']:.2f}",
                "Max DD": f"{res['max_drawdown_pct']:.1f}%",
                "Net PnL (€)": f"€{res['net_profit_cash']:+,.2f}",
                "Net (%)": f"{res['net_profit_pct']:+6.2f}%"
            })
            print(f"📊 {sym:7s} | Trades: {res['total_trades']:2d} | Win: {res['wins']:2d} | Loss: {res['losses']:2d} | BE: {res['breakevens']:2d} | WR: {res['win_rate']:5.1f}% | PF: {res['profit_factor']:4.2f} | Net: {res['net_profit_pct']:+6.2f}% (€{res['net_profit_cash']:+,.2f})")

    print("-" * 95)
    comb_wr = round((tot_wins / tot_trades) * 100.0, 1) if tot_trades > 0 else 0.0
    comb_gain_pct = round((tot_profit_cash / (10000.0 * len(TEST_PORTFOLIO))) * 100.0, 2)
    print(f"🏆 PORTFOLIO TOTAL ({len(TEST_PORTFOLIO)} PAIRS):")
    print(f"   • Total Executed Trades : {tot_trades}")
    print(f"   • Wins / Losses / BEs   : {tot_wins} Wins / {tot_losses} Losses / {tot_bes} Break-Evens")
    print(f"   • Portfolio Win Rate    : {comb_wr}%")
    print(f"   • Total Net Profit (€)  : +€{tot_profit_cash:+,.2f}")
    print("=" * 95)

    dp.shutdown()
