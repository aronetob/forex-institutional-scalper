#!/usr/bin/env python3
"""
Forensic Post-Mortem on Losing Trades
------------------------------------
Analyzes the exact reasons why trades were stopped out.
"""

import sys
from data_provider import DataProvider
from backtester import InstitutionalBacktester
import pandas as pd

dp = DataProvider()
bt = InstitutionalBacktester(dp)

print("=" * 90)
print("            FORENSIC LOSS POST-MORTEM (EURUSD, EURJPY, CHFJPY, USDCAD)")
print("=" * 90)

for sym in ["EURUSD", "EURJPY", "CHFJPY", "USDCAD"]:
    res = bt.run_backtest(
        symbol=sym,
        strategy_name="MTF_TREND",
        bars_count=2000,
        min_rr=2.0,
        risk_per_trade_pct=1.0,
        starting_balance=10000.0,
        require_killzone=True,
        use_breakeven=True
    )
    
    tdf = res.get("trades_df", pd.DataFrame())
    if tdf.empty:
        continue
        
    losses = tdf[tdf['pnl_r'] < 0]
    print(f"\n❌ {sym} Total Losses: {len(losses)} / {len(tdf)} trades")
    for _, t in losses.iterrows():
        print(f"   • Entry: {t['entry_time']} | Dir: {t['direction']:4s} @ {t['entry_price']:.5f} | SL: {t['stop_loss']:.5f} ({t['sl_pips']}p) | Reason: {t['reason']}")

dp.shutdown()
