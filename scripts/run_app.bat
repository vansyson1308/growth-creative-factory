@echo off
echo ============================================
echo   Growth Creative Factory - Streamlit App
echo ============================================
echo.

:: Check if venv exists
if not exist ".venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo Installing dependencies...
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

echo Starting Streamlit app...
streamlit run app.py --server.port 8501
pause
