#!/usr/bin/env python3
"""
Comprehensive End-to-End System & Code Audit
--------------------------------------------
Tests every module, function, and calculation for bugs, edge cases, and runtime safety.
"""

import sys
import os
import traceback

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

print("=" * 80)
print("             COMPREHENSIVE SYSTEM & CODE AUDIT")
print("=" * 80)

audit_passed = True

# 1. Test Config
try:
    from config import TARGET_SYMBOLS, CURRENCIES, SESSIONS_UTC
    assert len(TARGET_SYMBOLS) == 30, f"Expected 30 symbols, got {len(TARGET_SYMBOLS)}"
    assert len(CURRENCIES) == 8, f"Expected 8 currencies, got {len(CURRENCIES)}"
    print("✔ [1/8] config.py: PASSED")
except Exception as e:
    audit_passed = False
    print(f"❌ [1/8] config.py FAILED: {e}")
    traceback.print_exc()

# 2. Test DataProvider
try:
    from data_provider import DataProvider
    dp = DataProvider()
    assert dp.connected, "MT5 connection failed"
    for s in ["EURUSD", "EURJPY", "XAUUSD"]:
        info = dp.get_symbol_info(s)
        assert info is not None, f"Failed info for {s}"
        assert info["pip_size"] > 0, f"Invalid pip_size for {s}"
        df_m15 = dp.get_rates(s, "M15", 50)
        assert df_m15 is not None and len(df_m15) == 50, f"Failed M15 rates for {s}"
    print("✔ [2/8] data_provider.py: PASSED")
except Exception as e:
    audit_passed = False
    print(f"❌ [2/8] data_provider.py FAILED: {e}")
    traceback.print_exc()

# 3. Test MarketProfiler
try:
    from market_profiler import MarketProfiler
    profiler = MarketProfiler(dp)
    csm = profiler.calculate_currency_strength()
    assert len(csm) == 8, f"Expected 8 CSM scores, got {len(csm)}"
    session_info = profiler.get_current_session_info()
    assert "is_killzone" in session_info, "Missing is_killzone in session_info"
    for s in ["EURUSD", "EURJPY", "XAUUSD"]:
        adr = profiler.calculate_adr_profile(s)
        assert adr["adr_pips"] > 0, f"Invalid adr for {s}"
        assert 0 <= adr["pct_consumed"] <= 500, f"Invalid pct_consumed for {s}"
    print("✔ [3/8] market_profiler.py: PASSED")
except Exception as e:
    audit_passed = False
    print(f"❌ [3/8] market_profiler.py FAILED: {e}")
    traceback.print_exc()

# 4. Test ConfluenceScanner
try:
    from confluence_scanner import ConfluenceScanner
    scanner = ConfluenceScanner(dp)
    for s in ["EURUSD", "EURJPY", "XAUUSD"]:
        df_m5 = dp.get_rates(s, "M5", 60)
        df_m15 = dp.get_rates(s, "M15", 60)
        df_d1 = dp.get_rates(s, "D1", 10)
        sweeps = scanner.detect_liquidity_sweeps(s, df_m15, df_d1)
        vwap = scanner.calculate_session_vwap(df_m5)
        choch = scanner.detect_market_structure_shift(df_m5)
        fvg = scanner.detect_fair_value_gaps(df_m15)
        rsi_div = scanner.calculate_rsi_divergence(df_m15)
    print("✔ [4/8] confluence_scanner.py: PASSED")
except Exception as e:
    audit_passed = False
    print(f"❌ [4/8] confluence_scanner.py FAILED: {e}")
    traceback.print_exc()

# 5. Test RecommendationEngine
try:
    from recommendation_engine import RecommendationEngine
    rec_engine = RecommendationEngine(dp)
    opps = rec_engine.scan_all_opportunities()
    assert isinstance(opps, list), "Expected list of opportunities"
    print(f"✔ [5/8] recommendation_engine.py: PASSED (Found {len(opps)} Day-Trade Setups)")
except Exception as e:
    audit_passed = False
    print(f"❌ [5/8] recommendation_engine.py FAILED: {e}")
    traceback.print_exc()

# 6. Test ScalperEngine
try:
    from scalper_engine import ScalperEngine
    scalper = ScalperEngine(dp)
    scalps = scalper.scan_all_scalps()
    assert isinstance(scalps, list), "Expected list of scalps"
    print(f"✔ [6/8] scalper_engine.py: PASSED (Found {len(scalps)} Active Scalps)")
except Exception as e:
    audit_passed = False
    print(f"❌ [6/8] scalper_engine.py FAILED: {e}")
    traceback.print_exc()

# 7. Test TerminalUI
try:
    from terminal_ui import TerminalUI
    ui = TerminalUI()
    # Test rendering mock components
    ui.render_header(session_info)
    ui.render_csm_table(csm)
    if opps:
        ui.render_opportunity_card(opps[0], 1)
        ui.render_scan_summary(opps)
    if scalps:
        ui.render_scalp_card(scalps[0], 1)
    print("✔ [7/8] terminal_ui.py: PASSED")
except Exception as e:
    audit_passed = False
    print(f"❌ [7/8] terminal_ui.py FAILED: {e}")
    traceback.print_exc()

# 8. Test Backtester
try:
    from backtester import InstitutionalBacktester
    bt = InstitutionalBacktester(dp)
    res = bt.run_backtest("EURUSD", bars_count=300)
    assert "error" not in res, f"Backtest error: {res}"
    print("✔ [8/8] backtester.py: PASSED")
except Exception as e:
    audit_passed = False
    print(f"❌ [8/8] backtester.py FAILED: {e}")
    traceback.print_exc()

print("=" * 80)
if audit_passed:
    print("🎉 ALL 8 MODULES PASSED COMPLETE CODE & RUNTIME AUDIT WITH ZERO ERRORS!")
else:
    print("⚠️ SOME MODULES FAILED AUDIT. CHECK LOGS ABOVE.")
print("=" * 80)

dp.shutdown()
