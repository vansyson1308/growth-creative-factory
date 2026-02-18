@echo off
setlocal

black .
if errorlevel 1 exit /b %errorlevel%

ruff check . --fix
if errorlevel 1 exit /b %errorlevel%

pytest -q
if errorlevel 1 exit /b %errorlevel%

endlocal
