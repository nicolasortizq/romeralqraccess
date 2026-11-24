@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Ejecuta INSTALAR_WINDOWS.bat primero.& pause & exit /b 1)
".venv\Scripts\python.exe" Configurar_Impresora_Windows.py
pause
