# Production: Django + Gunicorn + WhiteNoise + NER (CPU), port 9000
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    DJANGO_SETTINGS_MODULE=server.settings.production

WORKDIR /app

# Runtime libs for numpy/scipy/torch wheels (OpenMP); no CUDA.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-prod.txt ./

# PyTorch CPU + app deps. Avoid `pip install -U pip` (breaks pinned packaging).
RUN pip install --no-cache-dir -r requirements-prod.txt \
    && python -c "import torch; assert not torch.cuda.is_available(); print('torch', torch.__version__, 'CPU OK')" \
    && (pip list 2>/dev/null | grep -qi nvidia && exit 1 || true)

COPY . .

# Entrypoint explícito + LF (CRLF de Windows rompe #!/bin/sh en Linux).
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
RUN sed -i 's/\r$//' /app/docker/entrypoint.sh \
    && chmod +x /app/docker/entrypoint.sh

RUN DJANGO_SECRET_KEY=docker-build-collectstatic-secret \
    DJANGO_ALLOWED_HOSTS=localhost \
    DJANGO_SKIP_MODEL_PRELOAD=1 \
    python manage.py collectstatic --noinput

EXPOSE 9000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
