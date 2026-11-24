@echo off
setlocal
cd /d "%~dp0"
echo ROMERAL - Instalacion Windows (Python 3.11 o 3.12 recomendado)
where py >nul 2>&1
if errorlevel 1 (
  echo ERROR: Instala Python para Windows desde python.org y activa el launcher py.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 (echo No se pudo crear entorno virtual.& pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (echo Error al actualizar pip.& pause & exit /b 1)
".venv\Scripts\python.exe" -m pip install -r requirements_windows.txt
if errorlevel 1 (echo Error al instalar dependencias.& pause & exit /b 1)
".venv\Scripts\python.exe" -c "import tkinter,fitz,numpy,PIL,requests,zeep,keyring; print('Dependencias verificadas')"
if errorlevel 1 (echo Faltan dependencias.& pause & exit /b 1)
echo.
echo Instalacion de dependencias finalizada.
echo Instala el controlador POS-80 y SumatraPDF para impresion automatica.
echo Ejecuta CONFIGURAR_IMPRESORA_WINDOWS.bat antes de imprimir.
pause
