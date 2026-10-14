#!/usr/bin/env bash
# Actualiza el proyecto y deja los contenedores al día:
#   - git pull (salvo SKIP_PULL=1, p. ej. desde el hook post-merge)
#   - reconstruye solo las imágenes cuyo código ha cambiado (backend, frontend,
#     camera); con la caché de Docker un cambio de código tarda segundos
#   - recrea los contenedores afectados y aplica migraciones
#
# Uso:  scripts/deploy.sh            (o `make deploy`)
#       SKIP_PULL=1 scripts/deploy.sh <commit-anterior>   (lo usa .githooks/post-merge)
#       FORCE=1 scripts/deploy.sh    (reconstruye todo aunque no haya cambios)
set -euo pipefail
cd "$(dirname "$0")/.."

BEFORE="$(git rev-parse "${1:-HEAD}")"
if [ "${SKIP_PULL:-0}" != "1" ]; then
  git pull --ff-only
fi
AFTER="$(git rev-parse HEAD)"

if [ "$BEFORE" = "$AFTER" ] && [ "${FORCE:-0}" != "1" ]; then
  echo "✔ Sin cambios nuevos (usa FORCE=1 para forzar)."
  exit 0
fi

CHANGED="$(git diff --name-only "$BEFORE" "$AFTER" || true)"
changed() { [ "${FORCE:-0}" = "1" ] || printf '%s\n' "$CHANGED" | grep -qE "$1"; }
# La cámara solo existe donde COMPOSE_PROFILES=camera (la Raspberry Pi).
has_service() { docker compose config --services | grep -qx "$1"; }

if changed '^backend/'; then
  echo "→ Cambios en backend: reconstruyendo imagen (backend + worker)…"
  docker compose build backend
fi

if changed '^frontend/'; then
  echo "→ Cambios en frontend: reconstruyendo imagen…"
  docker compose build frontend
fi

if has_service camera && changed '^camera/'; then
  echo "→ Cambios en camera: reconstruyendo imagen…"
  docker compose build camera
fi

echo "→ Levantando servicios (recrea los que tienen imagen nueva)…"
docker compose up -d --remove-orphans

echo "→ Aplicando migraciones…"
docker compose exec -T backend python manage.py migrate --noinput

echo "→ Limpiando imágenes antiguas…"
docker image prune -f >/dev/null

echo "✔ Actualizado a $(git log -1 --format='%h %s')"
