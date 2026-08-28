#!/usr/bin/env python3
"""
Institutional Forex Strategy & Market Opportunity Analyser
===========================================================
Main CLI Entry Point
Usage:
  python main.py            # Run full market scan
  python main.py --scan     # Run full market scan
  python main.py --live     # Continuous live market monitor
  python main.py --symbol EURUSD # Deep dive on a single asset
"""

import sys
import os
import time
import argparse
import logging
from datetime import datetime

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from config import SCAN_INTERVAL_SECONDS
from data_provider import DataProvider
from market_profiler import MarketProfiler
from recommendation_engine import RecommendationEngine
from terminal_ui import TerminalUI, console

from scalper_engine import ScalperEngine

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s | %(levelname)-8s | %(message)s"
)
logger = logging.getLogger("MainAnalyser")


def run_scalper_scan(scalper: ScalperEngine, ui: TerminalUI):
    """Executes ultra-fast M1/M5 scalping scan."""
    console.print("\n[bold yellow]⚡ SCANNING LIVE MARKET FOR M1/M5 PRECISION SCALPS...[/bold yellow]\n")
    t0 = time.time()
    scalps = scalper.scan_all_scalps()
    elapsed = time.time() - t0

    if not scalps:
        console.print(f"[dim]No active high-probability M1/M5 scalps at this second ({elapsed:.2f}s scan). Monitoring...[/dim]\n")
    else:
        for idx, sc in enumerate(scalps, 1):
            ui.render_scalp_card(sc, idx)


def run_scalper_live_loop(scalper: ScalperEngine, ui: TerminalUI, interval: int = 5):
    """Continuously polls market for live M1/M5 scalping opportunities."""
    console.print(f"[bold yellow]⚡ LIVE FOREX SCALPING RADAR ACTIVE (Sub-Second Scan / Refresh every {interval}s)... Press Ctrl+C to stop.[/bold yellow]\n")
    try:
        while True:
            console.clear()
            console.print("[bold yellow]⚡ INSTITUTIONAL FOREX LIVE SCALPER (M1 / M5)[/bold yellow]")
            console.print(f"⏰ UTC: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Polling Interval: {interval}s\n")
            run_scalper_scan(scalper, ui)
            console.print(f"[dim]Next scalp scan in {interval}s...[/dim]")
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[bold yellow]⏹️ Live Scalper stopped by user.[/bold yellow]")


def run_single_scan(engine: RecommendationEngine, profiler: MarketProfiler, ui: TerminalUI, specific_symbol: str = None):
    """Executes a complete scan across target Forex pairs and renders the results."""
    session_info = profiler.get_current_session_info()
    csm = profiler.calculate_currency_strength()

    ui.render_header(session_info)
    ui.render_csm_table(csm)

    if specific_symbol:
        console.print(f"\n[bold cyan]🔎 Running deep institutional analysis for {specific_symbol.upper()}...[/bold cyan]\n")
        opp = engine.analyze_symbol(specific_symbol.upper(), csm, session_info)
        if opp:
            ui.render_opportunity_card(opp, 1)
        else:
            console.print(f"[yellow]No high-conviction institutional setup currently active for {specific_symbol.upper()}.[/yellow]")
        return

    console.print("\n[bold cyan]🔍 Scanning all 30 Forex pairs & metals for institutional confluences...[/bold cyan]\n")
    opportunities = engine.scan_all_opportunities()

    # Render top cards
    for idx, opp in enumerate(opportunities[:5], 1):
        ui.render_opportunity_card(opp, idx)

    # Render summary table of all detected opportunities
    ui.render_scan_summary(opportunities)


def run_live_loop(engine: RecommendationEngine, profiler: MarketProfiler, ui: TerminalUI, interval: int = 30):
    """Continuously monitors the market and refreshes opportunities on each interval."""
    console.print(f"[bold green]🚀 Starting Live Institutional Forex Monitor (Refresh every {interval}s)... Press Ctrl+C to stop.[/bold green]\n")
    try:
        while True:
            console.clear()
            run_single_scan(engine, profiler, ui)
            console.print(f"\n[dim]Next market scan in {interval} seconds... (Press Ctrl+C to exit)[/dim]")
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[bold yellow]⏹️ Live Monitor stopped by user.[/bold yellow]")


def main():
    parser = argparse.ArgumentParser(description="Institutional Forex Strategy & Market Opportunity Analyser")
    parser.add_argument("--scan", action="store_true", help="Perform single market-wide scan (default)")
    parser.add_argument("--scalp", action="store_true", help="Run M1/M5 Ultra-Fast Live Scalper")
    parser.add_argument("--live", action="store_true", help="Run continuous live monitoring loop")
    parser.add_argument("--symbol", type=str, default=None, help="Analyze a specific symbol (e.g. EURUSD, GBPJPY, XAUUSD)")
    parser.add_argument("--interval", type=int, default=SCAN_INTERVAL_SECONDS, help="Live refresh interval in seconds")
    args = parser.parse_args()

    dp = DataProvider()
    if not dp.connected:
        console.print("[bold red]❌ Failed to connect to MetaTrader 5 terminal. Ensure MT5 is running and try again.[/bold red]")
        sys.exit(1)

    profiler = MarketProfiler(dp)
    engine = RecommendationEngine(dp)
    scalper = ScalperEngine(dp)
    ui = TerminalUI()

    try:
        if args.scalp and args.live:
            run_scalper_live_loop(scalper, ui, interval=max(3, args.interval if args.interval != SCAN_INTERVAL_SECONDS else 5))
        elif args.scalp:
            run_scalper_scan(scalper, ui)
        elif args.live:
            run_live_loop(engine, profiler, ui, interval=args.interval)
        else:
            run_single_scan(engine, profiler, ui, specific_symbol=args.symbol)
    finally:
        dp.shutdown()


if __name__ == "__main__":
    main()

