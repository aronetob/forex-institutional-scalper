#!/usr/bin/env python3
"""
Full Portfolio Validation Across All Key Forex Pairs & Crosses
--------------------------------------------------------------
Verifies that the upgraded institutional rules produce consistent profitability
across the entire portfolio of major and cross currency pairs.
"""

import sys
from data_provider import DataProvider
from backtester import InstitutionalBacktester

PORTFOLIO = [
    "EURUSD", "USDJPY", "AUDUSD", "CADJPY", "AUDJPY",
    "GBPAUD", "EURAUD", "EURGBP", "EURCAD", "GBPUSD"
]

if __name__ == "__main__":
    dp = DataProvider()
    bt = InstitutionalBacktester(dp)

    print("=" * 95)
    print("      FINAL PORTFOLIO VALIDATION ACROSS MAJOR & CROSS PAIRS")
    print("=" * 95)

    tot_trades = 0
    tot_wins = 0
    tot_losses = 0
    tot_bes = 0
    tot_profit = 0.0

    for s in PORTFOLIO:
        res = bt.run_backtest(
            symbol=s,
            strategy_name="MTF_TREND",
            bars_count=2000,
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
            tot_profit += res["net_profit_cash"]

            status = "🟢 PROFITABLE" if res["net_profit_cash"] >= 0 else "🔴 NEGATIVE"
            print(f"💎 {s:7s} | Trades: {res['total_trades']:2d} | Win: {res['wins']:2d} | Loss: {res['losses']:2d} | BE: {res['breakevens']:2d} | WR: {res['win_rate']:5.1f}% | PF: {res['profit_factor']:5.2f} | Net: {res['net_profit_pct']:+6.2f}% (€{res['net_profit_cash']:+,.2f}) -> {status}", flush=True)

    print("-" * 95, flush=True)
    comb_wr = round((tot_wins / tot_trades) * 100.0, 1) if tot_trades > 0 else 0.0
    print(f"🏆 TOTAL PORTFOLIO PERFORMANCE ({len(PORTFOLIO)} Pairs):", flush=True)
    print(f"   • Total Trades Executed : {tot_trades}", flush=True)
    print(f"   • Wins / Losses / BEs   : {tot_wins} Wins / {tot_losses} Losses / {tot_bes} Break-Evens", flush=True)
    print(f"   • Portfolio Win Rate    : {comb_wr}%", flush=True)
    print(f"   • Net Portfolio Gain    : +€{tot_profit:+,.2f}", flush=True)
    print("=" * 95, flush=True)

    dp.shutdown()
