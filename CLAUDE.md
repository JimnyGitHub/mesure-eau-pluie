# CLAUDE.md

Ce fichier fournit des instructions à Claude Code (claude.ai/code) pour travailler avec ce dépôt.

## Aperçu du projet

Système de surveillance de cuve d'eau de pluie avec deux composants :
- **Capteur ESP8266** (Arduino) : mesure le niveau d'eau via capteur ultrason, expose un endpoint JSON
- **Backend FastAPI** (`src/cuve-api/`) : collecte les mesures, stocke en SQLite, expose API REST et dashboard web

## Commandes

Toutes les commandes s'exécutent depuis `src/cuve-api/` :

```bash
# Installer les dépendances
pip install -r requirements.txt

# Lancer le serveur API (développement)
uvicorn app.main:app --reload

# Lancer en mode simulation (sans capteur réel)
CUVE_MODE=sim uvicorn app.main:app --reload

# Lancer les tests
pytest

# Lancer un test spécifique
pytest tests/test_volume.py::test_full_is_10000L

# Surveiller la connectivité du capteur (outil de diagnostic)
python monitor_cuve.py
```

## Architecture

### Abstraction capteur (`app/cuve.py`)
- Classe de base `CuveClient` avec `RealCuveClient` (HTTP vers ESP8266) et `SimCuveClient` (données aléatoires)
- Sélection via variable d'environnement `CUVE_MODE` (`real`/`sim`)

### Calcul de volume (`app/volume.py`)
- Convertit la distance ultrason en litres pour une cuve cylindrique horizontale
- Utilise la formule de segment circulaire : `A = r²·arccos((r-h)/r) - (r-h)·√(2rh-h²)`
- Ajuste le volume brut à la capacité nominale de la cuve

### Collecteur en arrière-plan (`app/main.py`)
- Tâche asyncio lancée au démarrage de FastAPI
- Interroge le capteur selon `CUVE_COLLECT_INTERVAL_SECONDS`, dédoublonne par timestamp capteur

### Base de données (`app/db.py`)
- SQLite avec table `readings` (distance_cm, sensor_timestamp, sensor_ip, fetched_at_epoch)
- Requêtes d'extrêmes par période (day/week/month/year/all)

## Configuration

Copier `.env.example` vers `.env`. Variables principales :
- `CUVE_MODE` : `real` ou `sim`
- `CUVE_SENSOR_URL` : endpoint ESP8266 (requis en mode `real`)
- `CUVE_TANK_*` : géométrie de la cuve pour le calcul de volume
- `CUVE_COLLECT_INTERVAL_SECONDS` : fréquence de collecte

## Endpoints API

- `GET /health` - statut et configuration
- `GET /api/last` - dernière mesure avec volume/pourcentage
- `GET /api/extremes?period=day&order=max&n=5` - mesures extrêmes
- `GET /api/dashboard` - tout-en-un pour l'interface web
- `GET /` - dashboard web (template Jinja2)

## Langue
Ce projet et toutes les interactions se font en français.
Veuillez toujours répondre en français.
