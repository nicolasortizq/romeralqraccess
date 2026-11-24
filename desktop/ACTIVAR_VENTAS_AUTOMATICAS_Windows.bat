@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Primero ejecuta INSTALAR_WINDOWS.bat.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" ACTIVAR_VENTAS_AUTOMATICAS.py
if errorlevel 1 pause
