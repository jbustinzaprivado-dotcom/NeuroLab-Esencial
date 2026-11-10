@echo off
REM NeuroLab Esencial en esta PC: doble clic. La primera vez instala todo (tarda unos minutos).
REM Requisitos: Python 3.12 o superior y Node.js 20 o superior.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Creando entorno de Python...
    python -m venv .venv || goto error
    .venv\Scripts\python.exe -m pip install --upgrade pip >nul
    .venv\Scripts\python.exe -m pip install -r requirements.txt || goto error
)
if not exist web\dist\index.html (
    echo Compilando la web...
    pushd web
    call npm install --no-audit --no-fund || goto error
    call npm run build || goto error
    popd
)
echo.
echo Abre http://localhost:8000  (usuario ana.quispe, contrasena neurolab2026)
echo Para detener: Ctrl+C en esta ventana.
echo.
.venv\Scripts\python.exe run.py
goto :eof
:error
echo.
echo [ERROR] No se pudo preparar NeuroLab Esencial. Revisa el mensaje anterior.
pause
