# Dockerfile pour l'API Cuve
# Utilise une image Python slim pour minimiser la taille de l'image finale
# permet d'installer les dépendances et de lancer l'application avec Uvicorn

FROM python:3.12-slim

# Évite les fichiers .pyc + logs immédiats
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Mode de l'application (simulé pour le moment)
ENV CUVE_MODE=sim

WORKDIR /app

# Dépendances système minimales (si tu as des wheels natives, ajoute build-essential/python3-dev)
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# Installer les deps python d'abord (meilleur cache)
COPY src/cuve-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copier le code
COPY . /app

# Dossier de travail où se trouve app.main:app
WORKDIR /app/src/cuve-api

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
