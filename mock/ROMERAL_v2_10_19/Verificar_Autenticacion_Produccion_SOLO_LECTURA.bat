@echo off
cd /d "%~dp0"
python VERIFICAR_AUTENTICACION_PRODUCCION.py
if errorlevel 9009 py -3 VERIFICAR_AUTENTICACION_PRODUCCION.py
 echo.
 echo Copie solamente la linea RESULTADO. No comparta contrasenas.
pause
