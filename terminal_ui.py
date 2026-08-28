#!/usr/bin/env python3
"""
Terminal UI & Rich Console Formatter
-------------------------------------
Renders institutional Forex analytics and opportunity cards
in a clean, colored, high-contrast terminal interface.
"""

import sys
from datetime import datetime
from typing import Dict, List, Any

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich.layout import Layout
from rich import box

console = Console()


class TerminalUI:
    """Renders formatted market intelligence tables and trade opportunity cards."""

    @staticmethod
    def render_header(session_info: Dict[str, Any]):
        """Prints the system header and current session status."""
        kz_text = f"[bold yellow]⚡ {session_info['killzone_name']}[/bold yellow]" if session_info["is_killzone"] else "[cyan]Standard Market Hours[/cyan]"
        
        header_text = Text()
        header_text.append("🏛️  INSTITUTIONAL FOREX STRATEGY & MARKET ANALYSER\n", style="bold white on blue")
        header_text.append(f"⏰ Time: {session_info['utc_time']} | Volume Status: {session_info['volume_status']}\n", style="bold bright_white")
        header_text.append(f"🌐 Active Session: {', '.join(session_info['active_sessions'])} | Killzone: ", style="dim")
        
        console.print(Panel(header_text, border_style="bright_blue", box=box.ROUNDED))

    @staticmethod
    def render_csm_table(csm: Dict[str, float]):
        """Prints a visual Currency Strength Matrix table."""
        table = Table(title="📊 CURRENCY STRENGTH MATRIX (CSM) - 8 MAJORS", box=box.ROUNDED, header_style="bold cyan")
        table.add_column("Rank", justify="center", style="dim", width=6)
        table.add_column("Currency", justify="center", style="bold white", width=10)
        table.add_column("Score (-10 to +10)", justify="right", style="bold", width=18)
        table.add_column("Institutional Flow", justify="left", width=25)
        table.add_column("Bias", justify="center", width=12)

        for rank, (curr, score) in enumerate(csm.items(), 1):
            if score >= 3.0:
                color = "green"
                bias = "[bold green]ACCUMULATING[/bold green]"
                symbol_ind = "▲"
            elif score > 0:
                color = "bright_green"
                bias = "[green]MILD BUY[/green]"
                symbol_ind = "▲"
            elif score <= -3.0:
                color = "red"
                bias = "[bold red]DISTRIBUTING[/bold red]"
                symbol_ind = "▼"
            elif score < 0:
                color = "bright_red"
                bias = "[red]MILD SELL[/red]"
                symbol_ind = "▼"
            else:
                color = "yellow"
                bias = "[yellow]NEUTRAL[/yellow]"
                symbol_ind = "■"

            bars = "█" * int(abs(score) * 1.5)
            sign = "+" if score > 0 else ""
            score_str = f"[{color}]{sign}{score:5.2f}[/{color}]"
            flow_bar = f"[{color}]{symbol_ind} {bars}[/{color}]"

            table.add_row(str(rank), curr, score_str, flow_bar, bias)

        console.print(table)

    @staticmethod
    def render_opportunity_card(opp: Dict[str, Any], index: int):
        """Renders an individual trade recommendation card."""
        is_buy = opp["direction"] == "BUY"
        dir_color = "bold green" if is_buy else "bold red"
        dir_badge = f"[{dir_color}]{opp['direction']}[/{dir_color}]"
        
        grade = opp["grade"]
        if "A+" in grade:
            grade_style = "bold white on dark_green"
        elif "A" in grade:
            grade_style = "bold green"
        else:
            grade_style = "bold yellow"

        title = f"#{index} | {opp['symbol']} {dir_badge} - [{grade_style}]{grade}[/{grade_style}] (Score: {opp['quality_score']}/100)"
        
        content = Text()
        content.append(f"📌 Setup: {opp['setup_name']}\n", style="bold bright_white")
        content.append(f"⏱️ Session: {opp['session']} | ADR Consumed: {opp['adr_consumed_pct']}% (Remaining: {opp['adr_remaining_pips']} pips)\n\n", style="dim")
        
        content.append("📋 TRADE EXECUTION LEVELS:\n", style="bold cyan")
        content.append(f"  • Order Type   : [bold yellow]{opp['order_type']}[/bold yellow]\n")
        content.append(f"  • Entry Price  : [bold bright_white]{opp['entry_price']}[/bold bright_white]\n")
        content.append(f"  • Stop Loss    : [bold red]{opp['stop_loss']}[/bold red] ({opp['sl_pips']} pips)\n")
        content.append(f"  • Take Profit 1: [bold green]{opp['take_profit_1']}[/bold green] ({opp['tp1_pips']} pips | 1:2.0 R:R) -> [dim]Close 50% & BE[/dim]\n")
        content.append(f"  • Take Profit 2: [bold bright_green]{opp['take_profit_2']}[/bold bright_green] ({opp['tp2_pips']} pips | Target)\n")
        content.append(f"  • Risk:Reward  : [bold bright_yellow]{opp['risk_reward']}[/bold bright_yellow]\n\n")

        content.append("🔍 INSTITUTIONAL CONFLUENCE FACTORS:\n", style="bold magenta")
        for reason in opp["reasons"]:
            content.append(f"  [bold green]✔[/bold green] {reason}\n")

        content.append(f"\n⚠️ Invalidation: [italic yellow]{opp['invalidation']}[/italic yellow]", style="yellow")

        border = "green" if is_buy else "red"
        console.print(Panel(content, title=title, border_style=border, box=box.HEAVY))

    @staticmethod
    def render_scan_summary(opportunities: List[Dict[str, Any]]):
        """Prints summary at the bottom of the scan."""
        if not opportunities:
            console.print(Panel("[yellow]No setups met the minimum institutional quality threshold (Score >= 55) at this moment.\nWaiting for high-probability market alignment...[/yellow]", title="Scan Complete", border_style="yellow"))
            return

        table = Table(title=f"🎯 ACTIVE TRADE OPPORTUNITIES SUMMARY ({len(opportunities)} SETUPS)", box=box.SIMPLE_HEAD, header_style="bold cyan")
        table.add_column("Symbol", style="bold white")
        table.add_column("Dir", justify="center")
        table.add_column("Grade", justify="center")
        table.add_column("Score", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("SL (Pips)", justify="right")
        table.add_column("TP1", justify="right")
        table.add_column("TP2", justify="right")
        table.add_column("R:R", justify="center")
        table.add_column("ADR %", justify="right")

        for op in opportunities:
            dir_style = "[green]BUY[/green]" if op["direction"] == "BUY" else "[red]SELL[/red]"
            table.add_row(
                op["symbol"],
                dir_style,
                op["grade"].split()[0] + " " + op["grade"].split()[1],
                str(op["quality_score"]),
                str(op["entry_price"]),
                f"{op['sl_pips']}p",
                str(op["take_profit_1"]),
                str(op["take_profit_2"]),
                "1:2.0 / 1:3.5",
                f"{op['adr_consumed_pct']}%"
            )

    @staticmethod
    def render_scalp_card(sc: Dict[str, Any], index: int):
        """Renders an ultra-fast precision M1/M5 Scalping setup card."""
        is_buy = sc["direction"] == "BUY"
        dir_color = "bold green" if is_buy else "bold red"
        dir_badge = f"[{dir_color}]{sc['direction']} SCALP[/{dir_color}]"

        grade = sc["grade"]
        grade_style = "bold white on dark_green" if "A+" in grade else "bold green"

        title = f"⚡ SCALP #{index} | {sc['symbol']} {dir_badge} - [{grade_style}]{grade}[/{grade_style}] (Score: {sc['quality_score']}/100)"

        content = Text()
        content.append(f"📌 Micro-Setup: {sc['setup_name']}\n", style="bold yellow")
        content.append(f"⏱️ Timeframe: {sc['timeframe']} | Est. Duration: {sc['est_duration']} | Spread: {sc['spread_pips']} pips\n\n", style="dim")

        content.append("⚡ SCALP EXECUTION LEVELS:\n", style="bold cyan")
        content.append(f"  • Entry Price  : [bold bright_white]{sc['entry_price']}[/bold bright_white]\n")
        content.append(f"  • Tight SL     : [bold red]{sc['stop_loss']}[/bold red] ([bold red]-{sc['sl_pips']} pips[/bold red])\n")
        content.append(f"  • Fast TP1 (1:2): [bold green]{sc['take_profit_1']}[/bold green] ([bold green]+{sc['tp1_pips']} pips[/bold green])\n")
        content.append(f"  • Runner TP2   : [bold bright_green]{sc['take_profit_2']}[/bold bright_green] ([bold bright_green]+{sc['tp2_pips']} pips[/bold bright_green])\n")
        content.append(f"  • Risk:Reward  : [bold bright_yellow]{sc['risk_reward']}[/bold bright_yellow]\n\n")

        content.append("🔥 MICRO-CONFLUENCE FACTORS:\n", style="bold magenta")
        for reason in sc["reasons"]:
            content.append(f"  [bold green]✔[/bold green] {reason}\n")

        border = "bright_green" if is_buy else "bright_red"
        console.print(Panel(content, title=title, border_style=border, box=box.DOUBLE))

