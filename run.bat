@echo off
REM Convenience launcher for Windows: activates a local .venv if present,
REM then runs the bot. Pass a different script name to run that instead:
REM   run.bat generate_session.py --lib telethon
cd /d "%~dp0"

if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

set SCRIPT=%1
if "%SCRIPT%"=="" set SCRIPT=telegram_session_bot.py
if not "%1"=="" shift

python "%SCRIPT%" %1 %2 %3 %4 %5 %6 %7 %8 %9
