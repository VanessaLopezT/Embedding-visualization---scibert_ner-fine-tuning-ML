#!/bin/sh
set -eu

APP_PORT="${APP_PORT:-9000}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-1}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-600}"

cd /app

# Comprobar checkpoints montados (no copiados en la imagen)
check_model_path() {
  label="$1"
  rel="$2"
  if [ -z "$rel" ]; then
    echo "[entrypoint] AVISO: $label sin ruta configurada." >&2
    return
  fi
  if [ ! -d "/app/$rel" ] && [ ! -f "/app/$rel" ]; then
    echo "[entrypoint] AVISO: $label no encontrado en /app/$rel (monte el volumen del checkpoint)." >&2
  fi
}

check_model_path "MODEL_TECH_CHECKPOINT" "${MODEL_TECH_CHECKPOINT:-TechBERT/best_model}"
check_model_path "MODEL_CMT_CHECKPOINT" "${MODEL_CMT_CHECKPOINT:-PatVetBERT/best_model}"

mkdir -p "${DATA_DIR:-/app/data}/articles" "${DATA_DIR:-/app/data}/example" "${DATA_DIR:-/app/data}/workspaces"

python manage.py migrate --noinput

exec gunicorn server.wsgi:application \
  --bind "0.0.0.0:${APP_PORT}" \
  --workers "${GUNICORN_WORKERS}" \
  --timeout "${GUNICORN_TIMEOUT}" \
  --access-logfile - \
  --error-logfile -
