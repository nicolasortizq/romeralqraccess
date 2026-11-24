@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" FLUJO_VENTAS_PLANO_v2_10.py
) else (
  py -3 FLUJO_VENTAS_PLANO_v2_10.py
)
if errorlevel 1 pause
