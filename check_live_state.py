from data_provider import DataProvider
from recommendation_engine import RecommendationEngine
from market_profiler import MarketProfiler
from scalper_engine import ScalperEngine

dp = DataProvider()
rec = RecommendationEngine(dp)
profiler = MarketProfiler(dp)
scalper = ScalperEngine(dp)

opps = rec.scan_all_opportunities()
scalps = scalper.scan_all_scalps()
session = profiler.get_current_session_info()

print("=" * 70)
print(f"⏰ Live UTC Time: {session['utc_time']} | Volume: {session['volume_status']}")
print(f"Active Session: {', '.join(session['active_sessions'])}")
print("=" * 70)
print(f"🎯 Total Day-Trade Setups: {len(opps)}")
for o in opps:
    print(f"   • {o['symbol']:7s} | {o['direction']:4s} | Score: {o['quality_score']:2d}/100 | Grade: {o['grade']:20s} | SL: {o['sl_pips']:4.1f}p | Invalidation: {o['invalidation']}")

print(f"\n⚡ Total Scalp Setups: {len(scalps)}")
for s in scalps:
    print(f"   • {s['symbol']:7s} | {s['direction']:4s} | Score: {s['quality_score']:2d}/100 | Grade: {s['grade']:20s} | SL: {s['sl_pips']:4.1f}p")
print("=" * 70)

dp.shutdown()
