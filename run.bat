@echo off
set PY=C:\Users\prodb\AppData\Local\Programs\Python\Python314\python.exe

echo ========================================
echo   Insider Signal Scanner
echo ========================================
echo.

echo [1/4] Fetching new SEC filings...
%PY% main.py

echo.
echo [2/4] Enriching with market data...
%PY% enrich.py

echo.
echo [3/4] Checking Google Trends...
%PY% google_trends.py

echo.
echo [4/4] Scoring and ranking signals...
%PY% score.py

echo.
echo Opening dashboard...
%PY% -m streamlit run dashboard.py