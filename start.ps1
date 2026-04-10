# Lance l'API cuve-eau-pluie avec Podman (Windows PowerShell)
# Usage : .\start.ps1  (depuis la racine du projet)
# La base SQLite est persistee dans le volume Podman nomme "cuve_data"

$IMAGE_NAME     = "cuve-api"
$CONTAINER_NAME = "cuve-api"
$ENV_FILE       = "src\cuve-api\.env"

# --- Proxy (optionnel) ---
# Le proxy tourne sur Windows a 127.0.0.1:PORT.
# Les dependances pip sont telechargees via WSL (qui accede au proxy Windows),
# puis installes en mode offline dans le conteneur (pas de proxy en build).
# Mettre $PROXY_PORT = "" pour desactiver (connexion PyPI directe dans le build).
$PROXY_PORT = "8888"

# --- Verification du .env ---
if (-not (Test-Path $ENV_FILE)) {
    Write-Host "ERREUR : $ENV_FILE introuvable."
    Write-Host "Copie src\cuve-api\.env.example en src\cuve-api\.env et configure-le."
    exit 1
}

Write-Host ""
Write-Host "=== Demarrage de la machine Podman ==="
podman machine start --log-level=error 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Podman machine demarree"
} else {
    Write-Host "Podman machine deja en cours (normal)"
}

# --- Telechargement des dependances pip via WSL (avec proxy) ---
if ($PROXY_PORT -ne "") {
    Write-Host ""
    Write-Host "=== Telechargement des dependances pip via WSL (proxy 127.0.0.1:$PROXY_PORT) ==="
    New-Item -ItemType Directory -Force -Path "src\cuve-api\wheels" | Out-Null

    # --python-version / --platform : force le telechargement des wheels
    # compatibles Python 3.12 / Linux x86_64 (= la cible du conteneur),
    # independamment de la version Python installee dans WSL.
    $PIP_CMD = "python3 -m pip " +
               "--proxy http://127.0.0.1:$PROXY_PORT " +
               "--trusted-host pypi.org " +
               "--trusted-host files.pythonhosted.org " +
               "--trusted-host pypi.python.org " +
               "download " +
               "--python-version 3.12 " +
               "--implementation cp " +
               "--abi cp312 " +
               "--platform manylinux_2_17_x86_64 " +
               "--only-binary=:all: " +
               "-r src/cuve-api/requirements.txt -d src/cuve-api/wheels/"

    wsl bash -c $PIP_CMD
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERREUR lors du telechargement des dependances."
        exit $LASTEXITCODE
    }
}

Write-Host ""
Write-Host "=== Build de l'image ==="
podman build -t $IMAGE_NAME src\cuve-api\
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERREUR lors du build."
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "=== Arret du conteneur existant (si present) ==="
podman stop $CONTAINER_NAME 2>$null
podman rm   $CONTAINER_NAME 2>$null

Write-Host ""
Write-Host "=== Lancement du conteneur ==="
podman run -d `
    --replace `
    --name $CONTAINER_NAME `
    -p 8000:8000 `
    -v cuve_data:/data `
    --env-file $ENV_FILE `
    -e CUVE_DB_PATH=/data/cuve.sqlite3 `
    $IMAGE_NAME

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERREUR lors du lancement du conteneur."
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Conteneur lance !"
Write-Host "Dashboard : http://localhost:8000"
Write-Host "Health    : http://localhost:8000/health"
