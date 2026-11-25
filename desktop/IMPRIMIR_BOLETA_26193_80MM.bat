@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Primero ejecuta INSTALAR_WINDOWS.bat para preparar dependencias.& pause & exit /b 1)
".venv\Scripts\python.exe" IMPRIMIR_FOLIO_26193.py
if errorlevel 1 pause
