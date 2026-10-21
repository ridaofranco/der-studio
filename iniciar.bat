@echo off
chcp 65001 >nul
title DER Studio
cd /d "%~dp0"

REM ---- 1. Buscar Python (lo instala si no esta) -------------------------
set "PY="
set "PYARGS="
py -3 --version >nul 2>nul && set "PY=py" && set "PYARGS=-3"
if defined PY goto :tengo_python
python --version >nul 2>nul && set "PY=python"
if defined PY goto :tengo_python
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if defined PY goto :tengo_python

echo.
echo  No encontre Python. Lo instalo ahora (solo esta vez, tarda un par de minutos)...
echo.
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%PY%" goto :tengo_python
echo.
echo  No pude instalar Python automaticamente.
echo  Descargalo de https://www.python.org/downloads/ (marca "Add python.exe to PATH")
echo  y despues volve a abrir iniciar.bat
start "" https://www.python.org/downloads/
pause
exit /b 1

:tengo_python
REM ---- 2. Primera vez: preparar el entorno -----------------------------
if exist ".venv\instalado.txt" goto :arrancar
echo.
echo  Preparando DER Studio (solo la primera vez)...
if not exist ".venv\Scripts\python.exe" "%PY%" %PYARGS% -m venv .venv
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
  echo.
  echo  Fallo la instalacion. Revisa tu conexion a internet y volve a abrir iniciar.bat
  pause
  exit /b 1
)
echo ok> ".venv\instalado.txt"

REM Acceso directo en el escritorio
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut(\"$d\DER Studio.lnk\"); $s.TargetPath='%~dp0iniciar.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%SystemRoot%\System32\imageres.dll,108'; $s.Save()" >nul 2>nul
echo  Listo. Te deje un acceso directo "DER Studio" en el escritorio.

:arrancar
REM ---- 3. Abrir la app ---------------------------------------------------
echo.
echo  Abriendo DER Studio... (no cierres esta ventana)
".venv\Scripts\python.exe" lanzador.py
if errorlevel 1 pause
