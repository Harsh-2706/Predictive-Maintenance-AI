@echo off
REM One-click setup + pipeline + tests + web app (Windows).
REM Double-click this file, or run it from the project folder.
REM Full output is also saved to run_log.txt.

cd /d "%~dp0"
set "LOG=%~dp0run_log.txt"
echo Run started %DATE% %TIME% > "%LOG%"

REM ---- Find Python: the py launcher first, then python on PATH ----
set PYEXE=
where py >nul 2>&1 && set PYEXE=py
if not defined PYEXE (
    where python >nul 2>&1 && set PYEXE=python
)
if not defined PYEXE (
    echo Python was not found. Install Python 3.10+ from python.org and tick "Add python.exe to PATH". >> "%LOG%"
    echo Python was not found. Install Python 3.10+ from python.org and tick "Add python.exe to PATH".
    goto :error
)
echo Using Python launcher: %PYEXE% >> "%LOG%"
%PYEXE% --version >> "%LOG%" 2>&1

if not exist .venv (
    echo [1/5] Creating virtual environment...
    %PYEXE% -m venv .venv >> "%LOG%" 2>&1 || goto :error
)
call .venv\Scripts\activate.bat || goto :error

echo [2/5] Installing requirements (first time takes a few minutes)...
python -m pip install --upgrade pip >> "%LOG%" 2>&1
pip install -r requirements.txt >> "%LOG%" 2>&1 || goto :error

echo [3/5] Running pipeline (about 4-8 minutes)...
python main.py >> "%LOG%" 2>&1 || goto :error

echo [4/5] Running tests...
python -m pytest -q >> "%LOG%" 2>&1 || goto :error
echo Tests passed. >> "%LOG%"

echo [5/5] Starting the web app at http://localhost:8000 ...
echo Web app starting >> "%LOG%"
echo Next time, use run_web.bat (web app) or run_streamlit.bat (Streamlit) to start without re-running the pipeline.
start "" /min cmd /c "timeout /t 20 /nobreak >nul & start http://localhost:8000"
python -m uvicorn api.main:app --port 8000
goto :eof

:error
echo.
echo FAILED - details are in run_log.txt in the project folder.
echo FAILED >> "%LOG%"
pause
exit /b 1
