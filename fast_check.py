#!/usr/bin/env python3
"""
Fast Portfolio Check across Diverse Asset Classes
"""

import sys
from data_provider import DataProvider
from backtester import InstitutionalBacktester

KEY_SYMBOLS = ["EURUSD", "USDJPY", "CADJPY", "AUDJPY", "GBPAUD", "AUDNZD"]

dp = DataProvider()
bt = InstitutionalBacktester(dp)

print("=" * 85)
print("             KEY ASSET CLASS PORTFOLIO CHECK (1,000 M15 BARS)")
print("=" * 85)

tot_trades = 0
tot_wins = 0
tot_losses = 0
tot_bes = 0
tot_pnl = 0.0

for s in KEY_SYMBOLS:
    res = bt.run_backtest(s, strategy_name="MTF_TREND", bars_count=1000)
    if "error" not in res and res["total_trades"] > 0:
        tot_trades += res["total_trades"]
        tot_wins += res["wins"]
        tot_losses += res["losses"]
        tot_bes += res["breakevens"]
        tot_pnl += res["net_profit_cash"]

        status = "🟢 PROFITABLE" if res["net_profit_cash"] >= 0 else "🔴 LOSS"
        print(f"💎 {s:7s} | Trades: {res['total_trades']:2d} | Win: {res['wins']:2d} | Loss: {res['losses']:2d} | BE: {res['breakevens']:2d} | WR: {res['win_rate']:5.1f}% | PF: {res['profit_factor']:5.2f} | Net: {res['net_profit_pct']:+6.2f}% (€{res['net_profit_cash']:+,.2f}) -> {status}")

print("-" * 85)
comb_wr = round((tot_wins / tot_trades) * 100.0, 1) if tot_trades > 0 else 0.0
print(f"🏆 PORTFOLIO TOTAL: {tot_trades} Trades | {tot_wins} Wins / {tot_losses} Losses / {tot_bes} BEs")
print(f"🔥 COMBINED WIN RATE: {comb_wr}% | NET PORTFOLIO PROFIT: +€{tot_pnl:+,.2f}")
print("=" * 85)

dp.shutdown()
