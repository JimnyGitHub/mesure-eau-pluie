FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
COPY wheels/ /tmp/wheels/

# Si des wheels locaux sont présents (build derrière proxy) : installation offline.
# Sinon : installation depuis PyPI (VM Proxmox sans proxy, CI, etc.)
RUN if ls /tmp/wheels/*.whl 1>/dev/null 2>&1; then \
        echo "--- Installation depuis wheels locaux (mode offline) ---" && \
        pip install --no-cache-dir --no-index --find-links=/tmp/wheels -r requirements.txt; \
    else \
        echo "--- Installation depuis PyPI (mode online) ---" && \
        pip install --no-cache-dir \
            --trusted-host pypi.org \
            --trusted-host files.pythonhosted.org \
            --trusted-host pypi.python.org \
            -r requirements.txt; \
    fi && rm -rf /tmp/wheels

COPY app/ app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
