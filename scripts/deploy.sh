#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# deploy.sh - Déploiement "1 commande" pour Cuve API (FastAPI/Uvicorn)
#
# Fonctionnalités :
# - Installation automatique des dépendances système via apt si manquantes
# - Mode --first-install :
#     * crée user système
#     * crée /opt/cuve-api /etc/cuve-api /var/lib/cuve-api
#     * génère le service systemd /etc/systemd/system/cuve-api.service
#     * enable + start
# - Déploiement standard :
#     * git pull
#     * venv
#     * pip install -r requirements.txt
#     * restart systemd
#
# Exemples :
#   sudo /opt/cuve-api/deploy.sh --first-install --git-url git@github.com:toi/tonrepo.git
#   sudo /opt/cuve-api/deploy.sh
#   sudo /opt/cuve-api/deploy.sh --dry-run
#
# Notes :
# - Ce script suppose que l'app se lance depuis /opt/cuve-api/src/cuve-api
#   et que l'ASGI app est "app.main:app"
# =============================================================================

APP_USER="cuve-api"
APP_GROUP="cuve-api"
APP_DIR="/opt/cuve-api"
APP_WORKDIR="/opt/cuve-api/src/cuve-api"
VENV_DIR="/opt/cuve-api/.venv"

ENV_DIR="/etc/cuve-api"
ENV_FILE="/etc/cuve-api/.env"

DATA_DIR="/var/lib/cuve-api"
DEFAULT_DB_PATH="/var/lib/cuve-api/cuve.sqlite3"

SERVICE_NAME="cuve-api.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"

REQUIREMENTS_FILE="/opt/cuve-api/src/cuve-api/requirements.txt"
UVICORN_APP="app.main:app"
BIND_HOST="0.0.0.0"
BIND_PORT="8000"

# --- Options CLI ---
FIRST_INSTALL=false
DRY_RUN=false
GIT_URL=""
FORCE_GIT_RESET=false

# -----------------------------
# Fonctions utilitaires
# -----------------------------
log() { echo "[deploy] $*"; }
warn() { echo "[deploy][WARN] $*" >&2; }
die() { echo "[deploy][ERREUR] $*" >&2; exit 1; }

run() {
  # Exécute une commande en respectant --dry-run
  if $DRY_RUN; then
    echo "[dry-run] $*"
  else
    eval "$@"
  fi
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    die "Ce script doit être lancé en root (utilise sudo)."
  fi
}

usage() {
  cat <<EOF
Usage: sudo $0 [options]

Options:
  --first-install            Initialise la machine (user, dossiers, systemd)
  --git-url <url>            URL SSH/HTTPS du repo à cloner si absent
  --force-git-reset          En cas de modifications locales, reset hard avant pull
  --dry-run                  N'applique rien, affiche seulement les actions
  --help                     Affiche l'aide

Exemples:
  sudo $0 --first-install --git-url git@github.com:toi/tonrepo.git
  sudo $0
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --first-install) FIRST_INSTALL=true; shift ;;
      --git-url) GIT_URL="${2:-}"; shift 2 ;;
      --force-git-reset) FORCE_GIT_RESET=true; shift ;;
      --dry-run) DRY_RUN=true; shift ;;
      --help) usage; exit 0 ;;
      *) die "Option inconnue: $1 (utilise --help)";;
    esac
  done
}

# -----------------------------
# Installation automatique apt
# -----------------------------
command_exists() { command -v "$1" >/dev/null 2>&1; }

