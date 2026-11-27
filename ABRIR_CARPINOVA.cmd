@echo off
setlocal DisableDelayedExpansion
set "CARPN_ROOT=%~dp0"
pushd "%CARPN_ROOT%" >nul
if errorlevel 1 (
  echo No se pudo abrir la carpeta local de CarpiNova.
  pause
  exit /b 1
)

if exist "%CARPN_ROOT%.venv\Scripts\python.exe" (
  set "CARPN_PYTHON=%CARPN_ROOT%.venv\Scripts\python.exe"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo No se encontro Python. Instale CarpiNova desde el procedimiento autorizado y vuelva a intentar.
    popd
    pause
    exit /b 1
  )
  set "CARPN_PYTHON=python"
)

if not "%~2"=="" (
  echo Use doble clic para elegir un archivo o arrastre un solo ZIP/JSON.
  popd
  pause
  exit /b 2
)
if "%~1"=="" (
  "%CARPN_PYTHON%" -m carpinova_agent.editor_launcher
) else (
  "%CARPN_PYTHON%" -m carpinova_agent.editor_launcher --input "%~1"
)
set "CARPN_EXIT=%ERRORLEVEL%"
popd
exit /b %CARPN_EXIT%
