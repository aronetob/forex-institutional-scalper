@echo off
title Institutional Forex Strategy Dashboard
cd /d "%~dp0"
cls
echo ===============================================================================
echo     LAUNCHING INSTITUTIONAL FOREX WEB DASHBOARD (STREAMLIT)
echo ===============================================================================
echo.
echo Starting Web Dashboard on http://localhost:8501 ...
python -m streamlit run dashboard.py
pause
