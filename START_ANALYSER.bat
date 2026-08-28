@echo off
title Institutional Forex Strategy & Live Scalper
cd /d "%~dp0"
cls
echo ===============================================================================
echo     LAUNCHING INSTITUTIONAL FOREX STRATEGY & LIVE SCALPER DASHBOARD
echo ===============================================================================
echo.
echo Starting Web Dashboard on http://localhost:8501 ...
echo.
python -m streamlit run dashboard.py
pause
