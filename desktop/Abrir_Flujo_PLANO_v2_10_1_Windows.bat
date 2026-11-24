@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" FLUJO_VENTAS_PLANO_v2_10_1.py
) else (
  echo Ejecuta INSTALAR_WINDOWS.bat primero.
  pause
  exit /b 1
)
if errorlevel 1 pause
