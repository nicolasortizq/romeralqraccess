@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" PRUEBA_IMPRESION_PLANO_80MM.py
) else (
  echo Ejecuta INSTALAR_WINDOWS.bat primero.
  pause
  exit /b 1
)
if errorlevel 1 pause
