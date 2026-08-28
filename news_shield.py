#!/usr/bin/env python3
"""
Institutional Economic News Shield & Slippage Protection
--------------------------------------------------------
Protects scalping accounts from catastrophic slippage by detecting upcoming
High-Impact (Red Folder) economic releases and automatically freezing signals
within a pre-configured time window (default: ±15 minutes).
"""

import sys
import os
import json
import logging
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

logger = logging.getLogger("NewsShield")

CACHE_FILE = os.path.join(os.path.dirname(__file__), "data", "economic_calendar_cache.json")
CACHE_DURATION_HOURS = 2


class NewsShield:
    """Real-time High-Impact Economic News Shield."""

    def __init__(self, cache_file: str = CACHE_FILE):
        self.cache_file = cache_file
        self.events: List[Dict[str, Any]] = []
        self._ensure_cache_dir()
        self.load_calendar()

    def _ensure_cache_dir(self):
        d = os.path.dirname(self.cache_file)
        if d and not os.path.exists(d):
            try:
                os.makedirs(d, exist_ok=True)
            except Exception:
                pass

    def load_calendar(self, force_refresh: bool = False):
        """Loads calendar from local cache if fresh, else fetches from live API."""
        now = datetime.now(timezone.utc)

        # Check local cache
        if not force_refresh and os.path.exists(self.cache_file):
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(self.cache_file), tz=timezone.utc)
                if (now - mtime).total_seconds() < (CACHE_DURATION_HOURS * 3600):
                    with open(self.cache_file, "r", encoding="utf-8") as f:
                        self.events = json.load(f)
                    if self.events:
                        return
            except Exception as e:
                logger.warning(f"Error reading calendar cache: {e}")

        # Fetch fresh data
        self._fetch_live_calendar()

    def _fetch_live_calendar(self):
        """Fetches live economic calendar JSON feed."""
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        req = urllib.request.Request(url, headers={"User-Agent": "InstitutionalTradingBot/2.0"})

        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw_data = json.loads(resp.read().decode("utf-8"))
                parsed_events = []
                for item in raw_data:
                    # Parse ISO timestamp
                    d_str = item.get("date", "")
                    try:
                        # Handle timezone offset e.g. 2026-08-17T08:30:00-04:00
                        dt = datetime.fromisoformat(d_str).astimezone(timezone.utc)
                        parsed_events.append({
                            "title": item.get("title", "Economic Event"),
                            "country": item.get("country", "").upper(),
                            "impact": item.get("impact", "Low"),
                            "time_utc": dt.isoformat(),
                            "timestamp": dt.timestamp(),
                            "forecast": item.get("forecast", ""),
                            "previous": item.get("previous", "")
                        })
                    except Exception:
                        continue

                self.events = parsed_events
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    json.dump(self.events, f, indent=2)
                logger.info(f"Successfully updated calendar cache: {len(self.events)} events.")

        except Exception as e:
            logger.warning(f"Failed to fetch live calendar ({e}). Using existing cache if available.")
            if os.path.exists(self.cache_file):
                try:
                    with open(self.cache_file, "r", encoding="utf-8") as f:
                        self.events = json.load(f)
                except Exception:
                    self.events = []

    def is_currency_shielded(self, currency: str, buffer_minutes: int = 15) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Checks if a specific currency is currently shielded due to nearby High-Impact news.
        Returns: (is_shielded, event_details)
        """
        now_ts = datetime.now(timezone.utc).timestamp()
        buf_sec = buffer_minutes * 60

        for event in self.events:
            if event.get("impact") == "High" and event.get("country") == currency:
                e_ts = event.get("timestamp", 0)
                diff = e_ts - now_ts

                # If news is within -buffer_minutes (after event) to +buffer_minutes (before event)
                if -buf_sec <= diff <= buf_sec:
                    mins_left = round(diff / 60.0, 1)
                    event_copy = dict(event)
                    event_copy["minutes_away"] = mins_left
                    return True, event_copy

        return False, None

    def is_symbol_shielded(self, symbol: str, buffer_minutes: int = 15) -> Tuple[bool, Optional[str]]:
        """
        Checks if either the base or quote currency of a symbol is shielded.
        e.g. for EURUSD: checks EUR and USD. For XAUUSD: checks USD.
        Handles broker suffixes like EURUSD.m, USDJPY.ecn via regex stripping.
        """
        import re
        # Strip any non-alpha characters and broker suffixes (e.g. .m, .ecn, .raw)
        clean = re.sub(r'[^A-Z]', '', symbol.upper())[:6]

        if "XAU" in clean or "XAG" in clean:
            currencies = ["USD"]
        elif len(clean) >= 6:
            currencies = [clean[:3], clean[3:6]]
        else:
            currencies = [clean[:3], clean[3:]]

        for curr in currencies:
            shielded, event = self.is_currency_shielded(curr, buffer_minutes)
            if shielded and event:
                mins = event["minutes_away"]
                if mins >= 0:
                    status_str = f"HIGH-IMPACT NEWS: {event['country']} '{event['title']}' in {mins:.0f}m"
                else:
                    status_str = f"HIGH-IMPACT NEWS: {event['country']} '{event['title']}' released {abs(mins):.0f}m ago"
                return True, status_str

        return False, None

    def get_upcoming_high_impact_events(self, hours_ahead: int = 12) -> List[Dict[str, Any]]:
        """Returns all upcoming High-Impact economic news for the next `hours_ahead` hours."""
        now_ts = datetime.now(timezone.utc).timestamp()
        max_ts = now_ts + (hours_ahead * 3600)

        upcoming = []
        for event in self.events:
            if event.get("impact") == "High":
                e_ts = event.get("timestamp", 0)
                if now_ts - 1800 <= e_ts <= max_ts: # show recent past 30m up to next hours
                    mins = round((e_ts - now_ts) / 60.0, 0)
                    upcoming.append({
                        "Time (UTC)": event["time_utc"][11:16],
                        "Currency": event["country"],
                        "Event Title": event["title"],
                        "Minutes Away": f"{mins:+.0f} min",
                        "Forecast": event["forecast"],
                        "Previous": event["previous"]
                    })

        return sorted(upcoming, key=lambda x: float(x["Minutes Away"].replace(" min", "")))


if __name__ == "__main__":
    shield = NewsShield()
    print("=" * 70)
    print("              ECONOMIC CALENDAR & NEWS SHIELD")
    print("=" * 70)
    upcoming = shield.get_upcoming_high_impact_events(hours_ahead=24)
    print(f"Upcoming High-Impact (Red Folder) Events (Next 24h): {len(upcoming)}")
    for ev in upcoming:
        print(f"  • [{ev['Time (UTC)']} UTC] {ev['Currency']:3s} | {ev['Event Title']:35s} | Away: {ev['Minutes Away']:>8s} | Forecast: {ev['Forecast']}")

    for sym in ["EURUSD", "USDJPY", "GBPUSD", "XAUUSD"]:
        is_shield, reason = shield.is_symbol_shielded(sym)
        status = f"🔴 BLOCKED ({reason})" if is_shield else "🟢 CLEAR (No News)"
        print(f"Shield Status {sym:7s}: {status}")
    print("=" * 70)