apt_install_if_missing() {
  # Vérifie et installe des paquets apt
  # Usage: apt_install_if_missing "git" "python3-venv" ...
  local pkgs=("$@")
  local missing=()

  # On détecte les paquets manquants via dpkg -s
  for p in "${pkgs[@]}"; do
    if ! dpkg -s "$p" >/dev/null 2>&1; then
      missing+=("$p")
    fi
  done

  if [[ ${#missing[@]} -eq 0 ]]; then
    log "Dépendances apt déjà présentes: ${pkgs[*]}"
    return
  fi

  log "Paquets apt manquants détectés: ${missing[*]}"
  run "apt-get update -y"
  run "DEBIAN_FRONTEND=noninteractive apt-get install -y ${missing[*]}"
}

ensure_system_deps() {
  # Dépendances minimales nécessaires au script et au venv
  apt_install_if_missing git python3 python3-venv python3-pip ca-certificates

  # Optionnel mais souvent utile (compilation de wheels)
  # Ajoute ici si ton requirements a du build natif:
  # apt_install_if_missing build-essential python3-dev
}

# -----------------------------
# Préparation système (user/dirs)
# -----------------------------
ensure_user_and_dirs() {
  if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    log "Création de l'utilisateur système ${APP_USER}"
    run "useradd --system --home '${APP_DIR}' --shell /usr/sbin/nologin '${APP_USER}'"
  else
    log "Utilisateur ${APP_USER} déjà présent"
  fi

  run "mkdir -p '${APP_DIR}' '${ENV_DIR}' '${DATA_DIR}'"
  run "chown -R '${APP_USER}:${APP_GROUP}' '${APP_DIR}' '${DATA_DIR}'"
  run "chmod 750 '${DATA_DIR}'"
  run "chmod 750 '${ENV_DIR}'"
}

# -----------------------------
# Repo git
# -----------------------------
ensure_repo_present() {
  if [[ -d "${APP_DIR}/.git" ]]; then
    log "Repo git déjà présent dans ${APP_DIR}"
    return
  fi

  if [[ -z "${GIT_URL}" ]]; then
    die "Repo absent dans ${APP_DIR} et --git-url non fourni. Clone manuellement ou passe --git-url."
  fi

  log "Clonage du repo: ${GIT_URL}"
  run "rm -rf '${APP_DIR:?}/'*"
  run "sudo -u '${APP_USER}' git clone '${GIT_URL}' '${APP_DIR}'"
}

git_update() {
  log "Mise à jour du code (git fetch/pull)"
  if $FORCE_GIT_RESET; then
    warn "--force-git-reset activé: reset hard avant pull"
    run "sudo -u '${APP_USER}' bash -lc \"cd '${APP_DIR}' && git fetch --all --prune && git reset --hard HEAD && git pull --ff-only\""
  else
    run "sudo -u '${APP_USER}' bash -lc \"cd '${APP_DIR}' && git fetch --all --prune && git pull --ff-only\""
  fi
}

# -----------------------------
# Vérifications .env et chemins
# -----------------------------
ensure_env_file_exists_or_create_hint() {
  if [[ -f "${ENV_FILE}" ]]; then
    log ".env OK: ${ENV_FILE}"
    return
  fi

  if $FIRST_INSTALL; then
    warn "Fichier .env absent: ${ENV_FILE}"
    warn "Je vais créer un squelette. Pense à le compléter (capteur, mode, etc.)."

    if $DRY_RUN; then
      echo "[dry-run] création squelette ${ENV_FILE}"
      return
    fi

    cat > "${ENV_FILE}" <<EOF
# -------------------------------
# Configuration Cuve API
# -------------------------------
# Mode: real (capteur) ou sim (simulation)
CUVE_MODE=real

# URL du capteur (à adapter)
CUVE_SENSOR_URL=http://192.168.X.Y/measure

# Chemin base SQLite (recommandé hors repo)
CUVE_DB_PATH=${DEFAULT_DB_PATH}

# Collecte
CUVE_COLLECT_INTERVAL_SECONDS=60

# Paramètres cuve (à adapter)
CUVE_TANK_TOTAL_LITERS=10000
CUVE_TANK_DIAMETER_CM=184.5
CUVE_TANK_LENGTH_CM=436.4
CUVE_TANK_FULL_AIR_GAP_CM=20
EOF

    chown root:"${APP_GROUP}" "${ENV_FILE}"
    chmod 640 "${ENV_FILE}"
    log "Squelette .env créé: ${ENV_FILE}"
    return
  fi

  die "Fichier .env manquant: ${ENV_FILE}. Crée-le (ou relance avec --first-install)."
}

ensure_paths() {
  if [[ ! -d "${APP_WORKDIR}" ]]; then
    die "WorkingDirectory introuvable: ${APP_WORKDIR}. Vérifie l'arborescence du repo."
  fi
  if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
    die "requirements.txt introuvable: ${REQUIREMENTS_FILE}"
  fi
}

# -----------------------------
# Venv + dépendances Python
# -----------------------------
ensure_venv_and_install() {
  if [[ ! -d "${VENV_DIR}" ]]; then
    log "Création du venv: ${VENV_DIR}"
    run "sudo -u '${APP_USER}' python3 -m venv '${VENV_DIR}'"
  else
    log "Venv déjà présent: ${VENV_DIR}"
  fi

  log "Upgrade pip/setuptools/wheel"
  run "sudo -u '${APP_USER}' '${VENV_DIR}/bin/python' -m pip install --upgrade pip setuptools wheel"

  log "Installation/MAJ des dépendances Python via requirements.txt"
  run "sudo -u '${APP_USER}' '${VENV_DIR}/bin/pip' install -r '${REQUIREMENTS_FILE}'"
}

# -----------------------------
# Génération du service systemd
# -----------------------------
write_systemd_service() {
  log "Génération du service systemd: ${SERVICE_PATH}"

  if $DRY_RUN; then
    echo "[dry-run] écriture ${SERVICE_PATH} (contenu ci-dessous)"
    cat <<EOF
[Unit]
Description=Cuve API (Mesure Eau de Pluie) - FastAPI/Uvicorn
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_GROUP}
EnvironmentFile=${ENV_FILE}
WorkingDirectory=${APP_WORKDIR}
ExecStart=${VENV_DIR}/bin/uvicorn ${UVICORN_APP} --host ${BIND_HOST} --port ${BIND_PORT}
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=${DATA_DIR}
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    return
  fi

  cat > "${SERVICE_PATH}" <<EOF
[Unit]
Description=Cuve API (Mesure Eau de Pluie) - FastAPI/Uvicorn
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_GROUP}
EnvironmentFile=${ENV_FILE}
WorkingDirectory=${APP_WORKDIR}
ExecStart=${VENV_DIR}/bin/uvicorn ${UVICORN_APP} --host ${BIND_HOST} --port ${BIND_PORT}
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=${DATA_DIR}
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

  chmod 644 "${SERVICE_PATH}"
}

systemd_reload_enable_start() {
  log "systemd daemon-reload"
  run "systemctl daemon-reload"

  log "Activation au boot: ${SERVICE_NAME}"
  run "systemctl enable '${SERVICE_NAME}' >/dev/null"

  log "Démarrage/restart service: ${SERVICE_NAME}"
  run "systemctl restart '${SERVICE_NAME}'"

  log "Status (court)"
  if $DRY_RUN; then
    echo "[dry-run] systemctl --no-pager --full status ${SERVICE_NAME}"
  else
    systemctl --no-pager --full status "${SERVICE_NAME}" | sed -n '1,14p' || true
  fi
}

# -----------------------------
# Main
# -----------------------------
main() {
  parse_args "$@"
  require_root

  ensure_system_deps

  if $FIRST_INSTALL; then
    log "=== MODE FIRST INSTALL ==="
    ensure_user_and_dirs
    ensure_repo_present
    ensure_env_file_exists_or_create_hint
    ensure_paths
    ensure_venv_and_install
    write_systemd_service
    systemd_reload_enable_start
    log "First install terminé."
    return
  fi

  log "=== MODE DEPLOIEMENT STANDARD ==="
  # En standard, on suppose que la machine est déjà initialisée,
  # mais on reste tolérant.
  ensure_user_and_dirs
  ensure_repo_present
  ensure_env_file_exists_or_create_hint
  ensure_paths

  git_update
  ensure_venv_and_install
  systemd_reload_enable_start
  log "Déploiement terminé."
}

main "$@"
