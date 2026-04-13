#!/bin/bash
# Lance l'API cuve-eau-pluie avec Docker (Linux / macOS / VM Proxmox)
# Usage : ./start.sh
# La base SQLite est persistée dans le volume Docker nommé "cuve_data"

set -e

IMAGE_NAME="cuve-api"
CONTAINER_NAME="cuve-api"
ENV_FILE="src/cuve-api/.env"

# --- Proxy (optionnel) ---
# Si vous avez un proxy local, les dépendances pip sont téléchargées sur l'hôte
# (où le proxy fonctionne) puis installées en mode offline dans le conteneur.
# Laisser vide si pas de proxy (ex: VM Proxmox avec accès internet direct).
#PROXY_PORT="8888"
# PROXY_PORT=""  # décommenter pour désactiver (install PyPI directe dans le build)

# --- Vérification du .env ---
if [ ! -f "$ENV_FILE" ]; then
    echo "ERREUR : $ENV_FILE introuvable."
    echo "Copie src/cuve-api/.env.example en src/cuve-api/.env et configure-le."
    exit 1
fi

# --- Téléchargement des dépendances pip sur l'hôte (avec proxy) ---
if [ -n "$PROXY_PORT" ]; then
    echo "=== Téléchargement des dépendances pip (proxy 127.0.0.1:${PROXY_PORT}) ==="
    mkdir -p src/cuve-api/wheels
    # --python-version / --platform : force le téléchargement des wheels
    # compatibles Python 3.12 / Linux x86_64 (= la cible du conteneur),
    # indépendamment de la version Python de l'hôte.
    python3 -m pip \
        --proxy "http://127.0.0.1:${PROXY_PORT}" \
        --trusted-host pypi.org \
        --trusted-host files.pythonhosted.org \
        --trusted-host pypi.python.org \
        download \
        --python-version 3.12 \
        --implementation cp \
        --abi cp312 \
        --platform manylinux_2_17_x86_64 \
        --only-binary=:all: \
        -r src/cuve-api/requirements.txt \
        -d src/cuve-api/wheels/
fi

echo ""
echo "=== Build de l'image Docker ==="
docker build -t "$IMAGE_NAME" src/cuve-api/

echo ""
echo "=== Arrêt du conteneur existant (si présent) ==="
docker stop "$CONTAINER_NAME" 2>/dev/null || true
docker rm   "$CONTAINER_NAME" 2>/dev/null || true

echo ""
echo "=== Lancement du conteneur ==="
docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    -p 8000:8000 \
    -v cuve_data:/data \
    --env-file "$ENV_FILE" \
    -e CUVE_DB_PATH=/data/cuve.sqlite3 \
    "$IMAGE_NAME"

echo ""
echo "Conteneur lancé !"
echo "Dashboard : http://localhost:8000"
echo "Health    : http://localhost:8000/health"
