import sys
from data_provider import DataProvider
from market_profiler import MarketProfiler
from config import TARGET_SYMBOLS

dp = DataProvider()
profiler = MarketProfiler(dp)

print("=" * 80)
print("         ADR VERIFICATION ACROSS ALL 30 SYMBOLS")
print("=" * 80)

for s in TARGET_SYMBOLS:
    adr = profiler.calculate_adr_profile(s)
    print(f"{s:7s} | ADR (14d): {adr['adr_pips']:6.1f} p | Today: {adr['today_range_pips']:5.1f} p | Rem: {adr['remaining_pips']:5.1f} p | % Used: {adr['pct_consumed']:4.1f}%")

print("=" * 80)
dp.shutdown()
