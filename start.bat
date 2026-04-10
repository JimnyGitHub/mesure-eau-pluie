@echo off
REM Lance l'API cuve-eau-pluie avec Podman (Windows CMD)
REM Usage : double-clic ou "start.bat" depuis la racine du projet
REM La base SQLite est persistee dans le volume Podman nomme "cuve_data"

set IMAGE_NAME=cuve-api
set CONTAINER_NAME=cuve-api
set ENV_FILE=src\cuve-api\.env

REM --- Proxy (optionnel) ---
REM Le proxy tourne sur Windows a 127.0.0.1:PORT.
REM Les dependances pip sont telechargees via WSL (qui accede au proxy Windows),
REM puis installes en mode offline dans le conteneur (pas de proxy en build).
REM Mettre PROXY_PORT= (vide) pour desactiver.
set PROXY_PORT=8888

REM --- Verification du .env ---
if not exist "%ENV_FILE%" (
    echo ERREUR : %ENV_FILE% introuvable.
    echo Copie src\cuve-api\.env.example en src\cuve-api\.env et configure-le.
    pause
    exit /b 1
)

echo.
echo === Demarrage de la machine Podman ===
podman machine start --log-level=error 2>nul
IF %ERRORLEVEL% EQU 0 (
    echo Podman machine demarree
) ELSE (
    echo Podman machine deja en cours ^(normal^)
)

REM --- Telechargement des dependances pip via WSL (avec proxy) ---
if not "%PROXY_PORT%"=="" (
    echo.
    echo === Telechargement des dependances pip via WSL ^(proxy 127.0.0.1:%PROXY_PORT%^) ===
    if not exist "src\cuve-api\wheels" mkdir "src\cuve-api\wheels"
    REM --python-version / --platform : force le telechargement des wheels
    REM compatibles Python 3.12 / Linux x86_64 (= la cible du conteneur),
    REM independamment de la version Python installee dans WSL.
    wsl python3 -m pip --proxy http://127.0.0.1:%PROXY_PORT% --trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host pypi.python.org download --python-version 3.12 --implementation cp --abi cp312 --platform manylinux_2_17_x86_64 --only-binary=:all: -r src/cuve-api/requirements.txt -d src/cuve-api/wheels/
    IF %ERRORLEVEL% NEQ 0 (
        echo ERREUR lors du telechargement des dependances.
        pause
        exit /b %ERRORLEVEL%
    )
)

echo.
echo === Build de l'image ===
podman build -t %IMAGE_NAME% src\cuve-api\
IF %ERRORLEVEL% NEQ 0 (
    echo ERREUR lors du build.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo === Arret du conteneur existant ^(si present^) ===
podman stop %CONTAINER_NAME% 2>nul
podman rm   %CONTAINER_NAME% 2>nul

echo.
echo === Lancement du conteneur ===
podman run -d ^
    --replace ^
    --name %CONTAINER_NAME% ^
    -p 8000:8000 ^
    -v cuve_data:/data ^
    --env-file %ENV_FILE% ^
    -e CUVE_DB_PATH=/data/cuve.sqlite3 ^
    %IMAGE_NAME%
IF %ERRORLEVEL% NEQ 0 (
    echo ERREUR lors du lancement du conteneur.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Conteneur lance !
echo Dashboard : http://localhost:8000
echo Health    : http://localhost:8000/health
pause
