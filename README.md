# Mesure Eau de Pluie

Système de surveillance du niveau d'eau dans une cuve de récupération d'eau de pluie.

## Composants

### Capteur ESP8266
Microcontrôleur avec capteur ultrasonique qui mesure la distance jusqu'à la surface de l'eau. Expose un endpoint JSON avec la mesure en temps réel.

### API FastAPI
Backend Python qui :
- Collecte les mesures du capteur à intervalle régulier
- Stocke l'historique dans une base SQLite
- Calcule le volume d'eau en litres et le pourcentage de remplissage
- Expose une API REST et un dashboard web

## Installation

```bash
cd src/cuve-api

# Créer un environnement virtuel (recommandé)
python -m venv .venv
source .venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Configurer l'environnement
cp .env.example .env
# Éditer .env avec vos paramètres
```

## Configuration

Éditer le fichier `.env` :

| Variable | Description | Défaut |
|----------|-------------|--------|
| `CUVE_MODE` | `real` (capteur réel) ou `sim` (simulation) | `real` |
| `CUVE_SENSOR_URL` | URL du capteur ESP8266 | - |
| `CUVE_DB_PATH` | Chemin de la base SQLite | `cuve.sqlite3` |
| `CUVE_COLLECT_INTERVAL_SECONDS` | Intervalle de collecte | `60` |
| `CUVE_TANK_TOTAL_LITERS` | Capacité nominale de la cuve | `10000` |
| `CUVE_TANK_DIAMETER_CM` | Diamètre de la cuve (cm) | `184.5` |
| `CUVE_TANK_LENGTH_CM` | Longueur de la cuve (cm) | `436.4` |
| `CUVE_TANK_FULL_AIR_GAP_CM` | Distance capteur-eau quand plein (cm) | `20` |

## Utilisation

### Lancer le serveur

```bash
cd src/cuve-api

# Mode réel (avec capteur)
uvicorn app.main:app --reload

# Mode simulation (sans capteur)
CUVE_MODE=sim uvicorn app.main:app --reload
```

Le dashboard web est accessible sur http://localhost:8000

### API REST

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Statut du service |
| `GET /api/last` | Dernière mesure |
| `GET /api/extremes` | Mesures extrêmes par période |
| `GET /api/dashboard` | Données complètes pour le dashboard |

### Outil de diagnostic

Pour vérifier la connectivité avec le capteur :

```bash
python monitor_cuve.py
```

## Tests

```bash
cd src/cuve-api
pytest
```

## Architecture technique

```
src/cuve-api/
├── app/
│   ├── main.py      # Application FastAPI, endpoints, collecteur
│   ├── cuve.py      # Clients capteur (réel/simulé)
│   ├── db.py        # Couche base de données SQLite
│   ├── volume.py    # Calcul volume cylindre horizontal
│   ├── config.py    # Configuration via variables d'env
│   └── templates/   # Template Jinja2 du dashboard
├── tests/           # Tests unitaires
└── requirements.txt
```

### Calcul du volume

La cuve est un cylindre horizontal. Le volume d'eau est calculé à partir de la hauteur d'eau mesurée en utilisant la formule du segment circulaire :

```
A = r²·arccos((r-h)/r) - (r-h)·√(2rh-h²)
Volume = A × Longueur
```

Le volume est ensuite ajusté proportionnellement à la capacité nominale de la cuve.
