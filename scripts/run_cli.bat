@echo off
echo ============================================
echo   Growth Creative Factory - CLI (Dry Run)
echo ============================================
echo.

if not exist ".venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

echo Running pipeline in dry-run mode...
python -m gcf run --input examples/ads_sample.csv --out output --mode dry --config config.yaml
echo.
echo Done! Check the output/ folder.
pause
