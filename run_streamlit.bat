@echo off
cd /d "%~dp0"
REM Start the original Streamlit dashboard without re-running the pipeline.
if not exist .venv\Scripts\activate.bat (
    echo The Python environment is not set up yet. Run run_all.bat first.
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat
echo Checking Python packages...
pip install -q -r requirements.txt
if errorlevel 1 (
    echo Could not install the required packages. Check your internet connection.
    pause
    exit /b 1
)
if not exist models\motor_model.pkl (
    echo Models not found. Run run_all.bat first ^(it trains them^).
    pause
    exit /b 1
)
echo Starting the Streamlit dashboard at http://localhost:8501  (close this window to stop it)
streamlit run dashboard\app.py
pause
