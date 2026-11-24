@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo ROMERAL no esta instalado. Ejecuta INSTALAR_WINDOWS.bat primero.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" romeral.py
if errorlevel 1 (echo ROMERAL finalizo con error.& pause)
